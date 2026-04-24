from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import ProgrammingError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import WorkerHeartbeat
from app.reports.service import utcnow

settings = get_settings()


def _missing_worker_heartbeat_table(exc: ProgrammingError) -> bool:
    message = str(exc).lower()
    return "worker_heartbeats" in message and (
        "does not exist" in message or "undefinedtableerror" in message
    )


def scheduler_worker_name() -> str:
    return os.getenv("SCHEDULER_WORKER_NAME", "scheduler-worker")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def heartbeat_is_fresh(last_seen_at: datetime | None) -> bool:
    if last_seen_at is None:
        return False
    age_seconds = (_as_utc(utcnow()) - _as_utc(last_seen_at)).total_seconds()
    return age_seconds <= settings.scheduler_worker_stale_after_seconds


async def record_worker_heartbeat(
    db: AsyncSession,
    *,
    worker_name: str,
    worker_type: str = "scheduler",
    status: str,
    metadata: dict[str, Any] | None = None,
) -> WorkerHeartbeat | None:
    try:
        heartbeat = await db.scalar(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_name == worker_name))
    except ProgrammingError as exc:
        if not _missing_worker_heartbeat_table(exc):
            raise
        await db.rollback()
        return None
    if heartbeat is None:
        heartbeat = WorkerHeartbeat(worker_name=worker_name, worker_type=worker_type)
        db.add(heartbeat)
        await db.flush()

    heartbeat.worker_type = worker_type
    heartbeat.status = status
    heartbeat.hostname = socket.gethostname()
    heartbeat.process_id = os.getpid()
    heartbeat.last_seen_at = utcnow()
    heartbeat.metadata_json = metadata or {}
    await db.flush()
    return heartbeat


async def get_worker_heartbeat(db: AsyncSession, worker_name: str) -> WorkerHeartbeat | None:
    try:
        return await db.scalar(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_name == worker_name))
    except ProgrammingError as exc:
        if not _missing_worker_heartbeat_table(exc):
            raise
        await db.rollback()
        return None
