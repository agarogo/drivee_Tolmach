from __future__ import annotations

DEFAULT_METRICS = [
    {
        "metric_key": "revenue",
        "business_name": "Выручка",
        "description": "Сумма price_order_local только по завершённым заказам.",
        "sql_expression_template": "SUM({base_alias}.price_order_local) FILTER (WHERE {base_alias}.status_order = 'done')",
        "grain": "order",
        "allowed_dimensions": ["city", "day"],
        "allowed_filters": ["city", "day"],
        "default_chart": "bar",
        "safety_tags": ["finance", "completed_only"],
    },
    {
        "metric_key": "orders_count",
        "business_name": "Заказы",
        "description": "Количество уникальных order_id.",
        "sql_expression_template": "COUNT(DISTINCT {base_alias}.order_id)",
        "grain": "order",
        "allowed_dimensions": ["city", "day", "client", "driver"],
        "allowed_filters": ["city", "day", "client", "driver"],
        "default_chart": "bar",
        "safety_tags": ["count", "order_grain"],
    },
    {
        "metric_key": "completed_trips",
        "business_name": "Завершённые поездки",
        "description": "Количество уникальных order_id со статусом done.",
        "sql_expression_template": "COUNT(DISTINCT {base_alias}.order_id) FILTER (WHERE {base_alias}.status_order = 'done')",
        "grain": "order",
        "allowed_dimensions": ["city", "day", "client", "driver"],
        "allowed_filters": ["city", "day", "client", "driver"],
        "default_chart": "bar",
        "safety_tags": ["count", "completed_only"],
    },
    {
        "metric_key": "client_cancellations",
        "business_name": "Отмены клиентом",
        "description": "Количество заказов, где заполнен clientcancel_timestamp.",
        "sql_expression_template": "COUNT(DISTINCT {base_alias}.order_id) FILTER (WHERE {base_alias}.clientcancel_timestamp IS NOT NULL)",
        "grain": "order",
        "allowed_dimensions": ["city", "day", "client"],
        "allowed_filters": ["city", "day", "client"],
        "default_chart": "bar",
        "safety_tags": ["count", "cancellations"],
    },
    {
        "metric_key": "driver_cancellations",
        "business_name": "Отмены водителем",
        "description": "Количество заказов, где заполнен drivercancel_timestamp.",
        "sql_expression_template": "COUNT(DISTINCT {base_alias}.order_id) FILTER (WHERE {base_alias}.drivercancel_timestamp IS NOT NULL)",
        "grain": "order",
        "allowed_dimensions": ["city", "day", "driver"],
        "allowed_filters": ["city", "day", "driver"],
        "default_chart": "bar",
        "safety_tags": ["count", "cancellations"],
    },
    {
        "metric_key": "avg_check",
        "business_name": "Средний чек",
        "description": "Средняя price_order_local по завершённым заказам.",
        "sql_expression_template": "ROUND(AVG({base_alias}.price_order_local) FILTER (WHERE {base_alias}.status_order = 'done'), 2)",
        "grain": "order",
        "allowed_dimensions": ["city", "day"],
        "allowed_filters": ["city", "day"],
        "default_chart": "bar",
        "safety_tags": ["finance", "completed_only"],
    },
    {
        "metric_key": "active_drivers",
        "business_name": "Активные водители",
        "description": "Количество уникальных driver_id по завершённым заказам.",
        "sql_expression_template": "COUNT(DISTINCT {base_alias}.driver_id) FILTER (WHERE {base_alias}.status_order = 'done' AND {base_alias}.driver_id IS NOT NULL)",
        "grain": "order",
        "allowed_dimensions": ["city", "day"],
        "allowed_filters": ["city", "day", "driver"],
        "default_chart": "bar",
        "safety_tags": ["count", "distinct", "completed_only"],
    },
    {
        "metric_key": "tender_decline_rate",
        "business_name": "Доля decline тендеров",
        "description": "Процент тендеров со статусом decline на уровне tender_id.",
        "sql_expression_template": "ROUND(100 * AVG(CASE WHEN {base_alias}.status_tender = 'decline' THEN 1 ELSE 0 END), 2)",
        "grain": "tender",
        "allowed_dimensions": ["city", "day", "driver"],
        "allowed_filters": ["city", "day", "driver"],
        "default_chart": "bar",
        "safety_tags": ["ratio", "tender_grain"],
    },
]

DEFAULT_DIMENSIONS = [
    {
        "dimension_key": "city",
        "business_name": "Город",
        "table_name": "dim.cities",
        "column_name": "city_name",
        "join_path": "JOIN dim.cities {dimension_alias} ON {dimension_alias}.city_id = {base_alias}.city_id",
        "data_type": "string",
    },
    {
        "dimension_key": "day",
        "business_name": "День",
        "table_name": "__grain__",
        "column_name": "{time_dimension_column}",
        "join_path": "",
        "data_type": "date",
    },
    {
        "dimension_key": "driver",
        "business_name": "Водитель",
        "table_name": "dim.drivers",
        "column_name": "driver_id",
        "join_path": "JOIN dim.drivers {dimension_alias} ON {dimension_alias}.driver_id = {base_alias}.driver_id",
        "data_type": "string",
    },
    {
        "dimension_key": "client",
        "business_name": "Клиент",
        "table_name": "dim.clients",
        "column_name": "user_id",
        "join_path": "JOIN dim.clients {dimension_alias} ON {dimension_alias}.user_id = {base_alias}.user_id",
        "data_type": "string",
    },
]

DEFAULT_SEMANTIC_TERMS = [
    {
        "term": "выручка",
        "aliases": ["доход", "оборот", "gmv", "сумма поездок"],
        "mapped_entity_type": "metric",
        "mapped_entity_key": "revenue",
    },
    {
        "term": "заказы",
        "aliases": ["количество заказов", "orders", "созданные заказы"],
        "mapped_entity_type": "metric",
        "mapped_entity_key": "orders_count",
    },
    {
        "term": "завершённые поездки",
        "aliases": ["поездки", "done trips", "completed trips"],
        "mapped_entity_type": "metric",
        "mapped_entity_key": "completed_trips",
    },
    {
        "term": "отмены клиентом",
        "aliases": ["client cancel", "клиентские отмены"],
        "mapped_entity_type": "metric",
        "mapped_entity_key": "client_cancellations",
    },
    {
        "term": "отмены водителем",
        "aliases": ["driver cancel", "водительские отмены"],
        "mapped_entity_type": "metric",
        "mapped_entity_key": "driver_cancellations",
    },
    {
        "term": "средний чек",
        "aliases": ["avg check", "средняя цена"],
        "mapped_entity_type": "metric",
        "mapped_entity_key": "avg_check",
    },
    {
        "term": "активные водители",
        "aliases": ["drivers", "driver activity"],
        "mapped_entity_type": "metric",
        "mapped_entity_key": "active_drivers",
    },
    {
        "term": "decline тендеров",
        "aliases": ["доля decline", "отклонённые тендеры", "decline rate"],
        "mapped_entity_type": "metric",
        "mapped_entity_key": "tender_decline_rate",
    },
    {
        "term": "город",
        "aliases": ["города", "city"],
        "mapped_entity_type": "dimension",
        "mapped_entity_key": "city",
    },
    {
        "term": "день",
        "aliases": ["по дням", "динамика", "date"],
        "mapped_entity_type": "dimension",
        "mapped_entity_key": "day",
    },
    {
        "term": "водитель",
        "aliases": ["driver"],
        "mapped_entity_type": "dimension",
        "mapped_entity_key": "driver",
    },
    {
        "term": "клиент",
        "aliases": ["client", "пассажир"],
        "mapped_entity_type": "dimension",
        "mapped_entity_key": "client",
    },
]

DEFAULT_SEMANTIC_EXAMPLES = [
    {
        "title": "Revenue by city",
        "natural_text": "Покажи выручку по топ-10 городам за последние 30 дней",
        "metric_key": "revenue",
        "dimension_keys": ["city"],
        "filter_keys": ["day"],
        "canonical_intent_json": {
            "metric_key": "revenue",
            "dimension_keys": ["city"],
            "period": {"kind": "rolling_days", "days": 30, "label": "последние 30 дней"},
            "limit": 10,
        },
        "sql_example": """
SELECT
  dim_city.city_name AS city,
  SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done') AS revenue
FROM fact.orders fo
JOIN dim.cities dim_city ON dim_city.city_id = fo.city_id
WHERE fo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY dim_city.city_name
ORDER BY revenue DESC
LIMIT 10
""".strip(),
        "domain_tag": "revenue",
        "is_active": True,
    },
    {
        "title": "Completed trips by day",
        "natural_text": "Покажи завершённые поездки по дням за неделю",
        "metric_key": "completed_trips",
        "dimension_keys": ["day"],
        "filter_keys": ["day"],
        "canonical_intent_json": {
            "metric_key": "completed_trips",
            "dimension_keys": ["day"],
            "period": {"kind": "rolling_days", "days": 7, "label": "последние 7 дней"},
        },
        "sql_example": """
SELECT
  fo.order_day AS day,
  COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.status_order = 'done') AS completed_trips
FROM fact.orders fo
WHERE fo.order_timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY fo.order_day
ORDER BY day ASC
LIMIT 20
""".strip(),
        "domain_tag": "operations",
        "is_active": True,
    },
    {
        "title": "Tender decline rate by city",
        "natural_text": "Какая доля decline тендеров по городам за неделю",
        "metric_key": "tender_decline_rate",
        "dimension_keys": ["city"],
        "filter_keys": ["day"],
        "canonical_intent_json": {
            "metric_key": "tender_decline_rate",
            "dimension_keys": ["city"],
            "period": {"kind": "rolling_days", "days": 7, "label": "последние 7 дней"},
        },
        "sql_example": """
SELECT
  dim_city.city_name AS city,
  ROUND(100 * AVG(CASE WHEN ft.status_tender = 'decline' THEN 1 ELSE 0 END), 2) AS tender_decline_rate
FROM fact.tenders ft
JOIN dim.cities dim_city ON dim_city.city_id = ft.city_id
WHERE ft.tender_timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY dim_city.city_name
ORDER BY tender_decline_rate DESC
LIMIT 20
""".strip(),
        "domain_tag": "tenders",
        "is_active": True,
    },
]

DEFAULT_APPROVED_TEMPLATES = [
    {
        "template_key": "weekly_kpi",
        "title": "Еженедельный KPI",
        "description": "Заказы, выручка, средний чек и отмены по дням.",
        "natural_text": "Покажи завершённые поездки по дням за последнюю неделю",
        "metric_key": "completed_trips",
        "dimension_keys": ["day"],
        "filter_keys": ["day"],
        "canonical_intent_json": {
            "metric_key": "completed_trips",
            "dimension_keys": ["day"],
            "period": {"kind": "rolling_days", "days": 7, "label": "последние 7 дней"},
        },
        "chart_type": "line",
        "category": "kpi",
        "is_active": True,
    },
    {
        "template_key": "revenue_by_city",
        "title": "Выручка по городам",
        "description": "Топ городов по выручке за последние 30 дней.",
        "natural_text": "Покажи выручку по топ-10 городам за последние 30 дней",
        "metric_key": "revenue",
        "dimension_keys": ["city"],
        "filter_keys": ["day"],
        "canonical_intent_json": {
            "metric_key": "revenue",
            "dimension_keys": ["city"],
            "period": {"kind": "rolling_days", "days": 30, "label": "последние 30 дней"},
            "limit": 10,
        },
        "chart_type": "bar",
        "category": "revenue",
        "is_active": True,
    },
    {
        "template_key": "client_cancellations_by_city",
        "title": "Отмены клиентом по городам",
        "description": "Города с наибольшим числом клиентских отмен.",
        "natural_text": "Покажи отмены клиентом по городам за последний месяц",
        "metric_key": "client_cancellations",
        "dimension_keys": ["city"],
        "filter_keys": ["day"],
        "canonical_intent_json": {
            "metric_key": "client_cancellations",
            "dimension_keys": ["city"],
            "period": {"kind": "rolling_days", "days": 30, "label": "последние 30 дней"},
        },
        "chart_type": "bar",
        "category": "cancellations",
        "is_active": True,
    },
]
