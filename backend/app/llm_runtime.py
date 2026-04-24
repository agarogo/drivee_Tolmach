from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _default_llm_device(provider_name: str) -> str:
    provider = provider_name.strip().lower()
    if provider in {"fallback", "fallback_rule"}:
        return "cpu"
    return "unknown"


def _as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _matches_model(candidate: dict[str, Any], expected_model: str) -> bool:
    expected = expected_model.strip().lower()
    if not expected:
        return False
    for key in ("model", "name"):
        value = str(candidate.get(key) or "").strip().lower()
        if value == expected:
            return True
    return False


async def probe_llm_runtime() -> dict[str, Any]:
    provider = settings.llm_provider
    model = settings.llm_model
    probe: dict[str, Any] = {
        "llm_device": _default_llm_device(provider),
        "llm_loaded": False,
        "llm_device_source": "config",
    }
    if provider != "ollama":
        return probe

    timeout = httpx.Timeout(max(0.2, settings.health_report_llm_timeout_seconds))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/ps")
            response.raise_for_status()
        payload = response.json()
        models = payload.get("models") if isinstance(payload, dict) else []
        if not isinstance(models, list):
            return probe

        selected: dict[str, Any] | None = None
        for item in models:
            if isinstance(item, dict) and _matches_model(item, model):
                selected = item
                break
        if selected is None:
            for item in models:
                if isinstance(item, dict):
                    selected = item
                    break
        if selected is None:
            return {**probe, "llm_device_source": "ollama_ps"}

        size_vram = _as_int(selected.get("size_vram"))
        loaded_model = str(selected.get("model") or selected.get("name") or "")
        return {
            "llm_device": "gpu" if size_vram > 0 else "cpu",
            "llm_loaded": True,
            "llm_loaded_model": loaded_model,
            "llm_device_source": "ollama_ps",
            "llm_size_vram_bytes": size_vram,
            "llm_size_bytes": _as_int(selected.get("size")),
        }
    except Exception as exc:  # pragma: no cover - best-effort health probe
        logger.warning("LLM runtime probe failed: provider=%s model=%s reason=%s", provider, model, exc)
        return probe


async def current_llm_device_hint() -> str:
    probe = await probe_llm_runtime()
    return str(probe.get("llm_device") or "unknown")


async def build_health_payload(*, app_name: str, mode: str | None = None) -> dict[str, Any]:
    probe = await probe_llm_runtime()
    payload = {
        "status": "ok",
        "app": app_name,
        "database_name": settings.database_label,
        "platform_database_name": settings.database_label,
        "analytics_database_name": settings.database_label,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_device": probe["llm_device"],
        "llm_loaded": probe["llm_loaded"],
        "llm_device_source": probe["llm_device_source"],
        "llm_strict_mode": settings.llm_strict_mode,
        "llm_rule_fallback_allowed": settings.llm_fallback_allowed,
    }
    if mode:
        payload["mode"] = mode
    if probe.get("llm_loaded_model"):
        payload["llm_loaded_model"] = probe["llm_loaded_model"]
    return payload


def build_llm_error_payload(
    *,
    error_code: str,
    provider: str,
    model: str,
    device_hint: str,
    fallback_used: bool,
    message: str,
) -> dict[str, Any]:
    return {
        "status": error_code,
        "error_code": error_code,
        "title": "Запрос выполнялся слишком долго",
        "body": "LLM не успела ответить за лимит времени. Проверь GPU/Ollama или упрости запрос.",
        "message": message,
        "provider": provider,
        "model": model,
        "device_hint": device_hint,
        "fallback_used": fallback_used,
    }
