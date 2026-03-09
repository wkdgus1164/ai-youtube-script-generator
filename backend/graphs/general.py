"""assistant-general: General AI assistant without tools.

Architecture:
  [chat_node] ──────────────────────────────────────────────► END

Responsibility: Build the general-purpose chat graph
Dependencies: graphs/llm.py, graphs/registry.py, graphs/state.py
"""
from __future__ import annotations

import logging

from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graphs.llm import create_llm
from graphs.registry import register_graph
from graphs.state import MessagesState

logger = logging.getLogger(__name__)

# TODO(template-user): Customize this prompt to fit your use case.
SYSTEM_PROMPT = (
    "You are a capable and helpful AI assistant. "
    "Answer accurately and concisely."
)


@register_graph("assistant-general", description="General AI assistant (no tools)")
def build_general_graph() -> CompiledStateGraph:
    """Build and compile the general assistant graph."""
    llm = create_llm(temperature=0.7)

    def chat_node(state: MessagesState) -> dict[str, list]:
        msgs = list(state["messages"])
        if not msgs or not isinstance(msgs[0], SystemMessage):
            msgs = [SystemMessage(content=SYSTEM_PROMPT)] + msgs
        return {"messages": [llm.invoke(msgs)]}

    graph = StateGraph(MessagesState)
    graph.add_node("chat", chat_node)
    graph.set_entry_point("chat")
    graph.add_edge("chat", END)
    return graph.compile()
