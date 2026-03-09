"""Prompt defaults, SafeDict, render helpers, and create_prompt_node factory.

All 6 editable prompt bodies are stored here as PromptConfig defaults.

Responsibility: Prompt management and prompt-node factory
Dependencies: state.py, text_utils.py, graphs/llm.py, langchain-core
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import HumanMessage

from graphs.llm import create_llm
from graphs.script_writer.state import ScriptGeneratorState
from graphs.script_writer.text_utils import extract_text, normalize_prompt_output


@dataclass(frozen=True)
class PromptConfig:
    body: str
    max_tokens: int
    temperature: float


EDITABLE_PROMPT_ORDER = (
    "prepare_outline",
    "draft_script",
    "differentiate_script",
    "expand_script",
    "format_script",
    "generate_intros",
)

EDITABLE_PROMPT_TITLES: dict[str, str] = {
    "prepare_outline": "2. 개요 수립",
    "draft_script": "3. 초안 작성",
    "differentiate_script": "4. 차별화 리라이트",
    "expand_script": "6. 대본 확장",
    "format_script": "7. 문단 포맷 정리",
    "generate_intros": "8. 도입부 생성",
}


PROMPTS: dict[str, PromptConfig] = {
    "prepare_outline": PromptConfig(
        body="""
당신은 일본어 경제/사회/금융 유튜브 채널의 수석 대본 작가입니다.

아래 원본 자료를 분석해서 최종 대본을 쓰기 위한 작성 전략을 일본어로 준비해주세요.

반드시 아래 항목을 포함하세요.
1. 추천 구조 타입: Type A, Type B, Type C 중 하나
2. 오프닝 훅 3개
3. 본문 전개 순서
4. 사실 기반으로만 쓸 때 주의할 포인트
5. 시청 지속 시간을 높일 감정선 설계

채널 원칙:
- 일본어 구어체 + です・ます조
- 숫자는 아라비아 숫자 사용
- 단순 정보 나열이 아니라 스토리텔링 중심
- 과장 대신 사실 기반의 긴장감을 유지
- 답변은 바로 본문으로 시작
- '以下は', '説明', '補足' 같은 서문 금지

원본 자료:
{transcript}
""".strip(),
        max_tokens=4096,
        temperature=0.2,
    ),
    "draft_script": PromptConfig(
        body="""
당신은 지식 스토리텔러 전문 유튜브 대본 작가입니다.

아래 작성 전략과 원본 자료를 바탕으로 일본어 최종 대본의 초안을 작성해주세요.

절대 준수 사항:
- 공백 포함 6,000자 이상 7,500자 이하
- 일본어 구어체 + です・ます조
- 숫자는 아라비아 숫자 사용
- 문단은 대체로 150~200자 길이를 목표로 하되, 전체 흐름을 우선
- 영상 지시문, 괄호 지시문, BGM 지시문 없이 순수 내레이션만 출력
- 단순 요약이 아니라 감정선이 있는 해설형 스토리텔링
- 절대 금지: '以下は', '構成', 'セグメント', 'ナレーター', 箇条書き, 見出し
- 답변은 완성된 본문 첫 문장부터 시작

작성 전략:
{outline}

원본 자료:
{transcript}
""".strip(),
        max_tokens=8192,
        temperature=0.3,
    ),
    "differentiate_script": PromptConfig(
        body="""
아래 일본어 대본 초안을 검토하고 최종 대본 후보로 다시 작성해주세요.

요구사항:
- 원본 대비 50% 수준으로 차별화된 콘텐츠
- 사실 기반을 유지하면서 사례, 관점, 시간축, 구성 순서를 재배치
- 기업명, 인물명, 지명, 제도명처럼 사실 관계상 중요한 고유명사는 유지
- 절대 금지: BYD 같은 고유명사를 `企業A`, `A社`처럼 일반화
- 허위 정보 금지
- 더 강한 후킹과 서사 흐름
- 절대 금지: '以下は', '解説します', 'セグメント', 'ナレーター', 목록 형식
- 출력은 완성된 일본어 내레이션 본문만

현재 초안:
{first_draft}
""".strip(),
        max_tokens=8192,
        temperature=0.25,
    ),
    "expand_script": PromptConfig(
        body="""
아래 일본어 대본은 아직 목표 길이에 부족합니다.

요구사항:
- 기존 내용을 삭제하지 말고 사실 기반의 흥미로운 내용을 1,800자 이상 추가
- 허위 정보 금지
- 경제적 의미, 사회적 파장, 시간축 비교, 시청자가 궁금해할 반전 포인트를 보강
- 기업명과 고유명사는 유지하고 `企業A`, `A社` 같은 플레이스홀더로 바꾸지 말 것
- 원문 자막을 따옴표처럼 길게 복사하지 말고 내레이션 문장으로 다시 쓸 것
- 최종 결과는 하나의 완성된 대본으로 출력
- 절대 금지: '以下は', '追加セクション', 'セグメント', 'ナレーター', 箇条書き, 見出し
- 출력은 이어서 읽을 수 있는 완성된 일본어 내레이션 본문만

현재 예상 길이: {estimated_minutes}분

현재 대본:
{draft_text}
""".strip(),
        max_tokens=8192,
        temperature=0.25,
    ),
    "format_script": PromptConfig(
        body="""
아래 일본어 대본의 문단을 정리해주세요.

요구사항:
- 한 문단은 대체로 150~200자
- 문단마다 줄바꿈
- TTS용 순수 내레이션만 유지
- 뜻은 유지하되 읽기 리듬을 개선
- 내용은 요약하거나 축약하지 말고 전체 정보량을 최대한 유지
- 전체 길이는 원문 대본의 85% 이상 유지
- 기업명과 고유명사는 유지하고 `企業A`, `A社` 같은 플레이스홀더는 제거
- `セクション1`, `オープニング`, `エンディング` 같은 헤딩 라벨은 모두 제거
- 원문 자막을 그대로 붙여 넣은 구어체 군더더기(예: え、あの、皆さんこんにちは)는 제거
- 제목, 목록, 역할 라벨, 메모 문구는 모두 제거
- 첫 줄부터 바로 완성된 내레이션 본문만 출력

대본:
{draft_text}
""".strip(),
        max_tokens=8192,
        temperature=0.2,
    ),
    "generate_intros": PromptConfig(
        body="""
아래 일본어 대본을 바탕으로 도입부만 3가지 버전으로 다시 작성해주세요.

요구사항:
- 각 버전은 공백 포함 500자 내외
- 더 자극적이되 사실만 사용
- 마지막 문장은 「その実像を掘り下げていきます」「この核心を掘り下げていきます」처럼 일본어 기대감 문장으로 마무리
- 출력 형식:
  バージョン1: ...

  バージョン2: ...

  バージョン3: ...
- 절대 금지: 사과문, 안내문, 설명문, 메타 발언
- 도입부만 출력

대본:
{formatted_draft}
""".strip(),
        max_tokens=4096,
        temperature=0.35,
    ),
}


ORCHESTRATOR_SYSTEM_PROMPT = """당신은 YouTube 일본어 대본 생성 워크플로우의 오케스트레이터입니다.
아래 순서대로 도구를 하나씩 호출하여 워크플로우를 진행하세요.

## 워크플로우 순서

1. fetch_transcript — 자막 추출 또는 source_text 사용
2. prepare_outline — 대본 작성 전략 수립
3. draft_script — 초안 작성
4. differentiate_script — 차별화 리라이트
5. measure_duration — 길이 측정

6. [조건 분기]
   - ToolMessage에 "estimated_minutes < 18" AND "loop_count < 3" 이면 → expand_script 호출 후 measure_duration 재호출
   - 그 외 (18분 이상 OR loop_count ≥ 3) → format_script 호출

7. format_script — 문단 포맷 정리
8. generate_intros — 도입부 3가지 버전 생성
9. compose_final — 최종 조립 및 완료 (이 도구가 workflow_complete를 True로 설정함)

## 중요 규칙

- 반드시 한 번에 하나의 도구만 호출하세요
- 도구 결과(ToolMessage)를 확인한 후 다음 단계를 결정하세요
- compose_final 호출 후에는 더 이상 도구를 호출하지 마세요
- 모든 도구는 인자가 없습니다 (상태에서 자동으로 값을 읽습니다)
""".strip()


class SafeDict(dict):
    """dict subclass that returns '{key}' for missing keys to prevent KeyError in format_map."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_prompt(prompt_key: str, variables: dict[str, Any]) -> str:
    """Render a prompt template with variables, tolerating missing keys."""
    config = PROMPTS[prompt_key]
    return render_prompt_body(config.body, variables)


def render_prompt_body(body: str, variables: dict[str, Any]) -> str:
    """Render an arbitrary prompt body with variables, tolerating missing keys."""
    serialized = {
        k: v if isinstance(v, str) else str(v)
        for k, v in variables.items()
    }
    return body.format_map(SafeDict(serialized))


# ── Prompt-node factory ───────────────────────────────────────────────────────
# DEPRECATED: create_prompt_node은 tool-calling 패턴으로 대체됨 (tools.py 참조)


def create_prompt_node(
    prompt_key: str,
    step: int,
    name: str,
    get_variables: Callable[[ScriptGeneratorState], dict[str, Any]],
    process_output: Callable[[str, ScriptGeneratorState], dict[str, Any]],
) -> Callable[[ScriptGeneratorState], Awaitable[dict[str, Any]]]:
    """Factory: LLM call → normalize → post-process pipeline for a prompt node.

    Args:
        prompt_key:     Key in PROMPTS dict.
        step:           1-based step number for progress events.
        name:           Human-readable node name for progress display.
        get_variables:  Extracts template variables from state.
        process_output: Processes normalized LLM output into a state update dict.

    Returns:
        An async node function compatible with LangGraph StateGraph.
    """
    config = PROMPTS[prompt_key]

    async def node(state: ScriptGeneratorState) -> dict[str, Any]:
        await adispatch_custom_event(
            "progress", {"step": step, "total": 9, "status": "running", "name": name}
        )
        variables = get_variables(state)
        rendered = render_prompt(prompt_key, variables)
        llm = create_llm(streaming=False, temperature=config.temperature, max_tokens=config.max_tokens)
        response = await llm.ainvoke([HumanMessage(content=rendered)])
        text = normalize_prompt_output(prompt_key, extract_text(response))
        result = process_output(text, state)
        await adispatch_custom_event(
            "progress", {"step": step, "total": 9, "status": "done", "name": name}
        )
        return result

    node.__name__ = prompt_key
    return node
