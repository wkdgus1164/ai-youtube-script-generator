"""ScriptGeneratorState: LangGraph state for the YouTube script writer workflow.

Responsibility: State type definition
Dependencies: langchain-core, langgraph
"""
from __future__ import annotations

from typing import Annotated, Any, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ScriptGeneratorState(TypedDict, total=False):
    """Full workflow state. Messages field uses add_messages reducer for streaming compat."""

    # Conversational field — managed by LangGraph's add_messages reducer
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Input fields set by parse_input
    youtube_url: str
    source_text: str
    target_language: str
    fallback_language: str

    # Transcript step
    transcript: str
    transcript_metadata: dict[str, Any]

    # Script generation steps
    outline: str
    first_draft: str
    draft_text: str

    # Duration measurement
    char_count: int
    char_count_with_spaces: int
    estimated_minutes: float
    loop_count: int

    # Final formatting
    formatted_draft: str
    intros: str
    final_output: dict[str, Any]

    # Tool-calling agent control
    workflow_complete: bool  # compose_final 도구가 True로 설정 → END 라우팅 트리거
