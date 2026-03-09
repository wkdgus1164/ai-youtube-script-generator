"""Execute LangGraph graphs and format output as OpenAI-compatible SSE.

Responsibility: Graph execution and SSE streaming
Dependencies: langgraph, models.py, config.py
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
from collections.abc import AsyncGenerator
from copy import deepcopy

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

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

_GRAPH_CONFIG = {"recursion_limit": 40}  # 에이전트 루프 마진 (기존 25 → 40)
_SCRIPT_WRITER_MODEL = "youtube-script-writer"


def _build_sse_chunk(
    completion_id: str,
    model: str,
    *,
    content: str | None = None,
    role: str | None = None,
    finish_reason: str | None = None,
) -> str:
    """Serialize one OpenAI-compatible streaming SSE chunk."""
    sse_chunk = ChatCompletionChunk(
        id=completion_id,
        model=model,
        choices=[
            StreamChoice(
                index=0,
                delta=DeltaMessage(role=role, content=content),
                finish_reason=finish_reason,
            )
        ],
    )
    return f"data: {sse_chunk.model_dump_json()}\n\n"


def _normalize_jsonish(value: object) -> object:
    """Convert runtime values into JSON-safe structures for panel rendering."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _normalize_jsonish(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_jsonish(item) for item in value]
    return str(value)


def _state_without_messages(state: dict[str, object]) -> dict[str, object]:
    """Build a JSON-safe snapshot of graph state excluding chat messages."""
    return _normalize_jsonish(
        {key: value for key, value in state.items() if key != "messages"}
    )


def _extract_update_payload(output: object) -> dict[str, object]:
    """Read Command.update or dict outputs from LangGraph events."""
    if isinstance(output, Command):
        return dict(output.update)
    if isinstance(output, dict):
        return dict(output)
    return {}


def _apply_state_update(state: dict[str, object], update: dict[str, object]) -> None:
    """Apply a LangGraph state update to the local streaming snapshot."""
    if not update:
        return

    messages = update.get("messages")
    if isinstance(messages, list):
        existing = list(state.get("messages", []))
        state["messages"] = existing + messages

    for key, value in update.items():
        if key == "messages":
            continue
        state[key] = value


def _tool_panel_name(step: object, step_name: str) -> str:
    """Render a stable panel title that preserves workflow order."""
    if isinstance(step, int):
        return f"{step}. {step_name}"
    return step_name


def _build_workflow_panel(data: dict[str, object], current_state: dict[str, object]) -> str:
    """Render one OpenWebUI tool-call details block from workflow telemetry."""
    tool_call_id = str(data.get("tool_call_id") or "")
    step_name = str(data.get("step_name") or "workflow_step")
    display_name = str(data.get("display_name") or step_name)
    step = data.get("step")
    loop_count = data.get("loop_count", 0)
    state_input = data.get("state_input")
    state_update = data.get("state_update")
    rendered_prompt = data.get("rendered_prompt")
    raw_output = data.get("raw_output")
    tool_message = data.get("tool_message")

    arguments: dict[str, object] = {
        "step_name": step_name,
        "display_name": display_name,
        "loop_count": loop_count,
        "state_input": (
            state_input if state_input is not None else _state_without_messages(current_state)
        ),
    }
    if rendered_prompt:
        arguments["rendered_prompt"] = rendered_prompt

    result: dict[str, object] = {
        "tool_message": tool_message or "",
        "raw_output": raw_output,
        "state_update": state_update if state_update is not None else {},
    }

    escaped_name = html.escape(_tool_panel_name(step, step_name), quote=True)
    escaped_arguments = html.escape(
        json.dumps(arguments, ensure_ascii=False),
        quote=True,
    )
    escaped_result = html.escape(
        json.dumps(result, ensure_ascii=False),
        quote=True,
    )

    return (
        f'<details type="tool_calls" done="true" id="{html.escape(tool_call_id, quote=True)}" '
        f'name="{escaped_name}" arguments="{escaped_arguments}" result="{escaped_result}">\n'
        "<summary>Tool Executed</summary>\n"
        "</details>\n"
    )


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
    yield _build_sse_chunk(completion_id, model, role="assistant", content="")
    current_state: dict[str, object] = {"messages": list(deepcopy(lc_messages))}

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
                    yield _build_sse_chunk(completion_id, model, content=token)

            elif model == _SCRIPT_WRITER_MODEL and kind == "on_chain_end":
                if event.get("name") == "parse_input":
                    update = _extract_update_payload(event.get("data", {}).get("output"))
                    _apply_state_update(current_state, update)

            elif model == _SCRIPT_WRITER_MODEL and kind == "on_tool_end":
                update = _extract_update_payload(event.get("data", {}).get("output"))
                _apply_state_update(current_state, update)

            elif kind == "on_custom_event":
                event_name = event.get("name", "")
                data = event.get("data", {})
                token: str | None = None

                if event_name == "workflow_step" and model == _SCRIPT_WRITER_MODEL:
                    token = _build_workflow_panel(
                        _normalize_jsonish(data),
                        current_state,
                    )

                elif event_name == "progress" and model != _SCRIPT_WRITER_MODEL:
                    step = data.get("step", 0)
                    total = data.get("total", 9)
                    name = data.get("name", "")
                    status = data.get("status", "")
                    if status == "running":
                        token = f"📝 [{step}/{total}] {name} 중...\n"
                    elif status == "done":
                        token = f"✅ [{step}/{total}] {name} 완료\n"

                elif event_name == "result":
                    result_text = data.get("text", "")
                    if result_text:
                        token = f"\n\n---\n\n{result_text}"

                if token:
                    yield _build_sse_chunk(completion_id, model, content=token)

    except TimeoutError:
        logger.error("Graph execution timed out")
        yield _build_sse_chunk(
            completion_id,
            model,
            content="\n\n[Error: Request timed out]",
            finish_reason="stop",
        )

    except Exception as e:
        logger.exception(f"Graph execution error: {e}")
        yield _build_sse_chunk(
            completion_id,
            model,
            content=f"\n\n[Error: {e}]",
            finish_reason="stop",
        )

    # Terminal chunk
    yield _build_sse_chunk(completion_id, model, finish_reason="stop")
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
    except TimeoutError:
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
