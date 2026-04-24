from datetime import datetime, time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query as ApiQuery, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.orchestrator import run_query_workflow
from app.auth import create_access_token, get_current_user, hash_password, require_admin, verify_password
from app.config import get_settings
from app.db import get_db
from app.models import (
    Chat,
    Message,
    Query,
    QueryClarification,
    QueryExecutionAudit,
    QueryEvent,
    Report,
    ReportArtifact,
    ReportDelivery,
    ReportRecipient,
    ReportVersion,
    Schedule,
    ScheduleRun,
    SqlGuardrailLog,
    Template,
    User,
)
from app.query_execution.benchmarks import BENCHMARK_PRESETS
from app.query_execution.service import (
    get_query_cache_stats,
    get_query_execution_summary,
    list_query_execution_audits,
)
from app.schemas import (
    ApprovedTemplateCreate,
    ApprovedTemplateOut,
    ApprovedTemplatePatch,
    AssistantMessageResponse,
    AuthResponse,
    BenchmarkPresetOut,
    ChatDeleteOut,
    ChatOut,
    ClarificationOut,
    DimensionCatalogCreate,
    DimensionCatalogOut,
    DimensionCatalogPatch,
    GuardrailLogOut,
    LogOut,
    LoginRequest,
    MessageOut,
    MetricCatalogCreate,
    MetricCatalogOut,
    MetricCatalogPatch,
    MessagesPage,
    QueryClarifyRequest,
    QueryExecutionAuditOut,
    QueryExecutionCacheStatsOut,
    QueryExecutionSummaryOut,
    QueryEventOut,
    QueryOut,
    QueryRunRequest,
    RegisterRequest,
    ReportArtifactOut,
    ReportCreate,
    ReportDeliveryOut,
    ReportOut,
    ReportPatch,
    ReportRecipientOut,
    ReportVersionOut,
    SchedulerSummaryOut,
    ScheduleCreate,
    ScheduleOut,
    SchedulePatch,
    ScheduleRequest,
    ScheduleRunOut,
    SemanticExampleCreate,
    SemanticExampleOut,
    SemanticExamplePatch,
    SemanticTermCreate,
    SemanticTermOut,
    SemanticTermPatch,
    SemanticValidationReportOut,
    SendMessageRequest,
    TemplateCreate,
    TemplateOut,
    UserOut,
)
from app.semantic import repository as semantic_repository
from app.semantic.service import (
    create_approved_template_entry,
    create_dimension_catalog_entry,
    create_metric_catalog_entry,
    create_semantic_example_entry,
    create_semantic_term_entry,
    delete_approved_template_entry,
    delete_dimension_catalog_entry,
    delete_metric_catalog_entry,
    delete_semantic_example_entry,
    delete_semantic_term_entry,
    update_approved_template_entry,
    update_dimension_catalog_entry,
    update_metric_catalog_entry,
    update_semantic_example_entry,
    update_semantic_term_entry,
    validate_semantic_layer,
)
from app.reports import (
    append_report_recipients,
    build_semantic_snapshot_from_query,
    create_report_version,
    create_run_record,
    execute_report_run,
    get_scheduler_summary,
    list_report_runs,
    next_run_at,
    parse_run_time,
    replace_report_recipients,
)
router = APIRouter()
settings = get_settings()


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


async def delete_chat_with_related_data(db: AsyncSession, chat: Chat) -> dict[str, int]:
    query_ids = list(
        (
            await db.scalars(
                select(Query.id).where(Query.chat_id == chat.id)
            )
        ).all()
    )
    counts = {
        "messages": int(await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id)) or 0),
        "queries": len(query_ids),
        "clarifications": 0,
        "events": 0,
        "guardrail_logs": 0,
        "reports_detached": 0,
        "query_audits_detached": 0,
    }
    if query_ids:
        counts["clarifications"] = int(
            await db.scalar(select(func.count(QueryClarification.id)).where(QueryClarification.query_id.in_(query_ids)))
            or 0
        )
        counts["events"] = int(
            await db.scalar(select(func.count(QueryEvent.id)).where(QueryEvent.query_id.in_(query_ids))) or 0
        )
        counts["guardrail_logs"] = int(
            await db.scalar(select(func.count(SqlGuardrailLog.id)).where(SqlGuardrailLog.query_id.in_(query_ids))) or 0
        )
        counts["reports_detached"] = int(
            await db.scalar(select(func.count(Report.id)).where(Report.query_id.in_(query_ids))) or 0
        )
        counts["query_audits_detached"] = int(
            await db.scalar(select(func.count(QueryExecutionAudit.id)).where(QueryExecutionAudit.query_id.in_(query_ids)))
            or 0
        )

        await db.execute(
            update(Report)
            .where(Report.query_id.in_(query_ids))
            .values(query_id=None, updated_at=datetime.utcnow())
        )
        await db.execute(
            update(QueryExecutionAudit)
            .where(QueryExecutionAudit.query_id.in_(query_ids))
            .values(query_id=None)
        )
        await db.execute(delete(QueryClarification).where(QueryClarification.query_id.in_(query_ids)))
        await db.execute(delete(QueryEvent).where(QueryEvent.query_id.in_(query_ids)))
        await db.execute(delete(SqlGuardrailLog).where(SqlGuardrailLog.query_id.in_(query_ids)))
        await db.execute(delete(Query).where(Query.id.in_(query_ids)))

    await db.execute(delete(Message).where(Message.chat_id == chat.id))
    await db.delete(chat)
    await db.flush()
    return counts


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


async def require_owned_schedule(db: AsyncSession, schedule_id: UUID, user: User) -> Schedule:
    item = await db.get(Schedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Расписание не найдено")
    await require_owned_report(db, item.report_id, user)
    return item


async def query_to_out(db: AsyncSession, item: Query) -> QueryOut:
    events = list(
        (
            await db.scalars(
                select(QueryEvent).where(QueryEvent.query_id == item.id).order_by(QueryEvent.started_at.asc())
            )
        ).all()
    )
    guardrails = list(
        (await db.scalars(select(SqlGuardrailLog).where(SqlGuardrailLog.query_id == item.id))).all()
    )
    clarifications = list(
        (
            await db.scalars(
                select(QueryClarification)
                .where(QueryClarification.query_id == item.id)
                .order_by(QueryClarification.created_at.asc())
            )
        ).all()
    )
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
        answer_type_code=item.answer_type_code,
        answer_type_key=item.answer_type_key,
        primary_view_mode=item.primary_view_mode,
        answer=item.answer_envelope_json or None,
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


def assistant_payload_from_query(output: QueryOut, item: Query) -> dict:
    return {
        **output.model_dump(mode="json"),
        "type": item.status,
        "rows": item.result_snapshot,
        "sql": item.corrected_sql or item.generated_sql,
        "answer": output.answer.model_dump(mode="json") if output.answer else None,
    }


async def run_to_out(db: AsyncSession, item: ScheduleRun) -> ScheduleRunOut:
    artifacts = list(
        (
            await db.scalars(
                select(ReportArtifact).where(ReportArtifact.run_id == item.id).order_by(ReportArtifact.created_at.asc())
            )
        ).all()
    )
    deliveries = list(
        (
            await db.scalars(
                select(ReportDelivery).where(ReportDelivery.run_id == item.id).order_by(ReportDelivery.created_at.asc())
            )
        ).all()
    )
    return ScheduleRunOut(
        id=item.id,
        schedule_id=item.schedule_id,
        report_id=item.report_id,
        report_version_id=item.report_version_id,
        requested_by_user_id=item.requested_by_user_id,
        trigger_type=item.trigger_type,
        status=item.status,
        queued_at=item.queued_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        next_retry_at=item.next_retry_at,
        retry_count=item.retry_count,
        max_retries=item.max_retries,
        retry_backoff_seconds=item.retry_backoff_seconds,
        final_sql=item.final_sql,
        chart_type=item.chart_type,
        chart_spec_json=item.chart_spec_json,
        semantic_snapshot_json=item.semantic_snapshot_json,
        result_snapshot=item.result_snapshot,
        execution_fingerprint=item.execution_fingerprint,
        explain_plan_json=item.explain_plan_json,
        explain_cost=float(item.explain_cost or 0),
        validator_summary_json=item.validator_summary_json,
        structured_error_json=item.structured_error_json,
        stack_trace=item.stack_trace,
        attempts_json=item.attempts_json,
        artifact_summary_json=item.artifact_summary_json,
        delivery_summary_json=item.delivery_summary_json,
        rows_returned=item.rows_returned,
        execution_ms=item.execution_ms,
        error_message=item.error_message,
        ran_at=item.ran_at,
        artifacts=[ReportArtifactOut.model_validate(row, from_attributes=True) for row in artifacts],
        deliveries=[ReportDeliveryOut.model_validate(row, from_attributes=True) for row in deliveries],
    )


async def schedule_to_out(db: AsyncSession, item: Schedule) -> ScheduleOut:
    report = await db.get(Report, item.report_id)
    recipients = list(
        (
            await db.scalars(
                select(ReportRecipient).where(ReportRecipient.report_id == item.report_id).order_by(ReportRecipient.added_at)
            )
        ).all()
    )
    recipient_out = [ReportRecipientOut.model_validate(row, from_attributes=True) for row in recipients]
    runs = list(
        (
            await db.scalars(
                select(ScheduleRun).where(ScheduleRun.schedule_id == item.id).order_by(ScheduleRun.ran_at.desc()).limit(10)
            )
        ).all()
    )
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
        max_retries=item.max_retries,
        retry_backoff_seconds=item.retry_backoff_seconds,
        last_error_message=item.last_error_message,
        last_error_at=item.last_error_at,
        is_active=item.is_active,
        recipients=[row.destination or row.email or "" for row in recipients if (row.destination or row.email)],
        delivery_targets=recipient_out,
        runs=[await run_to_out(db, row) for row in runs],
    )


async def report_to_out(db: AsyncSession, item: Report, include_detail: bool = True) -> ReportOut:
    recipients = list((await db.scalars(select(ReportRecipient).where(ReportRecipient.report_id == item.id))).all())
    versions = []
    schedules = []
    latest_runs: list[ScheduleRun] = []
    if include_detail:
        versions = list(
            (
                await db.scalars(
                    select(ReportVersion).where(ReportVersion.report_id == item.id).order_by(ReportVersion.version_number.desc())
                )
            ).all()
        )
        schedule_rows = list(
            (
                await db.scalars(
                    select(Schedule).where(Schedule.report_id == item.id).order_by(Schedule.created_at.desc())
                )
            ).all()
        )
        schedules = [await schedule_to_out(db, row) for row in schedule_rows]
        latest_runs = await list_report_runs(db, report_id=item.id, limit=10)
    first_schedule = schedules[0] if schedules else None
    return ReportOut(
        id=item.id,
        title=item.title,
        natural_text=item.natural_text,
        generated_sql=item.generated_sql,
        chart_type=item.chart_type,
        chart_spec=item.chart_spec,
        semantic_snapshot_json=item.semantic_snapshot_json,
        result_snapshot=item.result_snapshot,
        config_json=item.config_json,
        is_active=item.is_active,
        latest_version_number=item.latest_version_number,
        last_run_at=item.last_run_at,
        last_run_status=item.last_run_status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        recipients=[row.destination or row.email or "" for row in recipients if (row.destination or row.email)],
        delivery_targets=[ReportRecipientOut.model_validate(row, from_attributes=True) for row in recipients],
        schedules=schedules,
        versions=[ReportVersionOut.model_validate(row, from_attributes=True) for row in versions],
        latest_runs=[await run_to_out(db, row) for row in latest_runs],
        question=item.natural_text,
        sql_text=item.generated_sql,
        result=item.result_snapshot,
        schedule=first_schedule.model_dump(mode="json") if first_schedule else {},
    )


@router.get("/health")
@router.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": "Толмач by Drivee",
        "database": "postgresql",
        "database_name": settings.analytics_database_name,
        "mode": "read-only analytics executor",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
    }


@router.get("/metrics")
async def metrics() -> dict:
    return {"status": "ok", "service": "tolmach", "otel": "optional", "queries_endpoint": "/queries/run"}


@router.get("/traces-link")
async def traces_link() -> dict:
    return {
        "phoenix_url": "http://localhost:6006",
        "otel_endpoint_env": "OTEL_EXPORTER_OTLP_ENDPOINT",
        "note": "OpenTelemetry/Phoenix can subscribe to query_events; UI Trace Panel reads persisted events.",
    }


@router.post("/auth/register", response_model=AuthResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Введите корректный email")
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Пользователь уже существует")
    user = User(
        email=email,
        full_name=payload.full_name or email.split("@", 1)[0],
        password_hash=hash_password(payload.password),
        role="user",
        preferences={"theme": "dark"},
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    return AuthResponse(access_token=token, user=to_user_out(user))


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    user = await db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    user.last_login_at = datetime.utcnow()
    await db.commit()
    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    return AuthResponse(access_token=token, user=to_user_out(user))


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return to_user_out(user)


@router.post("/queries/run", response_model=QueryOut)
async def run_query(
    payload: QueryRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueryOut:
    question = payload.question.strip()
    chat = await ensure_query_chat(db, user, payload.chat_id, question)
    prior_count = await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id))
    if prior_count == 0:
        chat.title = make_chat_title(question)
    user_message = Message(chat_id=chat.id, role="user", content=question, payload={})
    db.add(user_message)
    await db.flush()

    item = await run_query_workflow(db, user, question, chat.id)
    output = await query_to_out(db, item)
    assistant_message = Message(
        chat_id=chat.id,
        role="assistant",
        content=item.ai_answer or "Готово.",
        payload=assistant_payload_from_query(output, item),
    )
    chat.updated_at = datetime.utcnow()
    db.add(assistant_message)
    await db.commit()
    return output


@router.post("/queries/{query_id}/clarify", response_model=QueryOut)
async def clarify_query(
    query_id: UUID,
    payload: QueryClarifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueryOut:
    original = await require_owned_query(db, query_id, user)
    clarification = await db.scalar(
        select(QueryClarification)
        .where(QueryClarification.query_id == query_id)
        .order_by(QueryClarification.created_at.desc())
    )
    answer = payload.freeform_answer or payload.chosen_option
    if not answer:
        raise HTTPException(status_code=400, detail="Нужно выбрать вариант или написать уточнение")
    if clarification:
        clarification.chosen_option = payload.chosen_option
        clarification.freeform_answer = payload.freeform_answer
        clarification.answered_at = datetime.utcnow()
    original.status = "clarified"
    await db.flush()
    clarified_question = f"{original.natural_text}. Уточнение: {answer}"
    chat: Chat | None = None
    if original.chat_id:
        chat = await require_owned_chat(db, original.chat_id, user)
        db.add(Message(chat_id=chat.id, role="user", content=answer, payload={"clarifies_query_id": str(original.id)}))
        await db.flush()
    item = await run_query_workflow(db, user, clarified_question, original.chat_id)
    output = await query_to_out(db, item)
    if chat:
        db.add(
            Message(
                chat_id=chat.id,
                role="assistant",
                content=item.ai_answer or "Готово.",
                payload=assistant_payload_from_query(output, item),
            )
        )
        chat.updated_at = datetime.utcnow()
        await db.commit()
    return output


@router.get("/queries/history", response_model=list[QueryOut])
async def query_history(
    limit: int = ApiQuery(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[QueryOut]:
    rows = list(
        (
            await db.scalars(
                select(Query).where(Query.user_id == user.id).order_by(Query.created_at.desc()).limit(limit)
            )
        ).all()
    )
    return [await query_to_out(db, row) for row in rows]


@router.get("/queries/{query_id}", response_model=QueryOut)
async def get_query(
    query_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueryOut:
    return await query_to_out(db, await require_owned_query(db, query_id, user))


@router.get("/templates", response_model=list[TemplateOut])
@router.get("/api/templates", response_model=list[TemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[TemplateOut]:
    rows = list(
        (
            await db.scalars(
                select(Template)
                .where(or_(Template.is_public.is_(True), Template.created_by == user.id))
                .order_by(Template.category.asc(), Template.use_count.desc(), Template.title.asc())
            )
        ).all()
    )
    return [TemplateOut.model_validate(row) for row in rows]


@router.post("/templates", response_model=TemplateOut)
@router.post("/api/templates", response_model=TemplateOut)
async def create_template(
    payload: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateOut:
    item = Template(created_by=user.id, **payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return TemplateOut.model_validate(item)


@router.get("/admin/semantic/validate", response_model=SemanticValidationReportOut)
async def admin_validate_semantic_catalog(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> SemanticValidationReportOut:
    return SemanticValidationReportOut.model_validate((await validate_semantic_layer(db)).as_dict())


@router.get("/admin/semantic/metrics", response_model=list[MetricCatalogOut])
async def admin_list_metric_catalog(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[MetricCatalogOut]:
    rows = await semantic_repository.list_metric_catalog_entries(db)
    return [MetricCatalogOut.model_validate(row) for row in rows]


@router.post("/admin/semantic/metrics", response_model=MetricCatalogOut)
async def admin_create_metric_catalog(
    payload: MetricCatalogCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> MetricCatalogOut:
    item = await create_metric_catalog_entry(db, payload.model_dump(), updated_by=user.id)
    return MetricCatalogOut.model_validate(item)


@router.patch("/admin/semantic/metrics/{metric_key}", response_model=MetricCatalogOut)
async def admin_update_metric_catalog(
    metric_key: str,
    payload: MetricCatalogPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> MetricCatalogOut:
    item = await update_metric_catalog_entry(
        db,
        metric_key,
        payload.model_dump(exclude_unset=True),
        updated_by=user.id,
    )
    return MetricCatalogOut.model_validate(item)


@router.delete("/admin/semantic/metrics/{metric_key}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_metric_catalog(
    metric_key: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_metric_catalog_entry(db, metric_key)


@router.get("/admin/semantic/dimensions", response_model=list[DimensionCatalogOut])
async def admin_list_dimension_catalog(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DimensionCatalogOut]:
    rows = await semantic_repository.list_dimension_catalog_entries(db)
    return [DimensionCatalogOut.model_validate(row) for row in rows]


@router.post("/admin/semantic/dimensions", response_model=DimensionCatalogOut)
async def admin_create_dimension_catalog(
    payload: DimensionCatalogCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> DimensionCatalogOut:
    item = await create_dimension_catalog_entry(db, payload.model_dump(), updated_by=user.id)
    return DimensionCatalogOut.model_validate(item)


@router.patch("/admin/semantic/dimensions/{dimension_key}", response_model=DimensionCatalogOut)
async def admin_update_dimension_catalog(
    dimension_key: str,
    payload: DimensionCatalogPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> DimensionCatalogOut:
    item = await update_dimension_catalog_entry(
        db,
        dimension_key,
        payload.model_dump(exclude_unset=True),
        updated_by=user.id,
    )
    return DimensionCatalogOut.model_validate(item)


@router.delete("/admin/semantic/dimensions/{dimension_key}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_dimension_catalog(
    dimension_key: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_dimension_catalog_entry(db, dimension_key)


@router.get("/admin/semantic/terms", response_model=list[SemanticTermOut])
async def admin_list_semantic_terms(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SemanticTermOut]:
    rows = await semantic_repository.list_semantic_terms(db)
    return [SemanticTermOut.model_validate(row) for row in rows]


@router.post("/admin/semantic/terms", response_model=SemanticTermOut)
async def admin_create_semantic_term(
    payload: SemanticTermCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> SemanticTermOut:
    item = await create_semantic_term_entry(db, payload.model_dump(), updated_by=user.id)
    return SemanticTermOut.model_validate(item)


@router.patch("/admin/semantic/terms/{term}", response_model=SemanticTermOut)
async def admin_update_semantic_term(
    term: str,
    payload: SemanticTermPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> SemanticTermOut:
    item = await update_semantic_term_entry(db, term, payload.model_dump(exclude_unset=True), updated_by=user.id)
    return SemanticTermOut.model_validate(item)


@router.delete("/admin/semantic/terms/{term}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_semantic_term(
    term: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_semantic_term_entry(db, term)


@router.get("/admin/semantic/examples", response_model=list[SemanticExampleOut])
async def admin_list_semantic_examples(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SemanticExampleOut]:
    rows = await semantic_repository.list_semantic_examples(db)
    return [SemanticExampleOut.model_validate(row) for row in rows]


@router.post("/admin/semantic/examples", response_model=SemanticExampleOut)
async def admin_create_semantic_example(
    payload: SemanticExampleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> SemanticExampleOut:
    item = await create_semantic_example_entry(db, payload.model_dump(), updated_by=user.id)
    return SemanticExampleOut.model_validate(item)


@router.patch("/admin/semantic/examples/{example_id}", response_model=SemanticExampleOut)
async def admin_update_semantic_example(
    example_id: UUID,
    payload: SemanticExamplePatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> SemanticExampleOut:
    item = await update_semantic_example_entry(
        db,
        example_id,
        payload.model_dump(exclude_unset=True),
        updated_by=user.id,
    )
    return SemanticExampleOut.model_validate(item)


@router.delete("/admin/semantic/examples/{example_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_semantic_example(
    example_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_semantic_example_entry(db, example_id)


@router.get("/admin/semantic/approved-templates", response_model=list[ApprovedTemplateOut])
async def admin_list_approved_templates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ApprovedTemplateOut]:
    rows = await semantic_repository.list_approved_templates(db)
    return [ApprovedTemplateOut.model_validate(row) for row in rows]


@router.post("/admin/semantic/approved-templates", response_model=ApprovedTemplateOut)
async def admin_create_approved_template(
    payload: ApprovedTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> ApprovedTemplateOut:
    item = await create_approved_template_entry(db, payload.model_dump(), updated_by=user.id)
    return ApprovedTemplateOut.model_validate(item)


@router.patch("/admin/semantic/approved-templates/{template_key}", response_model=ApprovedTemplateOut)
async def admin_update_approved_template(
    template_key: str,
    payload: ApprovedTemplatePatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> ApprovedTemplateOut:
    item = await update_approved_template_entry(
        db,
        template_key,
        payload.model_dump(exclude_unset=True),
        updated_by=user.id,
    )
    return ApprovedTemplateOut.model_validate(item)


@router.delete("/admin/semantic/approved-templates/{template_key}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_approved_template(
    template_key: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_approved_template_entry(db, template_key)


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


@router.get("/schedules", response_model=list[ScheduleOut])
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


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
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


@router.post("/schedules/{schedule_id}/toggle", response_model=ScheduleOut)
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


@router.post("/schedules/{schedule_id}/run-now", response_model=ScheduleRunOut)
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


@router.get("/schedules/{schedule_id}/history", response_model=list[ScheduleRunOut])
async def schedule_history(
    schedule_id: UUID,
    limit: int = ApiQuery(default=30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ScheduleRunOut]:
    item = await require_owned_schedule(db, schedule_id, user)
    rows = await list_report_runs(db, schedule_id=item.id, limit=limit)
    return [await run_to_out(db, row) for row in rows]


# Compatibility chat API for previous app shell.
@router.get("/api/chats", response_model=list[ChatOut])
async def list_chats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[ChatOut]:
    rows = list(
        (
            await db.scalars(
                select(Chat).where(Chat.user_id == user.id).order_by(Chat.updated_at.desc(), Chat.id.desc())
            )
        ).all()
    )
    return [await chat_out(db, row) for row in rows]


@router.post("/api/chats", response_model=ChatOut)
async def create_chat(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> ChatOut:
    chat = Chat(user_id=user.id, title="Новый запрос")
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return await chat_out(db, chat)


@router.delete("/api/chats/{chat_id}", response_model=ChatDeleteOut)
async def delete_chat(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatDeleteOut:
    chat = await require_owned_chat(db, chat_id, user)
    counts = await delete_chat_with_related_data(db, chat)
    await db.commit()
    return ChatDeleteOut(id=chat_id, deleted=True, deleted_related_counts=counts)


@router.get("/api/chats/{chat_id}/messages", response_model=MessagesPage)
async def list_messages(
    chat_id: UUID,
    limit: int = ApiQuery(default=50, ge=1, le=100),
    offset: int = ApiQuery(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessagesPage:
    await require_owned_chat(db, chat_id, user)
    total = await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat_id))
    rows = list(
        (
            await db.scalars(
                select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    items = list(reversed(rows))
    return MessagesPage(
        items=[MessageOut.model_validate(item) for item in items],
        has_more=(total or 0) > offset + len(rows),
        next_offset=offset + len(rows),
    )


@router.post("/api/chats/{chat_id}/messages", response_model=AssistantMessageResponse)
async def send_message(
    chat_id: UUID,
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantMessageResponse:
    chat = await require_owned_chat(db, chat_id, user)
    question = payload.question.strip()
    prior_count = await db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id))
    if prior_count == 0:
        chat.title = make_chat_title(question)
    user_message = Message(chat_id=chat.id, role="user", content=question, payload={})
    db.add(user_message)
    await db.flush()
    query = await run_query_workflow(db, user, question, chat_id)
    output = await query_to_out(db, query)
    assistant_message = Message(
        chat_id=chat.id,
        role="assistant",
        content=query.ai_answer,
        payload=assistant_payload_from_query(output, query),
    )
    chat.updated_at = datetime.utcnow()
    db.add(assistant_message)
    await db.commit()
    await db.refresh(chat)
    await db.refresh(user_message)
    await db.refresh(assistant_message)
    return AssistantMessageResponse(
        chat=await chat_out(db, chat),
        user_message=MessageOut.model_validate(user_message),
        assistant_message=MessageOut.model_validate(assistant_message),
    )


@router.get("/admin/logs", response_model=list[LogOut])
async def admin_logs(
    user_email: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[LogOut]:
    stmt = select(Query, User.email).outerjoin(User, User.id == Query.user_id)
    if user_email:
        stmt = stmt.where(User.email.ilike(f"%{user_email}%"))
    if date_from:
        stmt = stmt.where(Query.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        stmt = stmt.where(Query.created_at <= datetime.fromisoformat(date_to))
    rows = (await db.execute(stmt.order_by(Query.created_at.desc()).limit(300))).all()
    return [
        LogOut(
            id=query.id,
            created_at=query.created_at,
            user_email=email,
            question=query.natural_text,
            generated_sql=query.corrected_sql or query.generated_sql,
            status=query.status,
            duration_ms=query.execution_ms,
            prompt=str(query.interpretation_json),
            raw_response=str(query.sql_plan_json),
            error=query.error_message or query.block_reason,
        )
        for query, email in rows
    ]


@router.get("/admin/query-execution/cache", response_model=QueryExecutionCacheStatsOut)
async def admin_query_execution_cache_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> QueryExecutionCacheStatsOut:
    return QueryExecutionCacheStatsOut.model_validate(await get_query_cache_stats(db))


@router.get("/admin/query-execution/summary", response_model=QueryExecutionSummaryOut)
async def admin_query_execution_summary(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> QueryExecutionSummaryOut:
    return QueryExecutionSummaryOut.model_validate(await get_query_execution_summary(db))


@router.get("/admin/query-execution/audits", response_model=list[QueryExecutionAuditOut])
async def admin_query_execution_audits(
    limit: int = ApiQuery(default=50, ge=1, le=200),
    cache_hit: bool | None = None,
    status_filter: str | None = None,
    fingerprint: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[QueryExecutionAuditOut]:
    rows = await list_query_execution_audits(
        db,
        limit=limit,
        cache_hit=cache_hit,
        status=status_filter,
        fingerprint=fingerprint,
    )
    return [QueryExecutionAuditOut.model_validate(row) for row in rows]


@router.get("/admin/query-execution/benchmarks/presets", response_model=list[BenchmarkPresetOut])
async def admin_query_execution_benchmark_presets(
    _: User = Depends(require_admin),
) -> list[BenchmarkPresetOut]:
    return [
        BenchmarkPresetOut(key=item.key, title=item.title, question=item.question)
        for item in BENCHMARK_PRESETS
    ]


@router.get("/admin/scheduler/summary", response_model=SchedulerSummaryOut)
async def admin_scheduler_summary(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> SchedulerSummaryOut:
    return SchedulerSummaryOut.model_validate(await get_scheduler_summary(db))


@router.get("/admin/scheduler/runs", response_model=list[ScheduleRunOut])
async def admin_scheduler_runs(
    limit: int = ApiQuery(default=50, ge=1, le=200),
    status_filter: str | None = None,
    report_id: UUID | None = None,
    schedule_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ScheduleRunOut]:
    rows = await list_report_runs(
        db,
        report_id=report_id,
        schedule_id=schedule_id,
        limit=limit,
    )
    if status_filter:
        rows = [row for row in rows if row.status == status_filter]
    return [await run_to_out(db, row) for row in rows]
