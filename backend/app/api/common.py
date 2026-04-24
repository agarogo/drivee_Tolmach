import logging
from datetime import datetime, time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query as ApiQuery, Request, Response, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.providers import LLMProviderError
from app.ai.orchestrator import run_query_workflow
from app.auth import (
    apply_session_cookies,
    clear_session_cookies,
    create_session_bundle,
    get_current_user,
    hash_password,
    needs_password_rehash,
    require_admin,
    revoke_session,
    verify_password,
)
from app.config import get_settings
from app.db import get_db
from app.models import (
    Chat,
    Message,
    Query,
    QueryClarification,
    QueryExecutionAudit,
    QueryEvent,
    Report,
    ReportArtifact,
    ReportDelivery,
    ReportRecipient,
    ReportVersion,
    Schedule,
    ScheduleRun,
    SqlGuardrailLog,
    Template,
    User,
)
from app.query_execution.benchmarks import BENCHMARK_PRESETS
from app.query_execution.service import (
    get_query_cache_stats,
    get_query_execution_summary,
    list_query_execution_audits,
)
from app.schemas import (
    ApprovedTemplateCreate,
    ApprovedTemplateOut,
    ApprovedTemplatePatch,
    AssistantMessageResponse,
    AuthResponse,
    BenchmarkPresetOut,
    ChatDeleteOut,
    ChatOut,
    ClarificationOut,
    DimensionCatalogCreate,
    DimensionCatalogOut,
    DimensionCatalogPatch,
    GuardrailLogOut,
    LogOut,
    LoginRequest,
    LogoutResponse,
    MessageOut,
    MetricCatalogCreate,
    MetricCatalogOut,
    MetricCatalogPatch,
    MessagesPage,
    QueryClarifyRequest,
    QueryExecutionAuditOut,
    QueryExecutionCacheStatsOut,
    QueryExecutionSummaryOut,
    QueryEventOut,
    QueryOut,
    QueryRunRequest,
    RegisterRequest,
    ReportArtifactOut,
    ReportCreate,
    ReportDeliveryOut,
    ReportOut,
    ReportPatch,
    ReportRecipientOut,
    ReportVersionOut,
    SchedulerSummaryOut,
    ScheduleCreate,
    ScheduleOut,
    SchedulePatch,
    ScheduleRequest,
    ScheduleRunOut,
    SemanticExampleCreate,
    SemanticExampleOut,
    SemanticExamplePatch,
    SemanticTermCreate,
    SemanticTermOut,
    SemanticTermPatch,
    SemanticValidationReportOut,
    SendMessageRequest,
    TemplateCreate,
    TemplateOut,
    UserOut,
)
from app.semantic import repository as semantic_repository
from app.semantic.service import (
    create_approved_template_entry,
    create_dimension_catalog_entry,
    create_metric_catalog_entry,
    create_semantic_example_entry,
    create_semantic_term_entry,
    delete_approved_template_entry,
    delete_dimension_catalog_entry,
    delete_metric_catalog_entry,
    delete_semantic_example_entry,
    delete_semantic_term_entry,
    update_approved_template_entry,
    update_dimension_catalog_entry,
    update_metric_catalog_entry,
    update_semantic_example_entry,
    update_semantic_term_entry,
    validate_semantic_layer,
)
from app.reports import (
    append_report_recipients,
    build_semantic_snapshot_from_query,
    create_report_version,
    create_run_record,
    execute_report_run,
    get_scheduler_summary,
    list_report_runs,
    next_run_at,
    parse_run_time,
    replace_report_recipients,
)
settings = get_settings()
logger = logging.getLogger(__name__)


def to_user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


def make_chat_title(question: str) -> str:
    compact = " ".join(question.strip().split())
    if len(compact) <= 30:
        return compact
    return compact[:29].rstrip() + "..."


def _device_hint(request: Request) -> str:
    user_agent = (request.headers.get("user-agent") or "").strip()
    client_host = request.client.host if request.client else ""
    return " | ".join(part for part in (user_agent[:200], client_host) if part)[:255]


def _normalize_provider_name(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"fallback_rule", "fallback"}:
        return "fallback"
    if normalized in {"ollama", "production"}:
        return normalized
    return normalized


def _query_ai_telemetry(item: Query) -> dict[str, Any]:
    interpretation = item.interpretation_json if isinstance(item.interpretation_json, dict) else {}
    resolved_request = item.resolved_request_json if isinstance(item.resolved_request_json, dict) else {}
    candidates: list[dict[str, Any]] = []

    answer_type_decision = resolved_request.get("answer_type_decision")
    if isinstance(answer_type_decision, dict):
        provider = _normalize_provider_name(answer_type_decision.get("provider"))
        candidates.append(
            {
                "provider": provider,
                "model": str(answer_type_decision.get("llm_model") or ""),
                "llm_used": bool(answer_type_decision.get("llm_used")),
                "fallback_used": bool(answer_type_decision.get("fallback_used") or provider == "fallback"),
            }
        )

    for key in (
        "intent_telemetry",
        "clarification_telemetry",
        "llm_sql_plan_telemetry",
        "answer_summary_telemetry",
    ):
        telemetry = interpretation.get(key)
        if not isinstance(telemetry, dict):
            continue
        provider = _normalize_provider_name(telemetry.get("provider"))
        candidates.append(
            {
                "provider": provider,
                "model": str(telemetry.get("model") or ""),
                "llm_used": provider not in {"", "fallback"},
                "fallback_used": bool(telemetry.get("fallback_used") or provider == "fallback"),
            }
        )

    llm_used = any(bool(candidate.get("llm_used")) for candidate in candidates)
    fallback_used = any(bool(candidate.get("fallback_used")) for candidate in candidates)
    if llm_used:
        primary = next(candidate for candidate in reversed(candidates) if bool(candidate.get("llm_used")))
    else:
        primary = candidates[-1] if candidates else {}
    provider = str(primary.get("provider") or ("fallback" if fallback_used else ""))
    llm_model = str(primary.get("model") or "")

    return {
        "provider": provider,
        "llm_provider": provider,
        "llm_model": llm_model,
        "llm_used": llm_used,
        "fallback_used": fallback_used,
        "retrieval_used": True,
    }


async def _run_query_workflow_or_503(
    db: AsyncSession,
    user: User,
    question: str,
    chat_id: UUID | None,
) -> Query:
    try:
        return await run_query_workflow(db, user, question, chat_id)
    except LLMProviderError as exc:
        await db.rollback()
        logger.error("LLM dependency is unavailable for question processing: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


async def chat_out(db: AsyncSession, chat: Chat) -> ChatOut:
    count = await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id))
    return ChatOut(
        id=chat.id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        message_count=count or 0,
    )


async def require_owned_chat(db: AsyncSession, chat_id: UUID, user: User) -> Chat:
    chat = await db.get(Chat, chat_id)
    if not chat or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Чат не найден")
    return chat


async def ensure_query_chat(db: AsyncSession, user: User, chat_id: UUID | None, question: str) -> Chat:
    if chat_id:
        return await require_owned_chat(db, chat_id, user)
    chat = Chat(user_id=user.id, title=make_chat_title(question))
    db.add(chat)
    await db.flush()
    return chat


async def delete_chat_with_related_data(db: AsyncSession, chat: Chat) -> dict[str, int]:
    query_ids = list(
        (
            await db.scalars(
                select(Query.id).where(Query.chat_id == chat.id)
            )
        ).all()
    )
    counts = {
        "messages": int(await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id)) or 0),
        "queries": len(query_ids),
        "clarifications": 0,
        "events": 0,
        "guardrail_logs": 0,
        "reports_detached": 0,
        "query_audits_detached": 0,
    }
    if query_ids:
        counts["clarifications"] = int(
            await db.scalar(select(func.count(QueryClarification.id)).where(QueryClarification.query_id.in_(query_ids)))
            or 0
        )
        counts["events"] = int(
            await db.scalar(select(func.count(QueryEvent.id)).where(QueryEvent.query_id.in_(query_ids))) or 0
        )
        counts["guardrail_logs"] = int(
            await db.scalar(select(func.count(SqlGuardrailLog.id)).where(SqlGuardrailLog.query_id.in_(query_ids))) or 0
        )
        counts["reports_detached"] = int(
            await db.scalar(select(func.count(Report.id)).where(Report.query_id.in_(query_ids))) or 0
        )
        counts["query_audits_detached"] = int(
            await db.scalar(select(func.count(QueryExecutionAudit.id)).where(QueryExecutionAudit.query_id.in_(query_ids)))
            or 0
        )

        await db.execute(
            update(Report)
            .where(Report.query_id.in_(query_ids))
            .values(query_id=None, updated_at=datetime.utcnow())
        )
        await db.execute(
            update(QueryExecutionAudit)
            .where(QueryExecutionAudit.query_id.in_(query_ids))
            .values(query_id=None)
        )
        await db.execute(delete(QueryClarification).where(QueryClarification.query_id.in_(query_ids)))
        await db.execute(delete(QueryEvent).where(QueryEvent.query_id.in_(query_ids)))
        await db.execute(delete(SqlGuardrailLog).where(SqlGuardrailLog.query_id.in_(query_ids)))
        await db.execute(delete(Query).where(Query.id.in_(query_ids)))

    await db.execute(delete(Message).where(Message.chat_id == chat.id))
    await db.delete(chat)
    await db.flush()
    return counts


async def require_owned_query(db: AsyncSession, query_id: UUID, user: User) -> Query:
    item = await db.get(Query, query_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    return item


async def require_owned_report(db: AsyncSession, report_id: UUID, user: User) -> Report:
    item = await db.get(Report, report_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return item


async def require_owned_schedule(db: AsyncSession, schedule_id: UUID, user: User) -> Schedule:
    item = await db.get(Schedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    await require_owned_report(db, item.report_id, user)
    return item


async def query_to_out(db: AsyncSession, item: Query) -> QueryOut:
    ai_telemetry = _query_ai_telemetry(item)
    events = list(
        (
            await db.scalars(
                select(QueryEvent).where(QueryEvent.query_id == item.id).order_by(QueryEvent.started_at.asc())
            )
        ).all()
    )
    guardrails = list(
        (await db.scalars(select(SqlGuardrailLog).where(SqlGuardrailLog.query_id == item.id))).all()
    )
    clarifications = list(
        (
            await db.scalars(
                select(QueryClarification)
                .where(QueryClarification.query_id == item.id)
                .order_by(QueryClarification.created_at.asc())
            )
        ).all()
    )
    return QueryOut(
        id=item.id,
        chat_id=item.chat_id,
        natural_text=item.natural_text,
        generated_sql=item.generated_sql,
        corrected_sql=item.corrected_sql,
        confidence_score=float(item.confidence_score or 0),
        confidence_band=item.confidence_band,
        status=item.status,
        block_reason=item.block_reason,
        block_reasons=list((item.sql_plan_json or {}).get("block_reasons", [])),
        interpretation=item.interpretation_json,
        resolved_request=item.resolved_request_json,
        semantic_terms=item.semantic_terms_json,
        sql_plan=item.sql_plan_json,
        sql_explain_plan=item.sql_explain_plan_json,
        sql_explain_cost=float(item.sql_explain_cost or 0),
        confidence_reasons=item.confidence_reasons_json,
        ambiguity_flags=item.ambiguity_flags_json,
        rows_returned=item.rows_returned,
        execution_ms=item.execution_ms,
        provider=ai_telemetry["provider"],
        llm_provider=ai_telemetry["llm_provider"],
        llm_model=ai_telemetry["llm_model"],
        llm_used=ai_telemetry["llm_used"],
        fallback_used=ai_telemetry["fallback_used"],
        retrieval_used=ai_telemetry["retrieval_used"],
        answer_type_code=item.answer_type_code,
        answer_type_key=item.answer_type_key,
        primary_view_mode=item.primary_view_mode,
        answer=item.answer_envelope_json or None,
        chart_type=item.chart_type,
        chart_spec=item.chart_spec,
        result_snapshot=item.result_snapshot,
        ai_answer=item.ai_answer,
        error_message=item.error_message,
        auto_fix_attempts=item.auto_fix_attempts,
        clarifications=[ClarificationOut.model_validate(row, from_attributes=True) for row in clarifications],
        events=[QueryEventOut.model_validate(row, from_attributes=True) for row in events],
        guardrail_logs=[GuardrailLogOut.model_validate(row, from_attributes=True) for row in guardrails],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def assistant_payload_from_query(output: QueryOut, item: Query) -> dict:
    return {
        **output.model_dump(mode="json"),
        "type": item.status,
        "rows": item.result_snapshot,
        "sql": item.corrected_sql or item.generated_sql,
        "answer": output.answer.model_dump(mode="json") if output.answer else None,
    }


async def run_to_out(db: AsyncSession, item: ScheduleRun) -> ScheduleRunOut:
    artifacts = list(
        (
            await db.scalars(
                select(ReportArtifact).where(ReportArtifact.run_id == item.id).order_by(ReportArtifact.created_at.asc())
            )
        ).all()
    )
    deliveries = list(
        (
            await db.scalars(
                select(ReportDelivery).where(ReportDelivery.run_id == item.id).order_by(ReportDelivery.created_at.asc())
            )
        ).all()
    )
    return ScheduleRunOut(
        id=item.id,
        schedule_id=item.schedule_id,
        report_id=item.report_id,
        report_version_id=item.report_version_id,
        requested_by_user_id=item.requested_by_user_id,
        trigger_type=item.trigger_type,
        status=item.status,
        queued_at=item.queued_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        next_retry_at=item.next_retry_at,
        retry_count=item.retry_count,
        max_retries=item.max_retries,
        retry_backoff_seconds=item.retry_backoff_seconds,
        final_sql=item.final_sql,
        chart_type=item.chart_type,
        chart_spec_json=item.chart_spec_json,
        semantic_snapshot_json=item.semantic_snapshot_json,
        result_snapshot=item.result_snapshot,
        execution_fingerprint=item.execution_fingerprint,
        explain_plan_json=item.explain_plan_json,
        explain_cost=float(item.explain_cost or 0),
        validator_summary_json=item.validator_summary_json,
        structured_error_json=item.structured_error_json,
        stack_trace=item.stack_trace,
        attempts_json=item.attempts_json,
        artifact_summary_json=item.artifact_summary_json,
        delivery_summary_json=item.delivery_summary_json,
        rows_returned=item.rows_returned,
        execution_ms=item.execution_ms,
        error_message=item.error_message,
        ran_at=item.ran_at,
        artifacts=[ReportArtifactOut.model_validate(row, from_attributes=True) for row in artifacts],
        deliveries=[ReportDeliveryOut.model_validate(row, from_attributes=True) for row in deliveries],
    )


async def schedule_to_out(db: AsyncSession, item: Schedule) -> ScheduleOut:
    report = await db.get(Report, item.report_id)
    recipients = list(
        (
            await db.scalars(
                select(ReportRecipient).where(ReportRecipient.report_id == item.report_id).order_by(ReportRecipient.added_at)
            )
        ).all()
    )
    recipient_out = [ReportRecipientOut.model_validate(row, from_attributes=True) for row in recipients]
    runs = list(
        (
            await db.scalars(
                select(ScheduleRun).where(ScheduleRun.schedule_id == item.id).order_by(ScheduleRun.ran_at.desc()).limit(10)
            )
        ).all()
    )
    return ScheduleOut(
        id=item.id,
        report_id=item.report_id,
        report_title=report.title if report else "Отчёт",
        frequency=item.frequency,
        run_at_time=item.run_at_time,
        day_of_week=item.day_of_week,
        day_of_month=item.day_of_month,
        next_run_at=item.next_run_at,
        last_run_at=item.last_run_at,
        max_retries=item.max_retries,
        retry_backoff_seconds=item.retry_backoff_seconds,
        last_error_message=item.last_error_message,
        last_error_at=item.last_error_at,
        is_active=item.is_active,
        recipients=[row.destination or row.email or "" for row in recipients if (row.destination or row.email)],
        delivery_targets=recipient_out,
        runs=[await run_to_out(db, row) for row in runs],
    )


async def report_to_out(db: AsyncSession, item: Report, include_detail: bool = True) -> ReportOut:
    recipients = list((await db.scalars(select(ReportRecipient).where(ReportRecipient.report_id == item.id))).all())
    versions = []
    schedules = []
    latest_runs: list[ScheduleRun] = []
    if include_detail:
        versions = list(
            (
                await db.scalars(
                    select(ReportVersion).where(ReportVersion.report_id == item.id).order_by(ReportVersion.version_number.desc())
                )
            ).all()
        )
        schedule_rows = list(
            (
                await db.scalars(
                    select(Schedule).where(Schedule.report_id == item.id).order_by(Schedule.created_at.desc())
                )
            ).all()
        )
        schedules = [await schedule_to_out(db, row) for row in schedule_rows]
        latest_runs = await list_report_runs(db, report_id=item.id, limit=10)
    first_schedule = schedules[0] if schedules else None
    return ReportOut(
        id=item.id,
        title=item.title,
        natural_text=item.natural_text,
        generated_sql=item.generated_sql,
        chart_type=item.chart_type,
        chart_spec=item.chart_spec,
        semantic_snapshot_json=item.semantic_snapshot_json,
        result_snapshot=item.result_snapshot,
        config_json=item.config_json,
        is_active=item.is_active,
        latest_version_number=item.latest_version_number,
        last_run_at=item.last_run_at,
        last_run_status=item.last_run_status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        recipients=[row.destination or row.email or "" for row in recipients if (row.destination or row.email)],
        delivery_targets=[ReportRecipientOut.model_validate(row, from_attributes=True) for row in recipients],
        schedules=schedules,
        versions=[ReportVersionOut.model_validate(row, from_attributes=True) for row in versions],
        latest_runs=[await run_to_out(db, row) for row in latest_runs],
        question=item.natural_text,
        sql_text=item.generated_sql,
        result=item.result_snapshot,
        schedule=first_schedule.model_dump(mode="json") if first_schedule else {},
    )



__all__ = [name for name in globals() if not name.startswith("__")]
