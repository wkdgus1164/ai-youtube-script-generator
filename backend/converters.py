"""Convert between OpenAI-format messages and LangChain messages.

Responsibility: Message format conversion (OpenAI ↔ LangChain)
Dependencies: models.py, langchain-core
"""
from __future__ import annotations

import json

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from models import Message


def convert_messages(messages: list[Message]) -> list[BaseMessage]:
    """Convert ChatCompletionRequest messages to LangChain BaseMessage list.

    Args:
        messages: List of OpenAI-format Message objects.

    Returns:
        List of LangChain BaseMessage instances.
    """
    lc_messages: list[BaseMessage] = []

    for msg in messages:
        role = msg.role
        content = msg.content or ""

        if role == "system":
            lc_messages.append(SystemMessage(content=content))

        elif role == "user":
            lc_messages.append(HumanMessage(content=content))

        elif role == "assistant":
            if msg.tool_calls:
                # LangChain v0.3+ expects tool_calls in {name, args, id} format,
                # not the OpenAI nested {function: {name, arguments}} format.
                tool_calls = [
                    {
                        "name": tc.function.name,
                        "args": (
                            json.loads(tc.function.arguments)
                            if tc.function.arguments
                            else {}
                        ),
                        "id": tc.id,
                        "type": "tool_call",
                    }
                    for tc in msg.tool_calls
                ]
                lc_messages.append(AIMessage(content=content, tool_calls=tool_calls))
            else:
                lc_messages.append(AIMessage(content=content))

        elif role == "tool":
            lc_messages.append(
                ToolMessage(
                    content=content,
                    tool_call_id=msg.tool_call_id or "",
                )
            )

    return lc_messages
