# YouTube 대본 생성 그래프 통합 가이드

이 문서는 `youtube-script-writer-automation` 프로젝트의 워크플로우를
이 템플릿(`langgraph-openwebui-template`)에 통합할 때의 설계 지침입니다.

---

## 기존 프로젝트 구조 요약

```
services/workflow-orchestrator/app/
├── runtime/
│   ├── graph.py          # ✅ StateGraph 정의 — 재사용
│   ├── llm_client.py     # ✅ init_chat_model 사용 — 단순화 후 재사용
│   ├── runner.py         # ❌ SQLModel DB 레이어 — 제거
│   └── worker.py         # ❌ 비동기 실행 큐 — 제거
├── models/               # ❌ DB 모델 (WorkflowRun 등) — 제거
├── streamlit_app.py      # ❌ 별도 UI — OpenWebUI로 대체
└── database.py           # ❌ DB 레이어 — 제거

services/transcript-api/  # 별도 서비스 → 툴로 통합 (선택)
```

---

## 통합 아키텍처

### 호출 흐름

```
OpenWebUI 채팅 입력
"https://youtube.com/watch?v=xxxx 대본 써줘"
        ↓
graphs/youtube_script.py (@register_graph)
  1. 마지막 사용자 메시지에서 URL 또는 텍스트 추출
  2. ScriptWorkflowState 구성
  3. 8단계 LangGraph 파이프라인 실행
  4. final_output을 AIMessage로 변환
        ↓
OpenWebUI 채팅창에 대본 출력
```

### 파이프라인 노드 구성 (기존 동일)

```
fetch_transcript → prepare_outline → draft_script → differentiate_script
    → measure_duration → [expand_script(loop)] → format_script
    → generate_intros → compose_final
```

---

## 새 레포 파일 구조

```
backend/
├── graphs/
│   ├── youtube_script.py    # 신규: 메인 그래프 + 어댑터
│   └── youtube_nodes.py     # 신규: 8개 노드 함수
├── tools/
│   └── transcript_fetcher.py  # 신규: youtube-transcript-api 직접 호출
└── prompts/
    └── youtube_script.py    # 신규: 프롬프트 상수 (DB 대신)
```

---

## 설계 결정

### 1. State: MessagesState 확장

기존 `ScriptWorkflowState`는 커스텀 TypedDict. 템플릿 규칙에 따라 `MessagesState`를 상속 확장.

```python
# graphs/youtube_script.py
from graphs.state import MessagesState

class ScriptWorkflowState(MessagesState, total=False):
    youtube_url: str
    source_text: str
    target_language: str
    transcript: str
    outline: str
    first_draft: str
    draft_text: str
    char_count: int
    estimated_minutes: float
    loop_count: int
    formatted_draft: str
    intros: str
    final_output: dict
```

`messages` 필드를 그대로 유지하므로 OpenWebUI와 호환.

### 2. transcript-api: 별도 서비스 vs 직접 호출

| 방식 | 장점 | 단점 |
|------|------|------|
| 별도 서비스 유지 | 기존 코드 재사용, 독립 스케일링 | docker-compose에 서비스 추가 필요 |
| `youtube-transcript-api` 직접 호출 | 서비스 간 HTTP 불필요, 단순 | 의존성 추가 |

**권장: 직접 호출** — `tools/transcript_fetcher.py`로 통합.

```python
# tools/transcript_fetcher.py
from youtube_transcript_api import YouTubeTranscriptApi

def fetch_transcript(video_id: str, lang: str = "ja", fallback_lang: str = "en") -> dict:
    ...
```

### 3. LLMClient: DB 의존성 제거

기존 `WorkflowLLMClient`는 `PromptVersion` DB 모델에서 프롬프트를 읽음.
→ 프롬프트를 `prompts/youtube_script.py` 상수로 이동.

```python
# prompts/youtube_script.py
PROMPTS = {
    "prepare_outline": {
        "body": "...",
        "temperature": 0.7,
        "max_tokens": 2000,
    },
    "draft_script": { ... },
    ...
}
```

### 4. 어댑터 패턴: 채팅 메시지 → 워크플로우 입력

```python
# graphs/youtube_script.py
def _parse_input_from_messages(messages: list) -> dict:
    """마지막 사용자 메시지에서 URL 또는 텍스트를 추출"""
    last_user_message = next(
        (m for m in reversed(messages) if m.get("role") == "user"), None
    )
    content = last_user_message["content"] if last_user_message else ""

    url_match = re.search(r'https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+', content)
    if url_match:
        return {"youtube_url": url_match.group(0)}

    # URL 없으면 전체 내용을 원문 텍스트로 처리
    return {"source_text": content}
```

### 5. 스트리밍 처리

파이프라인이 오래 걸리므로 노드 완료마다 중간 상태 메시지를 스트리밍.
`astream_events`로 각 노드 완료 이벤트를 캡처하여 진행상황 전달 가능.

---

## 제거 대상 (DB/Persistence 레이어)

| 제거 항목 | 이유 |
|-----------|------|
| `WorkflowRun`, `NodeRun` DB 모델 | OpenWebUI가 히스토리 관리 (ADR-002) |
| `PromptVersion`, `WorkflowVersion` | 프롬프트를 코드 상수로 관리 |
| SQLModel, Alembic | DB 불필요 |
| LangSmith `@traceable` | 선택사항 — 필요 시 환경변수로 ON/OFF |
| Streamlit | OpenWebUI로 대체 |

---

## 추가 의존성

```toml
# backend/pyproject.toml
"youtube-transcript-api>=1.1.0"
```

---

## 새 에이전트 등록 예시

```python
# graphs/youtube_script.py
from graphs.registry import register_graph
from graphs.state import MessagesState

@register_graph("youtube-script-writer")
def build() -> CompiledStateGraph:
    ...
    return graph.compile()
```

등록 후 OpenWebUI 모델 선택에 `youtube-script-writer` 자동 노출.

---

## 참고 파일 (기존 프로젝트)

| 파일 | 역할 |
|------|------|
| `runtime/graph.py` | StateGraph 엣지 구조 — 그대로 이식 |
| `runtime/llm_client.py` | `init_chat_model` 호출 패턴 참고 |
| `runtime/runner.py` | 노드 함수 구현 참고 (DB 코드 제외) |
| `transcript-api/main.py` | 자막 추출 로직 참고 |
