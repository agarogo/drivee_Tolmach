from __future__ import annotations

import os
import socket
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import WorkerHeartbeat
from app.reports.service import utcnow

settings = get_settings()


def scheduler_worker_name() -> str:
    return os.getenv("SCHEDULER_WORKER_NAME", "scheduler-worker")


def heartbeat_is_fresh(last_seen_at: datetime | None) -> bool:
    if last_seen_at is None:
        return False
    age_seconds = (utcnow() - last_seen_at).total_seconds()
    return age_seconds <= settings.scheduler_worker_stale_after_seconds


async def record_worker_heartbeat(
    db: AsyncSession,
    *,
    worker_name: str,
    worker_type: str = "scheduler",
    status: str,
    metadata: dict[str, Any] | None = None,
) -> WorkerHeartbeat:
    heartbeat = await db.scalar(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_name == worker_name))
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
    return await db.scalar(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_name == worker_name))
