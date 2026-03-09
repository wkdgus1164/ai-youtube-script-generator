"""Tests for script writer workflow telemetry events."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from graphs.script_writer import graph as script_graph
from graphs.script_writer import tools as script_tools


def test_parse_input_emits_workflow_step_event(monkeypatch):
    captured: list[tuple[str, dict]] = []

    async def _fake_dispatch(name: str, data: dict):
        captured.append((name, data))

    monkeypatch.setattr(script_graph, "adispatch_custom_event", _fake_dispatch)

    result = asyncio.run(
        script_graph._parse_input(  # pylint: disable=protected-access
            {"messages": [HumanMessage(content="https://youtu.be/dQw4w9WgXcQ")]}
        )
    )

    workflow_event = next(data for name, data in captured if name == "workflow_step")
    assert result["youtube_url"] == "https://youtu.be/dQw4w9WgXcQ"
    assert workflow_event["step_name"] == "parse_input"
    assert workflow_event["state_input"]["user_message"] == "https://youtu.be/dQw4w9WgXcQ"
    assert workflow_event["state_update"]["youtube_url"] == "https://youtu.be/dQw4w9WgXcQ"


def test_fetch_transcript_manual_source_emits_workflow_step_event(monkeypatch):
    captured: list[tuple[str, dict]] = []

    async def _fake_dispatch(name: str, data: dict):
        captured.append((name, data))

    monkeypatch.setattr(script_tools, "adispatch_custom_event", _fake_dispatch)

    command = asyncio.run(
        script_tools.fetch_transcript.coroutine(
            {"source_text": "manual transcript", "loop_count": 0},
            "call-fetch",
        )
    )

    assert isinstance(command, Command)
    workflow_event = next(data for name, data in captured if name == "workflow_step")
    assert workflow_event["tool_call_id"] == "call-fetch"
    assert workflow_event["state_input"]["source_text"] == "manual transcript"
    assert workflow_event["raw_output"] == "manual transcript"
    assert workflow_event["state_update"]["transcript"] == "manual transcript"


def test_prepare_outline_emits_prompt_telemetry(monkeypatch):
    captured: list[tuple[str, dict]] = []

    class _FakeLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content="핵심 포인트\n배경 설명")

    async def _fake_dispatch(name: str, data: dict):
        captured.append((name, data))

    monkeypatch.setattr(script_tools, "create_llm", lambda **_kwargs: _FakeLLM())
    monkeypatch.setattr(script_tools, "adispatch_custom_event", _fake_dispatch)

    command = asyncio.run(
        script_tools.prepare_outline.coroutine(
            {"transcript": "원문 자막", "loop_count": 0},
            "call-outline",
        )
    )

    assert isinstance(command, Command)
    workflow_event = next(data for name, data in captured if name == "workflow_step")
    assert workflow_event["tool_call_id"] == "call-outline"
    assert "원문 자막" in workflow_event["rendered_prompt"]
    assert workflow_event["raw_output"] == "핵심 포인트\n배경 설명"
    assert workflow_event["state_update"]["outline"]
