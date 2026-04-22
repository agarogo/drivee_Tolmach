from dataclasses import asdict

from app.config import get_settings
from app.services.cache import TTLCache
from app.services.llm_providers import GeneratedQuery, OllamaProvider, RuleBasedProvider
from app.services.prompts import build_prompt

settings = get_settings()
cache = TTLCache(settings.cache_ttl_seconds)


class TextToSqlService:
    def __init__(self) -> None:
        if settings.llm_provider == "ollama":
            self.provider = OllamaProvider()
        else:
            self.provider = RuleBasedProvider()

    def generate(self, question: str, context_messages: list[dict]) -> GeneratedQuery:
        cache_key = f"{settings.llm_provider}:{settings.llm_model}:{question.strip().lower()}"
        cached = cache.get(cache_key)
        if cached:
            data = dict(cached)
            data["prompt"] = build_prompt(question, context_messages)
            return GeneratedQuery(**data)

        generated = self.provider.generate(question, context_messages)
        cache.set(cache_key, asdict(generated))
        return generated
