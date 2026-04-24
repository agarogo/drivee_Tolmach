from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from string import Template
from typing import Any

from app.config import get_settings

settings = get_settings()

PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"
SECTION_RE = re.compile(r"^##\s+(System|User)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class PromptDefinition:
    prompt_key: str
    version: str
    path: Path
    system_template: str
    user_template: str

    def render(self, context: dict[str, Any]) -> tuple[str, str]:
        safe_context = {key: str(value) for key, value in context.items()}
        return (
            Template(self.system_template).safe_substitute(safe_context).strip(),
            Template(self.user_template).safe_substitute(safe_context).strip(),
        )


class PromptRegistry:
    def __init__(self, prompt_root: Path | None = None) -> None:
        self.prompt_root = prompt_root or PROMPT_ROOT
        self._registry = self._discover_registry()

    def _discover_registry(self) -> dict[str, dict[str, Path]]:
        registry: dict[str, dict[str, Path]] = {}
        if not self.prompt_root.exists():
            raise FileNotFoundError(f"Prompt root {self.prompt_root} does not exist.")
        for prompt_dir in sorted(path for path in self.prompt_root.iterdir() if path.is_dir()):
            versions: dict[str, Path] = {}
            for prompt_file in sorted(prompt_dir.glob("v*.md")):
                version = prompt_file.stem.lower()
                versions[version] = prompt_file
            if versions:
                registry[prompt_dir.name] = versions
        if not registry:
            raise ValueError(f"No versioned prompts were found under {self.prompt_root}.")
        return registry

    def _version_sort_key(self, version: str) -> tuple[int, str]:
        match = re.match(r"^v(\d+)$", version.lower())
        if match:
            return int(match.group(1)), version.lower()
        return -1, version.lower()

    def latest_version(self, prompt_key: str) -> str:
        versions = self._registry.get(prompt_key, {})
        if not versions:
            raise KeyError(f"Prompt key {prompt_key} is not registered.")
        return sorted(versions, key=self._version_sort_key)[-1]

    def configured_version(self, prompt_key: str) -> str:
        mapping = {
            "answer_type_classifier": settings.llm_prompt_classifier_version,
            "intent_extraction": settings.llm_prompt_intent_version,
            "clarification_need": settings.llm_prompt_clarification_version,
            "sql_plan_draft": settings.llm_prompt_plan_version,
            "answer_summary": settings.llm_prompt_summary_version,
        }
        version = mapping.get(prompt_key) or self.latest_version(prompt_key)
        if version not in self._registry.get(prompt_key, {}):
            raise KeyError(f"Prompt {prompt_key} version {version} is not registered.")
        return version

    def get(self, prompt_key: str, version: str | None = None) -> PromptDefinition:
        resolved_version = version or self.configured_version(prompt_key)
        path = self._registry.get(prompt_key, {}).get(resolved_version)
        if path is None:
            raise KeyError(f"Prompt {prompt_key} version {resolved_version} is not registered.")
        text = path.read_text(encoding="utf-8")
        system_template, user_template = self._parse_sections(text, str(path))
        return PromptDefinition(
            prompt_key=prompt_key,
            version=resolved_version,
            path=path,
            system_template=system_template,
            user_template=user_template,
        )

    def _parse_sections(self, text: str, source: str) -> tuple[str, str]:
        matches = list(SECTION_RE.finditer(text))
        if len(matches) < 2:
            raise ValueError(f"Prompt file {source} must contain ## System and ## User sections.")
        sections: dict[str, str] = {}
        for index, match in enumerate(matches):
            section_name = match.group(1).lower()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            sections[section_name] = text[start:end].strip()
        if "system" not in sections or "user" not in sections:
            raise ValueError(f"Prompt file {source} must contain both ## System and ## User sections.")
        return sections["system"], sections["user"]


@lru_cache
def get_prompt_registry() -> PromptRegistry:
    return PromptRegistry()
