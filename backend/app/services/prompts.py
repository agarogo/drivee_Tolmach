SCHEMA_PROMPT = """
Drivee read-only dataset:

CREATE TABLE orders (
  order_id varchar,
  tender_id varchar,
  city_id integer,
  user_id varchar,
  driver_id varchar,
  status_order varchar,
  status_tender varchar,
  order_timestamp timestamptz,
  tender_timestamp timestamptz,
  driverdone_timestamp timestamptz,
  clientcancel_timestamp timestamptz,
  drivercancel_timestamp timestamptz,
  distance_in_meters integer,
  duration_in_seconds integer,
  price_order_local numeric,
  price_tender_local numeric,
  price_start_local numeric,
  primary key (order_id, tender_id)
);

CREATE TABLE cities (city_id integer primary key, name varchar, country varchar, timezone varchar, is_active boolean);
CREATE TABLE drivers (driver_id varchar primary key, city_id integer, rating numeric, status varchar, registered_at timestamptz, total_trips integer);
CREATE TABLE clients (user_id varchar primary key, city_id integer, registered_at timestamptz, total_orders integer, is_active boolean);

Recommended marts:
- mart_orders: one row per order_id.
- mart_tenders: one row per order_id + tender_id.
- mart_city_daily, mart_driver_daily, mart_client_daily: daily aggregates.
"""

SEMANTIC_LAYER = """
Business terms:
- выручка = SUM(mart_orders.price_order_local) FILTER (WHERE status_order = 'done')
- заказы = COUNT(DISTINCT mart_orders.order_id)
- завершённые поездки = COUNT(DISTINCT order_id) FILTER (WHERE status_order = 'done')
- отмены клиентом = COUNT(DISTINCT order_id) FILTER (WHERE clientcancel_timestamp IS NOT NULL)
- отмены водителем = COUNT(DISTINCT order_id) FILTER (WHERE drivercancel_timestamp IS NOT NULL)
- decline тендеров = AVG(CASE WHEN status_tender = 'decline' THEN 1 ELSE 0 END) from mart_tenders
- город = cities.name via city_id
- день = DATE(order_timestamp)

Guardrails:
- Only SELECT/WITH.
- Never write to Drivee dataset.
- No SELECT *.
- Always LIMIT or system limit injection.
"""


def build_prompt(question: str, context_messages: list[dict]) -> str:
    context = "\n".join(f"{item['role']}: {item['content']}" for item in context_messages[-10:])
    return f"""
Ты компонент контролируемого NL2SQL workflow продукта "Толмач by Drivee".
Возвращай JSON с SQL только по плану и semantic hints. Не используй write/DDL.

Схема:
{SCHEMA_PROMPT}

Семантический слой:
{SEMANTIC_LAYER}

Контекст:
{context or "нет"}

Вопрос:
{question}
""".strip()
