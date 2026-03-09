# OpenWebUI + LangGraph 백엔드 연동 가이드

## 1. Docker Compose로 전체 스택 실행

```bash
# 1. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 OPENAI_API_KEY 등 필수 값 입력

# 2. 스택 실행 (백엔드 + OpenWebUI)
docker compose up --build -d

# 3. 로그 확인
docker compose logs -f backend
docker compose logs -f openwebui
```

브라우저에서 http://localhost:3000 접속

---

## 2. OpenWebUI에서 LangGraph 백엔드 연동

### 방법 A: 환경변수로 자동 설정 (권장)

`docker-compose.yml`에 이미 포함되어 있습니다:

```yaml
OPENAI_API_BASE_URL: "http://backend:8000/v1"
OPENAI_API_KEY: "sk-langgraph-local"
```

백엔드가 healthy 상태가 된 뒤 OpenWebUI가 시작되며, 첫 실행부터 자동으로 적용됩니다.
또한 Compose는 OpenWebUI 커스텀 이미지를 함께 빌드하므로 Tool Calling 패널의 `Input` JSON도 `Output`처럼 pretty print 됩니다.

### 방법 B: UI에서 수동 설정

1. OpenWebUI 좌하단 **Settings** (톱니바퀴 아이콘) 클릭
2. **Admin Panel** → **Settings** → **Connections** 이동
3. **OpenAI API** 섹션:
   - **API Base URL**: `http://localhost:8000/v1`
   - **API Key**: `sk-langgraph-local` (`.env`의 `API_KEY` 값)
4. **Save** 클릭 후 **Verify Connection** 확인

---

## 3. 모델 선택

연동이 완료되면 채팅 화면 상단 모델 선택 드롭다운에 다음이 표시됩니다:

| 모델 ID | 설명 |
|---------|------|
| `youtube-script-writer` | YouTube URL 또는 원문 텍스트를 일본어 대본으로 변환 |

`EXTRA_MODELS`에 추가한 프로바이더 모델도 여기에 표시됩니다.

---

## 4. 전체 요청 플로우

```
사용자 입력
    │
    ▼
OpenWebUI
    │ POST http://backend:8000/v1/chat/completions
    │ { "model": "youtube-script-writer", "messages": [...], "stream": true }
    ▼
FastAPI backend/main.py
    │ verify_api_key() → 통과
    │ get_graph("youtube-script-writer") → script_writer 그래프 반환
    │ convert_messages() → LangChain 메시지로 변환
    │ StreamingResponse(stream_graph_response(...))
    ▼
LangGraph script_writer graph
    │ parse_input → orchestrator → tool loop
    ▼
    │ 각 단계 완료 시 OpenWebUI Tool Calling 스타일 패널 스트리밍
    ▼
FastAPI → SSE 청크 전송 → OpenWebUI → 실시간 렌더링
```

---

## 5. 새 에이전트 추가 방법

**파일 하나만 추가하면 됩니다** — 다른 파일은 수정할 필요가 없습니다.

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

---

## 6. 프로바이더 모델 추가

LangGraph 없이 프로바이더 모델을 직접 노출하려면 `.env`에 추가하세요:

```env
EXTRA_MODELS=gpt-4o,gpt-4o-mini,claude-opus-4-6
```

이 모델들은 패스스루 그래프로 자동 등록되어 OpenWebUI 모델 목록에 표시됩니다.

---

## 7. 프로덕션 배포 시 체크리스트

- [ ] `.env`에 강력한 `API_KEY` 및 `WEBUI_SECRET_KEY` 설정
- [ ] `WEBUI_AUTH=true`로 변경 (사용자 로그인 활성화)
- [ ] nginx 리버스 프록시 + HTTPS 적용
- [ ] 코드 실행 툴을 E2B/Docker 샌드박스로 교체

---

## 8. 개발 중 핫리로드

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

`docker-compose.yml`의 volume 마운트(`./backend:/app`) 덕분에
파일 수정 시 자동으로 반영됩니다.
