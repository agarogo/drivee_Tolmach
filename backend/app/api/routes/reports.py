from datetime import datetime, time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import next_run_at, parse_run_time, report_to_out, require_owned_query, require_owned_report
from app.auth import get_current_user
from app.db import get_db
from app.models import Report, ReportRecipient, ReportVersion, Schedule, ScheduleRun, User
from app.schemas import ReportCreate, ReportOut, ReportPatch, ScheduleRequest
from app.services.guardrails import validate_sql
from app.services.query_runner import execute_validated_query

router = APIRouter()


@router.post("/reports", response_model=ReportOut)
@router.post("/api/reports", response_model=ReportOut)
async def create_report(
    payload: ReportCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    query = await require_owned_query(db, payload.query_id, user) if payload.query_id else None
    natural_text = payload.natural_text or payload.question or (query.natural_text if query else "")
    generated_sql = payload.generated_sql or payload.sql_text or ((query.corrected_sql or query.generated_sql) if query else "")
    chart_spec = payload.chart_spec or (query.chart_spec if query else {})
    result_snapshot = payload.result_snapshot or payload.result or (query.result_snapshot if query else [])
    chart_type = payload.chart_type or (query.chart_type if query else "table_only")
    item = Report(
        user_id=user.id,
        query_id=query.id if query else None,
        title=payload.title,
        natural_text=natural_text,
        generated_sql=generated_sql,
        chart_type=chart_type,
        chart_spec=chart_spec,
        result_snapshot=result_snapshot,
        config_json=payload.config_json,
    )
    db.add(item)
    await db.flush()
    db.add(
        ReportVersion(
            report_id=item.id,
            version_number=1,
            generated_sql=generated_sql,
            chart_type=chart_type,
            config_json=payload.config_json,
            created_by=user.id,
        )
    )
    for email in payload.recipients:
        db.add(ReportRecipient(report_id=item.id, email=email))
    if payload.schedule:
        schedule = Schedule(
            report_id=item.id,
            frequency=payload.schedule.get("frequency", "weekly"),
            run_at_time=parse_run_time(payload.schedule.get("run_at_time")),
            day_of_week=payload.schedule.get("day_of_week") or 1,
            day_of_month=payload.schedule.get("day_of_month"),
            is_active=payload.schedule.get("is_active", True),
        )
        schedule.next_run_at = next_run_at(schedule.frequency, schedule.run_at_time, schedule.day_of_week, schedule.day_of_month)
        db.add(schedule)
    await db.commit()
    await db.refresh(item)
    return await report_to_out(db, item)


@router.get("/reports", response_model=list[ReportOut])
@router.get("/api/reports", response_model=list[ReportOut])
async def list_reports(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[ReportOut]:
    rows = list((await db.scalars(select(Report).where(Report.user_id == user.id).order_by(Report.updated_at.desc()).limit(100))).all())
    return [await report_to_out(db, row, include_detail=False) for row in rows]


@router.get("/reports/{report_id}", response_model=ReportOut)
async def get_report(report_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> ReportOut:
    return await report_to_out(db, await require_owned_report(db, report_id, user))


@router.patch("/reports/{report_id}", response_model=ReportOut)
async def patch_report(
    report_id: UUID,
    payload: ReportPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    item = await require_owned_report(db, report_id, user)
    data = payload.model_dump(exclude_unset=True)
    version_needed = "generated_sql" in data or "chart_type" in data or "config_json" in data
    for key, value in data.items():
        setattr(item, key, value)
    item.updated_at = datetime.utcnow()
    if version_needed:
        version_number = (await db.scalar(select(func.count(ReportVersion.id)).where(ReportVersion.report_id == item.id)) or 0) + 1
        db.add(
            ReportVersion(
                report_id=item.id,
                version_number=version_number,
                generated_sql=item.generated_sql,
                chart_type=item.chart_type,
                config_json=item.config_json,
                created_by=user.id,
            )
        )
    await db.commit()
    await db.refresh(item)
    return await report_to_out(db, item)


@router.post("/reports/{report_id}/run", response_model=ReportOut)
async def run_report(report_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> ReportOut:
    item = await require_owned_report(db, report_id, user)
    validation = await validate_sql(db, item.generated_sql, role=user.role)
    if not validation.ok or not validation.validated_sql:
        raise HTTPException(status_code=400, detail=validation.message)
    started = datetime.utcnow()
    execution_result = await execute_validated_query(
        validation.validated_sql,
        role=user.role,
        db=db,
        query_id=item.query_id,
        use_cache=True,
    )
    rows = execution_result.rows
    item.result_snapshot = rows[:200]
    item.updated_at = datetime.utcnow()
    schedule = await db.scalar(select(Schedule).where(Schedule.report_id == item.id).order_by(Schedule.created_at.desc()))
    if schedule:
        schedule.last_run_at = datetime.utcnow()
        schedule.next_run_at = next_run_at(schedule.frequency, schedule.run_at_time, schedule.day_of_week, schedule.day_of_month)
        db.add(
            ScheduleRun(
                schedule_id=schedule.id,
                report_id=item.id,
                status="ok",
                rows_returned=len(rows),
                execution_ms=execution_result.execution_ms or int((datetime.utcnow() - started).total_seconds() * 1000),
                ran_at=datetime.utcnow(),
            )
        )
    await db.commit()
    await db.refresh(item)
    return await report_to_out(db, item)


@router.post("/reports/{report_id}/share", response_model=ReportOut)
async def share_report(
    report_id: UUID,
    recipients: list[str],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    item = await require_owned_report(db, report_id, user)
    for email in recipients:
        db.add(ReportRecipient(report_id=item.id, email=email))
    await db.commit()
    return await report_to_out(db, item)


@router.post("/api/reports/{report_id}/schedule", response_model=ReportOut)
async def schedule_report_legacy(
    report_id: UUID,
    payload: ScheduleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    item = await require_owned_report(db, report_id, user)
    schedule = Schedule(
        report_id=item.id,
        frequency=payload.frequency,
        run_at_time=time(9, 0),
        day_of_week=1 if payload.frequency == "weekly" else None,
        is_active=True,
    )
    schedule.next_run_at = next_run_at(schedule.frequency, schedule.run_at_time, schedule.day_of_week, schedule.day_of_month)
    db.add(schedule)
    db.add(ReportRecipient(report_id=item.id, email=payload.email))
    await db.commit()
    return await report_to_out(db, item)
