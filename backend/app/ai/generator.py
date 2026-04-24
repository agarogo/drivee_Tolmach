from app.ai.types import Interpretation, SqlPlan


def _date_filter(interpretation: Interpretation, alias: str) -> str:
    date_range = interpretation.date_range or {}
    field = "tender_timestamp" if alias == "mt" else "order_timestamp"
    kind = date_range.get("kind")
    if kind == "rolling_days":
        return f"{alias}.{field} >= CURRENT_DATE - INTERVAL '{int(date_range['days'])} days'"
    if kind == "since_date":
        return f"{alias}.{field} >= DATE '{date_range['start']}'"
    if kind == "until_date":
        return f"{alias}.{field} < DATE '{date_range['end']}' + INTERVAL '1 day'"
    if kind == "exact_date":
        return f"DATE({alias}.{field}) = DATE '{date_range['date']}'"
    if kind == "between_dates":
        return (
            f"{alias}.{field} >= DATE '{date_range['start']}' "
            f"AND {alias}.{field} < DATE '{date_range['end']}' + INTERVAL '1 day'"
        )
    return ""


def generate_sql(plan: SqlPlan, interpretation: Interpretation) -> str:
    if plan.metric == "kpi":
        filters = [_date_filter(interpretation, "mo")]
        where = f"WHERE {' AND '.join(filter(None, filters))}" if any(filters) else ""
        return f"""
SELECT
  DATE(mo.order_timestamp) AS day,
  COUNT(DISTINCT mo.order_id) AS orders_count,
  COUNT(DISTINCT mo.order_id) FILTER (WHERE mo.status_order = 'done') AS completed_trips,
  SUM(mo.price_order_local) FILTER (WHERE mo.status_order = 'done') AS revenue,
  ROUND(AVG(mo.price_order_local) FILTER (WHERE mo.status_order = 'done'), 2) AS avg_check,
  COUNT(DISTINCT mo.order_id) FILTER (WHERE mo.clientcancel_timestamp IS NOT NULL) AS client_cancellations,
  COUNT(DISTINCT mo.order_id) FILTER (WHERE mo.drivercancel_timestamp IS NOT NULL) AS driver_cancellations
FROM mart_orders mo
{where}
GROUP BY DATE(mo.order_timestamp)
ORDER BY day ASC
LIMIT {plan.limit}
""".strip()

    alias = "mt" if plan.source_table.startswith("mart_tenders") else ("d" if plan.source_table.startswith("drivers") else "mo")
    selected_dimensions: list[str] = []
    for dim in plan.dimensions:
        if dim == "city":
            selected_dimensions.append("c.name AS city")
        elif dim == "day":
            field = "mt.tender_timestamp" if alias == "mt" else "mo.order_timestamp"
            selected_dimensions.append(f"DATE({field}) AS day")
        elif dim == "driver":
            selected_dimensions.append("d.driver_id AS driver_id")

    select_clause = ",\n  ".join(selected_dimensions + [f"{plan.metric_expression} AS {plan.metric}"])
    filters = []
    if alias in {"mo", "mt"}:
        filters.append(_date_filter(interpretation, alias))
    filters.extend(plan.filters)
    where = f"WHERE {' AND '.join(filter(None, filters))}" if any(filters) else ""
    joins = "\n".join(plan.joins)
    group_by = f"GROUP BY {', '.join(plan.group_by)}" if plan.group_by else ""
    order_by = f"ORDER BY {plan.order_by}" if plan.order_by else ""

    return f"""
SELECT
  {select_clause}
FROM {plan.source_table}
{joins}
{where}
{group_by}
{order_by}
LIMIT {plan.limit}
""".strip()
