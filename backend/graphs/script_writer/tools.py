"""Tool-calling agent 도구 모음: 9개 @tool 함수.

각 도구는 InjectedState로 상태를 읽고, Command(update={...})로 상태를 업데이트합니다.
LLM에게는 인자 없는 도구로 표시됩니다 (InjectedState / InjectedToolCallId는 schema에서 제외).

Responsibility: YouTube 대본 생성 워크플로우의 9단계 구현
Dependencies: state.py, prompts.py, text_utils.py, graphs/llm.py
"""
from __future__ import annotations

import re
from typing import Annotated, Any

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from graphs.llm import create_llm
from graphs.script_writer.prompt_store import get_prompt_config
from graphs.script_writer.prompts import render_prompt_body
from graphs.script_writer.state import ScriptGeneratorState
from graphs.script_writer.text_utils import (
    ensure_expanded_script,
    ensure_intros,
    ensure_outline,
    ensure_script_quality,
    extract_text,
    normalize_prompt_output,
    sanitize_script_output,
)

# ── LLM 호출 헬퍼 ─────────────────────────────────────────────────────────────


def _json_safe(value: Any) -> Any:
    """Convert arbitrary runtime values into JSON-safe structures for telemetry."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=str)]
    return str(value)


def _state_snapshot(state: ScriptGeneratorState) -> dict[str, Any]:
    """Snapshot the graph state without chat messages for workflow telemetry."""
    return _json_safe({key: value for key, value in state.items() if key != "messages"})


def _state_update(update: dict[str, Any]) -> dict[str, Any]:
    """Serialize a Command.update payload without messages for workflow telemetry."""
    return _json_safe({key: value for key, value in update.items() if key != "messages"})


async def _dispatch_workflow_step(
    *,
    step: int,
    step_name: str,
    display_name: str,
    tool_call_id: str,
    loop_count: int,
    state_input: dict[str, Any],
    state_update: dict[str, Any],
    tool_message: str,
    raw_output: Any,
    rendered_prompt: str | None = None,
) -> None:
    """Emit a structured workflow step event for OpenWebUI tool-style panels."""
    await adispatch_custom_event(
        "workflow_step",
        {
            "step": step,
            "step_name": step_name,
            "display_name": display_name,
            "tool_call_id": tool_call_id,
            "loop_count": loop_count,
            "state_input": _json_safe(state_input),
            "rendered_prompt": rendered_prompt,
            "raw_output": _json_safe(raw_output),
            "state_update": _json_safe(state_update),
            "tool_message": tool_message,
        },
    )


async def _call_llm(prompt_key: str, variables: dict[str, Any]) -> tuple[str, str, str]:
    """Effective prompt config로 LLM을 호출하고 정규화/원문 출력을 함께 반환합니다."""
    config = get_prompt_config(prompt_key)
    rendered = render_prompt_body(config.body, variables)
    llm = create_llm(streaming=False, temperature=config.temperature, max_tokens=config.max_tokens)
    response = await llm.ainvoke([HumanMessage(content=rendered)])
    raw_output = extract_text(response)
    normalized = normalize_prompt_output(prompt_key, raw_output)
    return normalized, rendered, raw_output


# ── 도구 1: fetch_transcript ──────────────────────────────────────────────────


@tool
async def fetch_transcript(
    state: Annotated[ScriptGeneratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """YouTube URL에서 자막을 추출하거나 source_text를 그대로 사용합니다."""
    await adispatch_custom_event(
        "progress", {"step": 1, "total": 9, "status": "running", "name": "자막 추출"}
    )

    source_text = state.get("source_text", "").strip()
    if source_text:
        char_count = len(source_text)
        result: dict[str, Any] = {
            "transcript": source_text,
            "transcript_metadata": {
                "source": "manual",
                "char_count": char_count,
                "estimated_duration_minutes": round(char_count / 320, 1),
            },
        }
        tool_message = f"자막 추출 완료: source_text 사용 ({char_count:,}자)"
        update = {
            "messages": [ToolMessage(content=tool_message, tool_call_id=tool_call_id)],
            **result,
        }
        await _dispatch_workflow_step(
            step=1,
            step_name="fetch_transcript",
            display_name="자막 추출",
            tool_call_id=tool_call_id,
            loop_count=int(state.get("loop_count", 0)),
            state_input=_state_snapshot(state),
            state_update=_state_update(update),
            tool_message=tool_message,
            raw_output=source_text,
        )
        await adispatch_custom_event(
            "progress",
            {"step": 1, "total": 9, "status": "done", "name": f"자막 추출 완료 ({char_count:,}자)"},
        )
        return Command(update=update)

    youtube_url = state.get("youtube_url", "").strip()
    if not youtube_url:
        raise ValueError("youtube_url 또는 source_text 중 하나는 필수입니다.")

    vid = _extract_video_id(youtube_url)
    target_lang = state.get("target_language", "ja") or "ja"
    fallback_lang = state.get("fallback_language", "en") or "en"

    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )

    try:
        api = YouTubeTranscriptApi()
        catalog = list(api.list(vid))

        selected = next((t for t in catalog if t.language_code == target_lang), None)
        strategy = "preferred_language"

        if selected is None:
            selected = next((t for t in catalog if t.language_code == fallback_lang), None)
            strategy = "fallback_language"

        if selected is None and catalog:
            selected = next((t for t in catalog if not t.is_generated), catalog[0])
            strategy = "first_available_transcript"

        if selected is None:
            raise NoTranscriptFound(
                video_id=vid,
                requested_language_codes=[target_lang, fallback_lang],
                transcript_data={},
            )

        items = selected.fetch()
        text = " ".join(item.text for item in items)
        char_count = len(text)
        tool_message = (
            f"자막 추출 완료: YouTube ({char_count:,}자, "
            f"{selected.language_code}, {strategy})"
        )
        update = {
            "messages": [ToolMessage(content=tool_message, tool_call_id=tool_call_id)],
            "transcript": text,
            "transcript_metadata": {
                "source": "youtube",
                "video_id": vid,
                "language": selected.language_code,
                "language_label": selected.language,
                "is_generated": selected.is_generated,
                "selection_strategy": strategy,
                "char_count": char_count,
                "estimated_duration_minutes": round(char_count / 320, 1),
            },
        }
        await _dispatch_workflow_step(
            step=1,
            step_name="fetch_transcript",
            display_name="자막 추출",
            tool_call_id=tool_call_id,
            loop_count=int(state.get("loop_count", 0)),
            state_input=_state_snapshot(state),
            state_update=_state_update(update),
            tool_message=tool_message,
            raw_output=text,
        )

        await adispatch_custom_event(
            "progress",
            {"step": 1, "total": 9, "status": "done", "name": f"자막 추출 완료 ({char_count:,}자)"},
        )
        return Command(update=update)

    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as e:
        raise ValueError(str(e)) from e


def _extract_video_id(url_or_id: str) -> str:
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/live/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, url_or_id)
        if m:
            return m.group(1)
    raise ValueError(f"유효한 YouTube URL 또는 video ID가 아닙니다: {url_or_id}")


# ── 도구 2: prepare_outline ───────────────────────────────────────────────────


@tool
async def prepare_outline(
    state: Annotated[ScriptGeneratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """자막 원문을 분석해 대본 작성 전략(개요)을 수립합니다."""
    await adispatch_custom_event(
        "progress", {"step": 2, "total": 9, "status": "running", "name": "개요 수립"}
    )

    text, rendered_prompt, raw_output = await _call_llm(
        "prepare_outline",
        {"transcript": state.get("transcript", "")},
    )
    outline = ensure_outline(text, state)
    tool_message = "개요 수립 완료"
    update = {
        "messages": [ToolMessage(content=tool_message, tool_call_id=tool_call_id)],
        "outline": outline,
    }
    await _dispatch_workflow_step(
        step=2,
        step_name="prepare_outline",
        display_name="개요 수립",
        tool_call_id=tool_call_id,
        loop_count=int(state.get("loop_count", 0)),
        state_input=_state_snapshot(state),
        state_update=_state_update(update),
        tool_message=tool_message,
        raw_output=raw_output,
        rendered_prompt=rendered_prompt,
    )

    await adispatch_custom_event(
        "progress", {"step": 2, "total": 9, "status": "done", "name": "개요 수립 완료"}
    )
    return Command(update=update)


# ── 도구 3: draft_script ──────────────────────────────────────────────────────


@tool
async def draft_script(
    state: Annotated[ScriptGeneratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """개요와 자막을 바탕으로 일본어 대본 초안을 작성합니다."""
    await adispatch_custom_event(
        "progress", {"step": 3, "total": 9, "status": "running", "name": "초안 작성"}
    )

    text, rendered_prompt, raw_output = await _call_llm("draft_script", {
        "outline": state.get("outline", ""),
        "transcript": state.get("transcript", ""),
    })
    first_draft = normalize_prompt_output("draft_script", text)
    tool_message = "초안 작성 완료"
    update = {
        "messages": [ToolMessage(content=tool_message, tool_call_id=tool_call_id)],
        "first_draft": first_draft,
    }
    await _dispatch_workflow_step(
        step=3,
        step_name="draft_script",
        display_name="초안 작성",
        tool_call_id=tool_call_id,
        loop_count=int(state.get("loop_count", 0)),
        state_input=_state_snapshot(state),
        state_update=_state_update(update),
        tool_message=tool_message,
        raw_output=raw_output,
        rendered_prompt=rendered_prompt,
    )

    await adispatch_custom_event(
        "progress", {"step": 3, "total": 9, "status": "done", "name": "초안 작성 완료"}
    )
    return Command(update=update)


# ── 도구 4: differentiate_script ─────────────────────────────────────────────


@tool
async def differentiate_script(
    state: Annotated[ScriptGeneratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """초안을 50% 차별화된 버전으로 리라이트합니다."""
    await adispatch_custom_event(
        "progress", {"step": 4, "total": 9, "status": "running", "name": "차별화 리라이트"}
    )

    text, rendered_prompt, raw_output = await _call_llm(
        "differentiate_script",
        {"first_draft": state.get("first_draft", "")},
    )
    draft_text = normalize_prompt_output("differentiate_script", text)
    tool_message = "차별화 리라이트 완료"
    update = {
        "messages": [ToolMessage(content=tool_message, tool_call_id=tool_call_id)],
        "draft_text": draft_text,
    }
    await _dispatch_workflow_step(
        step=4,
        step_name="differentiate_script",
        display_name="차별화 리라이트",
        tool_call_id=tool_call_id,
        loop_count=int(state.get("loop_count", 0)),
        state_input=_state_snapshot(state),
        state_update=_state_update(update),
        tool_message=tool_message,
        raw_output=raw_output,
        rendered_prompt=rendered_prompt,
    )

    await adispatch_custom_event(
        "progress", {"step": 4, "total": 9, "status": "done", "name": "차별화 리라이트 완료"}
    )
    return Command(update=update)


# ── 도구 5: measure_duration ──────────────────────────────────────────────────


@tool
async def measure_duration(
    state: Annotated[ScriptGeneratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """대본 길이를 측정하고 예상 방송 시간을 계산합니다 (320자/분 기준).

    ToolMessage 내용에는 estimated_minutes와 loop_count가 포함되며,
    오케스트레이터 LLM이 이 값을 읽고 expand_script vs format_script를 결정합니다.
    """
    await adispatch_custom_event(
        "progress", {"step": 5, "total": 9, "status": "running", "name": "길이 측정"}
    )

    draft_text = state.get("draft_text", "")
    char_count_with_spaces = len(draft_text)
    char_count = len(re.sub(r"\s", "", draft_text))
    estimated_minutes = round(char_count_with_spaces / 320, 1)
    loop_count = int(state.get("loop_count", 0))
    tool_message = (
        f"측정 완료: {estimated_minutes}분 ({char_count_with_spaces}자), "
        f"loop_count={loop_count}"
    )
    update = {
        "messages": [ToolMessage(content=tool_message, tool_call_id=tool_call_id)],
        "draft_text": draft_text,
        "char_count": char_count,
        "char_count_with_spaces": char_count_with_spaces,
        "estimated_minutes": estimated_minutes,
        "loop_count": loop_count,
    }
    await _dispatch_workflow_step(
        step=5,
        step_name="measure_duration",
        display_name="길이 측정",
        tool_call_id=tool_call_id,
        loop_count=loop_count,
        state_input=_state_snapshot(state),
        state_update=_state_update(update),
        tool_message=tool_message,
        raw_output={
            "draft_text": draft_text,
            "char_count": char_count,
            "char_count_with_spaces": char_count_with_spaces,
            "estimated_minutes": estimated_minutes,
            "loop_count": loop_count,
        },
    )

    await adispatch_custom_event(
        "progress",
        {"step": 5, "total": 9, "status": "done", "name": f"길이 측정 ({estimated_minutes}분)"},
    )
    return Command(update=update)


# ── 도구 6: expand_script ─────────────────────────────────────────────────────


@tool
async def expand_script(
    state: Annotated[ScriptGeneratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """대본이 목표 길이(18분)에 부족할 때 사실 기반 내용을 1,800자 이상 추가합니다."""
    await adispatch_custom_event(
        "progress", {"step": 6, "total": 9, "status": "running", "name": "대본 확장"}
    )

    text, rendered_prompt, raw_output = await _call_llm("expand_script", {
        "draft_text": state.get("draft_text", ""),
        "estimated_minutes": state.get("estimated_minutes", 0),
    })
    expanded = ensure_expanded_script(text, state)
    loop_count = int(state.get("loop_count", 0)) + 1
    tool_message = f"대본 확장 완료 (loop_count={loop_count})"
    update = {
        "messages": [ToolMessage(content=tool_message, tool_call_id=tool_call_id)],
        "draft_text": expanded,
        "loop_count": loop_count,
    }
    await _dispatch_workflow_step(
        step=6,
        step_name="expand_script",
        display_name="대본 확장",
        tool_call_id=tool_call_id,
        loop_count=loop_count,
        state_input=_state_snapshot(state),
        state_update=_state_update(update),
        tool_message=tool_message,
        raw_output=raw_output,
        rendered_prompt=rendered_prompt,
    )

    await adispatch_custom_event(
        "progress", {"step": 6, "total": 9, "status": "done", "name": "대본 확장 완료"}
    )
    return Command(update=update)


# ── 도구 7: format_script ─────────────────────────────────────────────────────


@tool
async def format_script(
    state: Annotated[ScriptGeneratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """대본 문단을 150~200자 기준으로 정리하고 TTS용 순수 내레이션으로 포맷합니다."""
    await adispatch_custom_event(
        "progress", {"step": 7, "total": 9, "status": "running", "name": "포맷 정리"}
    )

    text, rendered_prompt, raw_output = await _call_llm(
        "format_script",
        {"draft_text": state.get("draft_text", "")},
    )
    formatted_draft = normalize_prompt_output("format_script", text)
    tool_message = "포맷 정리 완료"
    update = {
        "messages": [ToolMessage(content=tool_message, tool_call_id=tool_call_id)],
        "formatted_draft": formatted_draft,
    }
    await _dispatch_workflow_step(
        step=7,
        step_name="format_script",
        display_name="포맷 정리",
        tool_call_id=tool_call_id,
        loop_count=int(state.get("loop_count", 0)),
        state_input=_state_snapshot(state),
        state_update=_state_update(update),
        tool_message=tool_message,
        raw_output=raw_output,
        rendered_prompt=rendered_prompt,
    )

    await adispatch_custom_event(
        "progress", {"step": 7, "total": 9, "status": "done", "name": "포맷 정리 완료"}
    )
    return Command(update=update)


# ── 도구 8: generate_intros ───────────────────────────────────────────────────


@tool
async def generate_intros(
    state: Annotated[ScriptGeneratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """포맷된 대본을 바탕으로 도입부 3가지 버전을 생성합니다."""
    await adispatch_custom_event(
        "progress", {"step": 8, "total": 9, "status": "running", "name": "도입부 생성"}
    )

    text, rendered_prompt, raw_output = await _call_llm(
        "generate_intros",
        {"formatted_draft": state.get("formatted_draft", "")},
    )
    intros = normalize_prompt_output("generate_intros", text)
    tool_message = "도입부 3가지 버전 생성 완료"
    update = {
        "messages": [ToolMessage(content=tool_message, tool_call_id=tool_call_id)],
        "intros": intros,
    }
    await _dispatch_workflow_step(
        step=8,
        step_name="generate_intros",
        display_name="도입부 생성",
        tool_call_id=tool_call_id,
        loop_count=int(state.get("loop_count", 0)),
        state_input=_state_snapshot(state),
        state_update=_state_update(update),
        tool_message=tool_message,
        raw_output=raw_output,
        rendered_prompt=rendered_prompt,
    )

    await adispatch_custom_event(
        "progress", {"step": 8, "total": 9, "status": "done", "name": "도입부 생성 완료"}
    )
    return Command(update=update)


# ── 도구 9: compose_final ─────────────────────────────────────────────────────


@tool
async def compose_final(
    state: Annotated[ScriptGeneratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """모든 결과물을 조립하고 최종 마크다운을 사용자에게 전달합니다.

    workflow_complete=True를 설정하여 END 라우팅을 트리거합니다.
    """
    await adispatch_custom_event(
        "progress", {"step": 9, "total": 9, "status": "running", "name": "최종 조립"}
    )

    # 최종 대본 품질 검사
    final_script = ensure_script_quality(
        "compose_final",
        normalize_prompt_output("format_script", str(state.get("formatted_draft", ""))),
        fallback=normalize_prompt_output("format_script", str(state.get("draft_text", ""))),
    )
    final_script = sanitize_script_output(final_script, state)

    # 도입부 검증 / 폴백
    intros = ensure_intros(
        normalize_prompt_output("generate_intros", str(state.get("intros", ""))),
        formatted_draft=final_script,
    )

    # 메타데이터 계산
    final_char_count_with_spaces = len(final_script)
    final_char_count = len(re.sub(r"\s", "", final_script))
    estimated_minutes = round(final_char_count_with_spaces / 320, 1)

    final_output: dict[str, Any] = {
        "status": "success",
        "도입부_3가지_버전": intros,
        "최종_대본": final_script,
        "메타데이터": {
            "estimated_minutes": estimated_minutes,
            "char_count": final_char_count,
            "char_count_with_spaces": final_char_count_with_spaces,
            "loop_count": state.get("loop_count", 0),
            "transcript_metadata": state.get("transcript_metadata", {}),
        },
    }

    markdown = (
        f"## 도입부 3가지 버전\n\n{intros}\n\n"
        f"---\n\n"
        f"## 최종 대본\n\n{final_script}\n\n"
        f"---\n\n"
        f"⏱️ 예상 길이: {estimated_minutes}분 ({final_char_count_with_spaces:,}자) · "
        f"루프: {state.get('loop_count', 0)}회"
    )
    tool_message = "최종 조립 완료"
    update = {
        "messages": [
            ToolMessage(content=tool_message, tool_call_id=tool_call_id),
            # non-streaming 경로(run_graph_sync)용 AIMessage
            AIMessage(content=markdown),
        ],
        "final_output": final_output,
        "workflow_complete": True,
    }
    await _dispatch_workflow_step(
        step=9,
        step_name="compose_final",
        display_name="최종 조립",
        tool_call_id=tool_call_id,
        loop_count=int(state.get("loop_count", 0)),
        state_input=_state_snapshot(state),
        state_update=_state_update(update),
        tool_message=tool_message,
        raw_output=markdown,
    )

    # SSE 스트리밍 경로용 custom event
    await adispatch_custom_event("result", {"text": markdown})

    await adispatch_custom_event(
        "progress", {"step": 9, "total": 9, "status": "done", "name": "최종 조립 완료"}
    )

    return Command(update=update)


# ── 도구 목록 ─────────────────────────────────────────────────────────────────

ALL_TOOLS = [
    fetch_transcript,
    prepare_outline,
    draft_script,
    differentiate_script,
    measure_duration,
    expand_script,
    format_script,
    generate_intros,
    compose_final,
]
