# LangGraph + OpenWebUI Template

OpenWebUI 채팅 인터페이스와 LangGraph 기반 AI 에이전트를 연결하는 프로덕션 레디 템플릿입니다.
OpenAI Chat Completions 호환 API를 노출하므로, OpenWebUI가 별도 수정 없이 LangGraph 워크플로우를 사용할 수 있습니다.

## 아키텍처

```mermaid
graph LR
    Browser -->|http://localhost:3000| OpenWebUI
    OpenWebUI -->|POST /v1/chat/completions| Backend[FastAPI Backend]
    Backend -->|@register_graph| GeneralGraph[assistant-general]
    Backend -->|@register_graph| ResearchGraph[assistant-research]
    Backend -->|@register_graph| DevGraph[assistant-dev]
    Backend -->|passthrough| ProviderAPI[OpenAI / Anthropic]
```

## 빠른 시작

```bash
# 1. 환경변수 설정
cp .env.example .env
# .env를 열어 OPENAI_API_KEY 입력

# 2. 스택 실행
docker compose up -d

# 3. 브라우저 열기
open http://localhost:3000
```

## 프로젝트 구조

```
backend/
├── graphs/
│   ├── __init__.py      # 자동 디스커버리 + 공개 API
│   ├── registry.py      # @register_graph 데코레이터, GraphEntry, get_graph()
│   ├── state.py         # 공유 MessagesState TypedDict
│   ├── llm.py           # create_llm() → init_chat_model (멀티 프로바이더)
│   ├── passthrough.py   # EXTRA_MODELS 패스스루 등록
│   ├── general.py       # assistant-general 그래프
│   ├── research.py      # assistant-research 그래프 (웹 검색)
│   └── dev.py           # assistant-dev 그래프 (코드 실행)
├── tools/
│   ├── web_search.py    # Tavily 웹 검색 도구
│   └── code_executor.py # Python 코드 실행 도구
├── converters.py        # OpenAI ↔ LangChain 메시지 변환
├── streaming.py         # SSE 스트리밍 + 동기 실행
├── config.py            # 환경변수 설정 (Pydantic Settings)
├── models.py            # OpenAI Pydantic 스키마
├── main.py              # FastAPI 엔드포인트 (~80줄)
└── requirements.txt
```

## 새 에이전트 추가

파일 하나만 추가하면 됩니다:

```python
# backend/graphs/my_agent.py
from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graphs.llm import create_llm
from graphs.registry import register_graph
from graphs.state import MessagesState

@register_graph("my-agent", description="My custom agent")
def build_my_agent_graph() -> CompiledStateGraph:
    llm = create_llm(temperature=0.5)

    def chat_node(state: MessagesState) -> dict:
        msgs = list(state["messages"])
        if not msgs or not isinstance(msgs[0], SystemMessage):
            msgs = [SystemMessage(content="You are a helpful assistant.")] + msgs
        return {"messages": [llm.invoke(msgs)]}

    graph = StateGraph(MessagesState)
    graph.add_node("chat", chat_node)
    graph.set_entry_point("chat")
    graph.add_edge("chat", END)
    return graph.compile()
```

재시작하면 OpenWebUI 모델 목록에 자동으로 나타납니다.

## 프로바이더 모델 추가

`.env`에 한 줄만 추가하면 됩니다:

```env
EXTRA_MODELS=gpt-4o,gpt-4o-mini,claude-opus-4-6
```

이 모델들은 패스스루 그래프로 자동 등록됩니다.

## 설계 결정 기록 (ADR)

상세 내용: [docs/context.md](docs/context.md)

| 결정 | 이유 요약 |
|------|----------|
| FastAPI (Platform 아님) | 가볍고 어디에나 배포, OpenAI API 직접 제어 |
| MemorySaver 제거 | OpenWebUI가 히스토리 관리, 중복 불필요 |
| `init_chat_model` | 모델명으로 프로바이더 자동 감지 |
| `@register_graph` | Open/Closed 원칙 — 파일 추가만으로 확장 |
| uv (pip 아님) | 10~100배 빠른 설치, lockfile 재현성 |

## 배포

### 로컬 (Docker Compose)
```bash
docker compose up -d
```

### Railway
[docs/railway-deploy.md](docs/railway-deploy.md) 참조

## 개발 명령어

```bash
make up      # Docker Compose 스택 시작
make down    # 스택 종료
make dev     # 핫리로드로 백엔드 단독 실행 (uv run)
make logs    # 백엔드 로그 스트리밍
make test    # 테스트 실행 (uv run pytest)
make lint    # ruff 린트 실행 (uv run ruff)
make sync    # 의존성 동기화 (uv sync)
```

의존성 추가 시:
```bash
cd backend && uv add <패키지명>          # 런타임 의존성
cd backend && uv add --dev <패키지명>    # 개발 의존성
```

## 기여 가이드

- 새 에이전트: `graphs/` 에 파일 추가 + `@register_graph` 데코레이터
- PR: 테스트 포함, `make lint` 통과 필수
- 이슈: GitHub Issues로 보고
