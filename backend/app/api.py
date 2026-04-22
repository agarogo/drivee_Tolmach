import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, require_admin, verify_password
from app.db import get_db
from app.models import Chat, Message, QueryLog, Report, Template, User
from app.schemas import (
    AssistantMessageResponse,
    AuthResponse,
    ChatOut,
    LogOut,
    LoginRequest,
    MessageOut,
    MessagesPage,
    RegisterRequest,
    ReportCreate,
    ReportOut,
    ScheduleRequest,
    SendMessageRequest,
    TemplateCreate,
    TemplateOut,
    UserOut,
)
from app.services.charts import recommend_chart
from app.services.guardrails import GuardrailError, ensure_safe_sql
from app.services.nl2sql import TextToSqlService
from app.services.query_runner import run_sql
from app.config import get_settings

router = APIRouter()
text_to_sql = TextToSqlService()
settings = get_settings()


def to_user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


def chat_out(db: Session, chat: Chat) -> ChatOut:
    count = db.query(func.count(Message.id)).filter(Message.chat_id == chat.id).scalar() or 0
    return ChatOut(
        id=chat.id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        message_count=count,
    )


def require_owned_chat(db: Session, chat_id: int, user: User) -> Chat:
    chat = db.get(Chat, chat_id)
    if not chat or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Чат не найден")
    return chat


def make_chat_title(question: str) -> str:
    compact = " ".join(question.strip().split())
    if len(compact) <= 30:
        return compact
    return compact[:29].rstrip() + "…"


@router.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": "Толмач",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "ollama_base_url": settings.ollama_base_url,
    }


@router.post("/auth/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Введите корректный email")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Пользователь уже существует")

    user = User(email=email, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return AuthResponse(access_token=token, user=to_user_out(user))


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return AuthResponse(access_token=token, user=to_user_out(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return to_user_out(user)


@router.get("/api/chats", response_model=list[ChatOut])
def list_chats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatOut]:
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == user.id)
        .order_by(Chat.updated_at.desc(), Chat.id.desc())
        .all()
    )
    return [chat_out(db, chat) for chat in chats]


@router.post("/api/chats", response_model=ChatOut)
def create_chat(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatOut:
    chat = Chat(user_id=user.id, title="Новый запрос")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat_out(db, chat)


@router.get("/api/chats/{chat_id}/messages", response_model=MessagesPage)
def list_messages(
    chat_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessagesPage:
    require_owned_chat(db, chat_id, user)
    total = db.query(func.count(Message.id)).filter(Message.chat_id == chat_id).scalar() or 0
    latest = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = list(reversed(latest))
    return MessagesPage(
        items=[MessageOut.model_validate(item) for item in items],
        has_more=total > offset + len(latest),
        next_offset=offset + len(latest),
    )


@router.post("/api/chats/{chat_id}/messages", response_model=AssistantMessageResponse)
def send_message(
    chat_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantMessageResponse:
    chat = require_owned_chat(db, chat_id, user)
    question = payload.question.strip()
    prior_count = db.query(func.count(Message.id)).filter(Message.chat_id == chat.id).scalar() or 0
    if prior_count == 0:
        chat.title = make_chat_title(question)

    user_message = Message(chat_id=chat.id, role="user", content=question, payload={})
    db.add(user_message)
    db.flush()

    context_rows = (
        db.query(Message)
        .filter(Message.chat_id == chat.id, Message.id != user_message.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(10)
        .all()
    )
    context = [
        {"role": item.role, "content": item.content}
        for item in reversed(context_rows)
    ]

    started = time.perf_counter()
    generated_sql = ""
    prompt = ""
    raw_response = ""
    status_text = "success"
    error = ""

    try:
        generated = text_to_sql.generate(question, context)
        generated_sql = generated.sql
        prompt = generated.prompt
        raw_response = generated.raw_response

        if generated.confidence < 0.6:
            status_text = "needs_clarification"
            assistant_payload = {
                "type": "clarification",
                "question": question,
                "interpretation": generated.interpretation,
                "confidence": generated.confidence,
                "sql": "",
                "rows": [],
                "chart_spec": {"type": "table_only"},
            }
            assistant_text = (
                "Мне не хватает уверенности, чтобы безопасно построить SQL. "
                "Уточните, пожалуйста, метрику, период и разрез."
            )
        else:
            safe_sql, guardrail_notes = ensure_safe_sql(generated.sql)
            generated_sql = safe_sql
            rows = run_sql(safe_sql)
            chart_spec = recommend_chart(rows)
            assistant_payload = {
                "type": "analysis",
                "question": question,
                "interpretation": generated.interpretation,
                "confidence": generated.confidence,
                "sql": safe_sql,
                "guardrails": guardrail_notes,
                "rows": rows,
                "chart_spec": chart_spec,
            }
            assistant_text = generated.answer_intro

    except GuardrailError as exc:
        status_text = "blocked"
        error = str(exc)
        assistant_payload = {
            "type": "blocked",
            "question": question,
            "interpretation": {},
            "confidence": 1,
            "sql": generated_sql,
            "guardrails": [str(exc)],
            "rows": [],
            "chart_spec": {"type": "table_only"},
        }
        assistant_text = f"{exc} Переформулируйте запрос как аналитический SELECT-вопрос."
    except Exception as exc:
        status_text = "error"
        error = str(exc)
        assistant_payload = {
            "type": "error",
            "question": question,
            "interpretation": {},
            "confidence": 0,
            "sql": generated_sql,
            "rows": [],
            "chart_spec": {"type": "table_only"},
        }
        assistant_text = "Не получилось выполнить запрос. Детали доступны администратору в логах."

    duration_ms = int((time.perf_counter() - started) * 1000)
    assistant_message = Message(
        chat_id=chat.id,
        role="assistant",
        content=assistant_text,
        payload=assistant_payload,
    )
    chat.updated_at = datetime.utcnow()
    db.add(assistant_message)
    db.add(
        QueryLog(
            user_id=user.id,
            chat_id=chat.id,
            question=question,
            generated_sql=generated_sql,
            status=status_text,
            duration_ms=duration_ms,
            prompt=prompt,
            raw_response=raw_response,
            error=error,
        )
    )
    db.commit()
    db.refresh(chat)
    db.refresh(user_message)
    db.refresh(assistant_message)

    return AssistantMessageResponse(
        chat=chat_out(db, chat),
        user_message=MessageOut.model_validate(user_message),
        assistant_message=MessageOut.model_validate(assistant_message),
    )


@router.get("/api/templates", response_model=list[TemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TemplateOut]:
    templates = (
        db.query(Template)
        .filter((Template.user_id.is_(None)) | (Template.user_id == user.id))
        .order_by(Template.user_id.nullsfirst(), Template.id.asc())
        .all()
    )
    return [TemplateOut.model_validate(item) for item in templates]


@router.post("/api/templates", response_model=TemplateOut)
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateOut:
    item = Template(user_id=user.id, title=payload.title, content=payload.content)
    db.add(item)
    db.commit()
    db.refresh(item)
    return TemplateOut.model_validate(item)


@router.get("/api/reports", response_model=list[ReportOut])
def list_reports(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReportOut]:
    items = (
        db.query(Report)
        .filter(Report.user_id == user.id)
        .order_by(Report.created_at.desc(), Report.id.desc())
        .limit(100)
        .all()
    )
    return [ReportOut.model_validate(item) for item in items]


@router.post("/api/reports", response_model=ReportOut)
def create_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    if payload.chat_id:
        require_owned_chat(db, payload.chat_id, user)
    item = Report(
        user_id=user.id,
        chat_id=payload.chat_id,
        title=payload.title,
        question=payload.question,
        sql_text=payload.sql_text,
        result=payload.result,
        chart_spec=payload.chart_spec,
        schedule={},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return ReportOut.model_validate(item)


@router.post("/api/reports/{report_id}/schedule", response_model=ReportOut)
def schedule_report(
    report_id: int,
    payload: ScheduleRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    item = db.get(Report, report_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    item.schedule = {
        "frequency": payload.frequency,
        "email": payload.email,
        "last_demo_log": f"Демо-рассылка запланирована: {payload.frequency} -> {payload.email}",
    }
    db.commit()
    db.refresh(item)
    return ReportOut.model_validate(item)


@router.get("/admin/logs", response_model=list[LogOut])
def admin_logs(
    user_email: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[LogOut]:
    query = db.query(QueryLog, User.email).outerjoin(User, User.id == QueryLog.user_id)
    if user_email:
        query = query.filter(User.email.ilike(f"%{user_email}%"))
    if date_from:
        query = query.filter(QueryLog.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(QueryLog.created_at <= datetime.fromisoformat(date_to))

    rows = query.order_by(QueryLog.created_at.desc(), QueryLog.id.desc()).limit(300).all()
    return [
        LogOut(
            id=log.id,
            created_at=log.created_at,
            user_email=email,
            question=log.question,
            generated_sql=log.generated_sql,
            status=log.status,
            duration_ms=log.duration_ms,
            prompt=log.prompt,
            raw_response=log.raw_response,
            error=log.error,
        )
        for log, email in rows
    ]
