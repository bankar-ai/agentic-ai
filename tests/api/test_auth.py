from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

_RealAsyncClient = httpx.AsyncClient


def _login_transport(csrf_token: str = "csrf-1", access_token: str = "access-1") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            response = httpx.Response(200, json={"user_id": "u1", "csrf_token": csrf_token})
            response.headers["set-cookie"] = f"access_token={access_token}; Path=/; HttpOnly"
            return response
        return httpx.Response(401, json={"detail": "Invalid email or password"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_login_endpoint_returns_session_on_success(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "svc-secret")
    get_settings.cache_clear()
    transport = _login_transport()

    with patch(
        "app.api.auth.httpx.AsyncClient",
        lambda **kwargs: _RealAsyncClient(base_url=kwargs["base_url"], transport=transport),
    ):
        client = TestClient(app)
        response = client.post("/auth/login", json={"email": "user@example.com", "password": "correct-password"})

    assert response.status_code == 200
    assert response.json() == {"access_token": "access-1", "csrf_token": "csrf-1"}


@pytest.mark.asyncio
async def test_login_endpoint_returns_401_on_bad_credentials(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "svc-secret")
    get_settings.cache_clear()

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid email or password"})

    transport = httpx.MockTransport(failing_handler)

    with patch(
        "app.api.auth.httpx.AsyncClient",
        lambda **kwargs: _RealAsyncClient(base_url=kwargs["base_url"], transport=transport),
    ):
        client = TestClient(app)
        response = client.post("/auth/login", json={"email": "user@example.com", "password": "wrong-password"})

    assert response.status_code == 401


def test_login_endpoint_rejects_malformed_body():
    client = TestClient(app)
    response = client.post("/auth/login", json={"email": "user@example.com"})

    assert response.status_code == 422
