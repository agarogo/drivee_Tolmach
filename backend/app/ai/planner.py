from app.ai.types import Interpretation, RetrievalResult, SqlPlan


METRIC_EXPRESSIONS = {
    "revenue": "SUM(mo.price_order_local) FILTER (WHERE mo.status_order = 'done')",
    "orders_count": "COUNT(DISTINCT mo.order_id)",
    "completed_trips": "COUNT(DISTINCT mo.order_id) FILTER (WHERE mo.status_order = 'done')",
    "client_cancellations": "COUNT(DISTINCT mo.order_id) FILTER (WHERE mo.clientcancel_timestamp IS NOT NULL)",
    "driver_cancellations": "COUNT(DISTINCT mo.order_id) FILTER (WHERE mo.drivercancel_timestamp IS NOT NULL)",
    "avg_check": "ROUND(AVG(mo.price_order_local) FILTER (WHERE mo.status_order = 'done'), 2)",
    "active_drivers": "COUNT(DISTINCT mo.driver_id) FILTER (WHERE mo.status_order = 'done')",
    "tender_decline_rate": "ROUND(100 * AVG(CASE WHEN mt.status_tender = 'decline' THEN 1 ELSE 0 END), 2)",
}


def build_plan(interpretation: Interpretation, retrieval: RetrievalResult) -> SqlPlan:
    metric = interpretation.metric or "orders_count"
    dimensions = interpretation.dimensions

    if metric == "kpi":
        return SqlPlan(
            metric=metric,
            metric_expression="multi_kpi",
            source_table="mart_orders mo",
            dimensions=["day"],
            joins=[],
            filters=[],
            group_by=["DATE(mo.order_timestamp)"],
            order_by="day ASC",
            limit=min(interpretation.limit, 100),
            chart_type="line",
            explanation=[
                "KPI строится на уровне уникального order_id через mart_orders.",
                "Дневная группировка выбрана для динамики.",
                "Выручка считается только по status_order = 'done'.",
            ],
        )

    source_table = "mart_tenders mt" if metric == "tender_decline_rate" else "mart_orders mo"
    joins: list[str] = []
    group_by: list[str] = []
    explanation: list[str] = []
    chart_type = "bar" if dimensions else "table_only"

    if "city" in dimensions:
        table_alias = "mt" if metric == "tender_decline_rate" else "mo"
        joins.append(f"JOIN cities c ON c.city_id = {table_alias}.city_id")
        group_by.append("c.name")
        explanation.append("Город берётся из справочника cities через city_id.")
    if "day" in dimensions:
        time_field = "mt.tender_timestamp" if metric == "tender_decline_rate" else "mo.order_timestamp"
        group_by.append(f"DATE({time_field})")
        chart_type = "line"
        explanation.append("Для динамики используется дневная группировка.")
    if "driver" in dimensions and metric != "active_drivers":
        joins.append("JOIN drivers d ON d.driver_id = mo.driver_id")
        group_by.append("d.driver_id")
        explanation.append("Водитель берётся из справочника drivers.")
    if metric == "active_drivers":
        source_table = "mart_orders mo"
        if "city" in dimensions and not joins:
            joins = ["JOIN cities c ON c.city_id = mo.city_id"]
            group_by = ["c.name"]
            chart_type = "bar"
        explanation.append("Активные водители считаются по фактическим завершённым поездкам из mart_orders.")
    if not dimensions:
        explanation.append("Пользователь запросил общий итог без разрезов, поэтому GROUP BY не используется.")

    metric_expression = METRIC_EXPRESSIONS.get(metric, METRIC_EXPRESSIONS["orders_count"])
    if retrieval.semantic_terms:
        explanation.append(
            "Использованы термины semantic layer: "
            + ", ".join(item["term"] for item in retrieval.semantic_terms[:4])
            + "."
        )

    return SqlPlan(
        metric=metric,
        metric_expression=metric_expression,
        source_table=source_table,
        dimensions=dimensions,
        joins=joins,
        filters=[],
        group_by=group_by,
        order_by="" if not dimensions else f"{metric} DESC" if chart_type != "line" else "day ASC",
        limit=interpretation.limit,
        chart_type=chart_type,
        explanation=explanation,
    )
