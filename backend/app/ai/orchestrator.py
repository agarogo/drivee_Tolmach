from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.answer import compose_answer, explain_interpretation
from app.ai.autofix import try_fix_sql
from app.ai.confidence import score_confidence
from app.ai.gateway.service import (
    build_answer_summary_with_ai,
    intent_result_to_interpretation,
    render_answer_summary,
    sql_plan_draft_to_interpretation,
)
from app.ai.interpreter import DANGEROUS_RE
from app.ai.llm_interpreter import clarification_stage, extract_intent_stage, sql_plan_draft_stage
from app.ai.retrieval import retrieve_context
from app.ai.semantic_catalog import load_semantic_catalog
from app.ai.semantic_compiler import SemanticCompilationError, compile_sql_query_bundle
from app.ai.types import Interpretation
from app.models import Query, QueryClarification, QueryEvent, SqlGuardrailLog, User
from app.semantic.errors import build_block_reason
from app.services.charts import recommend_chart
from app.services.guardrails import validate_sql
from app.services.observability import trace_span
from app.services.query_runner import execute_validated_query


PIPELINE_STEPS = [
    "Semantic layer",
    "AI intent extraction",
    "AI clarification planning",
    "Confidence scoring",
    "AI SQL plan draft",
    "Semantic SQL compilation",
    "Guardrails",
    "SQL execution",
    "Chart selection",
    "AI answer summary",
]


@asynccontextmanager
async def trace_step(db: AsyncSession, query: Query, step_name: str) -> AsyncIterator[QueryEvent]:
    started = time.perf_counter()
    event = QueryEvent(query_id=query.id, step_name=step_name, status="running", payload_json={})
    db.add(event)
    await db.flush()
    with trace_span("tolmach.query_step", {"query_id": query.id, "step_name": step_name}):
        try:
            yield event
            event.status = "ok" if event.status == "running" else event.status
        except Exception as exc:
            event.status = "error"
            event.payload_json = {**event.payload_json, "error": str(exc)}
            raise
        finally:
            event.finished_at = datetime.utcnow()
            event.duration_ms = int((time.perf_counter() - started) * 1000)
            await db.flush()


async def _persist_guardrail_logs(db: AsyncSession, query: Query, logs: list[dict]) -> None:
    for log in logs:
        message = log.get("message", "")
        if not isinstance(message, str):
            message = json.dumps(message, ensure_ascii=False, default=str)
        details = log.get("details", {})
        if not isinstance(details, dict):
            details = {"value": details}
        code = str(log.get("code", "")).strip()
        if code:
            details = {**details, "code": code}
        db.add(
            SqlGuardrailLog(
                query_id=query.id,
                check_name=str(log.get("check_name", "unknown")),
                status=str(log.get("status", "unknown")),
                severity=str(log.get("severity", "info")),
                message=message,
                details_json=details,
            )
        )
    await db.flush()


def _clarification_options(ambiguities: list[str]) -> list[dict]:
    return [
        {
            "label": "Revenue by city",
            "value": "revenue_by_city",
            "description": "Aggregate revenue by city.",
        },
        {
            "label": "Completed trips by day",
            "value": "completed_trips_by_day",
            "description": "Show completed trips grouped by day.",
        },
        {
            "label": "Last 30 days",
            "value": "last_30_days",
            "description": "Use a rolling 30 day window.",
        },
        {
            "label": "Orders KPI by day",
            "value": "orders_kpi_by_day",
            "description": "Switch to a daily KPI time series.",
        },
    ][: max(2, min(4, len(ambiguities) + 1))]


def _dangerous_interpretation(question: str, matched_text: str) -> Interpretation:
    return Interpretation(
        intent="dangerous_operation",
        metric="blocked_operation",
        date_range={"kind": "missing", "label": "period not specified"},
        ambiguity_flags=[],
        dangerous=True,
        dangerous_reason=f"Potential write/DDL operation detected: {matched_text}",
        source="guardrail_precheck",
        provider_confidence=0.0,
        fallback_used=False,
    )


def _resolved_request_payload(interpretation: Interpretation) -> dict:
    return {
        "metric": interpretation.metric,
        "dimensions": interpretation.dimensions,
        "filters": interpretation.filters,
        "period": interpretation.date_range,
        "limit": interpretation.limit,
        "source": interpretation.source,
        "provider_confidence": interpretation.provider_confidence,
        "fallback_used": interpretation.fallback_used,
        "clarification_reasons": interpretation.clarification_reasons,
    }


async def run_query_workflow(
    db: AsyncSession,
    user: User,
    question: str,
    chat_id: UUID | None = None,
) -> Query:
    query = Query(user_id=user.id, chat_id=chat_id, natural_text=question, status="running")
    db.add(query)
    await db.flush()

    async with trace_step(db, query, "Semantic layer") as event:
        catalog = await load_semantic_catalog(db)
        retrieval = await retrieve_context(db, question)
        query.semantic_terms_json = retrieval.semantic_terms
        event.payload_json = {
            **retrieval.as_dict(),
            "catalog": catalog.prompt_summary(),
        }

    dangerous_match = DANGEROUS_RE.search(question)
    clarification_result = None
    llm_plan_draft = None
    compiled_query = None

    if dangerous_match:
        interpretation = _dangerous_interpretation(question, dangerous_match.group(0))
        query.interpretation_json = interpretation.as_dict()
        query.resolved_request_json = _resolved_request_payload(interpretation)
    else:
        async with trace_step(db, query, "AI intent extraction") as event:
            intent_stage = await extract_intent_stage(question, retrieval, catalog)
            if intent_stage is None:
                raise RuntimeError("Intent extraction returned no result.")
            interpretation = intent_result_to_interpretation(
                intent_stage.structured,
                catalog,
                source=f"llm_gateway:intent_extraction@{intent_stage.response.telemetry.prompt_version}",
                fallback_used=intent_stage.response.telemetry.fallback_used,
            )
            query.interpretation_json = {
                **interpretation.as_dict(),
                "intent_extraction": intent_stage.structured.model_dump(mode="json"),
                "intent_telemetry": intent_stage.response.telemetry.as_dict(),
            }
            query.resolved_request_json = _resolved_request_payload(interpretation)
            event.payload_json = intent_stage.as_dict()

        if interpretation.ambiguity_flags or not interpretation.metric:
            async with trace_step(db, query, "AI clarification planning") as event:
                clarification_stage_result = await clarification_stage(
                    question,
                    retrieval,
                    catalog,
                    intent_stage.structured,
                )
                clarification_result = clarification_stage_result.structured
                if clarification_result.needs_clarification:
                    interpretation.clarification_question = clarification_result.question
                    interpretation.clarification_options = [
                        option.model_dump(mode="json") for option in clarification_result.options
                    ]
                    interpretation.ambiguity_flags = list(
                        dict.fromkeys(interpretation.ambiguity_flags + clarification_result.ambiguities)
                    )
                    query.interpretation_json = {
                        **query.interpretation_json,
                        "clarification_need": clarification_result.model_dump(mode="json"),
                        "clarification_telemetry": clarification_stage_result.response.telemetry.as_dict(),
                        "clarification_reasons": interpretation.clarification_reasons,
                    }
                event.payload_json = clarification_stage_result.as_dict()

    async with trace_step(db, query, "Confidence scoring") as event:
        confidence = score_confidence(interpretation, retrieval)
        query.confidence_score = confidence.score
        query.confidence_band = confidence.band
        query.confidence_reasons_json = confidence.reasons
        query.ambiguity_flags_json = confidence.ambiguities
        event.payload_json = confidence.as_dict()

    if interpretation.dangerous:
        async with trace_step(db, query, "Guardrails") as event:
            query.status = "blocked"
            query.block_reason = interpretation.dangerous_reason
            logs = [
                {
                    "check_name": "intent_safety",
                    "status": "failed",
                    "severity": "critical",
                    "code": "dangerous_request",
                    "message": interpretation.dangerous_reason,
                    "details": {"question": question},
                }
            ]
            await _persist_guardrail_logs(db, query, logs)
            event.status = "blocked"
            query.sql_plan_json = {
                **(query.sql_plan_json or {}),
                "block_reasons": [
                    build_block_reason(
                        "dangerous_request",
                        interpretation.dangerous_reason,
                        details={"question": question},
                    ).as_dict()
                ],
            }
            event.payload_json = {"blocked": True, "reason": query.block_reason, "block_reasons": query.sql_plan_json["block_reasons"]}
        query.ai_answer = (
            "Request blocked by the safety layer. Tolmach runs only in read-only mode, "
            "so write and DDL operations are never executed."
        )
        await db.commit()
        await db.refresh(query)
        return query

    if (clarification_result and clarification_result.needs_clarification) or confidence.band != "high":
        async with trace_step(db, query, "Clarification required") as event:
            query.status = "clarification_required"
            options = interpretation.clarification_options or _clarification_options(confidence.ambiguities)
            clarification = QueryClarification(
                query_id=query.id,
                question_text=interpretation.clarification_question or "Clarify the metric, period, or breakdown.",
                options_json=options,
            )
            db.add(clarification)
            query.resolved_request_json = {
                **(query.resolved_request_json or {}),
                "clarification_reasons": interpretation.clarification_reasons,
            }
            event.status = "needs_input"
            event.payload_json = {
                "ambiguities": confidence.ambiguities,
                "options": options,
                "clarification_reasons": interpretation.clarification_reasons,
            }
        query.ai_answer = (
            "Clarify the request before SQL planning. I found more than one plausible interpretation and will "
            "rebuild the server-side plan after you choose the correct option."
        )
        await db.commit()
        await db.refresh(query)
        return query

    try:
        async with trace_step(db, query, "AI SQL plan draft") as event:
            plan_stage = await sql_plan_draft_stage(question, retrieval, catalog, interpretation)
            llm_plan_draft = plan_stage.structured
            interpretation = sql_plan_draft_to_interpretation(
                llm_plan_draft,
                catalog,
                source=f"llm_gateway:sql_plan_draft@{plan_stage.response.telemetry.prompt_version}",
                fallback_used=plan_stage.response.telemetry.fallback_used,
            )
            query.interpretation_json = {
                **query.interpretation_json,
                **interpretation.as_dict(),
                "llm_sql_plan_draft": llm_plan_draft.model_dump(mode="json"),
                "llm_sql_plan_telemetry": plan_stage.response.telemetry.as_dict(),
            }
            query.resolved_request_json = {
                **query.resolved_request_json,
                **_resolved_request_payload(interpretation),
                "llm_plan_draft": llm_plan_draft.model_dump(mode="json"),
            }
            query.sql_plan_json = {
                "llm_plan_draft": llm_plan_draft.model_dump(mode="json"),
                "llm_plan_telemetry": plan_stage.response.telemetry.as_dict(),
            }
            event.payload_json = plan_stage.as_dict()

        async with trace_step(db, query, "Semantic SQL compilation") as event:
            compiled_query = compile_sql_query_bundle(interpretation, retrieval, catalog)
            plan = compiled_query.sql_plan
            sql = compiled_query.rendered_sql
            query.sql_plan_json = {
                **(query.sql_plan_json or {}),
                "planner_result": compiled_query.planner_result.as_dict(),
                "server_compiled_plan": plan.as_dict(),
                "compiled_sql_ast": plan.ast_json,
                "column_references": compiled_query.column_references,
                "source_tables": sorted(compiled_query.source_tables),
            }
            query.generated_sql = sql
            query.chart_type = plan.chart_type
            event.payload_json = {"plan": plan.as_dict(), "sql": sql, "planner": compiled_query.planner_result.as_dict()}
    except SemanticCompilationError as exc:
        query.status = "blocked"
        query.block_reason = str(exc)
        query.sql_plan_json = {
            **(query.sql_plan_json or {}),
            "block_reasons": [exc.reason.as_dict()],
        }
        query.ai_answer = f"Request could not be compiled through the semantic layer: {exc}"
        await db.commit()
        await db.refresh(query)
        return query

    async with trace_step(db, query, "Guardrails") as event:
        validation = await validate_sql(db, sql, role=user.role, query_id=query.id, compiled_query=compiled_query)
        await _persist_guardrail_logs(db, query, validation.logs)
        query.sql_plan_json = {
            **(query.sql_plan_json or {}),
            "validator_logs": validation.logs,
            "validator_summary": validation.validated_sql.validator_summary if validation.validated_sql else {},
            "block_reasons": validation.block_reasons,
        }
        event.payload_json = {"logs": validation.logs, "sql": validation.sql, "block_reasons": validation.block_reasons}
        if not validation.ok:
            query.status = "blocked"
            query.block_reason = validation.message
            event.status = "blocked"
            query.ai_answer = f"Request blocked by SQL guardrails: {validation.message}"
            await db.commit()
            await db.refresh(query)
            return query
        query.corrected_sql = validation.validated_sql.sql
        query.sql_explain_plan_json = validation.validated_sql.explain_plan
        query.sql_explain_cost = validation.validated_sql.explain_cost
        query.sql_plan_json = {
            **(query.sql_plan_json or {}),
            "validated_sql_ast": validation.validated_sql.ast_json,
        }

    rows: list[dict] = []
    execution_ms = 0
    validated = validation.validated_sql
    for attempt in range(0, 3):
        step_name = "SQL execution" if attempt == 0 else f"Auto-fix attempt {attempt}"
        try:
            async with trace_step(db, query, step_name) as event:
                started = time.perf_counter()
                execution_result = await execute_validated_query(
                    validated,
                    role=user.role,
                    db=db,
                    query_id=query.id,
                    use_cache=True,
                )
                rows = execution_result.rows
                execution_ms = int((time.perf_counter() - started) * 1000)
                event.payload_json = {
                    "rows_returned": len(rows),
                    "execution_ms": execution_ms,
                    "read_only": True,
                    "statement_timeout_ms": True,
                    "cache_hit": execution_result.cached,
                    "fingerprint": execution_result.fingerprint,
                    "execution_mode": execution_result.execution_mode,
                }
            break
        except Exception as exc:
            query.error_message = str(exc)
            query.status = "sql_error"
            if attempt >= 2:
                query.status = "autofix_failed"
                break
            query.auto_fix_attempts += 1
            fixed_sql = try_fix_sql(validated.sql, str(exc), plan, interpretation)
            if not fixed_sql:
                query.status = "autofix_failed"
                break
            async with trace_step(db, query, "Auto-fix node") as event:
                query.status = "autofix_running"
                query.corrected_sql = fixed_sql
                validation = await validate_sql(db, fixed_sql, role=user.role, query_id=query.id)
                await _persist_guardrail_logs(db, query, validation.logs)
                event.payload_json = {
                    "fixed_sql": fixed_sql,
                    "validation": validation.logs,
                    "block_reasons": validation.block_reasons,
                }
                if not validation.ok:
                    query.status = "autofix_failed"
                    break
                validated = validation.validated_sql
                query.corrected_sql = validated.sql
                query.sql_explain_plan_json = validated.explain_plan
                query.sql_explain_cost = validated.explain_cost
                query.sql_plan_json = {
                    **(query.sql_plan_json or {}),
                    "validator_logs": validation.logs,
                    "validator_summary": validated.validator_summary,
                    "block_reasons": validation.block_reasons,
                    "validated_sql_ast": validated.ast_json,
                }

    if query.status == "autofix_failed":
        query.ai_answer = (
            "SQL could not be repaired safely in automatic mode. Reformulate the request and I will build a fresh plan."
        )
        await db.commit()
        await db.refresh(query)
        return query

    async with trace_step(db, query, "Chart selection") as event:
        chart_spec = recommend_chart(rows)
        if chart_spec.get("type") == "table_only" and plan.chart_type != "table_only":
            chart_spec = {
                "type": plan.chart_type,
                "x": "day" if "day" in plan.dimensions else "city",
                "series": [{"key": plan.metric, "name": plan.metric_label or plan.metric}],
            }
        query.chart_spec = chart_spec
        query.chart_type = chart_spec.get("type", plan.chart_type)
        event.payload_json = {"chart_spec": chart_spec}

    async with trace_step(db, query, "AI answer summary") as event:
        query.status = "success"
        query.rows_returned = len(rows)
        query.execution_ms = execution_ms
        query.result_snapshot = rows[:200]
        fallback_answer = compose_answer(question, interpretation, confidence, plan, rows)
        summary_payload = {}
        if llm_plan_draft is not None:
            summary_stage = await build_answer_summary_with_ai(
                question=question,
                interpretation=interpretation,
                llm_plan_draft=llm_plan_draft,
                compiled_plan=plan,
                rows=rows,
                confidence_score=confidence.score,
                confidence_band=confidence.band,
                semantic_terms=retrieval.semantic_terms,
            )
            query.ai_answer = render_answer_summary(summary_stage.structured, fallback_answer)
            summary_payload = summary_stage.as_dict()
            query.interpretation_json = {
                **query.interpretation_json,
                "answer_summary_draft": summary_stage.structured.model_dump(mode="json"),
                "answer_summary_telemetry": summary_stage.response.telemetry.as_dict(),
            }
        else:
            query.ai_answer = fallback_answer
        explain = explain_interpretation(interpretation, plan, retrieval.semantic_terms)
        query.interpretation_json = {**query.interpretation_json, "explain": explain}
        query.resolved_request_json = {
            **query.resolved_request_json,
            "semantic_terms": [item["term"] for item in retrieval.semantic_terms[:8]],
            "confidence_band": confidence.band,
            "confidence_score": confidence.score,
        }
        event.payload_json = {"answer": query.ai_answer, "explain": explain, "summary": summary_payload}

    await db.commit()
    await db.refresh(query)
    return query
