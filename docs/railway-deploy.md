# Railway 배포 가이드

Railway 배포 방법은 세 가지입니다. 상황에 맞게 선택하세요.

| 방법 | 언제 | 사전 조건 |
|------|------|----------|
| **CLI** | 터미널 작업 선호, CI/CD 자동화 | `npm i -g @railway/cli` |
| **MCP** | AI 어시스턴트(Claude)에서 직접 조작 | Railway MCP 서버 설정 |
| **대시보드** | 초기 설정, 시각적 확인 | 브라우저 |

---

## 방법 1: Railway CLI

### 설치 및 로그인
```bash
npm install -g @railway/cli
railway login
```

### 프로젝트 초기화 및 배포
```bash
# 저장소 루트에서
railway init                         # 프로젝트 생성 및 연결
railway up                           # 백엔드 빌드 + 배포 (railway.toml 자동 참조)
```

### 환경변수 설정
```bash
# 개별 설정
railway variables set OPENAI_API_KEY=sk-your-key
railway variables set API_KEY=sk-langgraph-local-prod
railway variables set DEFAULT_LLM_MODEL=gpt-4o-mini
railway variables set EXTRA_MODELS=gpt-4o,gpt-4o-mini
railway variables set REQUEST_TIMEOUT=60

# .env 파일에서 일괄 import
railway variables import .env
```

### 운영 명령어
```bash
railway logs                          # 실시간 로그 스트리밍
railway logs --service agent-backend  # 특정 서비스 로그
railway status                        # 배포 상태 확인
railway run uv run python -c "from graphs import get_available_models; print(list(get_available_models()))"
```

### 도메인 생성
```bash
railway domain                        # 자동 도메인 생성
```

---

## 방법 2: Railway MCP (AI 어시스턴트에서)

> Claude Code에서 Railway MCP 서버를 설정하면 AI가 직접 Railway를 조작할 수 있습니다.

### MCP 서버 설정
```bash
# Claude Code에 Railway MCP 추가
claude mcp add railway -- npx -y @railway/mcp
```

또는 `~/.claude/mcp_servers.json`에 직접 추가:
```json
{
  "railway": {
    "command": "npx",
    "args": ["-y", "@railway/mcp"]
  }
}
```

### MCP로 가능한 작업

Railway MCP를 통해 AI에게 자연어로 요청할 수 있습니다:

- `"langgraph-backend 서비스의 최근 로그 보여줘"`
- `"EXTRA_MODELS 환경변수를 gpt-4o,claude-opus-4-6 으로 설정해줘"`
- `"백엔드 서비스 재배포해줘"`
- `"현재 배포 상태 알려줘"`
- `"서비스 도메인 생성해줘"`

### MCP로 가능한 작업 목록

| 작업 | MCP 가능 |
|------|----------|
| 환경변수 조회/수정 | ✅ |
| 서비스 재배포 | ✅ |
| 로그 조회 | ✅ |
| 배포 상태 확인 | ✅ |
| 도메인 생성 | ✅ |
| 프로젝트 생성 | ✅ |
| 새 서비스 추가 | ✅ |
| 빌드 로그 조회 | ✅ |

---

## 방법 3: 대시보드에서 직접 해야 하는 작업

아래 작업은 Railway 웹 대시보드(https://railway.app)에서 직접 수행해야 합니다.

### 초기 GitHub 연동
> CLI/MCP로 대체 불가 — OAuth 인증이 필요합니다.

1. 대시보드 → **New Project** → **Deploy from GitHub repo**
2. GitHub 계정 연동 후 저장소 선택

### OpenWebUI 서비스 추가
> Docker Hub 이미지로 서비스를 추가할 때는 대시보드를 사용합니다.

1. 프로젝트 → **New Service** → **Docker Image**
2. Image: `ghcr.io/open-webui/open-webui:main`
3. Port: `8080`
4. 환경변수 설정:
   ```
   ENABLE_OLLAMA_API=false
   OPENAI_API_BASE_URL=https://<your-backend>.railway.app/v1
   OPENAI_API_KEY=<API_KEY와 동일한 값>
   WEBUI_SECRET_KEY=<랜덤 32자>
   WEBUI_AUTH=true
   ```

### 커스텀 도메인 연결
> DNS 설정이 필요하므로 대시보드에서 수행합니다.

1. 서비스 → **Settings** → **Domains** → **Add Custom Domain**
2. 안내에 따라 DNS CNAME 레코드 추가

### 결제 및 플랜 관리
> 대시보드 → **Account** → **Billing**

---

## 트러블슈팅

### 헬스체크 실패
```bash
# 로그 확인
railway logs --service agent-backend

# 로컬에서 동일 이미지 테스트
docker build -f backend/Dockerfile backend/ -t langgraph-test
docker run -e OPENAI_API_KEY=test -p 8000:8000 langgraph-test
curl localhost:8000/health
```

### 모델 목록이 비어있음
```bash
railway run uv run python -c \
  "from graphs import get_available_models; print(list(get_available_models()))"
```

### 타임아웃 오류
```bash
railway variables set REQUEST_TIMEOUT=120
```

### 배포 후 환경변수 적용 안 됨
Railway는 환경변수 변경 후 자동 재배포되지 않습니다.
```bash
railway redeploy
```
