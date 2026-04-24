from app.api.common import *


router = APIRouter(tags=["Reports"])


@router.post("/reports", response_model=ReportOut)
@router.post("/api/reports", response_model=ReportOut)
async def create_report(
    payload: ReportCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    query = await require_owned_query(db, payload.query_id, user) if payload.query_id else None
    natural_text = payload.natural_text or payload.question or (query.natural_text if query else "")
    generated_sql = payload.generated_sql or payload.sql_text or (query.corrected_sql or query.generated_sql if query else "")
    chart_spec = payload.chart_spec or (query.chart_spec if query else {})
    result_snapshot = payload.result_snapshot or payload.result or (query.result_snapshot if query else [])
    chart_type = payload.chart_type or (query.chart_type if query else "table_only")
    semantic_snapshot = payload.semantic_snapshot or build_semantic_snapshot_from_query(query)
    item = Report(
        user_id=user.id,
        query_id=query.id if query else None,
        title=payload.title,
        natural_text=natural_text,
        generated_sql=generated_sql,
        chart_type=chart_type,
        chart_spec=chart_spec,
        semantic_snapshot_json=semantic_snapshot,
        result_snapshot=result_snapshot,
        config_json=payload.config_json,
    )
    db.add(item)
    await db.flush()
    await create_report_version(db, report=item, created_by=user.id)
    await replace_report_recipients(
        db,
        report=item,
        recipients=payload.recipients,
        delivery_targets=[target.model_dump() for target in payload.delivery_targets],
    )
    if payload.schedule:
        schedule = Schedule(
            report_id=item.id,
            frequency=payload.schedule.get("frequency", "weekly"),
            run_at_time=parse_run_time(payload.schedule.get("run_at_time")),
            day_of_week=payload.schedule.get("day_of_week") or 1,
            day_of_month=payload.schedule.get("day_of_month"),
            max_retries=int(payload.schedule.get("max_retries", settings.scheduler_default_max_retries)),
            retry_backoff_seconds=int(
                payload.schedule.get("retry_backoff_seconds", settings.scheduler_default_retry_backoff_seconds)
            ),
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
    rows = list(
        (
            await db.scalars(
                select(Report).where(Report.user_id == user.id).order_by(Report.updated_at.desc()).limit(100)
            )
        ).all()
    )
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
    semantic_snapshot = data.pop("semantic_snapshot", None)
    version_needed = any(
        key in data for key in ("generated_sql", "chart_type", "chart_spec", "config_json")
    ) or semantic_snapshot is not None
    for key, value in data.items():
        setattr(item, key, value)
    if semantic_snapshot is not None:
        item.semantic_snapshot_json = semantic_snapshot
    item.updated_at = datetime.utcnow()
    if version_needed:
        await create_report_version(db, report=item, created_by=user.id)
    await db.commit()
    await db.refresh(item)
    return await report_to_out(db, item)


@router.post("/reports/{report_id}/run", response_model=ReportOut)
async def run_report(report_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> ReportOut:
    item = await require_owned_report(db, report_id, user)
    run = await create_run_record(
        db,
        report=item,
        schedule_id=None,
        trigger_type="manual",
        requested_by_user_id=user.id,
        max_retries=0,
        retry_backoff_seconds=0,
    )
    await execute_report_run(db, run.id)
    await db.commit()
    await db.refresh(item)
    return await report_to_out(db, item)


@router.post("/reports/{report_id}/run-now", response_model=ScheduleRunOut)
async def run_report_now(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScheduleRunOut:
    item = await require_owned_report(db, report_id, user)
    run = await create_run_record(
        db,
        report=item,
        schedule_id=None,
        trigger_type="manual",
        requested_by_user_id=user.id,
        max_retries=0,
        retry_backoff_seconds=0,
    )
    run = await execute_report_run(db, run.id)
    await db.commit()
    return await run_to_out(db, run)


@router.get("/reports/{report_id}/history", response_model=list[ScheduleRunOut])
async def report_history(
    report_id: UUID,
    limit: int = ApiQuery(default=30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ScheduleRunOut]:
    item = await require_owned_report(db, report_id, user)
    rows = await list_report_runs(db, report_id=item.id, limit=limit)
    return [await run_to_out(db, row) for row in rows]


@router.post("/reports/{report_id}/share", response_model=ReportOut)
async def share_report(
    report_id: UUID,
    recipients: list[str],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    item = await require_owned_report(db, report_id, user)
    await append_report_recipients(db, report=item, recipients=recipients, delivery_targets=None)
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
        max_retries=settings.scheduler_default_max_retries,
        retry_backoff_seconds=settings.scheduler_default_retry_backoff_seconds,
        is_active=True,
    )
    schedule.next_run_at = next_run_at(schedule.frequency, schedule.run_at_time, schedule.day_of_week, schedule.day_of_month)
    db.add(schedule)
    await append_report_recipients(db, report=item, recipients=[payload.email], delivery_targets=None)
    await db.commit()
    return await report_to_out(db, item)
