"""Persistent prompt storage for the script-writer bounded context."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config import settings
from graphs.script_writer.prompts import (
    EDITABLE_PROMPT_ORDER,
    EDITABLE_PROMPT_TITLES,
    PROMPTS,
    PromptConfig,
)

_STORE_LOCK = Lock()


class ScriptWriterPromptView(BaseModel):
    """Prompt body plus static runtime settings exposed to the editor UI."""

    key: str
    title: str
    body: str
    default_body: str
    max_tokens: int
    temperature: float


class ScriptWriterPromptCollection(BaseModel):
    """GET response for the prompt editor."""

    prompts: list[ScriptWriterPromptView]


class ScriptWriterPromptUpdateRequest(BaseModel):
    """PUT request payload for prompt body updates."""

    model_config = ConfigDict(extra="forbid")

    prompts: dict[str, str] = Field(default_factory=dict)

    @field_validator("prompts")
    @classmethod
    def validate_prompts(cls, prompts: dict[str, str]) -> dict[str, str]:
        editable_keys = set(EDITABLE_PROMPT_ORDER)
        unknown = sorted(set(prompts) - editable_keys)
        if unknown:
            raise ValueError(f"Unknown prompt keys: {', '.join(unknown)}")

        cleaned: dict[str, str] = {}
        for key, body in prompts.items():
            normalized = body.strip()
            if not normalized:
                raise ValueError(f"Prompt body cannot be empty: {key}")
            cleaned[key] = normalized
        return cleaned


def _prompt_store_path() -> Path:
    path = Path(settings.script_writer_prompt_store_path)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path


def _default_prompt_bodies() -> dict[str, str]:
    return {key: PROMPTS[key].body for key in EDITABLE_PROMPT_ORDER}


def _load_prompt_overrides() -> dict[str, str]:
    path = _prompt_store_path()
    if not path.exists():
        return {}

    with _STORE_LOCK:
        payload = json.loads(path.read_text(encoding="utf-8"))

    raw_prompts = payload.get("prompts", payload) if isinstance(payload, dict) else {}
    defaults = _default_prompt_bodies()
    overrides: dict[str, str] = {}
    for key, body in raw_prompts.items():
        if key not in defaults or not isinstance(body, str):
            continue
        normalized = body.strip()
        if normalized and normalized != defaults[key]:
            overrides[key] = normalized
    return overrides


def _write_prompt_overrides(overrides: dict[str, str]) -> None:
    path = _prompt_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"prompts": overrides}

    with _STORE_LOCK:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def get_prompt_config(prompt_key: str) -> PromptConfig:
    """Return the effective prompt config, including persisted body overrides."""
    default_config = PROMPTS[prompt_key]
    if prompt_key not in EDITABLE_PROMPT_ORDER:
        return default_config

    override_body = _load_prompt_overrides().get(prompt_key)
    if not override_body:
        return default_config
    return PromptConfig(
        body=override_body,
        max_tokens=default_config.max_tokens,
        temperature=default_config.temperature,
    )


def list_prompt_configs() -> ScriptWriterPromptCollection:
    """Return the editable prompt list with effective and default bodies."""
    overrides = _load_prompt_overrides()
    prompts = [
        ScriptWriterPromptView(
            key=key,
            title=EDITABLE_PROMPT_TITLES[key],
            body=overrides.get(key, PROMPTS[key].body),
            default_body=PROMPTS[key].body,
            max_tokens=PROMPTS[key].max_tokens,
            temperature=PROMPTS[key].temperature,
        )
        for key in EDITABLE_PROMPT_ORDER
    ]
    return ScriptWriterPromptCollection(prompts=prompts)


def save_prompt_bodies(prompt_bodies: dict[str, str]) -> ScriptWriterPromptCollection:
    """Persist prompt body overrides and return the refreshed editor payload."""
    defaults = _default_prompt_bodies()
    merged = _load_prompt_overrides()
    merged.update(prompt_bodies)
    overrides = {
        key: body
        for key, body in merged.items()
        if body.strip() and body.strip() != defaults[key]
    }
    _write_prompt_overrides(overrides)
    return list_prompt_configs()


def reset_prompt_bodies() -> ScriptWriterPromptCollection:
    """Delete all prompt overrides so defaults are used again."""
    path = _prompt_store_path()
    with _STORE_LOCK:
        if path.exists():
            path.unlink()
    return list_prompt_configs()
