from __future__ import annotations

from datetime import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query as ApiQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.utils import run_to_out, schedule_to_out
from app.models import Report, Schedule, User
from app.reports import append_report_recipients, create_run_record, execute_report_run, list_report_runs, next_run_at, replace_report_recipients
from app.repositories.reports import require_owned_report, require_owned_schedule
from app.schemas import ScheduleCreate, ScheduleOut, SchedulePatch, ScheduleRunOut


router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[ScheduleOut]:
    rows = list(
        (
            await db.scalars(
                select(Schedule)
                .join(Report, Report.id == Schedule.report_id)
                .where(Report.user_id == user.id)
                .order_by(Schedule.next_run_at.asc().nullslast())
            )
        ).all()
    )
    return [await schedule_to_out(db, row) for row in rows]


@router.post("", response_model=ScheduleOut)
async def create_schedule(
    payload: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleOut:
    report = await require_owned_report(db, payload.report_id, user)
    item = Schedule(
        report_id=report.id,
        frequency=payload.frequency,
        run_at_time=payload.run_at_time or time(9, 0),
        day_of_week=payload.day_of_week,
        day_of_month=payload.day_of_month,
        max_retries=payload.max_retries,
        retry_backoff_seconds=payload.retry_backoff_seconds,
        is_active=payload.is_active,
    )
    item.next_run_at = next_run_at(item.frequency, item.run_at_time, item.day_of_week, item.day_of_month)
    db.add(item)
    await append_report_recipients(
        db,
        report=report,
        recipients=payload.recipients,
        delivery_targets=[target.model_dump() for target in payload.delivery_targets],
    )
    await db.commit()
    await db.refresh(item)
    return await schedule_to_out(db, item)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def patch_schedule(
    schedule_id: UUID,
    payload: SchedulePatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleOut:
    item = await require_owned_schedule(db, schedule_id, user)
    if not item:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    report = await require_owned_report(db, item.report_id, user)
    data = payload.model_dump(exclude_unset=True)
    recipients = data.pop("recipients", None)
    delivery_targets = data.pop("delivery_targets", None)
    for key, value in data.items():
        setattr(item, key, value)
    item.next_run_at = next_run_at(item.frequency, item.run_at_time, item.day_of_week, item.day_of_month)
    if recipients is not None or delivery_targets is not None:
        await replace_report_recipients(
            db,
            report=report,
            recipients=recipients,
            delivery_targets=[target.model_dump() if hasattr(target, "model_dump") else target for target in (delivery_targets or [])],
        )
    await db.commit()
    await db.refresh(item)
    return await schedule_to_out(db, item)


@router.post("/{schedule_id}/toggle", response_model=ScheduleOut)
async def toggle_schedule(schedule_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> ScheduleOut:
    item = await require_owned_schedule(db, schedule_id, user)
    if not item:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    await require_owned_report(db, item.report_id, user)
    item.is_active = not item.is_active
    item.next_run_at = next_run_at(item.frequency, item.run_at_time, item.day_of_week, item.day_of_month) if item.is_active else None
    await db.commit()
    await db.refresh(item)
    return await schedule_to_out(db, item)


@router.post("/{schedule_id}/run-now", response_model=ScheduleRunOut)
async def run_schedule_now(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleRunOut:
    item = await require_owned_schedule(db, schedule_id, user)
    report = await require_owned_report(db, item.report_id, user)
    run = await create_run_record(
        db,
        report=report,
        schedule_id=item.id,
        trigger_type="schedule_manual",
        requested_by_user_id=user.id,
        max_retries=item.max_retries,
        retry_backoff_seconds=item.retry_backoff_seconds,
    )
    run = await execute_report_run(db, run.id)
    await db.commit()
    return await run_to_out(db, run)


@router.get("/{schedule_id}/history", response_model=list[ScheduleRunOut])
async def schedule_history(
    schedule_id: UUID,
    limit: int = ApiQuery(default=30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ScheduleRunOut]:
    item = await require_owned_schedule(db, schedule_id, user)
    rows = await list_report_runs(db, schedule_id=item.id, limit=limit)
    return [await run_to_out(db, row) for row in rows]
