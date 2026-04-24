from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.gateway.schemas import (
    AnswerSummaryDraft,
    ClarificationNeedResult,
    ClarificationOption,
    FilterSelection,
    IntentExtractionResult,
    PeriodSelection,
    SQLPlanDraft,
)
from app.ai.interpreter import interpret_query as legacy_interpret_query
from app.config import get_settings
from app.services.observability import trace_span

settings = get_settings()

StructuredModelT = TypeVar("StructuredModelT", bound=BaseModel)


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedPrompt:
    prompt_key: str
    version: str
    system_prompt: str
    user_prompt: str
    context: dict[str, Any]
    source_path: str


@dataclass(frozen=True)
class LLMCallTelemetry:
    provider: str
    model: str
    prompt_key: str
    prompt_version: str
    duration_ms: int
    attempts: int
    timeout_seconds: int
    fallback_used: bool = False
    initial_provider: str = ""
    fallback_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_key": self.prompt_key,
            "prompt_version": self.prompt_version,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "timeout_seconds": self.timeout_seconds,
            "fallback_used": self.fallback_used,
            "initial_provider": self.initial_provider,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class LLMJsonResponse:
    payload: dict[str, Any]
    raw_text: str
    provider: str
    model: str


@dataclass(frozen=True)
class LLMStructuredResponse(Generic[StructuredModelT]):
    result: StructuredModelT
    raw_text: str
    provider: str
    model: str
    telemetry: LLMCallTelemetry


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    async def generate_structured(
        self,
        prompt: RenderedPrompt,
        schema: type[StructuredModelT],
    ) -> LLMStructuredResponse[StructuredModelT]:
        ...


def _strip_code_fences(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def extract_json_payload(raw_text: str) -> dict[str, Any]:
    text = _strip_code_fences(raw_text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMProviderError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise LLMProviderError("LLM response must be a JSON object.")
    return payload


def parse_structured_response(raw_text: str, schema: type[StructuredModelT]) -> StructuredModelT:
    payload = extract_json_payload(raw_text)
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError(f"LLM JSON failed schema validation: {exc}") from exc


class BaseHTTPLLMProvider:
    provider_name = "http"

    def __init__(
        self,
        *,
        model_name: str,
        timeout_seconds: int,
        max_retries: int,
        retry_backoff_ms: int,
        temperature: float,
    ) -> None:
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, max_retries)
        self.retry_backoff_ms = max(0, retry_backoff_ms)
        self.temperature = temperature

    async def generate_structured(
        self,
        prompt: RenderedPrompt,
        schema: type[StructuredModelT],
    ) -> LLMStructuredResponse[StructuredModelT]:
        last_error: Exception | None = None
        started = time.perf_counter()
        for attempt in range(1, self.max_retries + 1):
            try:
                with trace_span(
                    "tolmach.llm_call",
                    {
                        "provider": self.provider_name,
                        "model": self.model_name,
                        "prompt_key": prompt.prompt_key,
                        "prompt_version": prompt.version,
                        "attempt": attempt,
                    },
                ):
                    raw_text = await self._request_raw_text(prompt)
                result = parse_structured_response(raw_text, schema)
                telemetry = LLMCallTelemetry(
                    provider=self.provider_name,
                    model=self.model_name,
                    prompt_key=prompt.prompt_key,
                    prompt_version=prompt.version,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    attempts=attempt,
                    timeout_seconds=self.timeout_seconds,
                )
                return LLMStructuredResponse(
                    result=result,
                    raw_text=raw_text,
                    provider=self.provider_name,
                    model=self.model_name,
                    telemetry=telemetry,
                )
            except (httpx.HTTPError, LLMProviderError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                if self.retry_backoff_ms > 0:
                    await asyncio.sleep((self.retry_backoff_ms * attempt) / 1000)
        raise LLMProviderError(f"{self.provider_name} request failed after retries: {last_error}") from last_error

    async def _request_raw_text(self, prompt: RenderedPrompt) -> str:
        timeout = httpx.Timeout(self.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self._endpoint_url(),
                json=self._request_body(prompt),
                headers=self._request_headers(),
            )
            response.raise_for_status()
        return self._extract_response_text(response.json())

    def _request_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _endpoint_url(self) -> str:
        raise NotImplementedError

    def _request_body(self, prompt: RenderedPrompt) -> dict[str, Any]:
        raise NotImplementedError

    def _extract_response_text(self, response_json: dict[str, Any]) -> str:
        raise NotImplementedError


class ProductionLLMProvider(BaseHTTPLLMProvider):
    provider_name = "production"

    def __init__(self) -> None:
        model_name = settings.production_llm_model or settings.llm_model
        if not settings.production_llm_base_url:
            raise LLMProviderError("PRODUCTION_LLM_BASE_URL must be set for ProductionLLMProvider.")
        if not settings.production_llm_api_key:
            raise LLMProviderError("PRODUCTION_LLM_API_KEY must be set for ProductionLLMProvider.")
        super().__init__(
            model_name=model_name,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            retry_backoff_ms=settings.llm_retry_backoff_ms,
            temperature=settings.llm_temperature,
        )

    def _endpoint_url(self) -> str:
        return f"{settings.production_llm_base_url.rstrip('/')}/chat/completions"

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.production_llm_api_key}",
            "Content-Type": "application/json",
        }

    def _request_body(self, prompt: RenderedPrompt) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ],
        }

    def _extract_response_text(self, response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices") or []
        content = ""
        if choices:
            message = choices[0].get("message", {})
            raw_content = message.get("content", "")
            if isinstance(raw_content, str):
                content = raw_content
            elif isinstance(raw_content, list):
                content = "".join(str(item.get("text", "")) for item in raw_content if isinstance(item, dict))
        content = content.strip()
        if not content:
            raise LLMProviderError("Production provider returned an empty response.")
        return content


class OllamaLLMProvider(BaseHTTPLLMProvider):
    provider_name = "ollama"

    def __init__(self) -> None:
        super().__init__(
            model_name=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            retry_backoff_ms=settings.llm_retry_backoff_ms,
            temperature=settings.llm_temperature,
        )

    def _endpoint_url(self) -> str:
        return f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    def _request_body(self, prompt: RenderedPrompt) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ],
            "options": {"temperature": self.temperature},
        }

    def _extract_response_text(self, response_json: dict[str, Any]) -> str:
        content = str(response_json.get("message", {}).get("content", "")).strip()
        if not content:
            raise LLMProviderError("Ollama returned an empty response.")
        return content

    async def generate_json(self, system_prompt: str, user_prompt: str) -> LLMJsonResponse:
        prompt = RenderedPrompt(
            prompt_key="compat_raw_json",
            version="v1",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context={},
            source_path="<inline>",
        )
        raw_text = await self._request_raw_text(prompt)
        return LLMJsonResponse(
            payload=extract_json_payload(raw_text),
            raw_text=raw_text,
            provider=self.provider_name,
            model=self.model_name,
        )


class FallbackRuleProvider:
    provider_name = "fallback_rule"
    model_name = "deterministic-v1"

    async def generate_structured(
        self,
        prompt: RenderedPrompt,
        schema: type[StructuredModelT],
    ) -> LLMStructuredResponse[StructuredModelT]:
        started = time.perf_counter()
        payload = self._build_payload(prompt)
        raw_text = json.dumps(payload, ensure_ascii=False)
        result = schema.model_validate(payload)
        telemetry = LLMCallTelemetry(
            provider=self.provider_name,
            model=self.model_name,
            prompt_key=prompt.prompt_key,
            prompt_version=prompt.version,
            duration_ms=int((time.perf_counter() - started) * 1000),
            attempts=1,
            timeout_seconds=0,
            fallback_used=True,
            initial_provider=self.provider_name,
        )
        return LLMStructuredResponse(
            result=result,
            raw_text=raw_text,
            provider=self.provider_name,
            model=self.model_name,
            telemetry=telemetry,
        )

    def _build_payload(self, prompt: RenderedPrompt) -> dict[str, Any]:
        if prompt.prompt_key == "intent_extraction":
            return self._intent_payload(prompt.context)
        if prompt.prompt_key == "clarification_need":
            return self._clarification_payload(prompt.context)
        if prompt.prompt_key == "sql_plan_draft":
            return self._plan_payload(prompt.context)
        if prompt.prompt_key == "answer_summary":
            return self._summary_payload(prompt.context)
        raise LLMProviderError(f"FallbackRuleProvider does not support prompt key {prompt.prompt_key}.")

    def _intent_payload(self, context: dict[str, Any]) -> dict[str, Any]:
        interpretation = legacy_interpret_query(str(context.get("question", "")))
        return IntentExtractionResult(
            metric_key=interpretation.metric,
            dimension_keys=list(interpretation.dimensions),
            filters=[
                FilterSelection(
                    dimension_key=str(filter_key),
                    operator=str(filter_value.get("operator", "eq")),
                    values=[str(item) for item in filter_value.get("values", [])],
                )
                for filter_key, filter_value in (interpretation.filters or {}).items()
            ],
            period=PeriodSelection(**(interpretation.date_range or {"kind": "missing", "label": "period not specified"})),
            limit=interpretation.limit,
            sort_direction=str((interpretation.sorting or {}).get("direction", "desc")),
            ambiguities=list(interpretation.ambiguity_flags),
            confidence=0.45 if interpretation.metric else 0.2,
            reasoning="Rule-based fallback extracted the intent without a live LLM.",
        ).model_dump(mode="json")

    def _clarification_payload(self, context: dict[str, Any]) -> dict[str, Any]:
        intent_result = IntentExtractionResult.model_validate(context.get("intent_result") or {})
        ambiguities = list(intent_result.ambiguities)
        needs_clarification = bool(ambiguities or not intent_result.metric_key)
        options = [
            ClarificationOption(
                label="Revenue by city",
                value="revenue_by_city",
                description="Use revenue grouped by city.",
            ),
            ClarificationOption(
                label="Completed trips by day",
                value="completed_trips_by_day",
                description="Use completed trips grouped by day.",
            ),
        ]
        return ClarificationNeedResult(
            needs_clarification=needs_clarification,
            question="Clarify the metric, period, or breakdown." if needs_clarification else "",
            options=options[: 2 if needs_clarification else 0],
            ambiguities=ambiguities or (["Metric is missing."] if not intent_result.metric_key else []),
            confidence=max(0.0, min(intent_result.confidence, 1.0)),
            reasoning="Fallback clarification planner derived options from deterministic heuristics.",
        ).model_dump(mode="json")

    def _plan_payload(self, context: dict[str, Any]) -> dict[str, Any]:
        intent_result = self._coerce_intent_result(context)
        catalog = context.get("catalog")
        metric = catalog.get_metric(intent_result.metric_key) if catalog and intent_result.metric_key else None
        chart_preference = "line" if "day" in intent_result.dimension_keys else (metric.default_chart if metric else "table_only")
        return SQLPlanDraft(
            metric_key=intent_result.metric_key or "unknown_metric",
            dimension_keys=list(intent_result.dimension_keys),
            filters=list(intent_result.filters),
            period=intent_result.period,
            limit=intent_result.limit,
            sort_direction=intent_result.sort_direction,
            chart_preference=chart_preference,
            grain=metric.grain if metric else None,
            safety_notes=[
                "Fallback rule provider produced this intermediate plan.",
                "Server-side semantic compilation and SQL validation remain mandatory.",
            ],
            confidence=max(0.25, min(intent_result.confidence, 0.6)),
            reasoning="Fallback plan mirrors the deterministic intent extraction.",
        ).model_dump(mode="json")

    def _coerce_intent_result(self, context: dict[str, Any]) -> IntentExtractionResult:
        raw_intent = context.get("intent_result") or {}
        if raw_intent:
            return IntentExtractionResult.model_validate(raw_intent)
        resolved_intent = context.get("resolved_intent") or {}
        filters = []
        for dimension_key, filter_value in (resolved_intent.get("filters") or {}).items():
            filters.append(
                FilterSelection(
                    dimension_key=str(dimension_key),
                    operator=str(filter_value.get("operator", "eq")),
                    values=[str(item) for item in filter_value.get("values", [])],
                )
            )
        period = resolved_intent.get("date_range") or {"kind": "missing", "label": "period not specified"}
        return IntentExtractionResult(
            metric_key=resolved_intent.get("metric"),
            dimension_keys=list(resolved_intent.get("dimensions") or []),
            filters=filters,
            period=PeriodSelection(**period),
            limit=resolved_intent.get("limit"),
            sort_direction=str((resolved_intent.get("sorting") or {}).get("direction", "desc")),
            ambiguities=list(resolved_intent.get("ambiguity_flags") or []),
            confidence=max(0.0, min(float(resolved_intent.get("provider_confidence") or 0.4), 1.0)),
            reasoning=str(resolved_intent.get("reasoning") or "Resolved interpretation converted into a fallback plan."),
        )

    def _summary_payload(self, context: dict[str, Any]) -> dict[str, Any]:
        rows = list(context.get("rows") or [])
        metric_label = str(context.get("metric_label") or context.get("metric_key") or "metric")
        if not rows:
            return AnswerSummaryDraft(
                headline="No data returned",
                summary="The executed query returned no rows for the requested slice.",
                highlights=["Row count: 0"],
                caveats=["Summary generated by fallback provider."],
            ).model_dump(mode="json")
        metric_key = str(context.get("metric_key") or "")
        columns: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row.keys():
                key_str = str(key)
                if key_str not in seen:
                    seen.add(key_str)
                    columns.append(key_str)
        numeric_values = []
        if metric_key:
            for row in rows:
                value = row.get(metric_key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    numeric_values.append(float(value))
        highlights = [f"Row count: {len(rows)}"]
        if columns:
            highlights.append(f"Visible columns: {', '.join(columns[:6])}")
        if numeric_values:
            highlights.append(f"{metric_label} min/max: {min(numeric_values)} / {max(numeric_values)}")
        return AnswerSummaryDraft(
            headline=f"{metric_label} summary",
            summary=f"Summary derived strictly from {len(rows)} factual result rows.",
            highlights=highlights,
            caveats=["Fallback provider generated a deterministic answer summary."],
        ).model_dump(mode="json")
