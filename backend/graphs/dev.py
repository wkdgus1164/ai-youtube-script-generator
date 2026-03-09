"""assistant-dev: Development assistant with code execution and web search.

Architecture:
  [chat_node] ─(tool_call?)─► [tool_node] ─► [chat_node] ─► END
                  └─ no ──────────────────────────────────► END

Responsibility: Build the developer assistant graph with code + search tools
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
from tools import code_executor_tool, web_search_tool

logger = logging.getLogger(__name__)

# TODO(template-user): Customize this prompt to fit your use case.
SYSTEM_PROMPT = (
    "You are an expert software development assistant. "
    "Write code and verify it by running it with code_executor_tool before answering. "
    "Use web_search_tool for official docs or latest information when needed. "
    "Always include comments in code and add error handling."
)

TOOLS = [code_executor_tool, web_search_tool]


@register_graph("assistant-dev", description="Code writing and execution development assistant")
def build_dev_graph() -> CompiledStateGraph:
    """Build and compile the development assistant graph."""
    llm = create_llm(temperature=0.2).bind_tools(TOOLS)  # Low temp for code
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
