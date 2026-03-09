"""YouTube Script Writer graph: Tool-calling agent 패턴.

토폴로지:
  START → parse_input → orchestrator → [tool_calls?] → tools → [workflow_complete?] → orchestrator → ...
                                └─ [no calls] → END                          └─ [True] → END

Responsibility: StateGraph 조립 및 등록
Dependencies: tools.py, state.py, prompts.py, graphs/registry.py
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from graphs.llm import create_llm
from graphs.registry import register_graph
from graphs.script_writer.prompts import ORCHESTRATOR_SYSTEM_PROMPT
from graphs.script_writer.state import ScriptGeneratorState
from graphs.script_writer.tools import ALL_TOOLS

_YOUTUBE_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|v/|shorts/|live/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
)


async def _parse_input(state: ScriptGeneratorState) -> dict[str, Any]:
    """마지막 HumanMessage에서 YouTube URL 또는 원문 텍스트를 추출합니다."""
    await adispatch_custom_event(
        "progress", {"step": 0, "total": 9, "status": "running", "name": "입력 파싱"}
    )

    messages = list(state.get("messages", []))
    last_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    content = str(last_human.content).strip() if last_human else ""

    if _YOUTUBE_PATTERN.search(content):
        result: dict[str, Any] = {
            "youtube_url": content,
            "source_text": "",
            "target_language": "ja",
            "fallback_language": "en",
            "loop_count": 0,
        }
    else:
        result = {
            "youtube_url": "",
            "source_text": content,
            "target_language": "ja",
            "fallback_language": "en",
            "loop_count": 0,
        }

    await adispatch_custom_event(
        "workflow_step",
        {
            "step": 0,
            "step_name": "parse_input",
            "display_name": "입력 파싱",
            "tool_call_id": f"parse_input-{uuid.uuid4().hex[:12]}",
            "loop_count": int(result.get("loop_count", 0)),
            "state_input": {"user_message": content},
            "rendered_prompt": None,
            "raw_output": result,
            "state_update": result,
            "tool_message": "입력 파싱 완료",
        },
    )

    await adispatch_custom_event(
        "progress", {"step": 0, "total": 9, "status": "done", "name": "입력 파싱"}
    )
    return result


async def _orchestrator(state: ScriptGeneratorState) -> dict[str, Any]:
    """오케스트레이터 LLM: 시스템 프롬프트 + 메시지 히스토리를 보고 다음 도구를 호출합니다."""
    llm = create_llm(streaming=False, temperature=0.1)
    bound = llm.bind_tools(ALL_TOOLS)
    messages = [SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT)] + list(state.get("messages", []))
    response = await bound.ainvoke(messages)
    return {"messages": [response]}


def _route_after_tools(state: ScriptGeneratorState) -> str:
    """compose_final이 workflow_complete=True를 설정했으면 END, 아니면 orchestrator로 루프."""
    return END if state.get("workflow_complete") else "orchestrator"


@register_graph("youtube-script-writer", description="YouTube URL → 일본어 대본 자동 생성 (Tool-calling agent)")
def build_youtube_script_writer() -> CompiledStateGraph:
    graph = StateGraph(ScriptGeneratorState)

    graph.add_node("parse_input", _parse_input)
    graph.add_node("orchestrator", _orchestrator)
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    graph.add_edge(START, "parse_input")
    graph.add_edge("parse_input", "orchestrator")
    graph.add_conditional_edges("orchestrator", tools_condition)
    graph.add_conditional_edges("tools", _route_after_tools)

    return graph.compile()
