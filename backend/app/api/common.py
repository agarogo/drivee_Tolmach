from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Chat,
    Message,
    Query,
    QueryClarification,
    QueryEvent,
    Report,
    ReportRecipient,
    ReportVersion,
    Schedule,
    ScheduleRun,
    SqlGuardrailLog,
    User,
)
from app.schemas import ClarificationOut, ChatOut, GuardrailLogOut, QueryEventOut, QueryOut, ReportOut, ReportVersionOut, ScheduleOut, ScheduleRunOut, UserOut


def utcnow_naive() -> datetime:
    return datetime.utcnow()


def to_user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


def make_chat_title(question: str) -> str:
    compact = " ".join(question.strip().split())
    if len(compact) <= 30:
        return compact
    return compact[:29].rstrip() + "..."


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


def next_run_at(frequency: str, run_at: time | None, day_of_week: int | None, day_of_month: int | None) -> datetime:
    now = datetime.utcnow()
    target_time = run_at or time(9, 0)
    candidate = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
    if frequency == "daily":
        return candidate if candidate > now else candidate + timedelta(days=1)
    if frequency == "weekly":
        target_dow = day_of_week or 1
        days = (target_dow - now.isoweekday()) % 7
        candidate = candidate + timedelta(days=days)
        return candidate if candidate > now else candidate + timedelta(days=7)
    target_day = min(day_of_month or 1, 28)
    candidate = candidate.replace(day=target_day)
    if candidate <= now:
        candidate = (candidate.replace(day=1) + timedelta(days=32)).replace(day=target_day)
    return candidate


def parse_run_time(value: Any) -> time:
    if isinstance(value, time):
        return value
    if isinstance(value, str) and value:
        parts = value.split(":")
        return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    return time(9, 0)


async def query_to_out(db: AsyncSession, item: Query) -> QueryOut:
    events = list((await db.scalars(select(QueryEvent).where(QueryEvent.query_id == item.id).order_by(QueryEvent.started_at.asc()))).all())
    guardrails = list((await db.scalars(select(SqlGuardrailLog).where(SqlGuardrailLog.query_id == item.id))).all())
    clarifications = list((await db.scalars(select(QueryClarification).where(QueryClarification.query_id == item.id).order_by(QueryClarification.created_at.asc()))).all())
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


async def schedule_to_out(db: AsyncSession, item: Schedule) -> ScheduleOut:
    report = await db.get(Report, item.report_id)
    recipients = list((await db.scalars(select(ReportRecipient).where(ReportRecipient.report_id == item.report_id).order_by(ReportRecipient.added_at))).all())
    runs = list((await db.scalars(select(ScheduleRun).where(ScheduleRun.schedule_id == item.id).order_by(ScheduleRun.ran_at.desc()).limit(10))).all())
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
        is_active=item.is_active,
        recipients=[row.email for row in recipients],
        runs=[ScheduleRunOut.model_validate(row, from_attributes=True) for row in runs],
    )


async def report_to_out(db: AsyncSession, item: Report, include_detail: bool = True) -> ReportOut:
    recipients = list((await db.scalars(select(ReportRecipient).where(ReportRecipient.report_id == item.id))).all())
    versions = []
    schedules = []
    if include_detail:
        versions = list((await db.scalars(select(ReportVersion).where(ReportVersion.report_id == item.id).order_by(ReportVersion.version_number.desc()))).all())
        schedule_rows = list((await db.scalars(select(Schedule).where(Schedule.report_id == item.id).order_by(Schedule.created_at.desc()))).all())
        schedules = [await schedule_to_out(db, row) for row in schedule_rows]
    first_schedule = schedules[0] if schedules else None
    return ReportOut(
        id=item.id,
        title=item.title,
        natural_text=item.natural_text,
        generated_sql=item.generated_sql,
        chart_type=item.chart_type,
        chart_spec=item.chart_spec,
        result_snapshot=item.result_snapshot,
        config_json=item.config_json,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
        recipients=[row.email for row in recipients],
        schedules=schedules,
        versions=[ReportVersionOut.model_validate(row, from_attributes=True) for row in versions],
        question=item.natural_text,
        sql_text=item.generated_sql,
        result=item.result_snapshot,
        schedule=first_schedule.model_dump(mode="json") if first_schedule else {},
    )
