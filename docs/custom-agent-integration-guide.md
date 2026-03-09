# 커스텀 LangGraph 에이전트 통합 가이드

외부 LangGraph 워크플로우를 이 템플릿에 통합할 때의 설계 지침입니다.

---

## 통합 전 판단 기준

### 통합 가능한 워크플로우

- LangGraph `StateGraph` 기반으로 작성된 워크플로우
- 입력이 "사용자 텍스트 또는 URL" 수준으로 단순히 표현 가능한 것
- 최종 출력을 텍스트(마크다운 포함)로 반환할 수 있는 것

### 통합이 어려운 경우

- 외부 DB 스키마와 타이트하게 결합된 비즈니스 로직
- 별도 인증 시스템이나 유저 세션이 필요한 워크플로우
- 실시간 양방향 상태 관리가 필수인 경우 (WebSocket 등)

---

## 1단계: 제거할 것 vs 유지할 것

기존 프로젝트에서 이 템플릿에 가져올 때 아래 기준으로 분류합니다.

### 제거 대상

| 종류 | 이유 |
|------|------|
| DB 모델 (실행 이력, 버전 관리 등) | OpenWebUI가 대화 히스토리를 관리 (ADR-002) |
| 비동기 실행 큐 / 워커 프로세스 | FastAPI + LangGraph로 직접 처리 |
| 별도 UI (Streamlit, React 등) | OpenWebUI로 대체 |
| MemorySaver / Checkpointer | OpenWebUI가 히스토리를 매 요청마다 전달 |
| 프롬프트 버전 관리 DB 테이블 | 코드 상수 또는 환경변수로 대체 |

### 유지 및 이식 대상

| 종류 | 처리 방식 |
|------|-----------|
| `StateGraph` 정의 (노드, 엣지) | `graphs/` 폴더로 이식 |
| LLM 호출 로직 | `graphs/llm.py`의 `create_llm()` 사용으로 교체 |
| 외부 API 호출 (HTTP 클라이언트) | `tools/` 폴더로 분리 |
| 프롬프트 텍스트 | `graphs/<name>.py` 내 상수 또는 별도 파일 |

---

## 2단계: State 설계

### 기본 원칙

`graphs/state.py`의 `MessagesState`를 반드시 상속합니다.
`messages` 필드가 있어야 OpenWebUI와 스트리밍이 호환됩니다.

```python
# graphs/<your_graph>.py
from graphs.state import MessagesState

class YourWorkflowState(MessagesState, total=False):
    # 워크플로우 전용 필드를 추가
    input_data: str
    intermediate_result: str
    final_output: dict
```

### MessagesState 확장 시 주의사항

- 워크플로우 전용 필드는 `total=False` (선택적 필드)로 선언
- 필드명이 LangGraph 내부 예약어(`config`, `metadata` 등)와 충돌하지 않도록 확인
- 중간 결과물은 상태에 저장해 조건부 엣지에서 활용 가능

---

## 3단계: 채팅 메시지 어댑터 패턴

기존 워크플로우의 입력이 URL, 파일 경로, 구조화된 텍스트라면
OpenWebUI의 채팅 메시지에서 해당 입력을 추출하는 어댑터가 필요합니다.

### 어댑터 구현 위치

그래프 진입 노드(첫 번째 노드) 또는 별도 파싱 헬퍼로 구현합니다.

```python
from langchain_core.messages import BaseMessage

def parse_input(messages: list[BaseMessage]) -> dict:
    """마지막 사용자 메시지에서 워크플로우 입력을 추출"""
    last_human = next(
        (m for m in reversed(messages) if m.type == "human"), None
    )
    content = last_human.content if last_human else ""

    # 입력 형식에 맞게 파싱 (URL, 키워드, 텍스트 등)
    ...
    return {"input_data": content}
```

### 출력 어댑터

최종 노드에서 결과를 `AIMessage`로 변환합니다.

```python
from langchain_core.messages import AIMessage

def compose_final(state: YourWorkflowState) -> dict:
    result_text = state.get("final_output", "결과 없음")
    return {"messages": [AIMessage(content=result_text)]}
```

---

## 4단계: 외부 서비스 처리

### 옵션 A: 별도 서비스 유지 (HTTP 호출)

기존에 독립 서비스(FastAPI, 외부 API)가 있다면 `tools/`에 HTTP 클라이언트로 래핑합니다.

```python
# tools/your_external_service.py
import httpx
from langchain_core.tools import tool

@tool
def call_external_service(input: str) -> str:
    """외부 서비스를 호출합니다."""
    response = httpx.get(f"{EXTERNAL_API_URL}/endpoint", params={"q": input})
    return response.json()["result"]
```

`docker-compose.yml`에 해당 서비스를 추가합니다.

### 옵션 B: 라이브러리 직접 호출 (권장)

외부 서비스가 단순 Python 라이브러리로 대체 가능하다면 직접 사용합니다.
HTTP 오버헤드 제거, 서비스 간 의존성 감소.

```python
# tools/your_tool.py
from some_library import SomeClient

def fetch_data(identifier: str) -> dict:
    client = SomeClient()
    return client.get(identifier)
```

---

## 5단계: LLM 호출 통일

기존 코드에서 `ChatOpenAI`, `ChatAnthropic` 등을 직접 import하는 부분을
`graphs/llm.py`의 `create_llm()`으로 교체합니다.

```python
# ❌ 기존 방식
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)

# ✅ 이 템플릿 방식
from graphs.llm import create_llm
llm = create_llm(temperature=0.7)
```

`create_llm()`은 `.env`의 `DEFAULT_LLM_MODEL`을 기반으로 프로바이더를 자동 감지합니다.

---

## 6단계: 그래프 등록

```python
# graphs/<your_graph>.py
from graphs.registry import register_graph
from langgraph.graph.state import CompiledStateGraph

@register_graph("your-agent-name")
def build() -> CompiledStateGraph:
    graph = StateGraph(YourWorkflowState)
    # 노드, 엣지 추가
    ...
    return graph.compile()
```

`graphs/` 폴더에 파일을 추가하면 자동 디스커버리됩니다. **다른 파일 수정 불필요.**

---

## 통합 체크리스트

- [ ] `StateGraph`가 `MessagesState`를 상속하는 커스텀 State를 사용하는가
- [ ] `ChatOpenAI` 등 직접 import 없이 `create_llm()` 사용하는가
- [ ] DB 모델, 실행 큐, 별도 UI가 제거됐는가
- [ ] `MemorySaver` / Checkpointer가 없는가
- [ ] 마지막 노드가 `AIMessage`를 `messages`에 추가하는가
- [ ] `@register_graph` 데코레이터가 붙어있는가
- [ ] `uv add <new-dependency>`로 의존성을 추가했는가
- [ ] `uv run pytest tests/ -v` 통과하는가
