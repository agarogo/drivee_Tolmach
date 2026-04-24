from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import json
import logging
import re
from typing import Any, Generic, TypeVar

from app.ai.gateway.prompts import PromptRegistry, get_prompt_registry
from app.ai.gateway.providers import (
    FallbackRuleProvider,
    LLMProvider,
    LLMProviderError,
    LLMStructuredResponse,
    OllamaLLMProvider,
    ProductionLLMProvider,
    RenderedPrompt,
)
from app.ai.gateway.schemas import (
    AnswerTypeClassificationResult,
    AnswerSummaryDraft,
    ClarificationNeedResult,
    IntentExtractionResult,
    PeriodSelection,
    SQLPlanDraft,
)
from app.ai.interpreter import DANGEROUS_RE
from app.ai.types import Interpretation, RetrievalResult, SqlPlan
from app.config import get_settings
from app.semantic.errors import ClarificationCode, build_clarification_reason
from app.semantic.service import SemanticCatalog

settings = get_settings()
logger = logging.getLogger(__name__)
StructuredModelT = TypeVar(
    "StructuredModelT",
    AnswerTypeClassificationResult,
    IntentExtractionResult,
    ClarificationNeedResult,
    SQLPlanDraft,
    AnswerSummaryDraft,
)


@dataclass(frozen=True)
class GatewayStageResult(Generic[StructuredModelT]):
    structured: StructuredModelT
    response: LLMStructuredResponse[StructuredModelT]

    def as_dict(self) -> dict[str, Any]:
        return {
            "structured": self.structured.model_dump(mode="json"),
            "telemetry": self.response.telemetry.as_dict(),
            "provider": self.response.provider,
            "model": self.response.model,
        }


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    return None


def normalize_period_selection(period: PeriodSelection) -> dict[str, Any]:
    if period.kind == "rolling_days" and period.days:
        return {"kind": "rolling_days", "days": max(1, min(period.days, 365)), "label": period.label or f"last {period.days} days"}
    if period.kind == "since_date":
        start = _normalize_date(period.start)
        if start:
            return {"kind": "since_date", "start": start, "label": period.label or f"since {start}"}
    if period.kind == "until_date":
        end = _normalize_date(period.end)
        if end:
            return {"kind": "until_date", "end": end, "label": period.label or f"until {end}"}
    if period.kind == "exact_date":
        exact = _normalize_date(period.date)
        if exact:
            return {"kind": "exact_date", "date": exact, "label": period.label or exact}
    if period.kind == "between_dates":
        start = _normalize_date(period.start)
        end = _normalize_date(period.end)
        if start and end:
            return {"kind": "between_dates", "start": start, "end": end, "label": period.label or f"{start}..{end}"}
    return {"kind": "missing", "label": period.label or "period not specified"}


def _normalize_filters(filters: list[Any], catalog: SemanticCatalog) -> tuple[dict[str, Any], list[str]]:
    normalized: dict[str, Any] = {}
    ambiguities: list[str] = []
    for item in filters:
        dimension_key = str(item.dimension_key)
        if dimension_key not in catalog.dimensions and dimension_key not in catalog.filters:
            ambiguities.append(f"Filter {dimension_key} is missing in the semantic layer.")
            continue
        normalized[dimension_key] = {
            "operator": item.operator,
            "values": [value for value in item.values if value],
        }
    return normalized, ambiguities


def _clarification_reasons(
    *,
    metric_key: str | None,
    raw_metric_key: str | None,
    dimension_keys: list[str],
    raw_dimension_keys: list[str],
    filters: dict[str, Any],
    raw_filter_keys: list[str],
    ambiguities: list[str],
    period_kind: str,
) -> list[dict[str, Any]]:
    reasons = []
    if not metric_key:
        code = ClarificationCode.METRIC_REQUIRED if not raw_metric_key else ClarificationCode.METRIC_NOT_IN_CATALOG
        reasons.append(
            build_clarification_reason(
                code,
                "Metric is missing or not governed by the semantic catalog.",
                details={"metric_key": raw_metric_key or ""},
            ).as_dict()
        )
    missing_dimensions = sorted(set(raw_dimension_keys) - set(dimension_keys))
    for dimension_key in missing_dimensions:
        reasons.append(
            build_clarification_reason(
                ClarificationCode.DIMENSION_NOT_IN_CATALOG,
                f"Dimension {dimension_key} is not governed by the semantic catalog.",
                details={"dimension_key": dimension_key},
            ).as_dict()
        )
    missing_filters = sorted(set(raw_filter_keys) - set(filters))
    for filter_key in missing_filters:
        reasons.append(
            build_clarification_reason(
                ClarificationCode.FILTER_NOT_IN_CATALOG,
                f"Filter {filter_key} is not governed by the semantic catalog.",
                details={"filter_key": filter_key},
            ).as_dict()
        )
    if period_kind == "missing":
        reasons.append(
            build_clarification_reason(
                ClarificationCode.PERIOD_REQUIRED,
                "Period is missing; the result may be too broad without clarification.",
            ).as_dict()
        )
    for ambiguity in ambiguities:
        reasons.append(
            build_clarification_reason(
                ClarificationCode.AMBIGUOUS_REQUEST,
                ambiguity,
                details={"ambiguity": ambiguity},
            ).as_dict()
        )
    return reasons


def intent_result_to_interpretation(
    result: IntentExtractionResult,
    catalog: SemanticCatalog,
    *,
    source: str,
    fallback_used: bool,
) -> Interpretation:
    ambiguities = list(result.ambiguities)
    metric_key = result.metric_key if result.metric_key in catalog.metrics else None
    if result.metric_key and metric_key is None:
        ambiguities.append(f"Metric {result.metric_key} is missing in the semantic layer.")
    dimension_keys: list[str] = []
    for key in result.dimension_keys:
        if key in catalog.dimensions:
            dimension_keys.append(key)
        else:
            ambiguities.append(f"Dimension {key} is missing in the semantic layer.")
    filters, filter_ambiguities = _normalize_filters(result.filters, catalog)
    ambiguities.extend(filter_ambiguities)
    if not metric_key:
        ambiguities.append("Metric is not recognized.")
    clarification_options = []
    if ambiguities:
        clarification_options = [
            {"label": "Revenue by city", "value": "revenue_by_city", "description": "Use revenue grouped by city."},
            {"label": "Completed trips by day", "value": "completed_trips_by_day", "description": "Use completed trips grouped by day."},
        ]
    clarification_reasons = _clarification_reasons(
        metric_key=metric_key,
        raw_metric_key=result.metric_key,
        dimension_keys=dimension_keys,
        raw_dimension_keys=result.dimension_keys,
        filters=filters,
        raw_filter_keys=[item.dimension_key for item in result.filters],
        ambiguities=ambiguities,
        period_kind=result.period.kind,
    )
    return Interpretation(
        intent="analytics",
        metric=metric_key,
        dimensions=dimension_keys,
        filters=filters,
        date_range=normalize_period_selection(result.period),
        grouping=dimension_keys,
        sorting={"by": metric_key or "", "direction": result.sort_direction},
        top=result.limit if result.limit and result.limit <= 20 else None,
        limit=max(1, min(result.limit or (20 if dimension_keys else 1), settings.max_result_rows)),
        ambiguity_flags=list(dict.fromkeys(ambiguities)),
        clarification_question="Clarify the metric, period, or breakdown." if ambiguities else "",
        clarification_options=clarification_options,
        reasoning=result.reasoning.strip(),
        source=source,
        provider_confidence=max(0.0, min(float(result.confidence or 0.0), 1.0)),
        fallback_used=fallback_used,
        clarification_reasons=clarification_reasons,
    )


def sql_plan_draft_to_interpretation(
    draft: SQLPlanDraft,
    catalog: SemanticCatalog,
    *,
    source: str,
    fallback_used: bool,
) -> Interpretation:
    intent_result = IntentExtractionResult(
        metric_key=draft.metric_key,
        dimension_keys=draft.dimension_keys,
        filters=draft.filters,
        period=draft.period,
        limit=draft.limit,
        sort_direction=draft.sort_direction,
        ambiguities=[],
        confidence=draft.confidence,
        reasoning=draft.reasoning,
    )
    interpretation = intent_result_to_interpretation(
        intent_result,
        catalog,
        source=source,
        fallback_used=fallback_used,
    )
    interpretation.reasoning = draft.reasoning.strip()
    return interpretation


def render_answer_summary(draft: AnswerSummaryDraft, fallback_text: str) -> str:
    lines: list[str] = []
    if draft.headline:
        lines.append(draft.headline)
    if draft.summary:
        lines.append(draft.summary)
    lines.extend(f"- {item}" for item in draft.highlights if item)
    lines.extend(f"- Caveat: {item}" for item in draft.caveats if item)
    rendered = "\n".join(line for line in lines if line).strip()
    return rendered or fallback_text


def interpretation_to_intent_payload(interpretation: Interpretation) -> dict[str, Any]:
    return {
        "metric_key": interpretation.metric,
        "dimension_keys": list(interpretation.dimensions),
        "filters": [
            {
                "dimension_key": filter_key,
                "operator": str(filter_value.get("operator", "eq")),
                "values": [str(item) for item in filter_value.get("values", [])],
            }
            for filter_key, filter_value in (interpretation.filters or {}).items()
        ],
        "period": interpretation.date_range or {"kind": "missing", "label": "period not specified"},
        "limit": interpretation.limit,
        "sort_direction": str((interpretation.sorting or {}).get("direction", "desc")),
        "ambiguities": list(interpretation.ambiguity_flags),
        "confidence": max(0.0, min(float(interpretation.provider_confidence or 0.0), 1.0)),
        "reasoning": interpretation.reasoning,
    }


def _primary_provider() -> LLMProvider:
    provider_name = settings.llm_provider.strip().lower()
    if provider_name == "production":
        return ProductionLLMProvider()
    if provider_name == "ollama":
        return OllamaLLMProvider()
    if provider_name in {"fallback_rule", "fallback"}:
        if not settings.llm_fallback_allowed:
            raise LLMProviderError(
                "Fallback provider is disabled when APP_ENV is demo/production or LLM_STRICT_MODE=true."
            )
        return FallbackRuleProvider()
    raise LLMProviderError(f"Unsupported LLM_PROVIDER value: {settings.llm_provider}")


class AIGateway:
    def __init__(
        self,
        *,
        prompt_registry: PromptRegistry | None = None,
        primary_provider: LLMProvider | None = None,
        fallback_provider: LLMProvider | None = None,
        allow_rule_fallback: bool | None = None,
    ) -> None:
        self.prompt_registry = prompt_registry or get_prompt_registry()
        self.primary_provider = primary_provider or _primary_provider()
        if fallback_provider is not None:
            self.fallback_provider: LLMProvider | None = fallback_provider
        else:
            fallback_enabled = settings.llm_fallback_allowed if allow_rule_fallback is None else allow_rule_fallback
            self.fallback_provider = FallbackRuleProvider() if fallback_enabled else None

    async def _run_stage(
        self,
        *,
        prompt_key: str,
        schema: type[StructuredModelT],
        context: dict[str, Any],
    ) -> GatewayStageResult[StructuredModelT]:
        prompt_definition = self.prompt_registry.get(prompt_key)
        system_prompt, user_prompt = prompt_definition.render(context)
        rendered_prompt = RenderedPrompt(
            prompt_key=prompt_key,
            version=prompt_definition.version,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context=context,
            source_path=str(prompt_definition.path),
        )
        try:
            response = await self.primary_provider.generate_structured(rendered_prompt, schema)
        except LLMProviderError as exc:
            if not settings.llm_fallback_allowed or self.fallback_provider is None:
                logger.error(
                    "LLM stage failed without rule fallback: prompt_key=%s provider=%s reason=%s",
                    prompt_key,
                    getattr(self.primary_provider, "provider_name", ""),
                    exc,
                )
                raise
            logger.warning(
                "LLM stage fell back to deterministic provider: prompt_key=%s provider=%s reason=%s",
                prompt_key,
                getattr(self.primary_provider, "provider_name", ""),
                exc,
            )
            try:
                response = await self.fallback_provider.generate_structured(rendered_prompt, schema)
            except LLMProviderError as fallback_exc:
                raise fallback_exc.with_context(
                    fallback_used=True,
                    message=fallback_exc.message,
                ) from fallback_exc
            response = replace(
                response,
                telemetry=replace(
                    response.telemetry,
                    initial_provider=getattr(self.primary_provider, "provider_name", ""),
                    fallback_reason=str(exc),
                ),
            )
        return GatewayStageResult(structured=response.result, response=response)

    async def classify_answer_type(
        self,
        question: str,
        chat_context: dict[str, Any] | None,
        retrieval: RetrievalResult,
    ) -> GatewayStageResult[AnswerTypeClassificationResult]:
        return await self._run_stage(
            prompt_key="answer_type_classifier",
            schema=AnswerTypeClassificationResult,
            context={
                "question": question,
                "chat_context_json": _safe_json(chat_context or {}),
                "matched_semantic_terms_json": _safe_json(retrieval.semantic_terms[:8]),
                "templates_json": _safe_json(retrieval.templates[:3]),
                "examples_json": _safe_json(retrieval.examples[:3]),
            },
        )

    async def extract_intent(
        self,
        question: str,
        retrieval: RetrievalResult,
        catalog: SemanticCatalog,
    ) -> GatewayStageResult[IntentExtractionResult]:
        return await self._run_stage(
            prompt_key="intent_extraction",
            schema=IntentExtractionResult,
            context={
                "question": question,
                "catalog_summary_json": _safe_json(catalog.prompt_summary()),
                "matched_semantic_terms_json": _safe_json(retrieval.semantic_terms[:8]),
                "templates_json": _safe_json(retrieval.templates[:3]),
                "examples_json": _safe_json(retrieval.examples[:3]),
                "planner_candidates_json": _safe_json(retrieval.planner_candidates[:8]),
                "catalog": catalog,
            },
        )

    async def build_clarification(
        self,
        question: str,
        retrieval: RetrievalResult,
        catalog: SemanticCatalog,
        intent_result: IntentExtractionResult,
    ) -> GatewayStageResult[ClarificationNeedResult]:
        return await self._run_stage(
            prompt_key="clarification_need",
            schema=ClarificationNeedResult,
            context={
                "question": question,
                "intent_result_json": _safe_json(intent_result.model_dump(mode="json")),
                "matched_semantic_terms_json": _safe_json(retrieval.semantic_terms[:8]),
                "templates_json": _safe_json(retrieval.templates[:3]),
                "examples_json": _safe_json(retrieval.examples[:3]),
                "planner_candidates_json": _safe_json(retrieval.planner_candidates[:8]),
                "catalog_summary_json": _safe_json(catalog.prompt_summary()),
                "intent_result": intent_result.model_dump(mode="json"),
                "catalog": catalog,
            },
        )

    async def draft_sql_plan(
        self,
        question: str,
        retrieval: RetrievalResult,
        catalog: SemanticCatalog,
        interpretation: Interpretation,
    ) -> GatewayStageResult[SQLPlanDraft]:
        return await self._run_stage(
            prompt_key="sql_plan_draft",
            schema=SQLPlanDraft,
            context={
                "question": question,
                "resolved_intent_json": _safe_json(interpretation.as_dict()),
                "catalog_summary_json": _safe_json(catalog.prompt_summary()),
                "matched_semantic_terms_json": _safe_json(retrieval.semantic_terms[:8]),
                "examples_json": _safe_json(retrieval.examples[:3]),
                "templates_json": _safe_json(retrieval.templates[:3]),
                "planner_candidates_json": _safe_json(retrieval.planner_candidates[:8]),
                "intent_result": interpretation_to_intent_payload(interpretation),
                "resolved_intent": interpretation.as_dict(),
                "catalog": catalog,
            },
        )

    async def build_answer_summary(
        self,
        *,
        question: str,
        interpretation: Interpretation,
        llm_plan_draft: SQLPlanDraft,
        compiled_plan: SqlPlan,
        rows: list[dict[str, Any]],
        confidence_score: int,
        confidence_band: str,
        semantic_terms: list[dict[str, Any]],
    ) -> GatewayStageResult[AnswerSummaryDraft]:
        return await self._run_stage(
            prompt_key="answer_summary",
            schema=AnswerSummaryDraft,
            context={
                "question": question,
                "resolved_request_json": _safe_json(interpretation.as_dict()),
                "llm_plan_draft_json": _safe_json(llm_plan_draft.model_dump(mode="json")),
                "compiled_plan_json": _safe_json(compiled_plan.as_dict()),
                "row_count": len(rows),
                "rows_sample_json": _safe_json(rows[:25]),
                "confidence_score": confidence_score,
                "confidence_band": confidence_band,
                "semantic_terms_json": _safe_json(semantic_terms[:8]),
                "metric_key": compiled_plan.metric,
                "metric_label": compiled_plan.metric_label or compiled_plan.metric,
                "rows": rows[:25],
            },
        )


def create_ai_gateway() -> AIGateway:
    return AIGateway()


def create_classifier_gateway() -> AIGateway:
    return AIGateway(allow_rule_fallback=False)


async def classify_answer_type_with_ai(
    question: str,
    chat_context: dict[str, Any] | None,
    retrieval: RetrievalResult,
) -> GatewayStageResult[AnswerTypeClassificationResult]:
    return await create_classifier_gateway().classify_answer_type(question, chat_context, retrieval)


async def extract_intent_with_ai(
    question: str,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> GatewayStageResult[IntentExtractionResult]:
    return await create_ai_gateway().extract_intent(question, retrieval, catalog)


async def build_clarification_with_ai(
    question: str,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
    intent_result: IntentExtractionResult,
) -> GatewayStageResult[ClarificationNeedResult]:
    return await create_ai_gateway().build_clarification(question, retrieval, catalog, intent_result)


async def draft_sql_plan_with_ai(
    question: str,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
    interpretation: Interpretation,
) -> GatewayStageResult[SQLPlanDraft]:
    return await create_ai_gateway().draft_sql_plan(question, retrieval, catalog, interpretation)


async def build_answer_summary_with_ai(
    *,
    question: str,
    interpretation: Interpretation,
    llm_plan_draft: SQLPlanDraft,
    compiled_plan: SqlPlan,
    rows: list[dict[str, Any]],
    confidence_score: int,
    confidence_band: str,
    semantic_terms: list[dict[str, Any]],
) -> GatewayStageResult[AnswerSummaryDraft]:
    return await create_ai_gateway().build_answer_summary(
        question=question,
        interpretation=interpretation,
        llm_plan_draft=llm_plan_draft,
        compiled_plan=compiled_plan,
        rows=rows,
        confidence_score=confidence_score,
        confidence_band=confidence_band,
        semantic_terms=semantic_terms,
    )
