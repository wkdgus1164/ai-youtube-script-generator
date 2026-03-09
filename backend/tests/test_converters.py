"""Tests for OpenAI ↔ LangChain message conversion."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from converters import convert_messages
from models import FunctionCall, Message, ToolCall


def _msg(role, content=None, **kwargs) -> Message:
    return Message(role=role, content=content, **kwargs)


def test_system_message():
    result = convert_messages([_msg("system", "You are helpful.")])
    assert len(result) == 1
    assert isinstance(result[0], SystemMessage)
    assert result[0].content == "You are helpful."


def test_user_message():
    result = convert_messages([_msg("user", "Hello!")])
    assert isinstance(result[0], HumanMessage)
    assert result[0].content == "Hello!"


def test_assistant_message():
    result = convert_messages([_msg("assistant", "Hi there!")])
    assert isinstance(result[0], AIMessage)
    assert result[0].content == "Hi there!"


def test_assistant_with_tool_calls():
    tc = ToolCall(id="call-1", function=FunctionCall(name="search", arguments='{"q": "test"}'))
    result = convert_messages([_msg("assistant", "", tool_calls=[tc])])
    ai = result[0]
    assert isinstance(ai, AIMessage)
    # LangChain v0.3+ tool_calls format: {name, args, id} (not OpenAI's nested function dict)
    assert ai.tool_calls[0]["id"] == "call-1"
    assert ai.tool_calls[0]["name"] == "search"
    assert ai.tool_calls[0]["args"] == {"q": "test"}


def test_tool_message():
    result = convert_messages([_msg("tool", "search result", tool_call_id="call-1")])
    assert isinstance(result[0], ToolMessage)
    assert result[0].content == "search result"
    assert result[0].tool_call_id == "call-1"


def test_empty_content_defaults_to_empty_string():
    result = convert_messages([_msg("user", None)])
    assert result[0].content == ""


def test_full_conversation():
    messages = [
        _msg("system", "Be helpful."),
        _msg("user", "Hi"),
        _msg("assistant", "Hello!"),
    ]
    result = convert_messages(messages)
    assert len(result) == 3
    assert isinstance(result[0], SystemMessage)
    assert isinstance(result[1], HumanMessage)
    assert isinstance(result[2], AIMessage)
