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


def _jwt_with_sub(sub: str) -> str:
    import base64
    import json

    def b64(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS256'})}.{b64({'sub': sub})}.sig"


# AGT-051: /auth/login also captures and stores the refresh_token cookie, when present and a
# database is configured.


@pytest.mark.asyncio
async def test_login_endpoint_stores_the_refresh_token_when_database_configured(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "svc-secret")
    get_settings.cache_clear()
    access_token = _jwt_with_sub("user-1")

    class _FakeStore:
        def __init__(self):
            self.saved = []

        async def save_refresh_token(self, user_id, refresh_token):
            self.saved.append((user_id, refresh_token))

    fake_store = _FakeStore()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(
                200,
                json={"user_id": "u1", "csrf_token": "csrf-1"},
                headers=[
                    ("set-cookie", f"access_token={access_token}; Path=/; HttpOnly"),
                    ("set-cookie", "refresh_token=a-real-refresh-token; Path=/; HttpOnly"),
                ],
            )
        return httpx.Response(401)

    with (
        patch(
            "app.api.auth.httpx.AsyncClient",
            lambda **kwargs: _RealAsyncClient(base_url=kwargs["base_url"], transport=httpx.MockTransport(handler)),
        ),
        patch("app.api.auth.get_session_store", AsyncMock(return_value=fake_store)),
    ):
        client = TestClient(app)
        response = client.post("/auth/login", json={"email": "user@example.com", "password": "correct-password"})

    assert response.status_code == 200
    assert fake_store.saved == [("user-1", "a-real-refresh-token")]


@pytest.mark.asyncio
async def test_login_endpoint_succeeds_even_if_refresh_token_storage_fails(monkeypatch):
    """A storage failure must never break login itself -- the access/csrf token pair already
    works without it, just without silent refresh."""
    from unittest.mock import AsyncMock

    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "svc-secret")
    get_settings.cache_clear()
    access_token = _jwt_with_sub("user-1")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(
                200,
                json={"user_id": "u1", "csrf_token": "csrf-1"},
                headers=[
                    ("set-cookie", f"access_token={access_token}; Path=/; HttpOnly"),
                    ("set-cookie", "refresh_token=a-real-refresh-token; Path=/; HttpOnly"),
                ],
            )
        return httpx.Response(401)

    with (
        patch(
            "app.api.auth.httpx.AsyncClient",
            lambda **kwargs: _RealAsyncClient(base_url=kwargs["base_url"], transport=httpx.MockTransport(handler)),
        ),
        patch("app.api.auth.get_session_store", AsyncMock(side_effect=RuntimeError("db unavailable"))),
    ):
        client = TestClient(app)
        response = client.post("/auth/login", json={"email": "user@example.com", "password": "correct-password"})

    assert response.status_code == 200
    assert response.json()["access_token"] == access_token
