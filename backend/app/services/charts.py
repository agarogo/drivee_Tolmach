from datetime import date, datetime
from decimal import Decimal
from numbers import Number


def serialize_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def serialize_rows(rows: list[dict]) -> list[dict]:
    return [{key: serialize_value(value) for key, value in row.items()} for row in rows]


def recommend_chart(rows: list[dict]) -> dict:
    if not rows:
        return {"type": "table_only"}

    first = rows[0]
    columns = list(first.keys())
    numeric_cols = [
        col
        for col in columns
        if isinstance(first.get(col), Number)
        and not isinstance(first.get(col), bool)
    ]
    date_cols = [
        col
        for col in columns
        if isinstance(first.get(col), (date, datetime))
        or col.lower() in {"date", "day", "week", "month", "created_at"}
    ]
    category_cols = [col for col in columns if col not in numeric_cols]

    if date_cols and numeric_cols:
        return {
            "type": "line",
            "x": date_cols[0],
            "series": [{"key": col, "name": col} for col in numeric_cols[:3]],
        }

    if len(numeric_cols) == 1 and category_cols:
        return {
            "type": "bar",
            "x": category_cols[0],
            "series": [{"key": numeric_cols[0], "name": numeric_cols[0]}],
        }

    if len(numeric_cols) >= 2 and category_cols:
        return {
            "type": "grouped_bar",
            "x": category_cols[0],
            "series": [{"key": col, "name": col} for col in numeric_cols[:4]],
        }

    return {"type": "table_only"}
