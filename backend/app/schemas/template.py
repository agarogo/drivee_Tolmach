from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    natural_text: str
    canonical_intent_json: dict[str, Any]
    category: str
    chart_type: str
    is_public: bool
    use_count: int
    created_at: datetime


class TemplateCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    natural_text: str = Field(min_length=2, max_length=2000)
    description: str = ""
    canonical_intent_json: dict[str, Any] = Field(default_factory=dict)
    category: str = "general"
    chart_type: str = "bar"
    is_public: bool = False
