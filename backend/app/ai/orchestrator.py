from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.answer import (
    AnswerContractError,
    build_answer_envelope,
    explain_interpretation,
    legacy_chart_spec_from_answer,
    render_answer_text,
)
from app.ai.answer_classifier import AnswerTypeDecision, resolve_answer_type_decision
from app.ai.answer_strategy import build_answer_plan, compile_answer_query, execute_answer_plan
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
from app.ai.semantic_compiler import SemanticCompilationError
from app.ai.types import Interpretation
from app.chat_context import build_chat_continuation_context
from app.models import Query, QueryClarification, QueryEvent, SqlGuardrailLog, User
from app.semantic.errors import build_block_reason
from app.services.observability import trace_span
from app.services.guardrails import validate_sql


PIPELINE_STEPS = [
    "Semantic layer",
    "Chat continuity",
    "Answer type classification",
    "AI intent extraction",
    "AI clarification planning",
    "Confidence scoring",
    "AI SQL plan draft",
    "Semantic SQL compilation",
    "Guardrails",
    "SQL execution",
    "Answer contract selection",
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


async def _persist_guardrail_logs(
    db: AsyncSession,
    query: Query,
    logs: list[dict[str, Any]],
    *,
    block_key: str | None = None,
) -> None:
    for log in logs:
        message = log.get("message", "")
        if not isinstance(message, str):
            message = json.dumps(message, ensure_ascii=False, default=str)
        details = log.get("details", {})
        if not isinstance(details, dict):
            details = {"value": details}
        if block_key:
            details = {**details, "block_key": block_key}
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


def _clarification_options(ambiguities: list[str]) -> list[dict[str, Any]]:
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


def _resolved_request_payload(
    interpretation: Interpretation | None,
    *,
    decision: AnswerTypeDecision | None = None,
) -> dict[str, Any]:
    return {
        "metric": interpretation.metric if interpretation else "",
        "dimensions": interpretation.dimensions if interpretation else [],
        "filters": interpretation.filters if interpretation else {},
        "period": interpretation.date_range if interpretation else {},
        "limit": interpretation.limit if interpretation else 0,
        "source": interpretation.source if interpretation else "",
        "provider_confidence": interpretation.provider_confidence if interpretation else 0.0,
        "fallback_used": interpretation.fallback_used if interpretation else False,
        "clarification_reasons": interpretation.clarification_reasons if interpretation else [],
        "answer_type_decision": decision.model_dump(mode="json") if decision else {},
    }


def _payload_rows_from_envelope(envelope) -> list[dict[str, Any]]:
    payload = envelope.render_payload
    if payload is None:
        return []
    if payload.kind in {"comparison_top", "trend", "distribution", "table"}:
        return payload.rows
    if payload.kind == "single_value":
        return payload.supporting_rows
    if payload.kind == "full_report":
        for section in payload.sections:
            if getattr(section, "kind", "") == "table" and getattr(section, "rows", None):
                return section.rows
            if getattr(section, "kind", "") == "chart" and getattr(section, "rows", None):
                return section.rows
    return []


def _apply_answer_contract(query: Query, envelope) -> None:
    query.answer_type_code = int(envelope.answer_type)
    query.answer_type_key = str(envelope.answer_type_key)
    query.primary_view_mode = str(envelope.primary_view_mode)
    query.answer_envelope_json = envelope.model_dump(mode="json")
    query.chart_spec = legacy_chart_spec_from_answer(envelope)
    query.chart_type = query.chart_spec.get("type", "table_only")
    query.result_snapshot = _payload_rows_from_envelope(envelope)[:200]


def _combined_sql_text(executed_plan) -> str:
    if executed_plan is None or not executed_plan.blocks:
        return ""
    parts: list[str] = []
    for block in executed_plan.blocks.values():
        sql_text = block.validation.validated_sql.sql if block.validation.validated_sql else block.compiled.rendered_sql
        prefix = f"-- {block.spec.block_key}\n" if len(executed_plan.blocks) > 1 else ""
        parts.append(f"{prefix}{sql_text}".strip())
    return "\n\n".join(parts)


def _primary_block(executed_plan):
    return executed_plan.primary_block if executed_plan is not None else None


def _compiled_blocks_payload(block_specs: dict[str, Any]) -> dict[str, Any]:
    return {key: value.as_dict() for key, value in block_specs.items()}


async def run_query_workflow(
    db: AsyncSession,
    user: User,
    question: str,
    chat_id: UUID | None = None,
) -> Query:
    query = Query(user_id=user.id, chat_id=chat_id, natural_text=question, status="running")
    db.add(query)
    await db.flush()

    chat_context = await build_chat_continuation_context(
        db,
        user_id=user.id,
        chat_id=chat_id,
        question=question,
    )
    effective_question = chat_context.effective_question
    if chat_context.context_json:
        query.resolved_request_json = {
            **(query.resolved_request_json or {}),
            "chat_context": chat_context.context_json,
        }
        db.add(
            QueryEvent(
                query_id=query.id,
                step_name="Chat continuity",
                status="ok",
                payload_json=chat_context.context_json,
                finished_at=datetime.utcnow(),
                duration_ms=0,
            )
        )
        await db.flush()

    async with trace_step(db, query, "Semantic layer") as event:
        catalog = await load_semantic_catalog(db)
        retrieval = await retrieve_context(db, effective_question)
        query.semantic_terms_json = retrieval.semantic_terms
        event.payload_json = {
            **retrieval.as_dict(),
            "catalog": catalog.prompt_summary(),
            "effective_question": effective_question,
        }

    async with trace_step(db, query, "Answer type classification") as event:
        decision = await resolve_answer_type_decision(
            question=question,
            chat_context=chat_context.context_json,
            retrieval=retrieval,
        )
        query.answer_type_code = int(decision.answer_type)
        query.answer_type_key = str(decision.answer_type_key)
        query.primary_view_mode = str(decision.primary_view_mode)
        query.resolved_request_json = {
            **(query.resolved_request_json or {}),
            "answer_type_decision": decision.model_dump(mode="json"),
        }
        event.payload_json = decision.model_dump(mode="json")

    if decision.answer_type_key == "chat_help":
        query.status = "success"
        query.confidence_score = decision.confidence_score
        query.confidence_band = "high"
        query.confidence_reasons_json = [decision.reason]
        query.ambiguity_flags_json = []
        query.generated_sql = ""
        query.corrected_sql = ""
        query.sql_plan_json = {
            "answer_type_decision": decision.model_dump(mode="json"),
            "answer_strategy": None,
            "answer_blocks": {},
            "chat_help_path": True,
        }
        envelope = build_answer_envelope(
            question=question,
            decision=decision,
            status="success",
            query_id=query.id,
            chat_id=query.chat_id,
            created_at=query.created_at,
            updated_at=query.updated_at,
            semantic_terms=retrieval.semantic_terms,
            catalog=catalog,
        )
        _apply_answer_contract(query, envelope)
        query.ai_answer = render_answer_text(envelope)
        query.interpretation_json = {
            **(query.interpretation_json or {}),
            "answer_type_decision": decision.model_dump(mode="json"),
            "help_path": True,
            "explain": explain_interpretation(decision=decision, interpretation=None, envelope=envelope),
        }
        await db.commit()
        await db.refresh(query)
        return query

    dangerous_match = DANGEROUS_RE.search(question)
    clarification_result = None
    llm_plan_draft = None
    answer_plan = None
    compiled_blocks: dict[str, Any] = {}
    answer_specs: list[Any] = []
    executed_plan = None

    if dangerous_match:
        interpretation = _dangerous_interpretation(question, dangerous_match.group(0))
        query.interpretation_json = interpretation.as_dict()
        query.resolved_request_json = _resolved_request_payload(interpretation, decision=decision)
    else:
        async with trace_step(db, query, "AI intent extraction") as event:
            intent_stage = await extract_intent_stage(effective_question, retrieval, catalog)
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
                "answer_type_decision": decision.model_dump(mode="json"),
                "intent_extraction": intent_stage.structured.model_dump(mode="json"),
                "intent_telemetry": intent_stage.response.telemetry.as_dict(),
            }
            query.resolved_request_json = _resolved_request_payload(interpretation, decision=decision)
            event.payload_json = intent_stage.as_dict()

        if interpretation.ambiguity_flags or not interpretation.metric:
            async with trace_step(db, query, "AI clarification planning") as event:
                clarification_stage_result = await clarification_stage(
                    effective_question,
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
                "answer_type_decision": decision.model_dump(mode="json"),
                "block_reasons": [
                    build_block_reason(
                        "dangerous_request",
                        interpretation.dangerous_reason,
                        details={"question": question},
                    ).as_dict()
                ],
            }
            event.payload_json = {
                "blocked": True,
                "reason": query.block_reason,
                "block_reasons": query.sql_plan_json["block_reasons"],
            }
        envelope = build_answer_envelope(
            question=question,
            decision=decision,
            interpretation=interpretation,
            confidence=confidence,
            status="blocked",
            query_id=query.id,
            chat_id=query.chat_id,
            created_at=query.created_at,
            updated_at=query.updated_at,
            semantic_terms=retrieval.semantic_terms,
            notes=[interpretation.dangerous_reason],
        )
        _apply_answer_contract(query, envelope)
        query.ai_answer = (
            "Request blocked by the safety layer. Tolmach runs only in read-only mode, "
            "so write and DDL operations are never executed."
        )
        query.interpretation_json = {
            **(query.interpretation_json or {}),
            "explain": explain_interpretation(decision=decision, interpretation=interpretation, envelope=envelope),
        }
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
        envelope = build_answer_envelope(
            question=question,
            decision=decision,
            interpretation=interpretation,
            confidence=confidence,
            status="clarification_required",
            query_id=query.id,
            chat_id=query.chat_id,
            created_at=query.created_at,
            updated_at=query.updated_at,
            semantic_terms=retrieval.semantic_terms,
        )
        _apply_answer_contract(query, envelope)
        query.ai_answer = (
            "Clarify the request before SQL planning. I found more than one plausible interpretation and will "
            "rebuild the answer plan after you choose the correct option."
        )
        query.interpretation_json = {
            **(query.interpretation_json or {}),
            "explain": explain_interpretation(decision=decision, interpretation=interpretation, envelope=envelope),
        }
        await db.commit()
        await db.refresh(query)
        return query

    try:
        async with trace_step(db, query, "AI SQL plan draft") as event:
            plan_stage = await sql_plan_draft_stage(effective_question, retrieval, catalog, interpretation)
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
                "answer_type_decision": decision.model_dump(mode="json"),
                "llm_sql_plan_draft": llm_plan_draft.model_dump(mode="json"),
                "llm_sql_plan_telemetry": plan_stage.response.telemetry.as_dict(),
            }
            query.resolved_request_json = {
                **query.resolved_request_json,
                **_resolved_request_payload(interpretation, decision=decision),
                "llm_plan_draft": llm_plan_draft.model_dump(mode="json"),
            }
            query.sql_plan_json = {
                "answer_type_decision": decision.model_dump(mode="json"),
                "llm_plan_draft": llm_plan_draft.model_dump(mode="json"),
                "llm_plan_telemetry": plan_stage.response.telemetry.as_dict(),
            }
            event.payload_json = plan_stage.as_dict()

        async with trace_step(db, query, "Semantic SQL compilation") as event:
            answer_plan = build_answer_plan(
                decision=decision,
                interpretation=interpretation,
                retrieval=retrieval,
                catalog=catalog,
            )
            all_specs = []
            if answer_plan.primary_spec is not None:
                all_specs.append(answer_plan.primary_spec)
            all_specs.extend(answer_plan.secondary_specs)
            answer_specs = all_specs
            compiled_blocks = {
                spec.block_key: compile_answer_query(spec, retrieval=retrieval, catalog=catalog)
                for spec in all_specs
            }
            primary_compiled = compiled_blocks.get(answer_plan.primary_spec.block_key) if answer_plan.primary_spec else None
            if primary_compiled is not None:
                query.generated_sql = primary_compiled.rendered_sql
                query.chart_type = primary_compiled.sql_plan.chart_type
            query.sql_plan_json = {
                **(query.sql_plan_json or {}),
                "answer_strategy": answer_plan.as_dict(),
                "answer_compiled_blocks": _compiled_blocks_payload(compiled_blocks),
            }
            event.payload_json = {
                "answer_strategy": answer_plan.as_dict(),
                "compiled_blocks": _compiled_blocks_payload(compiled_blocks),
            }
    except SemanticCompilationError as exc:
        query.status = "blocked"
        query.block_reason = str(exc)
        query.sql_plan_json = {
            **(query.sql_plan_json or {}),
            "block_reasons": [exc.reason.as_dict()] if getattr(exc, "reason", None) else [],
        }
        envelope = build_answer_envelope(
            question=question,
            decision=decision,
            interpretation=interpretation,
            confidence=confidence,
            status="blocked",
            query_id=query.id,
            chat_id=query.chat_id,
            created_at=query.created_at,
            updated_at=query.updated_at,
            semantic_terms=retrieval.semantic_terms,
            notes=[str(exc)],
        )
        _apply_answer_contract(query, envelope)
        query.ai_answer = f"Request could not be compiled through the semantic layer: {exc}"
        query.interpretation_json = {
            **(query.interpretation_json or {}),
            "explain": explain_interpretation(decision=decision, interpretation=interpretation, envelope=envelope),
        }
        await db.commit()
        await db.refresh(query)
        return query

    async with trace_step(db, query, "Guardrails") as event:
        preflight_validations: dict[str, Any] = {}
        preflight_failures: dict[str, Any] = {}
        guardrail_logs: list[dict[str, Any]] = []
        for spec in answer_specs:
            compiled = compiled_blocks[spec.block_key]
            validation = await validate_sql(
                db,
                compiled.rendered_sql,
                role=user.role,
                query_id=query.id,
                compiled_query=type("Compiled", (), {"column_references": compiled.column_references})(),
            )
            tagged = [
                {
                    **log,
                    "details": {**(log.get("details") or {}), "block_key": spec.block_key},
                }
                for log in validation.logs
            ]
            guardrail_logs.extend(tagged)
            await _persist_guardrail_logs(db, query, tagged, block_key=spec.block_key)
            if validation.ok and validation.validated_sql is not None:
                preflight_validations[spec.block_key] = {
                    "validated_sql": validation.validated_sql.sql,
                    "explain_cost": validation.validated_sql.explain_cost,
                    "explain_plan": validation.validated_sql.explain_plan,
                    "row_limit": validation.validated_sql.row_limit,
                }
                continue
            preflight_failures[spec.block_key] = {
                "title": spec.title,
                "optional": spec.optional,
                "reason": validation.message,
                "block_reasons": validation.block_reasons,
            }

        query.sql_plan_json = {
            **(query.sql_plan_json or {}),
            "guardrail_preflight": preflight_validations,
            "guardrail_failures": preflight_failures,
        }
        event.payload_json = {
            "guardrail_preflight": preflight_validations,
            "guardrail_failures": preflight_failures,
            "guardrail_logs": guardrail_logs,
        }
        primary_failure = None
        if answer_plan.primary_spec is not None:
            primary_failure = preflight_failures.get(answer_plan.primary_spec.block_key)
        if primary_failure is not None:
            query.status = "blocked"
            query.block_reason = primary_failure["reason"] if primary_failure else "Primary answer block did not execute."
            event.status = "blocked"
            block_reasons = list(primary_failure.get("block_reasons", []) if primary_failure else [])
            query.sql_plan_json = {
                **(query.sql_plan_json or {}),
                "block_reasons": block_reasons,
            }
            envelope = build_answer_envelope(
                question=question,
                decision=decision,
                interpretation=interpretation,
                confidence=confidence,
                executed_plan=executed_plan,
                status="blocked",
                query_id=query.id,
                chat_id=query.chat_id,
                created_at=query.created_at,
                updated_at=query.updated_at,
                semantic_terms=retrieval.semantic_terms,
                notes=answer_plan.notes,
            )
            _apply_answer_contract(query, envelope)
            query.ai_answer = f"Request blocked while validating the primary {decision.answer_type_label.lower()} block."
            query.interpretation_json = {
                **(query.interpretation_json or {}),
                "explain": explain_interpretation(decision=decision, interpretation=interpretation, envelope=envelope),
            }
            await db.commit()
            await db.refresh(query)
            return query

        if answer_plan.primary_spec is not None:
            primary_validation = preflight_validations.get(answer_plan.primary_spec.block_key) or {}
            query.corrected_sql = str(primary_validation.get("validated_sql") or "")
            query.sql_explain_cost = float(primary_validation.get("explain_cost") or 0.0)
            query.sql_explain_plan_json = dict(primary_validation.get("explain_plan") or {})

    async with trace_step(db, query, "SQL execution") as event:
        executed_plan = await execute_answer_plan(
            db,
            query_id=query.id,
            role=user.role,
            plan=answer_plan,
            retrieval=retrieval,
            catalog=catalog,
        )
        primary_failure = None
        if answer_plan.primary_spec is not None:
            primary_failure = executed_plan.failures.get(answer_plan.primary_spec.block_key)
        if primary_failure is not None or _primary_block(executed_plan) is None:
            query.status = "blocked"
            query.block_reason = primary_failure.reason if primary_failure else "Primary answer block did not execute."
            event.status = "blocked"
            if primary_failure is not None and primary_failure.stage == "execution":
                synthetic = [
                    {
                        "check_name": "execution",
                        "status": "failed",
                        "severity": "critical",
                        "message": primary_failure.reason,
                        "details": {"block_key": primary_failure.block_key},
                    }
                ]
                await _persist_guardrail_logs(db, query, synthetic, block_key=primary_failure.block_key)
            block_reasons = list(primary_failure.block_reasons if primary_failure else [])
            query.sql_plan_json = {
                **(query.sql_plan_json or {}),
                "answer_blocks": {key: value.as_dict() for key, value in executed_plan.blocks.items()},
                "answer_failures": {key: value.as_dict() for key, value in executed_plan.failures.items()},
                "block_reasons": block_reasons,
            }
            envelope = build_answer_envelope(
                question=question,
                decision=decision,
                interpretation=interpretation,
                confidence=confidence,
                executed_plan=executed_plan,
                status="blocked",
                query_id=query.id,
                chat_id=query.chat_id,
                created_at=query.created_at,
                updated_at=query.updated_at,
                semantic_terms=retrieval.semantic_terms,
                notes=answer_plan.notes,
            )
            _apply_answer_contract(query, envelope)
            query.ai_answer = f"Request blocked while running the primary {decision.answer_type_label.lower()} block."
            query.interpretation_json = {
                **(query.interpretation_json or {}),
                "explain": explain_interpretation(decision=decision, interpretation=interpretation, envelope=envelope),
            }
            await db.commit()
            await db.refresh(query)
            return query

        primary_block = _primary_block(executed_plan)
        query.corrected_sql = primary_block.validation.validated_sql.sql if primary_block and primary_block.validation.validated_sql else query.corrected_sql
        query.sql_explain_plan_json = (
            primary_block.validation.validated_sql.explain_plan
            if primary_block and primary_block.validation.validated_sql
            else query.sql_explain_plan_json
        )
        query.sql_explain_cost = (
            primary_block.validation.validated_sql.explain_cost
            if primary_block and primary_block.validation.validated_sql
            else query.sql_explain_cost
        )
        for failure in executed_plan.failures.values():
            if failure.stage == "execution":
                synthetic = [
                    {
                        "check_name": "execution",
                        "status": "failed",
                        "severity": "warning" if failure.optional else "critical",
                        "message": failure.reason,
                        "details": {"block_key": failure.block_key},
                    }
                ]
                await _persist_guardrail_logs(db, query, synthetic, block_key=failure.block_key)
        query.status = "success"
        query.rows_returned = sum(len(block.rows) for block in executed_plan.blocks.values())
        query.execution_ms = executed_plan.total_execution_ms
        query.sql_plan_json = {
            **(query.sql_plan_json or {}),
            "answer_blocks": {key: value.as_dict() for key, value in executed_plan.blocks.items()},
            "answer_failures": {key: value.as_dict() for key, value in executed_plan.failures.items()},
        }
        event.payload_json = {
            "rows_returned": query.rows_returned,
            "execution_ms": query.execution_ms,
            "blocks": {
                key: {
                    "rows_returned": len(value.rows),
                    "execution_ms": value.execution_ms,
                    "cached": value.cached,
                    "execution_mode": value.execution_mode,
                    "fingerprint": value.fingerprint,
                }
                for key, value in executed_plan.blocks.items()
            },
        }

    async with trace_step(db, query, "Answer contract selection") as event:
        combined_sql = _combined_sql_text(executed_plan)
        try:
            envelope = build_answer_envelope(
                question=question,
                decision=decision,
                interpretation=interpretation,
                confidence=confidence,
                executed_plan=executed_plan,
                status="success",
                query_id=query.id,
                chat_id=query.chat_id,
                created_at=query.created_at,
                updated_at=query.updated_at,
                execution_ms=query.execution_ms,
                sql_text=combined_sql,
                sql_explain_cost=float(query.sql_explain_cost or 0.0),
                semantic_terms=retrieval.semantic_terms,
                notes=answer_plan.notes,
            )
        except AnswerContractError as exc:
            query.status = "blocked"
            query.block_reason = str(exc)
            query.error_message = str(exc)
            query.sql_plan_json = {
                **(query.sql_plan_json or {}),
                "answer_contract_error": str(exc),
            }
            event.status = "blocked"
            event.payload_json = {
                "answer_contract_error": str(exc),
            }
            envelope = build_answer_envelope(
                question=question,
                decision=decision,
                interpretation=interpretation,
                confidence=confidence,
                executed_plan=executed_plan,
                status="blocked",
                query_id=query.id,
                chat_id=query.chat_id,
                created_at=query.created_at,
                updated_at=query.updated_at,
                execution_ms=query.execution_ms,
                sql_text=combined_sql,
                sql_explain_cost=float(query.sql_explain_cost or 0.0),
                semantic_terms=retrieval.semantic_terms,
                notes=answer_plan.notes + [str(exc)],
            )
            _apply_answer_contract(query, envelope)
            query.ai_answer = "Answer contract could not be materialized from the executed result."
            query.interpretation_json = {
                **(query.interpretation_json or {}),
                "explain": explain_interpretation(decision=decision, interpretation=interpretation, envelope=envelope),
            }
            await db.commit()
            await db.refresh(query)
            return query

        _apply_answer_contract(query, envelope)
        event.payload_json = {
            "answer_type_code": query.answer_type_code,
            "answer_type_key": query.answer_type_key,
            "primary_view_mode": query.primary_view_mode,
            "switch_options": [item.model_dump(mode="json") for item in envelope.switch_options],
        }

    async with trace_step(db, query, "AI answer summary") as event:
        fallback_answer = render_answer_text(envelope)
        summary_payload = {}
        use_ai_summary = (
            llm_plan_draft is not None
            and decision.answer_type_key in {"single_value", "comparison_top", "trend", "distribution"}
            and executed_plan.primary_block is not None
        )
        if use_ai_summary:
            summary_stage = await build_answer_summary_with_ai(
                question=question,
                interpretation=interpretation,
                llm_plan_draft=llm_plan_draft,
                compiled_plan=executed_plan.primary_block.compiled.sql_plan,
                rows=executed_plan.primary_block.rows,
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
        explain = explain_interpretation(decision=decision, interpretation=interpretation, envelope=envelope)
        query.interpretation_json = {**query.interpretation_json, "explain": explain}
        query.resolved_request_json = {
            **query.resolved_request_json,
            "semantic_terms": [item["term"] for item in retrieval.semantic_terms[:8] if item.get("term")],
            "confidence_band": confidence.band,
            "confidence_score": confidence.score,
        }
        event.payload_json = {
            "answer": query.ai_answer,
            "explain": explain,
            "summary": summary_payload,
            "answer_type_key": query.answer_type_key,
        }

    await db.commit()
    await db.refresh(query)
    return query
