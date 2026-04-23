from app.ai.types import ConfidenceResult, Interpretation, RetrievalResult


def score_confidence(interpretation: Interpretation, retrieval: RetrievalResult) -> ConfidenceResult:
    if interpretation.dangerous:
        return ConfidenceResult(
            score=0,
            band="low",
            reasons=["Запрос содержит write/DDL операцию и не может быть выполнен."],
            ambiguities=[],
        )

    score = 25
    reasons: list[str] = []
    ambiguities = list(interpretation.ambiguity_flags)

    if interpretation.metric:
        score += 30
        reasons.append(f"Метрика распознана: {interpretation.metric}.")
    if interpretation.dimensions:
        score += 15
        reasons.append("Разрез распознан: " + ", ".join(interpretation.dimensions) + ".")
    elif interpretation.metric:
        score += 15
        reasons.append("Распознан общий итог без разреза.")
    if interpretation.date_range.get("kind") != "missing" or interpretation.metric == "active_drivers":
        score += 20
        reasons.append(f"Период распознан: {interpretation.date_range.get('label', 'не указан')}.")
    if retrieval.semantic_terms:
        score += min(20, len(retrieval.semantic_terms) * 4)
        reasons.append("Найдены совпадения в semantic layer.")
    if retrieval.examples:
        score += min(10, len(retrieval.examples) * 3)
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
        score += 10
        reasons.append("Метрика, разрез/итог и период согласованы без неоднозначностей.")

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
