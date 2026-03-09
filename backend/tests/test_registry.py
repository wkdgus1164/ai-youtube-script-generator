"""Tests for the graph registry."""
from __future__ import annotations

import pytest


def test_register_and_get(clean_registry):
    """Registered graph should be retrievable."""
    from graphs.registry import get_graph, register_graph

    sentinel = object()

    @register_graph("test-model", description="A test model")
    def build():
        return sentinel  # type: ignore[return-value]

    result = get_graph("test-model")
    assert result is sentinel


def test_get_unknown_raises_key_error(clean_registry):
    """Requesting an unregistered model should raise KeyError (no silent fallback)."""
    from graphs.registry import get_graph

    with pytest.raises(KeyError, match="unknown-model"):
        get_graph("unknown-model")


def test_get_available_models(clean_registry):
    """get_available_models should reflect registered models."""
    from graphs.registry import get_available_models, register_graph

    @register_graph("model-a", description="A")
    def build_a():
        return object()  # type: ignore[return-value]

    models = get_available_models()
    assert "model-a" in models
    assert models["model-a"]["description"] == "A"


def test_lru_cache_builds_once(clean_registry):
    """Graph builder should be called only once per model_id."""
    from graphs.registry import get_graph, register_graph

    call_count = 0

    @register_graph("cached-model")
    def build():
        nonlocal call_count
        call_count += 1
        return object()  # type: ignore[return-value]

    get_graph("cached-model")
    get_graph("cached-model")
    assert call_count == 1
