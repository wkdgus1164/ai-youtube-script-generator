"""LLM factory using init_chat_model for multi-provider support.

init_chat_model automatically detects the provider from the model name prefix
(e.g. "gpt-4o" → openai, "claude-..." → anthropic) so graph modules don't
need to import provider-specific classes.

Responsibility: LLM instantiation
Dependencies: langchain, config

TODO(template-user): If you need different defaults for a new provider,
add a condition here or pass kwargs when calling create_llm().
"""
from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from config import settings


def create_llm(
    *,
    model_name: str | None = None,
    temperature: float = 0.7,
    streaming: bool = True,
    **kwargs: object,
) -> BaseChatModel:
    """Create an LLM instance via init_chat_model.

    Args:
        model_name: Model identifier (e.g. "gpt-4o-mini", "claude-opus-4-6").
                    Defaults to settings.default_llm_model.
        temperature: Sampling temperature (0.0–1.0).
        streaming:   Enable token streaming.
        **kwargs:    Additional kwargs passed to init_chat_model.

    Returns:
        A BaseChatModel instance bound to the requested model.
    """
    return init_chat_model(
        model_name or settings.default_llm_model,
        temperature=temperature,
        streaming=streaming,
        **kwargs,
    )
