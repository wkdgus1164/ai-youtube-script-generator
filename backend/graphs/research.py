"""assistant-research: Research assistant with web search.

Architecture:
  [chat_node] ─(tool_call?)─► [tool_node] ─► [chat_node] ─► END
                  └─ no ──────────────────────────────────► END

Responsibility: Build the research assistant graph with web search tool
Dependencies: graphs/llm.py, graphs/registry.py, graphs/state.py, tools
"""
from __future__ import annotations

import logging

from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from graphs.llm import create_llm
from graphs.registry import register_graph
from graphs.state import MessagesState
from tools import web_search_tool

logger = logging.getLogger(__name__)

# TODO(template-user): Customize this prompt to fit your use case.
SYSTEM_PROMPT = (
    "You are a research assistant that finds and analyzes up-to-date information. "
    "Use web_search_tool when you need current information, then answer based on the results. "
    "Clearly cite your sources and provide accurate information."
)

TOOLS = [web_search_tool]


@register_graph("assistant-research", description="Web-search powered research assistant")
def build_research_graph() -> CompiledStateGraph:
    """Build and compile the research assistant graph."""
    llm = create_llm(temperature=0.3).bind_tools(TOOLS)
    tool_node = ToolNode(TOOLS)

    def chat_node(state: MessagesState) -> dict[str, list]:
        msgs = list(state["messages"])
        if not msgs or not isinstance(msgs[0], SystemMessage):
            msgs = [SystemMessage(content=SYSTEM_PROMPT)] + msgs
        return {"messages": [llm.invoke(msgs)]}

    def should_use_tools(state: MessagesState) -> str:
        """Route to tool_node if the last message has tool_calls."""
        last = list(state["messages"])[-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("chat", chat_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("chat")
    graph.add_conditional_edges("chat", should_use_tools)
    graph.add_edge("tools", "chat")
    return graph.compile()
