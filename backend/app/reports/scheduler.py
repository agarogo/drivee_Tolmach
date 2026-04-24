from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import PlatformSessionLocal
from app.models import Report, ReportArtifact, ReportDelivery, ReportRecipient, ReportVersion, Schedule, ScheduleRun, User
from app.reports.artifacts import BuiltArtifact, build_report_artifacts
from app.reports.delivery import DeliveryPayload, get_delivery_adapter
from app.reports.errors import ReportRuntimeError, ReportValidationError
from app.reports.service import create_run_record, utcnow
from app.reports.worker_runtime import (
    get_worker_heartbeat,
    heartbeat_is_fresh,
    record_worker_heartbeat,
    scheduler_worker_name,
)
from app.services.guardrails import validate_sql
from app.services.query_runner import execute_validated_query

settings = get_settings()
logger = logging.getLogger(__name__)

ACTIVE_RUN_STATUSES = {"queued", "running"}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "delivery_failed"}


def next_run_at(frequency: str, run_at: time | None, day_of_week: int | None, day_of_month: int | None) -> datetime:
    now = utcnow()
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
        hours, minutes, *_ = value.split(":")
        return time(int(hours), int(minutes) if minutes else 0)
    return time(9, 0)


def report_summary_from_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Query returned no rows."
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return f"Query returned {len(rows)} rows across {len(columns)} columns."


def _structured_error(exc: Exception) -> tuple[dict[str, Any], str, bool]:
    if isinstance(exc, ReportRuntimeError):
        return exc.as_dict(), traceback.format_exc(), exc.retryable
    return (
        {
            "code": "unexpected_report_error",
            "message": str(exc),
            "retryable": True,
            "details": {"exception_type": exc.__class__.__name__},
        },
        traceback.format_exc(),
        True,
    )


def _append_attempt(run: ScheduleRun, *, status: str, message: str, details: dict[str, Any] | None = None) -> None:
    attempts = list(run.attempts_json or [])
    attempts.append(
        {
            "attempt_number": len(attempts) + 1,
            "status": status,
            "message": message,
            "timestamp": utcnow().isoformat(),
            "details": details or {},
        }
    )
    run.attempts_json = attempts


async def _persist_artifacts(
    db: AsyncSession,
    *,
    report: Report,
    run: ScheduleRun,
    built_artifacts: list[BuiltArtifact],
) -> list[ReportArtifact]:
    artifacts: list[ReportArtifact] = []
    for item in built_artifacts:
        artifact = ReportArtifact(
            report_id=report.id,
            run_id=run.id,
            artifact_type=item.artifact_type,
            file_name=item.file_name,
            file_path=item.file_path,
            content_type=item.content_type,
            file_size_bytes=item.file_size_bytes,
            checksum_sha256=item.checksum_sha256,
            metadata_json=item.metadata_json,
        )
        db.add(artifact)
        artifacts.append(artifact)
    await db.flush()
    run.artifact_summary_json = [item.as_dict() for item in built_artifacts]
    return artifacts


async def _deliver_to_targets(
    db: AsyncSession,
    *,
    report: Report,
    run: ScheduleRun,
    recipients: list[ReportRecipient],
    artifacts: list[BuiltArtifact],
    summary_text: str,
) -> tuple[list[ReportDelivery], bool]:
    deliveries: list[ReportDelivery] = []
    any_failure = False
    for recipient in recipients:
        destination = (recipient.destination or recipient.email or "").strip()
        if not recipient.is_active or not destination:
            continue
        delivery = ReportDelivery(
            report_id=report.id,
            run_id=run.id,
            recipient_id=recipient.id,
            channel=recipient.channel,
            destination=destination,
            status="running",
            attempt_count=1,
        )
        db.add(delivery)
        await db.flush()
        payload = DeliveryPayload(
            report_title=report.title,
            destination=destination,
            channel=recipient.channel,
            run_status=run.status,
            rows_returned=run.rows_returned,
            execution_ms=run.execution_ms,
            artifacts=artifacts,
            summary_text=summary_text,
        )
        adapter = None
        try:
            adapter = get_delivery_adapter(recipient.channel)
            result = await adapter.send(payload)
            delivery.adapter_key = result.adapter_key
            delivery.external_message_id = result.external_message_id
            delivery.details_json = result.details
            delivery.status = "sent"
            delivery.sent_at = utcnow()
            recipient.last_sent_at = utcnow()
        except Exception as exc:
            structured, stack_trace, _ = _structured_error(exc)
            any_failure = True
            delivery.adapter_key = getattr(adapter, "adapter_key", recipient.channel)
            delivery.status = "failed"
            delivery.error_message = structured["message"]
            delivery.structured_error_json = structured
            delivery.stack_trace = stack_trace
            delivery.details_json = structured.get("details", {})
        deliveries.append(delivery)
    await db.flush()
    run.delivery_summary_json = [
        {
            "id": str(item.id),
            "channel": item.channel,
            "destination": item.destination,
            "status": item.status,
            "attempt_count": item.attempt_count,
            "error_message": item.error_message,
        }
        for item in deliveries
    ]
    return deliveries, any_failure


async def execute_report_run(db: AsyncSession, run_id: UUID) -> ScheduleRun:
    run = await db.get(ScheduleRun, run_id)
    if not run:
        raise ReportValidationError("Report run was not found.")

    report = await db.get(Report, run.report_id)
    if not report:
        raise ReportValidationError("Report was not found.")

    owner = await db.get(User, report.user_id)
    if not owner:
        raise ReportValidationError("Report owner was not found.")

    schedule = await db.get(Schedule, run.schedule_id) if run.schedule_id else None
    version = await db.get(ReportVersion, run.report_version_id) if run.report_version_id else None
    recipients = list(
        (
            await db.scalars(
                select(ReportRecipient).where(
                    ReportRecipient.report_id == report.id,
                    ReportRecipient.is_active.is_(True),
                )
            )
        ).all()
    )

    sql_text = (run.final_sql or (version.generated_sql if version else "") or report.generated_sql).strip()
    run.status = "running"
    run.started_at = utcnow()
    run.error_message = ""
    run.stack_trace = ""
    run.structured_error_json = {}
    await db.flush()

    try:
        validation = await validate_sql(db, sql_text, role=owner.role, query_id=report.query_id)
        if not validation.ok or not validation.validated_sql:
            raise ReportValidationError(
                validation.message,
                details={"logs": validation.logs, "block_reasons": validation.block_reasons},
            )

        execution = await execute_validated_query(
            validation.validated_sql,
            role=owner.role,
            db=db,
            query_id=report.query_id,
            use_cache=True,
        )
        snapshot_rows = execution.rows[: settings.report_result_snapshot_limit]
        semantic_snapshot = dict(run.semantic_snapshot_json or report.semantic_snapshot_json or {})
        chart_type = run.chart_type or report.chart_type
        summary_text = report_summary_from_rows(execution.rows)
        built_artifacts = build_report_artifacts(
            report_id=str(report.id),
            run_id=str(run.id),
            title=report.title,
            rows=execution.rows,
            chart_type=chart_type,
            semantic_snapshot=semantic_snapshot,
        )
        await _persist_artifacts(db, report=report, run=run, built_artifacts=built_artifacts)

        run.final_sql = validation.validated_sql.sql
        run.execution_fingerprint = execution.fingerprint
        run.explain_plan_json = validation.validated_sql.explain_plan
        run.explain_cost = validation.validated_sql.explain_cost
        run.validator_summary_json = validation.validated_sql.validator_summary
        run.rows_returned = execution.row_count
        run.execution_ms = execution.execution_ms
        run.result_snapshot = snapshot_rows
        run.finished_at = utcnow()
        run.ran_at = run.finished_at
        run.status = "succeeded"
        _append_attempt(
            run,
            status="succeeded",
            message="Report SQL validated and executed successfully.",
            details={"row_count": execution.row_count, "execution_ms": execution.execution_ms},
        )

        report.result_snapshot = snapshot_rows
        report.last_run_at = run.finished_at
        report.last_run_status = "succeeded"
        report.updated_at = utcnow()

        if schedule:
            schedule.last_run_at = run.finished_at
            schedule.last_error_message = ""
            schedule.last_error_at = None

        deliveries, any_delivery_failure = await _deliver_to_targets(
            db,
            report=report,
            run=run,
            recipients=recipients,
            artifacts=built_artifacts,
            summary_text=summary_text,
        )
        if any_delivery_failure:
            run.status = "delivery_failed"
            report.last_run_status = "delivery_failed"
            if schedule:
                schedule.last_error_message = "One or more report deliveries failed."
                schedule.last_error_at = utcnow()

        await db.flush()
        return run

    except Exception as exc:
        structured, stack_trace, retryable = _structured_error(exc)
        run.error_message = structured["message"]
        run.structured_error_json = structured
        run.stack_trace = stack_trace
        run.finished_at = utcnow()
        run.ran_at = run.finished_at
        _append_attempt(run, status="failed", message=structured["message"], details=structured)

        should_retry = retryable and run.retry_count < run.max_retries
        if should_retry:
            run.retry_count += 1
            multiplier = max(1, 2 ** max(0, run.retry_count - 1))
            run.next_retry_at = utcnow() + timedelta(seconds=max(30, run.retry_backoff_seconds) * multiplier)
            run.status = "queued"
            run.finished_at = None
        else:
            run.status = "failed"

        report.last_run_at = utcnow()
        report.last_run_status = run.status
        if schedule:
            schedule.last_error_message = run.error_message
            schedule.last_error_at = utcnow()
        await db.flush()
        return run


async def enqueue_due_schedules(db: AsyncSession, limit: int | None = None) -> list[ScheduleRun]:
    batch_size = max(1, limit or settings.scheduler_batch_size)
    now = utcnow()
    stmt = (
        select(Schedule)
        .options(selectinload(Schedule.report))
        .where(
            Schedule.is_active.is_(True),
            Schedule.next_run_at.is_not(None),
            Schedule.next_run_at <= now,
        )
        .order_by(Schedule.next_run_at.asc())
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    )
    schedules = list((await db.scalars(stmt)).all())
    created: list[ScheduleRun] = []
    for schedule in schedules:
        active_count = int(
            await db.scalar(
                select(func.count(ScheduleRun.id)).where(
                    ScheduleRun.schedule_id == schedule.id,
                    ScheduleRun.status.in_(tuple(ACTIVE_RUN_STATUSES)),
                )
            )
            or 0
        )
        if active_count:
            continue
        report = schedule.report or await db.get(Report, schedule.report_id)
        if not report:
            continue
        run = await create_run_record(
            db,
            report=report,
            schedule_id=schedule.id,
            trigger_type="schedule",
            requested_by_user_id=None,
            max_retries=schedule.max_retries,
            retry_backoff_seconds=schedule.retry_backoff_seconds,
        )
        schedule.next_run_at = next_run_at(schedule.frequency, schedule.run_at_time, schedule.day_of_week, schedule.day_of_month)
        created.append(run)
    await db.flush()
    return created


async def claim_runnable_runs(db: AsyncSession, limit: int | None = None) -> list[UUID]:
    batch_size = max(1, min(limit or settings.scheduler_max_concurrent_runs, settings.scheduler_max_concurrent_runs))
    now = utcnow()
    stmt = (
        select(ScheduleRun)
        .where(
            ScheduleRun.status == "queued",
            or_(ScheduleRun.next_retry_at.is_(None), ScheduleRun.next_retry_at <= now),
        )
        .order_by(ScheduleRun.queued_at.asc(), ScheduleRun.ran_at.asc())
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    )
    runs = list((await db.scalars(stmt)).all())
    claimed_ids: list[UUID] = []
    for run in runs:
        run.status = "running"
        run.started_at = now
        claimed_ids.append(run.id)
    await db.flush()
    return claimed_ids


async def run_scheduler_cycle() -> dict[str, Any]:
    enqueued = 0
    processed = 0
    failed = 0
    async with PlatformSessionLocal() as db:
        queued_runs = await enqueue_due_schedules(db)
        claimed_ids = await claim_runnable_runs(db)
        enqueued = len(queued_runs)
        await db.commit()

    for run_id in claimed_ids:
        async with PlatformSessionLocal() as db:
            try:
                run = await execute_report_run(db, run_id)
                if run.status == "failed":
                    failed += 1
                processed += 1
                await db.commit()
            except Exception:
                logger.exception("scheduler failed to execute run %s", run_id)
                await db.rollback()
                failed += 1

    return {
        "enqueued": enqueued,
        "processed": processed,
        "failed": failed,
    }


async def _best_effort_worker_heartbeat(*, status: str, metadata: dict[str, Any] | None = None) -> None:
    try:
        async with PlatformSessionLocal() as db:
            await record_worker_heartbeat(
                db,
                worker_name=scheduler_worker_name(),
                status=status,
                metadata=metadata,
            )
            await db.commit()
    except Exception:
        logger.exception("failed to update scheduler worker heartbeat")


async def scheduler_loop() -> None:
    logger.info("scheduler worker started")
    await _best_effort_worker_heartbeat(status="starting", metadata={"phase": "boot"})
    while settings.scheduler_enabled:
        try:
            await _best_effort_worker_heartbeat(status="running", metadata={"phase": "poll"})
            cycle = await run_scheduler_cycle()
            logger.info("scheduler cycle completed: %s", cycle)
            await _best_effort_worker_heartbeat(
                status="sleeping",
                metadata={**cycle, "next_poll_seconds": max(1, settings.scheduler_poll_interval_seconds)},
            )
        except Exception:
            logger.exception("scheduler cycle failed")
            await _best_effort_worker_heartbeat(
                status="error",
                metadata={"next_poll_seconds": max(1, settings.scheduler_poll_interval_seconds)},
            )
        await asyncio.sleep(max(1, settings.scheduler_poll_interval_seconds))


async def get_scheduler_summary(db: AsyncSession) -> dict[str, Any]:
    now = utcnow()
    succeeded_after = now - timedelta(hours=24)
    heartbeat = await get_worker_heartbeat(db, scheduler_worker_name())
    return {
        "worker_enabled": settings.scheduler_enabled,
        "worker_name": scheduler_worker_name(),
        "worker_alive": heartbeat_is_fresh(heartbeat.last_seen_at if heartbeat else None),
        "worker_status": heartbeat.status if heartbeat else "missing",
        "worker_last_seen_at": heartbeat.last_seen_at if heartbeat else None,
        "worker_hostname": heartbeat.hostname if heartbeat else "",
        "worker_process_id": heartbeat.process_id if heartbeat else 0,
        "worker_metadata": dict(heartbeat.metadata_json or {}) if heartbeat else {},
        "queued_runs": int(await db.scalar(select(func.count(ScheduleRun.id)).where(ScheduleRun.status == "queued")) or 0),
        "running_runs": int(await db.scalar(select(func.count(ScheduleRun.id)).where(ScheduleRun.status == "running")) or 0),
        "failed_runs": int(await db.scalar(select(func.count(ScheduleRun.id)).where(ScheduleRun.status == "failed")) or 0),
        "succeeded_runs_24h": int(
            await db.scalar(
                select(func.count(ScheduleRun.id)).where(
                    ScheduleRun.status.in_(("succeeded", "delivery_failed")),
                    ScheduleRun.ran_at >= succeeded_after,
                )
            )
            or 0
        ),
        "due_schedules": int(
            await db.scalar(
                select(func.count(Schedule.id)).where(
                    Schedule.is_active.is_(True),
                    Schedule.next_run_at.is_not(None),
                    Schedule.next_run_at <= now,
                )
            )
            or 0
        ),
        "retrying_runs": int(
            await db.scalar(
                select(func.count(ScheduleRun.id)).where(
                    ScheduleRun.status == "queued",
                    ScheduleRun.retry_count > 0,
                )
            )
            or 0
        ),
    }


async def list_report_runs(
    db: AsyncSession,
    *,
    report_id: UUID | None = None,
    schedule_id: UUID | None = None,
    limit: int = 50,
) -> list[ScheduleRun]:
    stmt = select(ScheduleRun).order_by(ScheduleRun.queued_at.desc()).limit(max(1, min(limit, 200)))
    if report_id is not None:
        stmt = stmt.where(ScheduleRun.report_id == report_id)
    if schedule_id is not None:
        stmt = stmt.where(ScheduleRun.schedule_id == schedule_id)
    return list((await db.scalars(stmt)).all())
