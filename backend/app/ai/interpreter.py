import re
from datetime import datetime

from app.ai.types import Interpretation


DANGEROUS_RE = re.compile(
    r"\b(drop|delete|update|insert|alter|truncate|create|grant|revoke|copy|merge|call)\b|"
    r"\b(удали|удалить|сотри|измени|запиши|создай таблицу|очисти)\b",
    re.IGNORECASE,
)


def _extract_top(question: str) -> int | None:
    match = re.search(r"(?:топ|top)[-\s]*(\d+)", question, flags=re.IGNORECASE)
    if match:
        return max(1, min(int(match.group(1)), 100))
    return None


def _normalize_date(value: str) -> str | None:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _extract_period(question: str) -> dict:
    lowered = question.lower()
    date_pattern = r"(\d{4}-\d{2}-\d{2}|\d{2}[./]\d{2}[./]\d{4})"
    between_match = re.search(rf"\b(?:с|от)\s+{date_pattern}\s+(?:по|до)\s+{date_pattern}", lowered)
    if between_match:
        start = _normalize_date(between_match.group(1))
        end = _normalize_date(between_match.group(2))
        if start and end:
            return {"kind": "between_dates", "start": start, "end": end, "label": f"с {start} по {end}"}

    since_match = re.search(rf"\b(?:с|от|после|начиная\s+с)\s+{date_pattern}", lowered)
    if since_match:
        start = _normalize_date(since_match.group(1))
        if start:
            return {"kind": "since_date", "start": start, "label": f"с {start}"}

    until_match = re.search(rf"\b(?:до|по)\s+{date_pattern}", lowered)
    if until_match:
        end = _normalize_date(until_match.group(1))
        if end:
            return {"kind": "until_date", "end": end, "label": f"до {end}"}

    exact_match = re.search(rf"\b(?:за|на)\s+{date_pattern}", lowered)
    if exact_match:
        exact = _normalize_date(exact_match.group(1))
        if exact:
            return {"kind": "exact_date", "date": exact, "label": exact}

    days_match = re.search(r"последн\w*\s+(\d+)\s+д", lowered)
    if days_match:
        days = int(days_match.group(1))
        return {"kind": "rolling_days", "days": days, "label": f"последние {days} дней"}
    if "недел" in lowered:
        return {"kind": "rolling_days", "days": 7, "label": "последняя неделя"}
    if "месяц" in lowered or "30 д" in lowered:
        return {"kind": "rolling_days", "days": 30, "label": "последние 30 дней"}
    if "сегодня" in lowered:
        return {"kind": "rolling_days", "days": 1, "label": "сегодня"}
    return {"kind": "missing", "label": "период не указан"}


def _is_total_query(lowered: str) -> bool:
    return any(phrase in lowered for phrase in ["всего", "итого", "суммар", "общее", "общий", "сколько было"])


def interpret_query(question: str) -> Interpretation:
    lowered = question.lower().strip()
    top = _extract_top(question)
    period = _extract_period(question)
    ambiguity_flags: list[str] = []

    dangerous_match = DANGEROUS_RE.search(question)
    if dangerous_match:
        return Interpretation(
            intent="dangerous_operation",
            metric="blocked_operation",
            date_range=period,
            top=top,
            limit=top or 100,
            ambiguity_flags=[],
            dangerous=True,
            dangerous_reason=f"Обнаружена потенциальная write/DDL операция: {dangerous_match.group(0)}",
        )

    metric = None
    intent = "analytics"
    if any(word in lowered for word in ["выруч", "доход", "оборот", "gmv"]):
        metric = "revenue"
    elif "средн" in lowered and any(word in lowered for word in ["чек", "цена"]):
        metric = "avg_check"
    elif any(word in lowered for word in ["kpi", "ключев"]):
        metric = "kpi"
    elif "decline" in lowered or "тендер" in lowered:
        metric = "tender_decline_rate"
    elif "отмен" in lowered and "водител" in lowered:
        metric = "driver_cancellations"
    elif "отмен" in lowered and "клиент" in lowered:
        metric = "client_cancellations"
    elif "отмен" in lowered:
        metric = "client_cancellations"
        ambiguity_flags.append("Неясно, нужны отмены клиентом или водителем.")
    elif "водител" in lowered and any(word in lowered for word in ["актив", "сколько", "колич"]):
        metric = "active_drivers"
    elif any(word in lowered for word in ["поезд", "заверш"]):
        metric = "completed_trips"
    elif any(word in lowered for word in ["заказ", "статистик"]):
        metric = "orders_count"

    dimensions: list[str] = []
    if any(word in lowered for word in ["город", "регион"]):
        dimensions.append("city")
    if any(word in lowered for word in ["день", "дням", "динамик", "тренд"]):
        dimensions.append("day")
    if "водител" in lowered and metric not in {"active_drivers", "driver_cancellations"}:
        dimensions.append("driver")

    if not metric:
        ambiguity_flags.append("Метрика не распознана: укажите выручку, заказы, отмены, водителей или KPI.")
    if period["kind"] == "missing" and metric not in {"active_drivers"}:
        ambiguity_flags.append("Период не указан: безопаснее уточнить диапазон дат.")
    if metric == "revenue" and "месяц" in lowered and "чист" not in lowered and "пол" not in lowered and not top:
        ambiguity_flags.append("Для выручки используется полная сумма поездки price_order_local; можно уточнить, если нужна другая трактовка.")
    if not dimensions and metric not in {"kpi"} and not _is_total_query(lowered):
        dimensions.append("city" if metric in {"revenue", "orders_count", "completed_trips", "client_cancellations", "driver_cancellations", "active_drivers"} else "day")

    limit = top or (1 if not dimensions and metric else 100 if "day" in dimensions else 20)
    return Interpretation(
        intent=intent,
        metric=metric,
        dimensions=dimensions,
        date_range=period,
        grouping=dimensions,
        sorting={"by": metric or "", "direction": "desc"},
        top=top,
        limit=limit,
        ambiguity_flags=ambiguity_flags,
    )
