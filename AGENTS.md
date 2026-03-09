# AGENTS.md

AI 코딩 어시스턴트(Claude, Codex, Gemini 등)를 위한 프로젝트 컨텍스트입니다.

## 프로젝트 개요

OpenWebUI 프론트엔드 + LangGraph 백엔드 통합 템플릿.
FastAPI가 OpenAI Chat Completions 호환 API를 노출하고,
OpenWebUI가 이 API를 통해 LangGraph 워크플로우를 호출합니다.

## 파일 구조

```
backend/
├── graphs/
│   ├── __init__.py      # pkgutil 자동 디스커버리 + 공개 API
│   ├── registry.py      # 단일 책임: 그래프 등록 + 조회
│   ├── state.py         # 단일 책임: 상태 타입 정의
│   ├── llm.py           # 단일 책임: LLM 생성 (init_chat_model)
│   ├── passthrough.py   # EXTRA_MODELS 패스스루 등록
│   ├── general.py       # assistant-general
│   ├── research.py      # assistant-research (Tavily 검색)
│   └── dev.py           # assistant-dev (코드 실행)
├── tools/
│   ├── web_search.py    # Tavily 웹 검색 도구
│   └── code_executor.py # Python 코드 실행 도구
├── converters.py        # OpenAI ↔ LangChain 메시지 변환
├── streaming.py         # SSE 스트리밍 + ainvoke 실행
├── config.py            # Pydantic v2 Settings (환경변수)
├── models.py            # OpenAI 호환 Pydantic 스키마
├── main.py              # FastAPI 앱 + 엔드포인트 (~80줄)
└── pyproject.toml       # uv 의존성 관리
```

## 핵심 규칙

1. **새 에이전트**: `graphs/` 폴더에 파일 추가 + `@register_graph` 데코레이터. **다른 파일 수정 불필요.**
2. **LLM 생성**: 반드시 `graphs/llm.py`의 `create_llm()` 사용. `ChatOpenAI` 등 직접 import 금지.
3. **State**: 반드시 `graphs/state.py`의 `MessagesState` 사용 (또는 상속하여 확장).
4. **커스텀 추상 클래스 금지**: `GraphPlugin` 같은 인터페이스 만들지 말 것. 데코레이터로 충분.
5. **MemorySaver 사용 금지**: OpenWebUI가 히스토리를 관리함. 백엔드에서 중복 저장 불필요.
6. **Silent fallback 금지**: 미등록 모델은 `KeyError`로 명시적 실패.
7. **패키지 매니저**: `uv` 사용. `pip` 직접 사용 금지.

## 타입 규칙

| 역할 | 타입 |
|------|------|
| 그래프 빌더 반환값 | `CompiledStateGraph` |
| LLM 팩토리 반환값 | `BaseChatModel` |
| 메시지 변환 입력 | `list[Message]` |
| 메시지 변환 출력 | `list[BaseMessage]` |
| 레지스트리 | `dict[str, GraphEntry]` |

## 모듈 의존성 (순환 없음)

```
main.py
  ├── graphs/__init__.py (자동 디스커버리)
  │     ├── graphs/general.py ──┐
  │     ├── graphs/research.py ─┼── graphs/registry.py
  │     ├── graphs/dev.py ──────┤   graphs/state.py
  │     └── graphs/passthrough.py   graphs/llm.py → config.py
  ├── converters.py → models.py
  └── streaming.py → models.py, config.py
```

## Docker / 로컬 실행

```bash
# 전체 스택 빌드 + 시작
docker compose up --build -d

# 헬스체크 포함 강제 재빌드 (캐시 문제 시)
docker compose build --no-cache backend && docker compose up -d
```

**주의사항:**
- `python:3.12-slim`에는 `curl` 없음 → 헬스체크는 `python -c "import urllib.request; ..."` 사용
- `./backend:/app` 볼륨 마운트 시 컨테이너 시작 시 venv 재생성으로 startup 느림 (정상)
- `depends_on: condition: service_started` 사용 중 (로컬 개발용). 프로덕션 배포 시 `service_healthy`로 교체 권장
- Dockerfile 변경 후 캐시 무효화 안 될 경우 `--no-cache` 플래그 사용
- **`.env` 수정 후 `docker compose restart`는 환경변수를 재로드하지 않음** → 반드시 `docker compose up -d <service>` 로 컨테이너 재생성

## LangChain 버전별 주의사항

**의존성 버전 제한**: `pyproject.toml`에 `<1.0.0` upper bound 금지. LangChain/LangGraph v1은 API 호환성 유지.

```toml
# ❌ v1.x 차단됨
"langgraph>=0.3.0,<1.0.0"
# ✅ 올바른 방식
"langgraph>=1.0.0"
```

**LangChain v0.3+ `AIMessage.tool_calls` 포맷 변경:**
```python
# ❌ 이전 (OpenAI 포맷, LangChain v0.2 이하)
{"id": "call-1", "type": "function", "function": {"name": "search", "arguments": '{"q":"test"}'}}

# ✅ 현재 (LangChain v0.3+)
{"id": "call-1", "name": "search", "args": {"q": "test"}, "type": "tool_call"}
```
`args`는 dict (파싱된 JSON), `arguments`(문자열) 아님.

## 패키지 매니저 (uv)

```bash
cd backend && uv sync                   # 의존성 설치
cd backend && uv add <pkg>              # 런타임 의존성 추가
cd backend && uv add --dev <pkg>        # 개발 의존성 추가
```

`requirements.txt` 없음 — `pyproject.toml` + `uv.lock` 사용.
`uv.lock`은 커밋 대상 (gitignore 금지).

## 테스트 및 개발

```bash
cd backend && uv run pytest tests/ -v
cd backend && uv run uvicorn main:app --reload --port 8000
cd backend && uv run ruff check .
```

## 검증 스크립트

```python
# 자동 디스커버리 + 타입 확인
from graphs import get_graph, get_available_models
models = get_available_models()
print(list(models.keys()))  # ['assistant-dev', 'assistant-general', 'assistant-research']

g = get_graph("assistant-general")
print(type(g).__name__)  # CompiledStateGraph

# 미등록 모델 → KeyError (silent fallback 아님)
try:
    get_graph("unknown-model")
except KeyError as e:
    print(f"Expected error: {e}")
```

## 아키텍처 설계 결정 (ADR)

자세한 내용: `docs/context.md`

커스텀 에이전트 통합 가이드: `docs/custom-agent-integration-guide.md`

| 결정 | 이유 |
|------|------|
| FastAPI (LangGraph Platform 아님) | 가볍고 OpenAI API 직접 제어, 어디에나 배포 가능 |
| MemorySaver 제거 | OpenWebUI가 히스토리 관리, 중복 저장 불필요 |
| `init_chat_model` | 모델명으로 프로바이더 자동 감지 |
| `@register_graph` 데코레이터 | Open/Closed 원칙 — 기존 코드 수정 없이 확장 |
| `uv` (pip 아님) | 10~100배 빠른 설치, `uv.lock`으로 완전한 재현성 |
