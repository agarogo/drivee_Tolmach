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
from app.ai.generator import generate_sql
from app.ai.interpreter import interpret_query
from app.ai.planner import build_plan
from app.ai.retrieval import retrieve_context
from app.models import Query, QueryClarification, QueryEvent, SqlGuardrailLog, User
from app.services.charts import recommend_chart
from app.services.guardrails import GuardrailError, validate_sql
from app.services.observability import trace_span
from app.services.query_runner import execute_validated_select


PIPELINE_STEPS = [
    "Разбор запроса",
    "Семантический слой",
    "Проверка confidence",
    "Guardrails",
    "Генерация SQL",
    "Выполнение SQL",
    "Построение графика",
    "Генерация ответа ИИ",
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
            "label": "Полная сумма поездки",
            "value": "полная выручка по price_order_local",
            "description": "Использовать price_order_local по завершённым поездкам.",
        },
        {
            "label": "Скользящие 30 дней",
            "value": "за последние 30 дней",
            "description": "Применить rolling window от текущей даты.",
        },
        {
            "label": "Город заказа",
            "value": "по city_id заказа",
            "description": "Группировать по городу заказа из cities.",
        },
        {
            "label": "KPI по дням",
            "value": "покажи KPI по дням за последнюю неделю",
            "description": "Выручка, поездки, средний чек и отмены.",
        },
    ][: max(2, min(4, len(ambiguities) + 1))]


async def run_query_workflow(
    db: AsyncSession,
    user: User,
    question: str,
    chat_id: UUID | None = None,
) -> Query:
    query = Query(user_id=user.id, chat_id=chat_id, natural_text=question, status="running")
    db.add(query)
    await db.flush()

    async with trace_step(db, query, "Разбор запроса") as event:
        interpretation = interpret_query(question)
        query.interpretation_json = interpretation.as_dict()
        event.payload_json = {"interpretation": interpretation.as_dict()}

    async with trace_step(db, query, "Семантический слой") as event:
        retrieval = await retrieve_context(db, question, interpretation)
        query.semantic_terms_json = retrieval.semantic_terms
        event.payload_json = retrieval.as_dict()

    async with trace_step(db, query, "Проверка confidence") as event:
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
                    "message": interpretation.dangerous_reason,
                    "details": {"question": question},
                }
            ]
            await _persist_guardrail_logs(db, query, logs)
            event.status = "blocked"
            event.payload_json = {"blocked": True, "reason": query.block_reason}
        query.ai_answer = (
            "Запрос заблокирован системой безопасности. Толмач работает только в READ-ONLY режиме; "
            "write/DDL операции не выполняются."
        )
        await db.commit()
        await db.refresh(query)
        return query

    if confidence.band != "high":
        async with trace_step(db, query, "Уточняющий вопрос") as event:
            query.status = "clarification_required"
            options = _clarification_options(confidence.ambiguities)
            clarification = QueryClarification(
                query_id=query.id,
                question_text="Уточните запрос",
                options_json=options,
            )
            db.add(clarification)
            event.status = "needs_input"
            event.payload_json = {"ambiguities": confidence.ambiguities, "options": options}
        query.ai_answer = (
            "Уточните запрос: найдено несколько вариантов интерпретации. "
            "После уточнения я безопасно пересоберу SQL."
        )
        await db.commit()
        await db.refresh(query)
        return query

    async with trace_step(db, query, "Генерация SQL") as event:
        plan = build_plan(interpretation, retrieval)
        sql = generate_sql(plan, interpretation)
        query.sql_plan_json = plan.as_dict()
        query.generated_sql = sql
        query.chart_type = plan.chart_type
        event.payload_json = {"plan": plan.as_dict(), "sql": sql}

    async with trace_step(db, query, "Guardrails") as event:
        validation = await validate_sql(db, sql, role=user.role, query_id=query.id)
        await _persist_guardrail_logs(db, query, validation.logs)
        event.payload_json = {"logs": validation.logs, "sql": validation.sql}
        if not validation.ok:
            query.status = "blocked"
            query.block_reason = validation.message
            event.status = "blocked"
            query.ai_answer = f"Запрос заблокирован: {validation.message}"
            await db.commit()
            await db.refresh(query)
            return query

    rows: list[dict] = []
    execution_ms = 0
    validated = validation.validated_sql
    for attempt in range(0, 3):
        step_name = "Выполнение SQL" if attempt == 0 else f"Auto-Fix попытка {attempt}"
        try:
            async with trace_step(db, query, step_name) as event:
                started = time.perf_counter()
                rows = await execute_validated_select(validated)
                execution_ms = int((time.perf_counter() - started) * 1000)
                event.payload_json = {"rows_returned": len(rows), "execution_ms": execution_ms}
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
            async with trace_step(db, query, "Auto-Fix Node") as event:
                query.status = "autofix_running"
                query.corrected_sql = fixed_sql
                validation = await validate_sql(db, fixed_sql, role=user.role, query_id=query.id)
                await _persist_guardrail_logs(db, query, validation.logs)
                event.payload_json = {"fixed_sql": fixed_sql, "validation": validation.logs}
                if not validation.ok:
                    query.status = "autofix_failed"
                    break
                validated = validation.validated_sql

    if query.status == "autofix_failed":
        query.ai_answer = "SQL не удалось безопасно исправить автоматически. Попробуйте переформулировать запрос."
        await db.commit()
        await db.refresh(query)
        return query

    async with trace_step(db, query, "Построение графика") as event:
        chart_spec = recommend_chart(rows)
        if chart_spec.get("type") == "table_only" and plan.chart_type != "table_only":
            chart_spec = {
                "type": plan.chart_type,
                "x": "day" if "day" in plan.dimensions else "city",
                "series": [{"key": plan.metric, "name": plan.metric}],
            }
        query.chart_spec = chart_spec
        query.chart_type = chart_spec.get("type", plan.chart_type)
        event.payload_json = {"chart_spec": chart_spec}

    async with trace_step(db, query, "Генерация ответа ИИ") as event:
        query.status = "success"
        query.rows_returned = len(rows)
        query.execution_ms = execution_ms
        query.result_snapshot = rows[:200]
        query.ai_answer = compose_answer(question, interpretation, confidence, plan, rows)
        explain = explain_interpretation(interpretation, plan, retrieval.semantic_terms)
        query.interpretation_json = {**query.interpretation_json, "explain": explain}
        event.payload_json = {"answer": query.ai_answer, "explain": explain}

    await db.commit()
    await db.refresh(query)
    return query
