"""Tests for OpenWebUI workflow panel streaming."""
from __future__ import annotations

import asyncio
import json

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

from streaming import _build_workflow_panel, stream_graph_response


class _FakeGraph:
    def __init__(self, events):
        self._events = events

    async def astream_events(self, _inputs, config=None):
        assert config is not None
        for event in self._events:
            yield event


def _collect_stream(events, model: str = "youtube-script-writer") -> str:
    async def _run() -> str:
        graph = _FakeGraph(events)
        chunks: list[str] = []
        async for chunk in stream_graph_response(
            graph,
            [HumanMessage(content="seed input")],
            model,
            "chatcmpl-test",
        ):
            chunks.append(chunk)

        content = ""
        for chunk in chunks:
            for line in chunk.splitlines():
                if not line.startswith("data: "):
                    continue
                payload = line.removeprefix("data: ")
                if payload == "[DONE]":
                    continue
                delta = json.loads(payload)["choices"][0]["delta"]
                content += delta.get("content") or ""
        return content

    return asyncio.run(_run())


def test_build_workflow_panel_escapes_and_keeps_large_fields():
    large_text = 'A "quoted" line\n' + ("x" * 100_050) + "TAIL_MARKER"
    panel = _build_workflow_panel(
        {
            "step": 5,
            "step_name": "measure_duration",
            "display_name": "길이 측정",
            "tool_call_id": "call-1",
            "loop_count": 0,
            "state_input": {"draft_text": large_text},
            "rendered_prompt": None,
            "raw_output": {"draft_text": large_text},
            "state_update": {"estimated_minutes": 5.2},
            "tool_message": '완료 "done"',
        },
        {"messages": []},
    )

    assert 'type="tool_calls"' in panel
    assert 'name="5. measure_duration"' in panel
    assert "&quot;" in panel
    assert "TAIL_MARKER" in panel
    assert "[Truncated at" not in panel


def test_stream_graph_response_renders_workflow_panels_and_ignores_progress():
    events = [
        {
            "event": "on_custom_event",
            "name": "workflow_step",
            "data": {
                "step": 0,
                "step_name": "parse_input",
                "display_name": "입력 파싱",
                "tool_call_id": "parse-1",
                "loop_count": 0,
                "state_input": {"user_message": "hello world"},
                "rendered_prompt": None,
                "raw_output": {"source_text": "hello world"},
                "state_update": {"source_text": "hello world", "loop_count": 0},
                "tool_message": "입력 파싱 완료",
            },
        },
        {
            "event": "on_chain_end",
            "name": "parse_input",
            "data": {
                "output": {
                    "youtube_url": "",
                    "source_text": "hello world",
                    "target_language": "ja",
                    "fallback_language": "en",
                    "loop_count": 0,
                }
            },
        },
        {
            "event": "on_custom_event",
            "name": "progress",
            "data": {"step": 1, "total": 9, "status": "running", "name": "자막 추출"},
        },
        {
            "event": "on_custom_event",
            "name": "workflow_step",
            "data": {
                "step": 1,
                "step_name": "fetch_transcript",
                "display_name": "자막 추출",
                "tool_call_id": "call-1",
                "loop_count": 0,
                "rendered_prompt": None,
                "raw_output": "hello world",
                "state_update": {"transcript": "hello world"},
                "tool_message": "자막 추출 완료",
            },
        },
        {
            "event": "on_tool_end",
            "name": "fetch_transcript",
            "data": {
                "output": Command(
                    update={
                        "messages": [ToolMessage(content="자막 추출 완료", tool_call_id="call-1")],
                        "transcript": "hello world",
                    }
                )
            },
        },
        {
            "event": "on_custom_event",
            "name": "result",
            "data": {"text": "## final output"},
        },
    ]

    content = _collect_stream(events)

    assert content.count('<details type="tool_calls" done="true"') == 2
    assert "0. parse_input" in content
    assert "1. fetch_transcript" in content
    assert "source_text" in content
    assert "## final output" in content
    assert "📝" not in content
    assert "✅" not in content


def test_stream_graph_response_preserves_loop_order():
    events = [
        {
            "event": "on_custom_event",
            "name": "workflow_step",
            "data": {
                "step": 5,
                "step_name": "measure_duration",
                "display_name": "길이 측정",
                "tool_call_id": "call-1",
                "loop_count": 0,
                "state_input": {"draft_text": "draft"},
                "rendered_prompt": None,
                "raw_output": {"estimated_minutes": 5.0},
                "state_update": {"estimated_minutes": 5.0, "loop_count": 0},
                "tool_message": "측정 완료",
            },
        },
        {
            "event": "on_tool_end",
            "name": "measure_duration",
            "data": {
                "output": Command(
                    update={
                        "messages": [ToolMessage(content="측정 완료", tool_call_id="call-1")],
                        "estimated_minutes": 5.0,
                        "loop_count": 0,
                    }
                )
            },
        },
        {
            "event": "on_custom_event",
            "name": "workflow_step",
            "data": {
                "step": 6,
                "step_name": "expand_script",
                "display_name": "대본 확장",
                "tool_call_id": "call-2",
                "loop_count": 1,
                "rendered_prompt": "expand prompt",
                "raw_output": "expanded draft",
                "state_update": {"draft_text": "expanded draft", "loop_count": 1},
                "tool_message": "대본 확장 완료",
            },
        },
        {
            "event": "on_tool_end",
            "name": "expand_script",
            "data": {
                "output": Command(
                    update={
                        "messages": [ToolMessage(content="대본 확장 완료", tool_call_id="call-2")],
                        "draft_text": "expanded draft",
                        "loop_count": 1,
                    }
                )
            },
        },
        {
            "event": "on_custom_event",
            "name": "workflow_step",
            "data": {
                "step": 5,
                "step_name": "measure_duration",
                "display_name": "길이 측정",
                "tool_call_id": "call-3",
                "loop_count": 1,
                "rendered_prompt": None,
                "raw_output": {"estimated_minutes": 18.2},
                "state_update": {"estimated_minutes": 18.2, "loop_count": 1},
                "tool_message": "측정 완료",
            },
        },
    ]

    content = _collect_stream(events)

    first_measure = content.index("5. measure_duration")
    expand = content.index("6. expand_script")
    second_measure = content.rindex("5. measure_duration")
    assert first_measure < expand < second_measure
