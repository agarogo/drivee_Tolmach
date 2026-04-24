from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, PLATFORM_SCHEMA, PlatformBase, utcnow, uuid_pk


class Template(PlatformBase, Base):
    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    natural_text: Mapped[str] = mapped_column(Text)
    canonical_intent_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    chart_type: Mapped[str] = mapped_column(String(32), default="bar")
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
