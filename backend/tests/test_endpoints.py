"""Integration tests for FastAPI endpoints."""
from __future__ import annotations

import pytest


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "time" in data


def test_models_endpoint_returns_registered_models(client):
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    model_ids = [m["id"] for m in data["data"]]
    # At minimum the three built-in graphs should be present
    assert "assistant-general" in model_ids
    assert "assistant-research" in model_ids
    assert "assistant-dev" in model_ids


def test_models_endpoint_requires_auth():
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as c:
        resp = c.get("/v1/models")  # No auth header
    assert resp.status_code == 401


def test_chat_completions_unknown_model_returns_404(client):
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "nonexistent-model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
        },
    )
    assert resp.status_code == 404
    assert "nonexistent-model" in resp.json()["detail"]


# TODO(template-user): Add integration tests that mock the LLM to avoid
# real API calls. Example using unittest.mock:
#
# from unittest.mock import AsyncMock, patch
#
# def test_chat_completions_non_streaming(client):
#     with patch("graphs.general.create_llm") as mock_llm_factory:
#         mock_llm = MagicMock()
#         mock_llm.invoke.return_value = AIMessage(content="Hello!")
#         mock_llm_factory.return_value = mock_llm
#         ...
