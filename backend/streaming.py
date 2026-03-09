"""Execute LangGraph graphs and format output as OpenAI-compatible SSE.

Responsibility: Graph execution and SSE streaming
Dependencies: langgraph, models.py, config.py
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langgraph.graph.state import CompiledStateGraph

from config import settings
from models import (
    ChatCompletionChunk,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    DeltaMessage,
    StreamChoice,
    UsageInfo,
)

logger = logging.getLogger(__name__)

_GRAPH_CONFIG = {"recursion_limit": 25}


async def stream_graph_response(
    graph: CompiledStateGraph,
    lc_messages: list[BaseMessage],
    model: str,
    completion_id: str,
) -> AsyncGenerator[str, None]:
    """Execute a LangGraph graph via astream_events and yield OpenAI SSE chunks.

    Args:
        graph:         Compiled LangGraph graph.
        lc_messages:   Converted LangChain messages.
        model:         Model ID string (used in SSE payload).
        completion_id: Unique completion ID for this request.

    Yields:
        SSE-formatted data strings (each line is "data: <json>\\n\\n").
    """
    # First chunk: signal role
    first_chunk = ChatCompletionChunk(
        id=completion_id,
        model=model,
        choices=[
            StreamChoice(
                index=0,
                delta=DeltaMessage(role="assistant", content=""),
                finish_reason=None,
            )
        ],
    )
    yield f"data: {first_chunk.model_dump_json()}\n\n"

    try:
        async for event in graph.astream_events(
            {"messages": lc_messages},
            config=_GRAPH_CONFIG,
        ):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk_data = event.get("data", {})
                chunk: AIMessageChunk = chunk_data.get("chunk")
                if chunk and chunk.content:
                    token = (
                        chunk.content
                        if isinstance(chunk.content, str)
                        else str(chunk.content)
                    )
                    sse_chunk = ChatCompletionChunk(
                        id=completion_id,
                        model=model,
                        choices=[
                            StreamChoice(
                                index=0,
                                delta=DeltaMessage(content=token),
                                finish_reason=None,
                            )
                        ],
                    )
                    yield f"data: {sse_chunk.model_dump_json()}\n\n"

    except asyncio.TimeoutError:
        logger.error("Graph execution timed out")
        error_chunk = ChatCompletionChunk(
            id=completion_id,
            model=model,
            choices=[
                StreamChoice(
                    index=0,
                    delta=DeltaMessage(content="\n\n[Error: Request timed out]"),
                    finish_reason="stop",
                )
            ],
        )
        yield f"data: {error_chunk.model_dump_json()}\n\n"

    except Exception as e:
        logger.exception(f"Graph execution error: {e}")
        error_chunk = ChatCompletionChunk(
            id=completion_id,
            model=model,
            choices=[
                StreamChoice(
                    index=0,
                    delta=DeltaMessage(content=f"\n\n[Error: {e}]"),
                    finish_reason="stop",
                )
            ],
        )
        yield f"data: {error_chunk.model_dump_json()}\n\n"

    # Terminal chunk
    final_chunk = ChatCompletionChunk(
        id=completion_id,
        model=model,
        choices=[
            StreamChoice(
                index=0,
                delta=DeltaMessage(),
                finish_reason="stop",
            )
        ],
    )
    yield f"data: {final_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


async def run_graph_sync(
    graph: CompiledStateGraph,
    lc_messages: list[BaseMessage],
    model: str,
    completion_id: str,
) -> ChatCompletionResponse:
    """Execute a LangGraph graph synchronously and return a single response.

    Args:
        graph:         Compiled LangGraph graph.
        lc_messages:   Converted LangChain messages.
        model:         Model ID string.
        completion_id: Unique completion ID for this request.

    Returns:
        ChatCompletionResponse with the last AI message as content.

    Raises:
        HTTPException(504): if execution exceeds settings.request_timeout.
    """
    from fastapi import HTTPException

    try:
        result = await asyncio.wait_for(
            graph.ainvoke({"messages": lc_messages}, config=_GRAPH_CONFIG),
            timeout=settings.request_timeout,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Request timed out")

    final_messages = result.get("messages", [])
    last_ai = next(
        (m for m in reversed(final_messages) if isinstance(m, AIMessage)), None
    )

    content = ""
    if last_ai:
        content = (
            last_ai.content
            if isinstance(last_ai.content, str)
            else json.dumps(last_ai.content, ensure_ascii=False)
        )

    return ChatCompletionResponse(
        id=completion_id,
        model=model,
        choices=[
            Choice(
                index=0,
                message=ChoiceMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=UsageInfo(),
    )
