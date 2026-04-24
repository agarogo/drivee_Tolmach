from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Report, Schedule, User


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
