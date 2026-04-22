from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.services.charts import serialize_rows

settings = get_settings()


def run_sql(sql: str) -> list[dict]:
    with engine.begin() as conn:
        conn.execute(text(f"SET LOCAL statement_timeout = {settings.query_timeout_ms};"))
        result = conn.execute(text(sql))
        rows = [dict(row._mapping) for row in result.fetchall()]
    return serialize_rows(rows)
