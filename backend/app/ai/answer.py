from app.ai.types import ConfidenceResult, Interpretation, SqlPlan


METRIC_LABELS = {
    "revenue": "выручка",
    "orders_count": "заказы",
    "completed_trips": "поездки",
    "client_cancellations": "отмены клиентом",
    "driver_cancellations": "отмены водителем",
    "avg_check": "средний чек",
    "active_drivers": "активные водители",
    "tender_decline_rate": "доля decline тендеров",
}


def explain_interpretation(interpretation: Interpretation, plan: SqlPlan, semantic_terms: list[dict]) -> dict:
    return {
        "metric": interpretation.metric or "не определена",
        "dimensions": interpretation.dimensions,
        "period": interpretation.date_range.get("label", "не указан"),
        "filters": interpretation.filters,
        "grouping": plan.group_by,
        "sorting": plan.order_by,
        "limit": plan.limit,
        "semantic_terms": [item["term"] for item in semantic_terms],
        "sql_reasoning": plan.explanation,
        "chart_reasoning": f"Тип графика {plan.chart_type} выбран по метрике {plan.metric} и разрезам {', '.join(plan.dimensions) or 'без разреза'}.",
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
    if interpretation.date_range.get("kind") == "missing" and metric == "active_drivers":
        period = "весь доступный период"
    metric_label = METRIC_LABELS.get(metric, metric)
    dimensions_label = ", ".join(plan.dimensions) if plan.dimensions else "без разреза"

    bullets = []
    if leader is not None and metric_value is not None:
        bullets.append(f"лидер по выборке: {leader} — {metric_value}")
    elif metric_value is not None:
        bullets.append(f"{metric_label}: {metric_value}")
    bullets.append(f"строк в результате: {len(rows)}")
    bullets.append(f"confidence: {confidence.score}% ({confidence.band})")

    if metric_value is not None and leader is None:
        main = f"{metric_label} за период {period}: {metric_value}."
    elif metric_value is not None and leader is not None:
        main = f"максимальное значение в выборке: {leader} — {metric_value}."
    else:
        main = f"результат построен по {len(rows)} строкам."

    return (
        f"Система поняла запрос так: метрика = {metric_label}, разрез = {dimensions_label}, период = {period}. "
        f"Главный вывод: {main}\n"
        + "\n".join(f"- {item}" for item in bullets)
    )
