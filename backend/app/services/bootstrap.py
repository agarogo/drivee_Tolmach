import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import Cancellation, City, Order, Template, User


DEFAULT_TEMPLATES = [
    ("Еженедельный KPI", "Покажи KPI за последнюю неделю по дням"),
    ("Отчёт по регионам", "Сравни отмены по федеральным округам"),
]


def seed_users(db: Session) -> None:
    if db.query(User).count() > 0:
        return

    users = [
        User(email="admin@tolmach.local", password_hash=hash_password("admin123"), role="admin"),
        User(email="user@tolmach.local", password_hash=hash_password("user123"), role="user"),
    ]
    users.extend(
        User(
            email=f"demo{i}@tolmach.local",
            password_hash=hash_password("demo123"),
            role="user",
        )
        for i in range(1, 9)
    )
    db.add_all(users)


def seed_templates(db: Session) -> None:
    for title, content in DEFAULT_TEMPLATES:
        exists = db.query(Template).filter(Template.user_id.is_(None), Template.title == title).first()
        if not exists:
            db.add(Template(user_id=None, title=title, content=content))


def seed_analytics(db: Session) -> None:
    if db.query(City).count() == 0:
        db.add_all(
            [
                City(name="Москва", federal_district="Центральный"),
                City(name="Санкт-Петербург", federal_district="Северо-Западный"),
                City(name="Казань", federal_district="Приволжский"),
                City(name="Екатеринбург", federal_district="Уральский"),
                City(name="Новосибирск", federal_district="Сибирский"),
                City(name="Краснодар", federal_district="Южный"),
                City(name="Владивосток", federal_district="Дальневосточный"),
                City(name="Ростов-на-Дону", federal_district="Южный"),
                City(name="Нижний Новгород", federal_district="Приволжский"),
                City(name="Пермь", federal_district="Приволжский"),
            ]
        )
        db.flush()

    if db.query(Order).count() > 0:
        return

    random.seed(42)
    cities = db.query(City).all()
    now = datetime.utcnow()
    orders: list[Order] = []
    cancellations: list[Cancellation] = []

    for idx in range(1, 181):
        city = random.choice(cities)
        created_at = now - timedelta(days=random.randint(0, 59), hours=random.randint(0, 23))
        status = "cancelled" if random.random() < 0.22 else "completed"
        amount = round(random.uniform(420, 4200), 2)
        order = Order(
            city_id=city.id,
            customer_ref=f"customer-{random.randint(1, 35)}",
            amount=amount,
            status=status,
            created_at=created_at,
        )
        db.add(order)
        orders.append(order)

    db.flush()

    cancelled_orders = [order for order in orders if order.status == "cancelled"]
    completed_sample = random.sample([order for order in orders if order.status == "completed"], 16)
    reasons = [
        "client_changed_plans",
        "driver_no_show",
        "long_waiting_time",
        "price_too_high",
        "duplicate_order",
    ]
    for order in cancelled_orders + completed_sample:
        cancellations.append(
            Cancellation(
                order_id=order.id,
                city_id=order.city_id,
                reason=random.choice(reasons),
                created_at=order.created_at + timedelta(minutes=random.randint(1, 25)),
            )
        )

    db.add_all(cancellations[:55])


def bootstrap_demo_data(db: Session) -> None:
    seed_users(db)
    seed_templates(db)
    seed_analytics(db)
    db.commit()
