from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Query, Report, ReportRecipient, ReportVersion, ScheduleRun

settings = get_settings()


def utcnow() -> datetime:
    return datetime.utcnow()


def build_semantic_snapshot_from_query(query: Query | None) -> dict[str, Any]:
    if query is None:
        return {}
    return {
        "query_id": str(query.id),
        "interpretation": dict(query.interpretation_json or {}),
        "resolved_request": dict(query.resolved_request_json or {}),
        "semantic_terms": list(query.semantic_terms_json or []),
        "sql_plan": dict(query.sql_plan_json or {}),
    }


def normalize_delivery_targets(
    recipients: list[str] | None,
    delivery_targets: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for email in recipients or []:
        value = email.strip().lower()
        if not value:
            continue
        key = ("email", value)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "channel": "email",
                "destination": value,
                "config_json": {},
                "is_active": True,
            }
        )
    for item in delivery_targets or []:
        channel = str(item.get("channel", "email")).strip().lower() or "email"
        destination = str(item.get("destination", "")).strip()
        if not destination:
            continue
        key = (channel, destination.lower())
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "channel": channel,
                "destination": destination,
                "config_json": dict(item.get("config_json") or {}),
                "is_active": bool(item.get("is_active", True)),
            }
        )
    return normalized


async def replace_report_recipients(
    db: AsyncSession,
    *,
    report: Report,
    recipients: list[str] | None = None,
    delivery_targets: list[dict[str, Any]] | None = None,
) -> list[ReportRecipient]:
    targets = normalize_delivery_targets(recipients, delivery_targets)
    existing = list((await db.scalars(select(ReportRecipient).where(ReportRecipient.report_id == report.id))).all())
    for row in existing:
        await db.delete(row)
    await db.flush()

    created: list[ReportRecipient] = []
    for item in targets:
        destination = item["destination"]
        recipient = ReportRecipient(
            report_id=report.id,
            email=destination if item["channel"] == "email" else None,
            channel=item["channel"],
            destination=destination,
            config_json=item["config_json"],
            is_active=item["is_active"],
        )
        db.add(recipient)
        created.append(recipient)
    await db.flush()
    return created


async def append_report_recipients(
    db: AsyncSession,
    *,
    report: Report,
    recipients: list[str] | None = None,
    delivery_targets: list[dict[str, Any]] | None = None,
) -> list[ReportRecipient]:
    requested = normalize_delivery_targets(recipients, delivery_targets)
    existing = list((await db.scalars(select(ReportRecipient).where(ReportRecipient.report_id == report.id))).all())
    existing_keys = {
        (row.channel.strip().lower(), (row.destination or row.email or "").strip().lower())
        for row in existing
    }
    created: list[ReportRecipient] = []
    for item in requested:
        key = (item["channel"], item["destination"].lower())
        if key in existing_keys:
            continue
        recipient = ReportRecipient(
            report_id=report.id,
            email=item["destination"] if item["channel"] == "email" else None,
            channel=item["channel"],
            destination=item["destination"],
            config_json=item["config_json"],
            is_active=item["is_active"],
        )
        db.add(recipient)
        created.append(recipient)
    await db.flush()
    return created


async def create_report_version(
    db: AsyncSession,
    *,
    report: Report,
    created_by,
) -> ReportVersion:
    next_version = int((await db.scalar(select(func.max(ReportVersion.version_number)).where(ReportVersion.report_id == report.id))) or 0) + 1
    version = ReportVersion(
        report_id=report.id,
        version_number=next_version,
        generated_sql=report.generated_sql,
        chart_type=report.chart_type,
        chart_spec_json=report.chart_spec,
        semantic_snapshot_json=report.semantic_snapshot_json,
        config_json=report.config_json,
        created_by=created_by,
    )
    report.latest_version_number = next_version
    db.add(version)
    await db.flush()
    return version


async def latest_report_version(db: AsyncSession, report_id) -> ReportVersion | None:
    return await db.scalar(
        select(ReportVersion)
        .where(ReportVersion.report_id == report_id)
        .order_by(ReportVersion.version_number.desc())
        .limit(1)
    )


async def create_run_record(
    db: AsyncSession,
    *,
    report: Report,
    schedule_id=None,
    trigger_type: str,
    requested_by_user_id=None,
    max_retries: int = 0,
    retry_backoff_seconds: int = 0,
) -> ScheduleRun:
    version = await latest_report_version(db, report.id)
    run = ScheduleRun(
        schedule_id=schedule_id,
        report_id=report.id,
        report_version_id=version.id if version else None,
        requested_by_user_id=requested_by_user_id,
        trigger_type=trigger_type,
        status="queued",
        queued_at=utcnow(),
        next_retry_at=utcnow(),
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        final_sql=(version.generated_sql if version else report.generated_sql) or report.generated_sql,
        chart_type=(version.chart_type if version else report.chart_type) or report.chart_type,
        chart_spec_json=(version.chart_spec_json if version else report.chart_spec) or report.chart_spec,
        semantic_snapshot_json=(version.semantic_snapshot_json if version else report.semantic_snapshot_json) or report.semantic_snapshot_json,
        ran_at=utcnow(),
    )
    db.add(run)
    await db.flush()
    return run


async def clear_report_runs_for_tests(db: AsyncSession) -> None:
    await db.execute(delete(ScheduleRun))
    await db.flush()
