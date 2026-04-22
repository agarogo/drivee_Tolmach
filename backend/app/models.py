from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    chats: Mapped[list["Chat"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="Новый запрос")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="chats")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    chat: Mapped[Chat] = relationship(back_populates="messages")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id"), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text)
    generated_sql: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), index=True)
    duration_ms: Mapped[int] = mapped_column(default=0)
    prompt: Mapped[str] = mapped_column(Text, default="")
    raw_response: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped[User | None] = relationship()


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    question: Mapped[str] = mapped_column(Text)
    sql_text: Mapped[str] = mapped_column(Text)
    result: Mapped[list] = mapped_column(JSON, default=list)
    chart_spec: Mapped[dict] = mapped_column(JSON, default=dict)
    schedule: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    federal_district: Mapped[str] = mapped_column(String(120), index=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    customer_ref: Mapped[str] = mapped_column(String(80), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    city: Mapped[City] = relationship()


class Cancellation(Base):
    __tablename__ = "cancellations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    reason: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    order: Mapped[Order] = relationship()
    city: Mapped[City] = relationship()
