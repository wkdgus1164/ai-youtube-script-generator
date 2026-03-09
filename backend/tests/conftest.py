"""Shared test fixtures."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config import settings


@pytest.fixture
def client():
    """FastAPI TestClient with auth header pre-set."""
    from main import app
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {settings.api_key}"
        yield c


@pytest.fixture
def clean_registry(monkeypatch):
    """Provide an isolated registry for each test — prevents cross-test pollution."""
    import graphs.registry as reg
    original = dict(reg._REGISTRY)
    reg._build_cached.cache_clear()
    reg._REGISTRY.clear()
    yield reg
    reg._REGISTRY.clear()
    reg._REGISTRY.update(original)
    reg._build_cached.cache_clear()
