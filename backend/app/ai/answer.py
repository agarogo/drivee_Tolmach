from app.ai.types import ConfidenceResult, Interpretation, SqlPlan


def explain_interpretation(interpretation: Interpretation, plan: SqlPlan, semantic_terms: list[dict]) -> dict:
    return {
        "metric": plan.metric_label or interpretation.metric or "не определена",
        "dimensions": interpretation.dimensions,
        "dimension_labels": plan.dimension_labels,
        "period": interpretation.date_range.get("label", "не указан"),
        "filters": interpretation.filters,
        "grouping": plan.group_by,
        "sorting": plan.order_by,
        "limit": plan.limit,
        "source": interpretation.source,
        "provider_confidence": interpretation.provider_confidence,
        "fallback_used": interpretation.fallback_used,
        "semantic_terms": [item["term"] for item in semantic_terms],
        "sql_reasoning": plan.explanation,
        "chart_reasoning": (
            f"Тип графика {plan.chart_type} выбран по метрике {plan.metric_label or plan.metric} и разрезам "
            f"{', '.join(plan.dimension_labels.get(key, key) for key in plan.dimensions) or 'без разреза'}."
        ),
    }


def compose_answer(
    question: str,
    interpretation: Interpretation,
    confidence: ConfidenceResult,
    plan: SqlPlan,
    rows: list[dict],
) -> str:
    if not rows:
        return (
            "Система поняла запрос так: данных по выбранным условиям не найдено. "
            "Проверьте период или разрез и попробуйте ещё раз."
        )

    first = rows[0]
    metric = interpretation.metric or plan.metric
    metric_value = first.get(metric)
    dimension = next((key for key in first.keys() if key != metric), None)
    leader = first.get(dimension) if dimension else None
    period = interpretation.date_range.get("label", "выбранный период")
    metric_label = plan.metric_label or metric
    dimensions_label = (
        ", ".join(plan.dimension_labels.get(key, key) for key in plan.dimensions) if plan.dimensions else "без разреза"
    )

    bullets = []
    if leader is not None and metric_value is not None:
        bullets.append(f"лидер по выборке: {leader} - {metric_value}")
    elif metric_value is not None:
        bullets.append(f"{metric_label}: {metric_value}")
    bullets.append(f"строк в результате: {len(rows)}")
    bullets.append(f"confidence: {confidence.score}% ({confidence.band})")
    bullets.append(f"pipeline: {interpretation.source}")

    if metric_value is not None and leader is None:
        main = f"{metric_label} за период {period}: {metric_value}."
    elif metric_value is not None and leader is not None:
        main = f"максимальное значение в выборке: {leader} - {metric_value}."
    else:
        main = f"результат построен по {len(rows)} строкам."

    return (
        f"Система поняла запрос так: метрика = {metric_label}, разрез = {dimensions_label}, период = {period}. "
        f"Главный вывод: {main}\n"
        + "\n".join(f"- {item}" for item in bullets)
    )
