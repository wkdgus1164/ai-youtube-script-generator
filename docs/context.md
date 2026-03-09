# 프로젝트 기술 컨텍스트

AI 어시스턴트 및 팀원을 위한 상세 기술 컨텍스트입니다.
빠른 참조는 루트의 `AGENTS.md`를 보세요.

---

## 아키텍처 설계 결정 (ADR)

### ADR-001: FastAPI (LangGraph Platform 미사용)

**결정**: 자체 FastAPI 서버로 OpenAI 호환 API를 직접 구현.

**이유**:
- LangGraph Platform은 자체 인프라, 복잡한 설정, 유료 플랜 필요
- FastAPI는 가볍고 어디에나 배포 가능 (Docker, Railway, Fly.io 등)
- OpenAI API 포맷을 직접 제어하므로 OpenWebUI와 투명하게 통합됨

### ADR-002: MemorySaver 제거

**결정**: LangGraph `MemorySaver`를 사용하지 않음.

**이유**:
- OpenWebUI가 대화 히스토리를 완전히 관리하고, 매 요청마다 전체 메시지 목록을 전송
- 백엔드에서 중복 저장하면 메모리 낭비이며 두 시스템 간 상태 불일치 발생 가능
- `thread_id` 전달 불필요 — `configurable` 없이 그래프 실행

### ADR-003: `init_chat_model` 사용

**결정**: 프로바이더별 클래스(`ChatOpenAI`, `ChatAnthropic`) 대신 `init_chat_model` 사용.

**이유**:
- 모델명 접두사로 프로바이더 자동 감지 (`gpt-*` → OpenAI, `claude-*` → Anthropic)
- 그래프 모듈이 프로바이더 패키지를 직접 import할 필요 없음
- 새 프로바이더 지원 시 `llm.py`만 수정하면 됨

### ADR-004: `@register_graph` 데코레이터 패턴

**결정**: 중앙 if/elif 라우터 대신 데코레이터 기반 자가 등록.

**이유**:
- Open/Closed 원칙: 새 에이전트 추가 시 기존 파일(`router.py` 등) 수정 불필요
- `pkgutil.iter_modules` 자동 디스커버리로 파일 추가만으로 완성
- `lru_cache`로 그래프 빌드 1회 보장

### ADR-005: uv 패키지 매니저

**결정**: pip + requirements.txt 대신 uv + pyproject.toml + uv.lock.

**이유**:
- Rust 기반으로 pip 대비 10~100배 빠른 설치
- `uv.lock`은 해시 포함 완전한 재현성 보장 (`requirements.txt`는 해시 없음)
- `uv run`으로 venv 활성화 없이 명령 실행 가능
- Dockerfile에서 `uv sync --frozen`으로 lockfile 기반 결정론적 빌드

---

## 알려진 함정 (Gotchas)

### LangChain v0.3 AIMessage.tool_calls 포맷 변경

```python
# ❌ 이전 (v0.2): OpenAI 포맷 그대로
AIMessage(tool_calls=[{"id": "call-1", "type": "function", "function": {"name": "search", "arguments": '{"q":"test"}'}}])

# ✅ 현재 (v0.3+): LangChain 네이티브 포맷
AIMessage(tool_calls=[{"id": "call-1", "name": "search", "args": {"q": "test"}, "type": "tool_call"}])
```

`args`는 반드시 dict (파싱된 JSON). `arguments`(문자열)로 넘기면 `TypeError` 발생.

### uv venv에 pip 없음

uv가 생성한 `.venv`에는 pip가 없습니다.

```bash
# ❌ 동작 안 함
.venv/bin/pip install foo

# ✅ 올바른 방법
uv add foo           # pyproject.toml에 추가 + 설치
uv run pip install   # 임시 설치 (권장 안 함)
```

### astream_events version 파라미터

LangGraph `astream_events()`에서 `version="v2"` 파라미터는 현재 기본값이므로 명시 불필요.

### LangChain/LangGraph `<1.0.0` 버전 제한 함정

`pyproject.toml`에 `<1.0.0` upper bound를 걸면 v1.x 릴리스가 통째로 차단됩니다.

```toml
# ❌ v1.x 설치 불가
"langgraph>=0.3.0,<1.0.0"

# ✅ v1.x 포함 최신 버전 허용
"langgraph>=1.0.0"
```

LangGraph v1 / LangChain v1은 핵심 API(`StateGraph`, `ToolNode`, `init_chat_model`, `langchain_core.messages.*`)를 그대로 유지하므로 코드 변경 없이 업그레이드 가능.

### python:3.12-slim에 curl 없음

`Dockerfile` 헬스체크에서 `curl` 사용 불가 — slim 이미지에는 curl이 포함되지 않습니다.

```dockerfile
# ❌ 실행 오류: exec: "curl": executable file not found in $PATH
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1

# ✅ Python 내장 urllib 사용
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
```

### 로컬 개발 시 service_healthy 조건 문제

`docker-compose.yml`의 `depends_on: condition: service_healthy`는 프로덕션용입니다.
로컬 개발에서 `./backend:/app` 볼륨 마운트를 쓰면 macOS `.venv`가 컨테이너 안으로 마운트되고,
`uv run`이 시작 시 venv를 재생성하여 startup이 느려집니다.
현재 프로젝트는 `service_started` 조건을 사용합니다.

```yaml
# ✅ 로컬 개발 (현재 설정)
depends_on:
  backend:
    condition: service_started

# 프로덕션 배포 시 service_healthy로 교체 권장
```

### Docker 빌드 캐시가 Dockerfile 변경을 무시하는 경우

HEALTHCHECK 같은 메타데이터 변경이 캐시에 남아있을 경우 `--no-cache`로 강제 재빌드:

```bash
docker compose build --no-cache backend
```

---

## 패키지 버전 (2026-03 기준)

| 패키지 | 버전 |
|--------|------|
| langgraph | 1.0.10 |
| langchain | 1.2.10 |
| langchain-core | 1.2.17 |
| langchain-openai | 1.1.10 |
| langchain-anthropic | 1.3.4 |
| fastapi | 0.135.1 |
| uvicorn | 0.41.0 |
| pydantic | 2.12.5 |
| uv | 0.10.9 |

정확한 전체 버전: `backend/uv.lock` 참조.

---

## 테스트 구조

```
backend/tests/
├── conftest.py          # TestClient fixture, clean_registry fixture
├── test_registry.py     # @register_graph, get_graph(), lru_cache, KeyError
├── test_converters.py   # 각 메시지 역할 변환 (system/user/assistant/tool)
├── test_models.py       # Pydantic 직렬화/역직렬화
└── test_endpoints.py    # /health, /v1/models, /v1/chat/completions 통합 테스트
```

`clean_registry` fixture는 전역 `_REGISTRY`를 테스트 간 격리합니다 — 각 테스트 전후로 레지스트리 상태를 복원합니다.

---

## 로컬 개발 환경 설정

```bash
git clone <repo>
cd <repo>/backend
uv sync           # 의존성 설치 (.venv 자동 생성)
cp ../.env.example ../.env
# .env에 OPENAI_API_KEY 입력
uv run uvicorn main:app --reload --port 8000
```

검증:
```bash
curl localhost:8000/health
curl localhost:8000/v1/models -H "Authorization: Bearer sk-langgraph-local"
```
