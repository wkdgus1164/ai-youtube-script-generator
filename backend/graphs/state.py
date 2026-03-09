"""Shared LangGraph state for conversational graphs.

All graph modules should use MessagesState (or subclass it) instead of
defining their own State TypedDict.

Responsibility: State type definitions
Dependencies: langchain-core, langgraph
"""
from __future__ import annotations

from typing import Annotated, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class MessagesState(TypedDict):
    """Standard conversational state with message history managed by LangGraph."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
