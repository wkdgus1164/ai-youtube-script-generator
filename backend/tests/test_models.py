"""Tests for Pydantic schema serialization/deserialization."""
from __future__ import annotations

import pytest

from models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    Message,
)


def test_chat_completion_request_basic():
    req = ChatCompletionRequest(
        model="assistant-general",
        messages=[Message(role="user", content="Hi")],
    )
    assert req.model == "assistant-general"
    assert req.stream is False
    assert req.messages[0].role == "user"


def test_chat_completion_request_stream_default():
    req = ChatCompletionRequest(
        model="x",
        messages=[Message(role="user", content="test")],
    )
    assert req.stream is False


def test_chat_completion_response_serialization():
    resp = ChatCompletionResponse(
        id="chatcmpl-abc",
        model="assistant-general",
        choices=[
            Choice(
                index=0,
                message=ChoiceMessage(role="assistant", content="Hello!"),
                finish_reason="stop",
            )
        ],
    )
    data = resp.model_dump()
    assert data["choices"][0]["message"]["content"] == "Hello!"
    assert data["object"] == "chat.completion"


def test_message_roles():
    for role in ("system", "user", "assistant", "tool"):
        msg = Message(role=role, content="test")  # type: ignore[arg-type]
        assert msg.role == role
