from __future__ import annotations

from datetime import datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.answer_contracts import AnswerEnvelope


class SemanticLayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    term: str
    semantic_key: str
    item_kind: str
    aliases: list[str]
    sql_expression: str
    table_name: str
    description: str
    metric_type: str
    dimension_type: str
    semantic_config_json: dict[str, Any]
    updated_at: datetime

class SemanticLayerCreate(BaseModel):
    term: str = Field(min_length=2, max_length=128)
    semantic_key: str = Field(min_length=2, max_length=128)
    item_kind: Literal["metric", "dimension", "filter", "legacy"] = "legacy"
    aliases: list[str] = Field(default_factory=list)
    sql_expression: str
    table_name: str
    description: str = ""
    metric_type: str = "metric"
    dimension_type: str = ""
    semantic_config_json: dict[str, Any] = Field(default_factory=dict)

class MetricCatalogBase(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    description: str = ""
    sql_expression_template: str = Field(min_length=2)
    grain: str = Field(min_length=2, max_length=64)
    allowed_dimensions: list[str] = Field(default_factory=list)
    allowed_filters: list[str] = Field(default_factory=list)
    default_chart: str = "table_only"
    safety_tags: list[str] = Field(default_factory=list)
    is_active: bool = True

class MetricCatalogCreate(MetricCatalogBase):
    metric_key: str = Field(min_length=2, max_length=128)

class MetricCatalogPatch(BaseModel):
    business_name: str | None = None
    description: str | None = None
    sql_expression_template: str | None = None
    grain: str | None = None
    allowed_dimensions: list[str] | None = None
    allowed_filters: list[str] | None = None
    default_chart: str | None = None
    safety_tags: list[str] | None = None
    is_active: bool | None = None

class MetricCatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    metric_key: str
    business_name: str
    description: str
    sql_expression_template: str
    grain: str
    allowed_dimensions: list[str] = Field(validation_alias="allowed_dimensions_json")
    allowed_filters: list[str] = Field(validation_alias="allowed_filters_json")
    default_chart: str
    safety_tags: list[str] = Field(validation_alias="safety_tags_json")
    is_active: bool
    created_at: datetime
    updated_at: datetime

class DimensionCatalogBase(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    table_name: str = Field(min_length=2, max_length=128)
    column_name: str = Field(min_length=1)
    join_path: str = ""
    data_type: str = Field(min_length=2, max_length=32)
    is_active: bool = True

class DimensionCatalogCreate(DimensionCatalogBase):
    dimension_key: str = Field(min_length=2, max_length=128)

class DimensionCatalogPatch(BaseModel):
    business_name: str | None = None
    table_name: str | None = None
    column_name: str | None = None
    join_path: str | None = None
    data_type: str | None = None
    is_active: bool | None = None

class DimensionCatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dimension_key: str
    business_name: str
    table_name: str
    column_name: str
    join_path: str
    data_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class SemanticTermBase(BaseModel):
    aliases: list[str] = Field(default_factory=list)
    mapped_entity_type: Literal["metric", "dimension", "filter"]
    mapped_entity_key: str = Field(min_length=2, max_length=128)
    is_active: bool = True

class SemanticTermCreate(SemanticTermBase):
    term: str = Field(min_length=2, max_length=128)

class SemanticTermPatch(BaseModel):
    term: str | None = None
    aliases: list[str] | None = None
    mapped_entity_type: Literal["metric", "dimension", "filter"] | None = None
    mapped_entity_key: str | None = None
    is_active: bool | None = None

class SemanticTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    term: str
    aliases: list[str]
    mapped_entity_type: str
    mapped_entity_key: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class SemanticExampleBase(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    natural_text: str = Field(min_length=2)
    metric_key: str = Field(min_length=2, max_length=128)
    dimension_keys: list[str] = Field(default_factory=list)
    filter_keys: list[str] = Field(default_factory=list)
    canonical_intent_json: dict[str, Any] = Field(default_factory=dict)
    sql_example: str = Field(min_length=2)
    domain_tag: str = "general"
    is_active: bool = True

class SemanticExampleCreate(SemanticExampleBase):
    pass

class SemanticExamplePatch(BaseModel):
    title: str | None = None
    natural_text: str | None = None
    metric_key: str | None = None
    dimension_keys: list[str] | None = None
    filter_keys: list[str] | None = None
    canonical_intent_json: dict[str, Any] | None = None
    sql_example: str | None = None
    domain_tag: str | None = None
    is_active: bool | None = None

class SemanticExampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    natural_text: str
    metric_key: str
    dimension_keys: list[str] = Field(validation_alias="dimension_keys_json")
    filter_keys: list[str] = Field(validation_alias="filter_keys_json")
    canonical_intent_json: dict[str, Any]
    sql_example: str
    domain_tag: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class ApprovedTemplateBase(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str = ""
    natural_text: str = Field(min_length=2)
    metric_key: str = Field(min_length=2, max_length=128)
    dimension_keys: list[str] = Field(default_factory=list)
    filter_keys: list[str] = Field(default_factory=list)
    canonical_intent_json: dict[str, Any] = Field(default_factory=dict)
    chart_type: str = "table_only"
    category: str = "general"
    is_active: bool = True

class ApprovedTemplateCreate(ApprovedTemplateBase):
    template_key: str = Field(min_length=2, max_length=128)

class ApprovedTemplatePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    natural_text: str | None = None
    metric_key: str | None = None
    dimension_keys: list[str] | None = None
    filter_keys: list[str] | None = None
    canonical_intent_json: dict[str, Any] | None = None
    chart_type: str | None = None
    category: str | None = None
    is_active: bool | None = None

class ApprovedTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_key: str
    title: str
    description: str
    natural_text: str
    metric_key: str
    dimension_keys: list[str] = Field(validation_alias="dimension_keys_json")
    filter_keys: list[str] = Field(validation_alias="filter_keys_json")
    canonical_intent_json: dict[str, Any]
    chart_type: str
    category: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class SemanticValidationIssueOut(BaseModel):
    level: str
    code: str
    entity_type: str
    entity_key: str
    message: str

class SemanticValidationReportOut(BaseModel):
    ok: bool
    issues: list[SemanticValidationIssueOut] = Field(default_factory=list)
