import random
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.config import get_settings
from app.models import (
    AccessPolicy,
    ApprovedTemplate,
    ChartPreference,
    Chat,
    City,
    Client,
    DimensionCatalog,
    Driver,
    MetricCatalog,
    Order,
    Report,
    ReportRecipient,
    ReportVersion,
    SemanticExample,
    SemanticLayer,
    SemanticTerm,
    Template,
    User,
)
from app.semantic.defaults import (
    DEFAULT_APPROVED_TEMPLATES,
    DEFAULT_DIMENSIONS,
    DEFAULT_METRICS,
    DEFAULT_SEMANTIC_EXAMPLES,
    DEFAULT_SEMANTIC_TERMS,
)

settings = get_settings()


def _metric_config(
    *,
    base_table: str,
    expression: str,
    time_field: str,
    supported_dimensions: list[str],
    default_chart_type: str,
    default_order_direction: str,
    value_type: str,
) -> dict:
    return {
        "base_table": base_table,
        "expression_by_base": {base_table: expression},
        "time_field_by_base": {base_table: time_field},
        "supported_dimensions": supported_dimensions,
        "default_chart_type": default_chart_type,
        "default_order_direction": default_order_direction,
        "value_type": value_type,
    }


def _dimension_config(
    *,
    expressions_by_base: dict[str, str],
    joins_by_base: dict[str, str] | None = None,
    select_alias: str,
    value_type: str,
    allowed_operators: list[str],
) -> dict:
    return {
        "expression_by_base": expressions_by_base,
        "group_expression_by_base": expressions_by_base,
        "joins_by_base": joins_by_base or {},
        "select_alias": select_alias,
        "value_type": value_type,
        "allowed_operators": allowed_operators,
    }


DEFAULT_TEMPLATES = [
    {
        "title": "Еженедельный KPI",
        "description": "Заказы, выручка, средний чек и отмены по дням.",
        "natural_text": "Покажи KPI за последнюю неделю по дням",
        "category": "kpi",
        "chart_type": "line",
        "canonical_intent_json": {
            "metric": "kpi",
            "dimensions": ["day"],
            "date_range": "last_7_days",
        },
    },
    {
        "title": "Отчёт по городам",
        "description": "Топ городов по выручке и завершённым поездкам.",
        "natural_text": "Покажи выручку по топ-10 городам за последние 30 дней",
        "category": "revenue",
        "chart_type": "bar",
        "canonical_intent_json": {
            "metric": "revenue",
            "dimensions": ["city"],
            "date_range": "last_30_days",
            "limit": 10,
        },
    },
    {
        "title": "Отмены клиентом",
        "description": "Города с наибольшим числом клиентских отмен.",
        "natural_text": "Покажи отмены клиентом по городам за последний месяц",
        "category": "cancellations",
        "chart_type": "bar",
        "canonical_intent_json": {
            "metric": "client_cancellations",
            "dimensions": ["city"],
            "date_range": "last_30_days",
        },
    },
    {
        "title": "Активные водители",
        "description": "Активные водители и завершённые поездки по городам.",
        "natural_text": "Сколько активных водителей по городам и сколько поездок они завершили",
        "category": "drivers",
        "chart_type": "grouped_bar",
        "canonical_intent_json": {
            "metric": "active_drivers",
            "dimensions": ["city"],
        },
    },
]


SEMANTIC_TERMS = [
    {
        "term": "выручка",
        "semantic_key": "revenue",
        "item_kind": "metric",
        "aliases": ["доход", "оборот", "сумма поездок", "gmv"],
        "sql_expression": "SUM(fact.orders.price_order_local) FILTER (WHERE fact.orders.status_order = 'done')",
        "table_name": "fact.orders",
        "description": "Сумма price_order_local только по завершённым поездкам.",
        "metric_type": "money",
        "dimension_type": "",
        "semantic_config_json": _metric_config(
            base_table="fact.orders fo",
            expression="SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done')",
            time_field="fo.order_timestamp",
            supported_dimensions=["city", "day"],
            default_chart_type="bar",
            default_order_direction="desc",
            value_type="money",
        ),
    },
    {
        "term": "заказы",
        "semantic_key": "orders_count",
        "item_kind": "metric",
        "aliases": ["количество заказов", "созданные заказы"],
        "sql_expression": "COUNT(DISTINCT fact.orders.order_id)",
        "table_name": "fact.orders",
        "description": "Уникальные order_id. Важно: одна строка dataset может быть order_id + tender_id.",
        "metric_type": "count",
        "dimension_type": "",
        "semantic_config_json": _metric_config(
            base_table="fact.orders fo",
            expression="COUNT(DISTINCT fo.order_id)",
            time_field="fo.order_timestamp",
            supported_dimensions=["city", "day"],
            default_chart_type="bar",
            default_order_direction="desc",
            value_type="count",
        ),
    },
    {
        "term": "завершённые поездки",
        "semantic_key": "completed_trips",
        "item_kind": "metric",
        "aliases": ["поездки", "done trips", "выполненные поездки"],
        "sql_expression": "COUNT(DISTINCT fact.orders.order_id) FILTER (WHERE fact.orders.status_order = 'done')",
        "table_name": "fact.orders",
        "description": "Уникальные завершённые заказы на уровне поездки.",
        "metric_type": "count",
        "dimension_type": "",
        "semantic_config_json": _metric_config(
            base_table="fact.orders fo",
            expression="COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.status_order = 'done')",
            time_field="fo.order_timestamp",
            supported_dimensions=["city", "day"],
            default_chart_type="bar",
            default_order_direction="desc",
            value_type="count",
        ),
    },
    {
        "term": "отмены клиентом",
        "semantic_key": "client_cancellations",
        "item_kind": "metric",
        "aliases": ["client cancel", "клиентские отмены"],
        "sql_expression": "COUNT(DISTINCT fact.orders.order_id) FILTER (WHERE fact.orders.clientcancel_timestamp IS NOT NULL)",
        "table_name": "fact.orders",
        "description": "Отмены, где заполнен clientcancel_timestamp.",
        "metric_type": "count",
        "dimension_type": "",
        "semantic_config_json": _metric_config(
            base_table="fact.orders fo",
            expression="COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.clientcancel_timestamp IS NOT NULL)",
            time_field="fo.order_timestamp",
            supported_dimensions=["city", "day"],
            default_chart_type="bar",
            default_order_direction="desc",
            value_type="count",
        ),
    },
    {
        "term": "отмены водителем",
        "semantic_key": "driver_cancellations",
        "item_kind": "metric",
        "aliases": ["driver cancel", "водительские отмены"],
        "sql_expression": "COUNT(DISTINCT fact.orders.order_id) FILTER (WHERE fact.orders.drivercancel_timestamp IS NOT NULL)",
        "table_name": "fact.orders",
        "description": "Отмены, где заполнен drivercancel_timestamp.",
        "metric_type": "count",
        "dimension_type": "",
        "semantic_config_json": _metric_config(
            base_table="fact.orders fo",
            expression="COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.drivercancel_timestamp IS NOT NULL)",
            time_field="fo.order_timestamp",
            supported_dimensions=["city", "day"],
            default_chart_type="bar",
            default_order_direction="desc",
            value_type="count",
        ),
    },
    {
        "term": "decline тендеров",
        "semantic_key": "tender_decline_rate",
        "item_kind": "metric",
        "aliases": ["доля decline", "отклонённые тендеры"],
        "sql_expression": "AVG(CASE WHEN fact.tenders.status_tender = 'decline' THEN 1 ELSE 0 END)",
        "table_name": "fact.tenders",
        "description": "Доля отклонённых тендеров на уровне tender_id.",
        "metric_type": "ratio",
        "dimension_type": "",
        "semantic_config_json": _metric_config(
            base_table="fact.tenders ft",
            expression="ROUND(100 * AVG(CASE WHEN ft.status_tender = 'decline' THEN 1 ELSE 0 END), 2)",
            time_field="ft.tender_timestamp",
            supported_dimensions=["city", "day"],
            default_chart_type="bar",
            default_order_direction="desc",
            value_type="ratio",
        ),
    },
    {
        "term": "средний чек",
        "semantic_key": "avg_check",
        "item_kind": "metric",
        "aliases": ["avg check", "средняя цена"],
        "sql_expression": "AVG(fact.orders.price_order_local) FILTER (WHERE fact.orders.status_order = 'done')",
        "table_name": "fact.orders",
        "description": "Средняя price_order_local по завершённым поездкам.",
        "metric_type": "money",
        "dimension_type": "",
        "semantic_config_json": _metric_config(
            base_table="fact.orders fo",
            expression="ROUND(AVG(fo.price_order_local) FILTER (WHERE fo.status_order = 'done'), 2)",
            time_field="fo.order_timestamp",
            supported_dimensions=["city", "day"],
            default_chart_type="bar",
            default_order_direction="desc",
            value_type="money",
        ),
    },
    {
        "term": "город",
        "semantic_key": "city",
        "item_kind": "dimension",
        "aliases": ["города", "city"],
        "sql_expression": "dim.cities.city_name",
        "table_name": "dim.cities",
        "description": "Справочник городов, join через city_id.",
        "metric_type": "dimension",
        "dimension_type": "category",
        "semantic_config_json": _dimension_config(
            expressions_by_base={
                "fact.orders fo": "c.city_name",
                "fact.tenders ft": "c.city_name",
            },
            joins_by_base={
                "fact.orders fo": "JOIN dim.cities c ON c.city_id = fo.city_id",
                "fact.tenders ft": "JOIN dim.cities c ON c.city_id = ft.city_id",
            },
            select_alias="city",
            value_type="string",
            allowed_operators=["eq", "in"],
        ),
    },
    {
        "term": "день",
        "semantic_key": "day",
        "item_kind": "dimension",
        "aliases": ["по дням", "динамика", "date"],
        "sql_expression": "DATE(fact.orders.order_timestamp)",
        "table_name": "fact.orders",
        "description": "Дата заказа в UTC для дневной динамики.",
        "metric_type": "dimension",
        "dimension_type": "time",
        "semantic_config_json": _dimension_config(
            expressions_by_base={
                "fact.orders fo": "DATE(fo.order_timestamp)",
                "fact.tenders ft": "DATE(ft.tender_timestamp)",
            },
            select_alias="day",
            value_type="date",
            allowed_operators=["eq", "between"],
        ),
    },
    {
        "term": "водители",
        "semantic_key": "active_drivers",
        "item_kind": "metric",
        "aliases": ["drivers", "активные водители"],
        "sql_expression": "COUNT(DISTINCT fact.orders.driver_id) FILTER (WHERE fact.orders.status_order = 'done')",
        "table_name": "fact.orders",
        "description": "Активные водители как уникальные driver_id с завершёнными поездками в фактах.",
        "metric_type": "count",
        "dimension_type": "",
        "semantic_config_json": _metric_config(
            base_table="fact.orders fo",
            expression="COUNT(DISTINCT fo.driver_id) FILTER (WHERE fo.status_order = 'done')",
            time_field="fo.order_timestamp",
            supported_dimensions=["city", "day"],
            default_chart_type="bar",
            default_order_direction="desc",
            value_type="count",
        ),
    },
]


SEMANTIC_EXAMPLES = [
    {
        "title": "Revenue by city",
        "natural_text": "Покажи выручку по топ-10 городам за последние 30 дней",
        "canonical_intent_json": {"metric": "revenue", "dimensions": ["city"], "limit": 10},
        "sql_example": """
SELECT c.city_name AS city,
       SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done') AS revenue
FROM fact.orders fo
JOIN dim.cities c ON c.city_id = fo.city_id
WHERE fo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.city_name
ORDER BY revenue DESC
LIMIT 10
""".strip(),
        "domain_tag": "revenue",
    },
    {
        "title": "Client cancellations by city",
        "natural_text": "Покажи отмены клиентом по городам за последний месяц",
        "canonical_intent_json": {"metric": "client_cancellations", "dimensions": ["city"]},
        "sql_example": """
SELECT c.city_name AS city,
       COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.clientcancel_timestamp IS NOT NULL) AS client_cancellations
FROM fact.orders fo
JOIN dim.cities c ON c.city_id = fo.city_id
WHERE fo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.city_name
ORDER BY client_cancellations DESC
LIMIT 20
""".strip(),
        "domain_tag": "cancellations",
    },
    {
        "title": "Tender decline share",
        "natural_text": "Какая доля decline тендеров по городам за неделю",
        "canonical_intent_json": {"metric": "tender_decline_rate", "dimensions": ["city"]},
        "sql_example": """
SELECT c.city_name AS city,
       ROUND(100 * AVG(CASE WHEN ft.status_tender = 'decline' THEN 1 ELSE 0 END), 2) AS decline_rate_pct
FROM fact.tenders ft
JOIN dim.cities c ON c.city_id = ft.city_id
WHERE ft.tender_timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY c.city_name
ORDER BY decline_rate_pct DESC
LIMIT 20
""".strip(),
        "domain_tag": "tenders",
    },
]


async def seed_users(db: AsyncSession) -> list[User]:
    users_count = await db.scalar(select(func.count(User.id)))
    if users_count and users_count > 0:
        return list((await db.scalars(select(User))).all())

    users = [
        User(
            email="admin@tolmach.local",
            full_name="Администратор Толмача",
            password_hash=hash_password("admin123"),
            role="admin",
            preferences={"theme": "dark", "sql_strip": True},
        ),
        User(
            email="user@tolmach.local",
            full_name="Мария Королёва",
            password_hash=hash_password("user123"),
            role="user",
            preferences={"theme": "dark", "default_chart": "auto"},
        ),
    ]
    users.extend(
        User(
            email=f"demo{i}@tolmach.local",
            full_name=f"Demo User {i}",
            password_hash=hash_password("demo123"),
            role="user",
        )
        for i in range(1, 5)
    )
    db.add_all(users)
    await db.flush()
    return users


async def seed_drivee_dataset(db: AsyncSession) -> None:
    cities_count = await db.scalar(select(func.count(City.city_id)))
    if not cities_count:
        db.add_all(
            [
                City(city_id=1, name="Москва", country="RU", timezone="Europe/Moscow", is_active=True),
                City(city_id=2, name="Санкт-Петербург", country="RU", timezone="Europe/Moscow", is_active=True),
                City(city_id=3, name="Казань", country="RU", timezone="Europe/Moscow", is_active=True),
                City(city_id=4, name="Екатеринбург", country="RU", timezone="Asia/Yekaterinburg", is_active=True),
                City(city_id=5, name="Новосибирск", country="RU", timezone="Asia/Novosibirsk", is_active=True),
                City(city_id=6, name="Краснодар", country="RU", timezone="Europe/Moscow", is_active=True),
                City(city_id=7, name="Владивосток", country="RU", timezone="Asia/Vladivostok", is_active=True),
                City(city_id=8, name="Ростов-на-Дону", country="RU", timezone="Europe/Moscow", is_active=True),
                City(city_id=9, name="Нижний Новгород", country="RU", timezone="Europe/Moscow", is_active=True),
                City(city_id=10, name="Пермь", country="RU", timezone="Asia/Yekaterinburg", is_active=True),
            ]
        )
        await db.flush()

    drivers_count = await db.scalar(select(func.count(Driver.driver_id)))
    if not drivers_count:
        random.seed(42)
        drivers = []
        for idx in range(1, 81):
            city_id = random.randint(1, 10)
            drivers.append(
                Driver(
                    driver_id=f"drv_{idx:04d}",
                    city_id=city_id,
                    rating=round(random.uniform(3.2, 5.0), 2),
                    status=random.choices(["active", "inactive", "blocked"], [0.78, 0.16, 0.06])[0],
                    registered_at=datetime.utcnow() - timedelta(days=random.randint(30, 900)),
                    total_trips=random.randint(10, 1800),
                )
            )
        db.add_all(drivers)
        await db.flush()

    clients_count = await db.scalar(select(func.count(Client.user_id)))
    if not clients_count:
        random.seed(43)
        clients = []
        for idx in range(1, 121):
            clients.append(
                Client(
                    user_id=f"cli_{idx:04d}",
                    city_id=random.randint(1, 10),
                    registered_at=datetime.utcnow() - timedelta(days=random.randint(5, 1200)),
                    total_orders=random.randint(1, 320),
                    is_active=random.random() > 0.08,
                )
            )
        db.add_all(clients)
        await db.flush()

    orders_count = await db.scalar(select(func.count(Order.order_id)))
    if orders_count and orders_count > 0:
        return

    random.seed(44)
    drivers = list((await db.scalars(select(Driver))).all())
    clients = list((await db.scalars(select(Client))).all())
    now = datetime.utcnow()
    rows: list[Order] = []
    for order_idx in range(1, 241):
        client = random.choice(clients)
        driver_candidates = [driver for driver in drivers if driver.city_id == client.city_id] or drivers
        status_order = random.choices(["done", "cancelled"], [0.78, 0.22])[0]
        tender_count = random.choices([1, 2, 3], [0.72, 0.22, 0.06])[0]
        order_ts = now - timedelta(days=random.randint(0, 75), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        accepted_tender = random.randint(1, tender_count)
        price_start = round(random.uniform(180, 720), 2)
        price_order = round(price_start * random.uniform(1.0, 3.4), 2)
        distance = random.randint(900, 38_000)
        duration = random.randint(300, 4200)

        for tender_idx in range(1, tender_count + 1):
            driver = random.choice(driver_candidates)
            tender_status = "done" if tender_idx == accepted_tender and status_order == "done" else random.choice(["decline", "timeout"])
            tender_ts = order_ts + timedelta(seconds=tender_idx * random.randint(30, 180))
            client_cancel = None
            driver_cancel = None
            done_ts = None
            cancel_before_accept = None
            if status_order == "done" and tender_status == "done":
                done_ts = tender_ts + timedelta(seconds=duration)
            elif status_order == "cancelled":
                if random.random() < 0.58:
                    client_cancel = tender_ts + timedelta(minutes=random.randint(1, 15))
                    cancel_before_accept = client_cancel if tender_status != "done" else None
                else:
                    driver_cancel = tender_ts + timedelta(minutes=random.randint(1, 15))

            rows.append(
                Order(
                    order_id=f"ord_{order_idx:05d}",
                    tender_id=f"tnd_{order_idx:05d}_{tender_idx}",
                    city_id=client.city_id,
                    user_id=client.user_id,
                    driver_id=driver.driver_id,
                    offset_hours=3,
                    status_order=status_order,
                    status_tender=tender_status,
                    order_timestamp=order_ts,
                    tender_timestamp=tender_ts,
                    driverdone_timestamp=done_ts,
                    clientcancel_timestamp=client_cancel,
                    drivercancel_timestamp=driver_cancel,
                    order_modified_local=tender_ts + timedelta(minutes=random.randint(1, 30)),
                    cancel_before_accept_local=cancel_before_accept,
                    distance_in_meters=distance,
                    duration_in_seconds=duration,
                    price_order_local=price_order,
                    price_tender_local=round(price_order * random.uniform(0.95, 1.1), 2),
                    price_start_local=price_start,
                )
            )

    db.add_all(rows)


async def seed_semantics(db: AsyncSession) -> None:
    for item in DEFAULT_METRICS:
        exists = await db.scalar(select(MetricCatalog).where(MetricCatalog.metric_key == item["metric_key"]))
        if not exists:
            db.add(
                MetricCatalog(
                    metric_key=item["metric_key"],
                    business_name=item["business_name"],
                    description=item["description"],
                    sql_expression_template=item["sql_expression_template"],
                    grain=item["grain"],
                    allowed_dimensions_json=item["allowed_dimensions"],
                    allowed_filters_json=item["allowed_filters"],
                    default_chart=item["default_chart"],
                    safety_tags_json=item["safety_tags"],
                    is_active=True,
                )
            )
        else:
            exists.business_name = item["business_name"]
            exists.description = item["description"]
            exists.sql_expression_template = item["sql_expression_template"]
            exists.grain = item["grain"]
            exists.allowed_dimensions_json = item["allowed_dimensions"]
            exists.allowed_filters_json = item["allowed_filters"]
            exists.default_chart = item["default_chart"]
            exists.safety_tags_json = item["safety_tags"]
            exists.is_active = True

    for item in DEFAULT_DIMENSIONS:
        exists = await db.scalar(select(DimensionCatalog).where(DimensionCatalog.dimension_key == item["dimension_key"]))
        if not exists:
            db.add(
                DimensionCatalog(
                    dimension_key=item["dimension_key"],
                    business_name=item["business_name"],
                    table_name=item["table_name"],
                    column_name=item["column_name"],
                    join_path=item["join_path"],
                    data_type=item["data_type"],
                    is_active=True,
                )
            )
        else:
            exists.business_name = item["business_name"]
            exists.table_name = item["table_name"]
            exists.column_name = item["column_name"]
            exists.join_path = item["join_path"]
            exists.data_type = item["data_type"]
            exists.is_active = True

    for item in DEFAULT_SEMANTIC_TERMS:
        exists = await db.scalar(select(SemanticTerm).where(SemanticTerm.term == item["term"]))
        if not exists:
            db.add(
                SemanticTerm(
                    term=item["term"],
                    aliases=item["aliases"],
                    mapped_entity_type=item["mapped_entity_type"],
                    mapped_entity_key=item["mapped_entity_key"],
                    is_active=True,
                )
            )
        else:
            exists.aliases = item["aliases"]
            exists.mapped_entity_type = item["mapped_entity_type"]
            exists.mapped_entity_key = item["mapped_entity_key"]
            exists.is_active = True

    for item in DEFAULT_SEMANTIC_EXAMPLES:
        exists = await db.scalar(select(SemanticExample).where(SemanticExample.title == item["title"]))
        if not exists:
            db.add(
                SemanticExample(
                    title=item["title"],
                    natural_text=item["natural_text"],
                    canonical_intent_json=item["canonical_intent_json"],
                    sql_example=item["sql_example"],
                    domain_tag=item["domain_tag"],
                    metric_key=item["metric_key"],
                    dimension_keys_json=item["dimension_keys"],
                    filter_keys_json=item["filter_keys"],
                    is_active=item["is_active"],
                )
            )
        else:
            exists.natural_text = item["natural_text"]
            exists.canonical_intent_json = item["canonical_intent_json"]
            exists.sql_example = item["sql_example"]
            exists.domain_tag = item["domain_tag"]
            exists.metric_key = item["metric_key"]
            exists.dimension_keys_json = item["dimension_keys"]
            exists.filter_keys_json = item["filter_keys"]
            exists.is_active = item["is_active"]

    for item in DEFAULT_APPROVED_TEMPLATES:
        exists = await db.scalar(select(ApprovedTemplate).where(ApprovedTemplate.template_key == item["template_key"]))
        if not exists:
            db.add(
                ApprovedTemplate(
                    template_key=item["template_key"],
                    title=item["title"],
                    description=item["description"],
                    natural_text=item["natural_text"],
                    metric_key=item["metric_key"],
                    dimension_keys_json=item["dimension_keys"],
                    filter_keys_json=item["filter_keys"],
                    canonical_intent_json=item["canonical_intent_json"],
                    chart_type=item["chart_type"],
                    category=item["category"],
                    is_active=item["is_active"],
                )
            )
        else:
            exists.title = item["title"]
            exists.description = item["description"]
            exists.natural_text = item["natural_text"]
            exists.metric_key = item["metric_key"]
            exists.dimension_keys_json = item["dimension_keys"]
            exists.filter_keys_json = item["filter_keys"]
            exists.canonical_intent_json = item["canonical_intent_json"]
            exists.chart_type = item["chart_type"]
            exists.category = item["category"]
            exists.is_active = item["is_active"]

    for item in SEMANTIC_TERMS:
        exists = await db.scalar(select(SemanticLayer).where(SemanticLayer.term == item["term"]))
        if not exists:
            db.add(SemanticLayer(**item))
        else:
            exists.semantic_key = item["semantic_key"]
            exists.item_kind = item["item_kind"]
            exists.aliases = item["aliases"]
            exists.sql_expression = item["sql_expression"]
            exists.table_name = item["table_name"]
            exists.description = item["description"]
            exists.metric_type = item["metric_type"]
            exists.dimension_type = item["dimension_type"]
            exists.semantic_config_json = item["semantic_config_json"]

    for item in SEMANTIC_EXAMPLES:
        exists = await db.scalar(select(SemanticExample).where(SemanticExample.title == item["title"]))
        if not exists:
            db.add(
                SemanticExample(
                    **item,
                    metric_key=str(item.get("canonical_intent_json", {}).get("metric", "")),
                    dimension_keys_json=list(item.get("canonical_intent_json", {}).get("dimensions", [])),
                    filter_keys_json=list(item.get("canonical_intent_json", {}).get("filter_keys", [])),
                    is_active=True,
                )
            )
        else:
            exists.metric_key = str(item.get("canonical_intent_json", {}).get("metric", ""))
            exists.dimension_keys_json = list(item.get("canonical_intent_json", {}).get("dimensions", []))
            exists.filter_keys_json = list(item.get("canonical_intent_json", {}).get("filter_keys", []))
            exists.is_active = True

    for item in DEFAULT_TEMPLATES:
        exists = await db.scalar(select(Template).where(Template.title == item["title"], Template.is_public.is_(True)))
        if not exists:
            db.add(Template(is_public=True, **item))

    all_columns = {
        "dim.cities": ["city_id", "city_name", "country", "timezone", "is_active", "first_seen_at", "last_seen_at"],
        "dim.drivers": ["driver_id", "city_id", "first_seen_at", "last_seen_at", "tenders_count", "completed_orders_count"],
        "dim.clients": ["user_id", "city_id", "first_seen_at", "last_seen_at", "orders_count", "completed_orders_count"],
        "fact.orders": [
            "order_id",
            "city_id",
            "user_id",
            "driver_id",
            "accepted_tender_id",
            "status_order",
            "order_timestamp",
            "order_day",
            "tender_count",
            "declined_tenders_count",
            "timeout_tenders_count",
            "driverdone_timestamp",
            "clientcancel_timestamp",
            "drivercancel_timestamp",
            "order_modified_local",
            "cancel_before_accept_local",
            "distance_in_meters",
            "duration_in_seconds",
            "price_order_local",
        ],
        "fact.tenders": [
            "order_id",
            "tender_id",
            "city_id",
            "user_id",
            "driver_id",
            "status_tender",
            "tender_timestamp",
            "tender_day",
            "driveraccept_timestamp",
            "driverarrived_timestamp",
            "driverstartride_timestamp",
            "driverdone_timestamp",
            "clientcancel_timestamp",
            "drivercancel_timestamp",
            "order_modified_local",
            "cancel_before_accept_local",
            "price_tender_local",
            "price_start_local",
        ],
        "mart.city_daily": [
            "day",
            "city_id",
            "orders_count",
            "completed_trips",
            "client_cancellations",
            "driver_cancellations",
            "active_drivers",
            "revenue",
            "avg_check",
            "avg_duration_seconds",
            "avg_distance_meters",
            "tenders_count",
            "declined_tenders_count",
            "tender_decline_rate",
        ],
        "mart.driver_daily": [
            "day",
            "driver_id",
            "city_id",
            "orders_count",
            "completed_trips",
            "driver_cancellations",
            "revenue",
        ],
        "mart.client_daily": [
            "day",
            "user_id",
            "city_id",
            "orders_count",
            "completed_trips",
            "client_cancellations",
            "revenue",
        ],
        "mart.orders_kpi_daily": [
            "day",
            "orders_count",
            "completed_trips",
            "client_cancellations",
            "driver_cancellations",
            "active_drivers",
            "active_cities",
            "revenue",
            "avg_check",
            "avg_duration_seconds",
            "avg_distance_meters",
            "tenders_count",
            "declined_tenders_count",
            "tender_decline_rate",
        ],
        "raw.train_raw": [
            "order_id_raw",
            "tender_id_raw",
            "city_id_raw",
            "user_id_raw",
            "driver_id_raw",
            "status_order_raw",
            "status_tender_raw",
            "order_timestamp_raw",
            "tender_timestamp_raw",
        ],
        "staging.train_typed": [
            "order_id",
            "tender_id",
            "city_id",
            "user_id",
            "driver_id",
            "status_order",
            "status_tender",
            "order_timestamp",
            "tender_timestamp",
            "driverdone_timestamp",
            "clientcancel_timestamp",
            "drivercancel_timestamp",
            "distance_in_meters",
            "duration_in_seconds",
            "price_order_local",
            "price_tender_local",
            "price_start_local",
            "is_valid",
        ],
    }
    for role in ["user", "admin"]:
        for table, columns in all_columns.items():
            exists = await db.scalar(
                select(AccessPolicy).where(
                    AccessPolicy.role == role,
                    AccessPolicy.table_name == table,
                    AccessPolicy.is_active.is_(True),
                )
            )
            if not exists:
                db.add(AccessPolicy(role=role, table_name=table, allowed_columns_json=columns, row_limit=1000))

    if not await db.scalar(select(func.count(ChartPreference.id))):
        db.add_all(
            [
                ChartPreference(metric_type="money", dimension_type="category", chart_type="bar", priority=10),
                ChartPreference(metric_type="count", dimension_type="category", chart_type="bar", priority=10),
                ChartPreference(metric_type="ratio", dimension_type="category", chart_type="bar", priority=20),
                ChartPreference(metric_type="money", dimension_type="time", chart_type="line", priority=10),
                ChartPreference(metric_type="count", dimension_type="time", chart_type="line", priority=10),
                ChartPreference(metric_type="multi_kpi", dimension_type="time", chart_type="line", priority=10),
            ]
        )


async def seed_demo_report(db: AsyncSession, users: list[User]) -> None:
    owner = next((user for user in users if user.email == "user@tolmach.local"), users[0])
    if await db.scalar(select(func.count(Report.id)).where(Report.user_id == owner.id)):
        return

    report = Report(
        user_id=owner.id,
        title="Еженедельная выручка по городам",
        natural_text="Покажи выручку по топ-10 городам за последние 30 дней",
        generated_sql="""
SELECT c.city_name AS city,
       SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done') AS revenue
FROM fact.orders fo
JOIN dim.cities c ON c.city_id = fo.city_id
WHERE fo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.city_name
ORDER BY revenue DESC
LIMIT 10
""".strip(),
        chart_type="bar",
        chart_spec={"type": "bar", "x": "city", "series": [{"key": "revenue", "name": "Выручка"}]},
        result_snapshot=[],
        config_json={"source": "seed", "readonly": True},
    )
    db.add(report)
    await db.flush()
    db.add(
        ReportVersion(
            report_id=report.id,
            version_number=1,
            generated_sql=report.generated_sql,
            chart_type=report.chart_type,
            chart_spec_json=report.chart_spec,
            semantic_snapshot_json={},
            config_json=report.config_json,
            created_by=owner.id,
        )
    )
    db.add(ReportRecipient(report_id=report.id, email="ops-team@drivee.example"))


def _database_host(database_url: str) -> str:
    parsed = urlparse(database_url.replace("+asyncpg", ""))
    return (parsed.hostname or "").lower()


def _is_local_database(database_url: str) -> bool:
    return _database_host(database_url) in {"", "db", "localhost", "127.0.0.1"}


async def bootstrap_demo_data(db: AsyncSession, allow_nonlocal: bool = False) -> None:
    if settings.is_production:
        raise RuntimeError("Demo bootstrap is disabled when APP_ENV=production.")
    if (
        not allow_nonlocal
        and not settings.demo_bootstrap_allow_nonlocal
        and not _is_local_database(settings.platform_database_url)
    ):
        raise RuntimeError(
            "Demo bootstrap is blocked for non-local databases. "
            "Use a local PostgreSQL DSN or pass allow_nonlocal explicitly."
        )
    users = await seed_users(db)
    await seed_drivee_dataset(db)
    await seed_semantics(db)
    await seed_demo_report(db, users)
    await db.commit()
