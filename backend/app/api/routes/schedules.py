from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import next_run_at, require_owned_report, schedule_to_out
from app.auth import get_current_user
from app.db import get_db
from app.models import Report, ReportRecipient, Schedule, User
from app.schemas import ScheduleCreate, ScheduleOut, SchedulePatch

router = APIRouter()


@router.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[ScheduleOut]:
    rows = list((await db.scalars(select(Schedule).join(Report, Report.id == Schedule.report_id).where(Report.user_id == user.id).order_by(Schedule.next_run_at.asc().nullslast()))).all())
    return [await schedule_to_out(db, row) for row in rows]


@router.post("/schedules", response_model=ScheduleOut)
async def create_schedule(
    payload: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleOut:
    report = await require_owned_report(db, payload.report_id, user)
    item = Schedule(
        report_id=report.id,
        frequency=payload.frequency,
        run_at_time=payload.run_at_time,
        day_of_week=payload.day_of_week,
        day_of_month=payload.day_of_month,
        is_active=payload.is_active,
    )
    item.next_run_at = next_run_at(item.frequency, item.run_at_time, item.day_of_week, item.day_of_month)
    db.add(item)
    for email in payload.recipients:
        db.add(ReportRecipient(report_id=report.id, email=email))
    await db.commit()
    await db.refresh(item)
    return await schedule_to_out(db, item)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
async def patch_schedule(
    schedule_id: UUID,
    payload: SchedulePatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleOut:
    item = await db.get(Schedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    report = await require_owned_report(db, item.report_id, user)
    data = payload.model_dump(exclude_unset=True)
    recipients = data.pop("recipients", None)
    for key, value in data.items():
        setattr(item, key, value)
    item.next_run_at = next_run_at(item.frequency, item.run_at_time, item.day_of_week, item.day_of_month)
    if recipients is not None:
        for email in recipients:
            db.add(ReportRecipient(report_id=report.id, email=email))
    await db.commit()
    await db.refresh(item)
    return await schedule_to_out(db, item)


@router.post("/schedules/{schedule_id}/toggle", response_model=ScheduleOut)
async def toggle_schedule(schedule_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> ScheduleOut:
    item = await db.get(Schedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    await require_owned_report(db, item.report_id, user)
    item.is_active = not item.is_active
    item.next_run_at = next_run_at(item.frequency, item.run_at_time, item.day_of_week, item.day_of_month) if item.is_active else None
    await db.commit()
    await db.refresh(item)
    return await schedule_to_out(db, item)
