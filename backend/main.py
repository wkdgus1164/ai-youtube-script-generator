"""LangGraph + OpenAI-compatible API backend.

Endpoints:
    GET  /health                 - Health check
    GET  /v1/models              - Available model list
    POST /v1/chat/completions    - Chat completions (streaming and non-streaming)

Responsibility: FastAPI app, middleware, and endpoint definitions
Dependencies: graphs, converters, streaming, models, config
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from config import settings
from converters import convert_messages
from graphs import get_available_models, get_graph
from models import ChatCompletionRequest, ModelInfo, ModelList
from streaming import run_graph_sync, stream_graph_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LangGraph OpenAI-Compatible API",
    version="1.0.0",
    description="LangGraph-based agent platform integrated with OpenWebUI",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ───────────────────────────────────────────────────────────────────────

async def verify_api_key(request: Request) -> None:
    """Validate Bearer token or api-key header."""
    if not settings.api_key:
        return  # Skip auth if key is empty

    auth = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("api-key", "")

    token = ""
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ").strip()
    elif api_key_header:
        token = api_key_header.strip()

    if token != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "time": int(time.time())}


@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_models() -> ModelList:
    """Return models shown in the OpenWebUI model picker."""
    return ModelList(
        data=[ModelInfo(id=model_id) for model_id in get_available_models()]
    )


@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI Chat Completions compatible endpoint.

    - stream=True  → StreamingResponse (SSE)
    - stream=False → JSONResponse (single response)
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    model = request.model

    logger.info(
        f"[{completion_id}] model={model} stream={request.stream} "
        f"msgs={len(request.messages)}"
    )

    try:
        graph = get_graph(model)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    lc_messages = convert_messages(request.messages)

    if request.stream:
        return StreamingResponse(
            stream_graph_response(graph, lc_messages, model, completion_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    response = await run_graph_sync(graph, lc_messages, model, completion_id)
    return JSONResponse(content=response.model_dump())


# ── Error handler ──────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": {"message": str(exc), "type": "internal_error"}},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
