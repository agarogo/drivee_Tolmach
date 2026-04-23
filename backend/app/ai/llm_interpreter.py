from __future__ import annotations

from app.ai.gateway.schemas import ClarificationNeedResult, IntentExtractionResult, SQLPlanDraft
from app.ai.gateway.service import (
    GatewayStageResult,
    build_clarification_with_ai,
    draft_sql_plan_with_ai,
    extract_intent_with_ai,
    intent_result_to_interpretation,
    sql_plan_draft_to_interpretation,
)
from app.ai.interpreter import DANGEROUS_RE
from app.ai.types import Interpretation, RetrievalResult
from app.semantic.service import SemanticCatalog


def _dangerous_interpretation(question: str, matched_text: str) -> Interpretation:
    return Interpretation(
        intent="dangerous_operation",
        metric="blocked_operation",
        date_range={"kind": "missing", "label": "period not specified"},
        ambiguity_flags=[],
        dangerous=True,
        dangerous_reason=f"Potential write/DDL operation detected: {matched_text}",
        source="guardrail_precheck",
        provider_confidence=0.0,
    )


async def extract_intent_stage(
    question: str,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> GatewayStageResult[IntentExtractionResult] | None:
    dangerous_match = DANGEROUS_RE.search(question)
    if dangerous_match:
        return None
    return await extract_intent_with_ai(question, retrieval, catalog)


async def clarification_stage(
    question: str,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
    intent_result: IntentExtractionResult,
) -> GatewayStageResult[ClarificationNeedResult]:
    return await build_clarification_with_ai(question, retrieval, catalog, intent_result)


async def sql_plan_draft_stage(
    question: str,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
    interpretation: Interpretation,
) -> GatewayStageResult[SQLPlanDraft]:
    return await draft_sql_plan_with_ai(question, retrieval, catalog, interpretation)


async def interpret_with_ai(question: str, retrieval: RetrievalResult, catalog: SemanticCatalog) -> Interpretation:
    dangerous_match = DANGEROUS_RE.search(question)
    if dangerous_match:
        return _dangerous_interpretation(question, dangerous_match.group(0))

    intent_stage = await extract_intent_with_ai(question, retrieval, catalog)
    interpretation = intent_result_to_interpretation(
        intent_stage.structured,
        catalog,
        source=f"llm_gateway:intent_extraction@{intent_stage.response.telemetry.prompt_version}",
        fallback_used=intent_stage.response.telemetry.fallback_used,
    )
    interpretation.reasoning = (
        interpretation.reasoning
        or f"provider={intent_stage.response.provider}; model={intent_stage.response.model}"
    )
    if interpretation.ambiguity_flags:
        clarification = await build_clarification_with_ai(question, retrieval, catalog, intent_stage.structured)
        interpretation.clarification_question = clarification.structured.question
        interpretation.clarification_options = [
            option.model_dump(mode="json") for option in clarification.structured.options
        ]
        if clarification.structured.ambiguities:
            interpretation.ambiguity_flags = list(
                dict.fromkeys(interpretation.ambiguity_flags + clarification.structured.ambiguities)
            )
    return interpretation


__all__ = [
    "clarification_stage",
    "extract_intent_stage",
    "interpret_with_ai",
    "sql_plan_draft_stage",
    "sql_plan_draft_to_interpretation",
]
