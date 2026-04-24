from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, PLATFORM_SCHEMA, PlatformBase, utcnow, uuid_pk


class MetricCatalog(PlatformBase, Base):
    __tablename__ = "metric_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    metric_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    business_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    sql_expression_template: Mapped[str] = mapped_column(Text)
    grain: Mapped[str] = mapped_column(String(64), index=True)
    allowed_dimensions_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    allowed_filters_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    default_chart: Mapped[str] = mapped_column(String(32), default="table_only")
    safety_tags_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class DimensionCatalog(PlatformBase, Base):
    __tablename__ = "dimension_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    dimension_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    business_name: Mapped[str] = mapped_column(String(255))
    table_name: Mapped[str] = mapped_column(String(128), index=True)
    column_name: Mapped[str] = mapped_column(Text)
    join_path: Mapped[str] = mapped_column(Text, default="")
    data_type: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class SemanticTerm(PlatformBase, Base):
    __tablename__ = "semantic_terms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    term: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    mapped_entity_type: Mapped[str] = mapped_column(String(32), index=True)
    mapped_entity_key: Mapped[str] = mapped_column(String(128), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class EmbeddingsCache(Base):
    __tablename__ = "embeddings_cache"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_key",
            "embedding_provider",
            "embedding_model",
            name="uq_app_embeddings_cache_entity_provider_model",
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_key: Mapped[str] = mapped_column(String(255), index=True)
    source_table: Mapped[str] = mapped_column(String(128))
    source_title: Mapped[str] = mapped_column(String(255), default="")
    source_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding_provider: Mapped[str] = mapped_column(String(64), index=True)
    embedding_model: Mapped[str] = mapped_column(String(128), index=True)
    vector_dims: Mapped[int] = mapped_column(Integer, default=0)
    embedding_json: Mapped[list[float]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class SemanticLayer(PlatformBase, Base):
    __tablename__ = "semantic_layer"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    term: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    semantic_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    item_kind: Mapped[str] = mapped_column(String(32), default="legacy", index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sql_expression: Mapped[str] = mapped_column(Text)
    table_name: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    metric_type: Mapped[str] = mapped_column(String(64), default="metric")
    dimension_type: Mapped[str] = mapped_column(String(64), default="")
    semantic_config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class SemanticExample(PlatformBase, Base):
    __tablename__ = "semantic_examples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    title: Mapped[str] = mapped_column(String(255))
    natural_text: Mapped[str] = mapped_column(Text)
    canonical_intent_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sql_example: Mapped[str] = mapped_column(Text)
    domain_tag: Mapped[str] = mapped_column(String(64), default="general", index=True)
    metric_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    dimension_keys_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    filter_keys_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class ApprovedTemplate(PlatformBase, Base):
    __tablename__ = "approved_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    template_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    natural_text: Mapped[str] = mapped_column(Text)
    metric_key: Mapped[str] = mapped_column(String(128), index=True)
    dimension_keys_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    filter_keys_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    canonical_intent_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    chart_type: Mapped[str] = mapped_column(String(32), default="table_only")
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class AccessPolicy(PlatformBase, Base):
    __tablename__ = "access_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    role: Mapped[str] = mapped_column(String(20), index=True)
    table_name: Mapped[str] = mapped_column(String(128), index=True)
    allowed_columns_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    row_limit: Mapped[int] = mapped_column(Integer, default=1000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ChartPreference(PlatformBase, Base):
    __tablename__ = "chart_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pk)
    metric_type: Mapped[str] = mapped_column(String(64), index=True)
    dimension_type: Mapped[str] = mapped_column(String(64), index=True)
    chart_type: Mapped[str] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    notes: Mapped[str] = mapped_column(Text, default="")
