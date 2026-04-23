from app.ai.types import ConfidenceResult, Interpretation, RetrievalResult


def score_confidence(interpretation: Interpretation, retrieval: RetrievalResult) -> ConfidenceResult:
    if interpretation.dangerous:
        return ConfidenceResult(
            score=0,
            band="low",
            reasons=["Запрос содержит write/DDL операцию и не может быть выполнен."],
            ambiguities=[],
        )

    score = max(25, int(round(max(0.0, min(interpretation.provider_confidence, 1.0)) * 55)) + 15)
    reasons: list[str] = []
    ambiguities = list(interpretation.ambiguity_flags)

    if interpretation.metric:
        score += 18
        reasons.append(f"Метрика распознана: {interpretation.metric}.")
    if interpretation.dimensions:
        score += 10
        reasons.append("Разрез распознан: " + ", ".join(interpretation.dimensions) + ".")
    elif interpretation.metric:
        score += 15
        reasons.append("Распознан общий итог без разреза.")
    if interpretation.date_range.get("kind") != "missing" or interpretation.metric == "active_drivers":
        score += 15
        reasons.append(f"Период распознан: {interpretation.date_range.get('label', 'не указан')}.")
    if retrieval.semantic_terms:
        score += min(12, len(retrieval.semantic_terms) * 3)
        reasons.append("Найдены совпадения в semantic layer.")
    if retrieval.examples:
        score += min(8, len(retrieval.examples) * 2)
        reasons.append("Найдены few-shot примеры похожих запросов.")
    if interpretation.top:
        score += 5
        reasons.append(f"Лимит top-{interpretation.top} распознан явно.")
    if (
        interpretation.metric
        and (interpretation.dimensions or interpretation.limit == 1)
        and interpretation.date_range.get("kind") != "missing"
        and not ambiguities
    ):
        score += 12
        reasons.append("Метрика, разрез/итог и период согласованы без неоднозначностей.")
    if interpretation.source == "llm_structured":
        reasons.append("Основной pipeline использовал structured LLM intent parsing.")
    if interpretation.fallback_used:
        score -= 10
        reasons.append("Использован fallback path: confidence снижена.")
    if interpretation.reasoning:
        reasons.append(f"AI reasoning: {interpretation.reasoning}")

    score -= min(35, len(ambiguities) * 12)
    score = max(0, min(100, score))

    if score >= 85 and not ambiguities:
        band = "high"
    elif score >= 55:
        band = "medium"
    else:
        band = "low"

    if not reasons:
        reasons.append("Недостаточно совпадений с бизнес-словарём.")

    return ConfidenceResult(score=score, band=band, reasons=reasons, ambiguities=ambiguities)
