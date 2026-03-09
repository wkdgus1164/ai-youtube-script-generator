"""Environment-based settings module.

All configuration is injected via .env file or environment variables.

Responsibility: Application configuration
Dependencies: pydantic-settings
"""
from __future__ import annotations

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM Provider Keys ─────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str | None = None
    default_llm_model: str = "gpt-4o-mini"

    # ── LangSmith (optional) ──────────────────────────────────────
    langchain_api_key: str | None = None
    langchain_tracing_v2: bool = False
    langchain_project: str = "langgraph-openwebui"

    # ── Backend Auth ──────────────────────────────────────────────
    # Bearer token OpenWebUI sends when calling the backend
    api_key: str = "sk-langgraph-local"

    # ── Timeout ───────────────────────────────────────────────────
    request_timeout: int = 60

    # ── Tavily (assistant-research tool) ──────────────────────────
    tavily_api_key: str | None = None

    # ── Passthrough models ────────────────────────────────────────
    # Provider models to expose in OpenWebUI model picker (comma-separated)
    # TODO(template-user): Add any provider models you want to expose here,
    # e.g. EXTRA_MODELS=gpt-4o,gpt-4o-mini,claude-opus-4-6
    extra_models: str = ""

    @property
    def extra_models_list(self) -> list[str]:
        return [m.strip() for m in self.extra_models.split(",") if m.strip()]


settings = Settings()
