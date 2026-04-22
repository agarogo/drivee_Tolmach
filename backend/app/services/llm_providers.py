import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import get_settings
from app.services.prompts import build_prompt

settings = get_settings()


@dataclass
class GeneratedQuery:
    sql: str
    interpretation: dict
    answer_intro: str
    confidence: float
    prompt: str
    raw_response: str


def _extract_top_n(question: str, default: int = 10) -> int:
    match = re.search(r"(?:топ|top)[-\s]*(\d+)", question, re.IGNORECASE)
    if match:
        return max(1, min(int(match.group(1)), 100))
    return default


def _period_sql(question: str, default_days: int = 30) -> tuple[str, str]:
    lowered = question.lower()
    match = re.search(r"последн\w*\s+(\d+)\s+д", lowered)
    if match:
        days = int(match.group(1))
        return f"CURRENT_DATE - INTERVAL '{days} days'", f"последние {days} дней"
    if "недел" in lowered:
        return "CURRENT_DATE - INTERVAL '7 days'", "последняя неделя"
    if "месяц" in lowered:
        return "CURRENT_DATE - INTERVAL '30 days'", "последние 30 дней"
    return f"CURRENT_DATE - INTERVAL '{default_days} days'", f"последние {default_days} дней"


def _answer_intro(interpretation: dict) -> str:
    return (
        "Я понял запрос так: "
        f"метрика = {interpretation.get('metric') or 'не определена'}, "
        f"разрез = {interpretation.get('dimension') or 'не определён'}, "
        f"период = {interpretation.get('period') or 'не указан'}."
    )


def parse_model_json(text: str) -> dict:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.S).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


class RuleBasedProvider:
    dangerous = re.compile(
        r"\b(drop|delete|update|insert|alter|truncate)\b|удали|сотри|измени таблицу",
        re.IGNORECASE,
    )

    def generate(self, question: str, context_messages: list[dict]) -> GeneratedQuery:
        prompt = build_prompt(question, context_messages)
        lowered = question.lower()
        top_n = _extract_top_n(question)
        period_expr, period_label = _period_sql(question)

        if self.dangerous.search(question):
            sql = question.strip()
            interpretation = {
                "metric": "опасная операция",
                "dimension": None,
                "period": None,
                "warning": "Пользователь просит выполнить небезопасное действие.",
            }
            return self._finish(sql, interpretation, 0.98, prompt)

        is_revenue = any(word in lowered for word in ["выруч", "revenue", "оборот", "продаж"])
        is_cancel = any(word in lowered for word in ["отмен", "cancel"])
        is_kpi = "kpi" in lowered or "ключев" in lowered
        by_day = any(word in lowered for word in ["по дня", "динамик", "день"])
        by_region = any(word in lowered for word in ["регион", "округ"])

        if is_kpi:
            sql = f"""
SELECT
  DATE(o.created_at) AS day,
  COUNT(*) AS orders_count,
  SUM(CASE WHEN o.status = 'completed' THEN o.amount ELSE 0 END) AS revenue,
  ROUND(AVG(CASE WHEN o.status = 'completed' THEN o.amount END), 2) AS avg_check,
  COUNT(*) FILTER (WHERE o.status = 'cancelled') AS cancelled_orders
FROM orders o
WHERE o.created_at >= {period_expr}
GROUP BY day
ORDER BY day
LIMIT 100
""".strip()
            interpretation = {
                "metric": "KPI: заказы, выручка, средний чек, отменённые заказы",
                "dimension": "день",
                "period": period_label,
            }
            return self._finish(sql, interpretation, 0.91, prompt)

        if is_cancel and by_region:
            sql = f"""
SELECT
  c.federal_district AS region,
  COUNT(*) AS cancellations
FROM cancellations ca
JOIN cities c ON c.id = ca.city_id
WHERE ca.created_at >= {period_expr}
GROUP BY c.federal_district
ORDER BY cancellations DESC
LIMIT {top_n if top_n != 10 else 100}
""".strip()
            interpretation = {
                "metric": "количество отмен",
                "dimension": "федеральный округ",
                "period": period_label,
            }
            return self._finish(sql, interpretation, 0.9, prompt)

        if is_cancel:
            select_dim = "DATE(ca.created_at) AS day" if by_day else "c.name AS city"
            group_dim = "day" if by_day else "c.name"
            order_by = "day" if by_day else "cancellations DESC"
            sql = f"""
SELECT
  {select_dim},
  COUNT(*) AS cancellations
FROM cancellations ca
JOIN cities c ON c.id = ca.city_id
WHERE ca.created_at >= {period_expr}
GROUP BY {group_dim}
ORDER BY {order_by}
LIMIT {top_n}
""".strip()
            interpretation = {
                "metric": "количество отмен",
                "dimension": "день" if by_day else "город",
                "period": period_label,
            }
            return self._finish(sql, interpretation, 0.88, prompt)

        if is_revenue or "город" in lowered or "топ" in lowered:
            if by_day:
                sql = f"""
SELECT
  DATE(o.created_at) AS day,
  SUM(o.amount) AS revenue
FROM orders o
WHERE o.status = 'completed'
  AND o.created_at >= {period_expr}
GROUP BY day
ORDER BY day
LIMIT 100
""".strip()
                interpretation = {
                    "metric": "выручка",
                    "dimension": "день",
                    "period": period_label,
                }
                return self._finish(sql, interpretation, 0.9, prompt)

            sql = f"""
SELECT
  c.name AS city,
  SUM(o.amount) AS revenue
FROM orders o
JOIN cities c ON c.id = o.city_id
WHERE o.status = 'completed'
  AND o.created_at >= {period_expr}
GROUP BY c.name
ORDER BY revenue DESC
LIMIT {top_n}
""".strip()
            interpretation = {
                "metric": "выручка",
                "dimension": "город",
                "period": period_label,
                "limit": top_n,
            }
            return self._finish(sql, interpretation, 0.93, prompt)

        interpretation = {
            "metric": None,
            "dimension": None,
            "period": period_label,
            "needs_clarification": True,
        }
        return self._finish("", interpretation, 0.45, prompt)

    def _finish(
        self,
        sql: str,
        interpretation: dict,
        confidence: float,
        prompt: str,
    ) -> GeneratedQuery:
        raw = json.dumps(
            {
                "sql": sql,
                "interpretation": interpretation,
                "answer_intro": _answer_intro(interpretation),
                "confidence": confidence,
                "provider": "rule_based",
            },
            ensure_ascii=False,
        )
        return GeneratedQuery(sql, interpretation, _answer_intro(interpretation), confidence, prompt, raw)


class OllamaProvider:
    def __init__(self) -> None:
        self.fallback = RuleBasedProvider()

    def generate(self, question: str, context_messages: list[dict]) -> GeneratedQuery:
        prompt = build_prompt(question, context_messages)
        payload = {
            "model": settings.llm_model,
            "stream": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": "Ты аккуратный Text-to-SQL ассистент. Возвращай только JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": settings.llm_temperature,
                "num_ctx": 8192,
            },
        }
        request = urllib.request.Request(
            f"{settings.ollama_base_url.rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=settings.llm_timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
            raw = body.get("message", {}).get("content", "")
            parsed = parse_model_json(raw)
            interpretation = dict(parsed.get("interpretation") or {})
            answer_intro = str(parsed.get("answer_intro") or _answer_intro(interpretation))
            return GeneratedQuery(
                sql=str(parsed.get("sql") or ""),
                interpretation=interpretation,
                answer_intro=answer_intro,
                confidence=float(parsed.get("confidence") or 0.7),
                prompt=prompt,
                raw_response=raw,
            )
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            fallback = self.fallback.generate(question, context_messages)
            fallback.raw_response = (
                f"Ollama fallback: HTTP {exc.code}: {error_body}\n\n"
                f"{fallback.raw_response}"
            )
            return fallback
        except Exception as exc:
            fallback = self.fallback.generate(question, context_messages)
            fallback.raw_response = (
                f"Ollama fallback: {type(exc).__name__}: {exc}\n\n"
                f"{fallback.raw_response}"
            )
            return fallback
