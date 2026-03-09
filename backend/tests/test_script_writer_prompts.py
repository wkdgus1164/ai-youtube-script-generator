"""Tests for persisted script-writer prompt editing and timeout settings."""
from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, HumanMessage

from config import settings
from graphs.script_writer.prompt_store import (
    get_prompt_config,
    reset_prompt_bodies,
    save_prompt_bodies,
)
from graphs.script_writer.prompts import PROMPTS
from streaming import run_graph_sync


class _FakeGraph:
    async def ainvoke(self, _inputs, config=None):
        assert config is not None
        return {"messages": [AIMessage(content="final content")]}


def test_prompt_store_persists_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings,
        "script_writer_prompt_store_path",
        str(tmp_path / "script_writer_prompts.json"),
    )

    reset_prompt_bodies()
    assert get_prompt_config("prepare_outline").body == PROMPTS["prepare_outline"].body

    save_prompt_bodies({"prepare_outline": "커스텀 개요 프롬프트"})
    assert get_prompt_config("prepare_outline").body == "커스텀 개요 프롬프트"

    reset_prompt_bodies()
    assert get_prompt_config("prepare_outline").body == PROMPTS["prepare_outline"].body


def test_prompt_editor_api_round_trip(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings,
        "script_writer_prompt_store_path",
        str(tmp_path / "script_writer_prompts.json"),
    )

    reset_prompt_bodies()

    response = client.get("/api/script-writer/prompts")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["prompts"]) == 6

    response = client.put(
        "/api/script-writer/prompts",
        json={"prompts": {"prepare_outline": "새 프롬프트 본문"}},
    )
    assert response.status_code == 200
    updated = response.json()
    edited = next(item for item in updated["prompts"] if item["key"] == "prepare_outline")
    assert edited["body"] == "새 프롬프트 본문"

    response = client.post("/api/script-writer/prompts/reset")
    assert response.status_code == 200
    reset_payload = response.json()
    reset_item = next(item for item in reset_payload["prompts"] if item["key"] == "prepare_outline")
    assert reset_item["body"] == PROMPTS["prepare_outline"].body


def test_run_graph_sync_allows_unlimited_timeout(monkeypatch):
    monkeypatch.setattr(settings, "request_timeout", None)

    response = asyncio.run(
        run_graph_sync(
            _FakeGraph(),
            [HumanMessage(content="hello")],
            "youtube-script-writer",
            "chatcmpl-test",
        )
    )

    assert response.choices[0].message.content == "final content"
