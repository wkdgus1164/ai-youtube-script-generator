"""Typed graph registry with decorator-based registration.

Provides @register_graph for self-registration and get_graph() for lookup.
Graphs are built once and cached via lru_cache.

Responsibility: Graph registration and lookup
Dependencies: langgraph (CompiledStateGraph type only)
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Callable

from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)

BuildGraphFn = Callable[[], CompiledStateGraph]


class GraphEntry(TypedDict):
    description: str
    build_fn: BuildGraphFn


_REGISTRY: dict[str, GraphEntry] = {}


def register_graph(model_id: str, *, description: str = "") -> Callable[[BuildGraphFn], BuildGraphFn]:
    """Decorator: register a graph builder function in the registry.

    Usage:
        @register_graph("my-agent", description="My custom agent")
        def build_my_agent() -> CompiledStateGraph:
            ...
    """
    def decorator(build_fn: BuildGraphFn) -> BuildGraphFn:
        _REGISTRY[model_id] = GraphEntry(description=description, build_fn=build_fn)
        logger.debug(f"Registered graph: {model_id!r}")
        return build_fn
    return decorator


@lru_cache(maxsize=None)
def _build_cached(model_id: str) -> CompiledStateGraph:
    """Build and cache a graph. Called at most once per model_id."""
    return _REGISTRY[model_id]["build_fn"]()


def get_graph(model_id: str) -> CompiledStateGraph:
    """Return the compiled graph for model_id.

    Raises:
        KeyError: if model_id is not registered (explicit failure, no silent fallback).
    """
    if model_id not in _REGISTRY:
        available = list(_REGISTRY)
        raise KeyError(
            f"Unknown model {model_id!r}. "
            f"Available models: {available}"
        )
    return _build_cached(model_id)


def get_available_models() -> dict[str, GraphEntry]:
    """Return a copy of the full registry."""
    return dict(_REGISTRY)
