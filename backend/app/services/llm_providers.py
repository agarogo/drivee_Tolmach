import json
from dataclasses import dataclass

from app.ai.generator import generate_sql
from app.ai.interpreter import interpret_query
from app.ai.planner import build_plan
from app.ai.types import RetrievalResult
from app.services.prompts import build_prompt


@dataclass
class GeneratedQuery:
    sql: str
    interpretation: dict
    answer_intro: str
    confidence: float
    prompt: str
    raw_response: str


class RuleBasedProvider:
    def generate(self, question: str, context_messages: list[dict]) -> GeneratedQuery:
        prompt = build_prompt(question, context_messages)
        interpretation = interpret_query(question)
        if interpretation.dangerous:
            sql = question.strip()
            confidence = 1.0
        else:
            plan = build_plan(interpretation, RetrievalResult([], [], []))
            sql = generate_sql(plan, interpretation) if interpretation.metric else ""
            confidence = 0.9 if interpretation.metric and not interpretation.ambiguity_flags else 0.55
        answer_intro = (
            "Система поняла запрос так: "
            f"метрика = {interpretation.metric or 'не определена'}, "
            f"разрез = {', '.join(interpretation.dimensions) or 'не определён'}, "
            f"период = {interpretation.date_range.get('label', 'не указан')}."
        )
        raw_response = json.dumps(
            {
                "provider": "controlled_rule_based",
                "interpretation": interpretation.as_dict(),
                "sql": sql,
                "confidence": confidence,
            },
            ensure_ascii=False,
        )
        return GeneratedQuery(sql, interpretation.as_dict(), answer_intro, confidence, prompt, raw_response)


class OllamaProvider:
    """Compatibility provider.

    The production MVP uses app.ai.orchestrator instead of a direct question-to-SQL prompt.
    This provider intentionally falls back to the controlled deterministic path.
    """

    def __init__(self) -> None:
        self.fallback = RuleBasedProvider()

    def generate(self, question: str, context_messages: list[dict]) -> GeneratedQuery:
        return self.fallback.generate(question, context_messages)
