SCHEMA_PROMPT = """
CREATE TABLE cities (
  id integer primary key,
  name varchar,
  federal_district varchar
);

CREATE TABLE orders (
  id integer primary key,
  city_id integer references cities(id),
  customer_ref varchar,
  amount numeric,
  status varchar, -- completed, cancelled
  created_at timestamp
);

CREATE TABLE cancellations (
  id integer primary key,
  order_id integer references orders(id),
  city_id integer references cities(id),
  reason varchar,
  created_at timestamp
);
"""

SEMANTIC_LAYER = """
Бизнес-термины:
- выручка = SUM(orders.amount), только orders.status = 'completed'
- заказы = COUNT(*) из orders
- отмены = COUNT(*) из cancellations
- город = cities.name через JOIN cities ON cities.id = orders.city_id/cancellations.city_id
- регион/федеральный округ = cities.federal_district
- топ-N = ORDER BY метрика DESC LIMIT N
- последние N дней = created_at >= CURRENT_DATE - INTERVAL 'N days'
- по дням = DATE(created_at) и GROUP BY day

Guardrails:
- Разрешён только SELECT.
- Запрещены DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE.
- Запрещён доступ к password, password_hash, credit_card, ssn.
- Если LIMIT отсутствует, система добавит LIMIT 1000.
"""


def build_prompt(question: str, context_messages: list[dict]) -> str:
    context = "\n".join(
        f"{item['role']}: {item['content']}" for item in context_messages[-10:]
    )
    return f"""
Ты NL2SQL-аналитик продукта "Толмач".
Отвечай строго валидным JSON без markdown и без пояснений вокруг JSON.

Формат:
{{
  "sql": "SELECT ...",
  "interpretation": {{
    "metric": "название метрики",
    "dimension": "разрез или null",
    "period": "период или null"
  }},
  "answer_intro": "Я понял запрос так: метрика = ..., разрез = ..., период = ...",
  "confidence": 0.0
}}

Если вопрос опасный или просит изменить данные, верни SQL как исходную опасную команду и confidence 1.0:
guardrails заблокируют её до выполнения.

Схема:
{SCHEMA_PROMPT}

Семантический слой:
{SEMANTIC_LAYER}

Последние сообщения чата:
{context or "нет"}

Вопрос пользователя:
{question}
""".strip()
