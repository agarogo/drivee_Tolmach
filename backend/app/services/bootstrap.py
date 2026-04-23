import random
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.models import (
    AccessPolicy,
    ChartPreference,
    Chat,
    City,
    Client,
    Driver,
    Order,
    Report,
    ReportRecipient,
    ReportVersion,
    Schedule,
    ScheduleRun,
    SemanticExample,
    SemanticLayer,
    Template,
    User,
)


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
        "aliases": ["доход", "оборот", "сумма поездок", "gmv"],
        "sql_expression": "SUM(mart_orders.price_order_local) FILTER (WHERE mart_orders.status_order = 'done')",
        "table_name": "mart_orders",
        "description": "Сумма price_order_local только по завершённым поездкам.",
        "metric_type": "money",
        "dimension_type": "",
    },
    {
        "term": "заказы",
        "aliases": ["количество заказов", "созданные заказы"],
        "sql_expression": "COUNT(DISTINCT mart_orders.order_id)",
        "table_name": "mart_orders",
        "description": "Уникальные order_id. Важно: одна строка dataset может быть order_id + tender_id.",
        "metric_type": "count",
        "dimension_type": "",
    },
    {
        "term": "завершённые поездки",
        "aliases": ["поездки", "done trips", "выполненные поездки"],
        "sql_expression": "COUNT(DISTINCT mart_orders.order_id) FILTER (WHERE mart_orders.status_order = 'done')",
        "table_name": "mart_orders",
        "description": "Уникальные завершённые заказы на уровне поездки.",
        "metric_type": "count",
        "dimension_type": "",
    },
    {
        "term": "отмены клиентом",
        "aliases": ["client cancel", "клиентские отмены"],
        "sql_expression": "COUNT(DISTINCT mart_orders.order_id) FILTER (WHERE mart_orders.clientcancel_timestamp IS NOT NULL)",
        "table_name": "mart_orders",
        "description": "Отмены, где заполнен clientcancel_timestamp.",
        "metric_type": "count",
        "dimension_type": "",
    },
    {
        "term": "отмены водителем",
        "aliases": ["driver cancel", "водительские отмены"],
        "sql_expression": "COUNT(DISTINCT mart_orders.order_id) FILTER (WHERE mart_orders.drivercancel_timestamp IS NOT NULL)",
        "table_name": "mart_orders",
        "description": "Отмены, где заполнен drivercancel_timestamp.",
        "metric_type": "count",
        "dimension_type": "",
    },
    {
        "term": "decline тендеров",
        "aliases": ["доля decline", "отклонённые тендеры"],
        "sql_expression": "AVG(CASE WHEN mart_tenders.status_tender = 'decline' THEN 1 ELSE 0 END)",
        "table_name": "mart_tenders",
        "description": "Доля отклонённых тендеров на уровне tender_id.",
        "metric_type": "ratio",
        "dimension_type": "",
    },
    {
        "term": "средний чек",
        "aliases": ["avg check", "средняя цена"],
        "sql_expression": "AVG(mart_orders.price_order_local) FILTER (WHERE mart_orders.status_order = 'done')",
        "table_name": "mart_orders",
        "description": "Средняя price_order_local по завершённым поездкам.",
        "metric_type": "money",
        "dimension_type": "",
    },
    {
        "term": "город",
        "aliases": ["города", "city"],
        "sql_expression": "cities.name",
        "table_name": "cities",
        "description": "Справочник городов, join через city_id.",
        "metric_type": "dimension",
        "dimension_type": "category",
    },
    {
        "term": "день",
        "aliases": ["по дням", "динамика", "date"],
        "sql_expression": "DATE(mart_orders.order_timestamp)",
        "table_name": "mart_orders",
        "description": "Дата заказа в UTC для дневной динамики.",
        "metric_type": "dimension",
        "dimension_type": "time",
    },
    {
        "term": "водители",
        "aliases": ["drivers", "активные водители"],
        "sql_expression": "COUNT(DISTINCT mart_orders.driver_id) FILTER (WHERE mart_orders.status_order = 'done')",
        "table_name": "mart_orders",
        "description": "Активные водители как уникальные driver_id с завершёнными поездками в фактах.",
        "metric_type": "count",
        "dimension_type": "",
    },
]


SEMANTIC_EXAMPLES = [
    {
        "title": "Revenue by city",
        "natural_text": "Покажи выручку по топ-10 городам за последние 30 дней",
        "canonical_intent_json": {"metric": "revenue", "dimensions": ["city"], "limit": 10},
        "sql_example": """
SELECT c.name AS city,
       SUM(mo.price_order_local) FILTER (WHERE mo.status_order = 'done') AS revenue
FROM mart_orders mo
JOIN cities c ON c.city_id = mo.city_id
WHERE mo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.name
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
SELECT c.name AS city,
       COUNT(DISTINCT mo.order_id) FILTER (WHERE mo.clientcancel_timestamp IS NOT NULL) AS client_cancellations
FROM mart_orders mo
JOIN cities c ON c.city_id = mo.city_id
WHERE mo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.name
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
SELECT c.name AS city,
       ROUND(100 * AVG(CASE WHEN mt.status_tender = 'decline' THEN 1 ELSE 0 END), 2) AS decline_rate_pct
FROM mart_tenders mt
JOIN cities c ON c.city_id = mt.city_id
WHERE mt.tender_timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY c.name
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
    for item in SEMANTIC_TERMS:
        exists = await db.scalar(select(SemanticLayer).where(SemanticLayer.term == item["term"]))
        if not exists:
            db.add(SemanticLayer(**item))
        else:
            exists.aliases = item["aliases"]
            exists.sql_expression = item["sql_expression"]
            exists.table_name = item["table_name"]
            exists.description = item["description"]
            exists.metric_type = item["metric_type"]
            exists.dimension_type = item["dimension_type"]

    for item in SEMANTIC_EXAMPLES:
        exists = await db.scalar(select(SemanticExample).where(SemanticExample.title == item["title"]))
        if not exists:
            db.add(SemanticExample(**item))

    for item in DEFAULT_TEMPLATES:
        exists = await db.scalar(select(Template).where(Template.title == item["title"], Template.is_public.is_(True)))
        if not exists:
            db.add(Template(is_public=True, **item))

    all_columns = {
        "orders": [
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
        ],
        "train": [
            "order_id",
            "tender_id",
            "city_id",
            "user_id",
            "driver_id",
            "offset_hours",
            "status_order",
            "status_tender",
            "order_timestamp",
            "tender_timestamp",
            "driveraccept_timestamp",
            "driverarrived_timestamp",
            "driverstartride_timestamp",
            "driverdone_timestamp",
            "clientcancel_timestamp",
            "drivercancel_timestamp",
            "order_modified_local",
            "cancel_before_accept_local",
            "distance_in_meters",
            "duration_in_seconds",
            "price_order_local",
            "price_tender_local",
            "price_start_local",
        ],
        "cities": ["city_id", "name", "country", "timezone", "is_active"],
        "drivers": ["driver_id", "city_id", "rating", "status", "registered_at", "total_trips"],
        "clients": ["user_id", "city_id", "registered_at", "total_orders", "is_active"],
        "mart_orders": [
            "order_id",
            "city_id",
            "user_id",
            "driver_id",
            "status_order",
            "order_timestamp",
            "driverdone_timestamp",
            "clientcancel_timestamp",
            "drivercancel_timestamp",
            "distance_in_meters",
            "duration_in_seconds",
            "price_order_local",
        ],
        "mart_tenders": [
            "order_id",
            "tender_id",
            "city_id",
            "user_id",
            "driver_id",
            "status_tender",
            "tender_timestamp",
            "price_tender_local",
            "price_start_local",
        ],
        "mart_city_daily": [
            "day",
            "city_id",
            "orders_count",
            "completed_trips",
            "client_cancellations",
            "driver_cancellations",
            "revenue",
            "avg_check",
            "avg_duration_seconds",
            "avg_distance_meters",
        ],
        "mart_driver_daily": ["day", "driver_id", "city_id", "completed_trips", "revenue", "driver_cancellations"],
        "mart_client_daily": ["day", "user_id", "city_id", "orders_count", "completed_trips", "client_cancellations"],
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
SELECT c.name AS city,
       SUM(mo.price_order_local) FILTER (WHERE mo.status_order = 'done') AS revenue
FROM mart_orders mo
JOIN cities c ON c.city_id = mo.city_id
WHERE mo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.name
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
            config_json=report.config_json,
            created_by=owner.id,
        )
    )
    schedule = Schedule(
        report_id=report.id,
        frequency="weekly",
        run_at_time=time(9, 0),
        day_of_week=1,
        next_run_at=datetime.utcnow() + timedelta(days=3),
        is_active=True,
    )
    db.add(schedule)
    db.add(ReportRecipient(report_id=report.id, email="ops-team@drivee.example"))
    await db.flush()
    db.add(
        ScheduleRun(
            schedule_id=schedule.id,
            report_id=report.id,
            status="ok",
            rows_returned=10,
            execution_ms=184,
            ran_at=datetime.utcnow() - timedelta(days=4),
        )
    )


async def bootstrap_demo_data(db: AsyncSession) -> None:
    users = await seed_users(db)
    await seed_drivee_dataset(db)
    await seed_semantics(db)
    await seed_demo_report(db, users)
    await db.commit()
