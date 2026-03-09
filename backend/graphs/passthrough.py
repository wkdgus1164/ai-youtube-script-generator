"""Passthrough graphs for provider models from EXTRA_MODELS config.

Each model in EXTRA_MODELS is registered as a simple passthrough graph that
forwards messages directly to the provider model without any custom logic.

Responsibility: Register provider models as passthrough graphs
Dependencies: graphs/llm.py, graphs/registry.py, graphs/state.py, config

TODO(template-user): To add a system prompt to passthrough graphs,
modify _register_one() to prepend a SystemMessage in the chat node.
"""
from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from config import settings
from graphs.llm import create_llm
from graphs.registry import register_graph
from graphs.state import MessagesState

logger = logging.getLogger(__name__)


def _register_one(model_name: str) -> None:
    """Register a single provider model as a passthrough graph."""

    @register_graph(model_name, description=f"Direct {model_name} (passthrough)")
    def build() -> CompiledStateGraph:
        llm = create_llm(model_name=model_name)
        graph = StateGraph(MessagesState)
        graph.add_node("chat", lambda s: {"messages": [llm.invoke(s["messages"])]})
        graph.set_entry_point("chat")
        graph.add_edge("chat", END)
        return graph.compile()


def _register_passthrough_models() -> None:
    """Register all models listed in EXTRA_MODELS env var."""
    for model_name in settings.extra_models_list:
        _register_one(model_name)
        logger.info(f"Registered passthrough graph for {model_name!r}")


_register_passthrough_models()
