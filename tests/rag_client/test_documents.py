import httpx
import pytest

from app.rag_client.auth import RagPlatformAuth, RagPlatformAuthError, StaticTokenAuth
from app.rag_client.documents import (
    RagPlatformDocumentsClient,
    RagPlatformDocumentsError,
)

DOC = {"document_id": "d1", "filename": "geo.pdf", "created_at": "2026-10-01T12:00:00Z"}


def _login_response(csrf_token: str = "csrf-1", access_token: str = "access-1") -> httpx.Response:
    response = httpx.Response(200, json={"user_id": "u1", "csrf_token": csrf_token})
    response.headers["set-cookie"] = f"access_token={access_token}; Path=/; HttpOnly"
    return response


@pytest.mark.asyncio
async def test_list_documents_returns_documents():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _login_response()
        if request.url.path == "/documents":
            assert request.headers["x-csrf-token"] == "csrf-1"
            assert request.headers["cookie"] == "access_token=access-1; csrf_token=csrf-1"
            return httpx.Response(200, json={"documents": [DOC], "has_more": False})
        return httpx.Response(404)

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        docs_client = RagPlatformDocumentsClient("http://rag.test", auth, client)

        result = await docs_client.list_documents()

        assert len(result.documents) == 1
        assert result.documents[0].filename == "geo.pdf"
        assert result.has_more is False


@pytest.mark.asyncio
async def test_list_documents_refreshes_session_once_on_401():
    calls = {"documents": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _login_response(csrf_token="csrf-1", access_token="access-1")
        if request.url.path == "/auth/refresh":
            return _login_response(csrf_token="csrf-2", access_token="access-2")
        if request.url.path == "/documents":
            calls["documents"] += 1
            if request.headers["x-csrf-token"] == "csrf-1":
                return httpx.Response(401, json={"detail": "expired"})
            return httpx.Response(200, json={"documents": [DOC], "has_more": False})
        return httpx.Response(404)

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        docs_client = RagPlatformDocumentsClient("http://rag.test", auth, client)

        result = await docs_client.list_documents()

        assert calls["documents"] == 2
        assert len(result.documents) == 1


@pytest.mark.asyncio
async def test_connection_error_raises_documents_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _login_response()
        raise httpx.ConnectError("connection refused")

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        docs_client = RagPlatformDocumentsClient("http://rag.test", auth, client)

        with pytest.raises(RagPlatformDocumentsError):
            await docs_client.list_documents()


@pytest.mark.asyncio
async def test_static_token_auth_cannot_refresh_so_a_401_surfaces_as_auth_error():
    """AGT-025: an end-user session (StaticTokenAuth) has no password and can't refresh -- a
    401 propagates as RagPlatformAuthError, same as RagPlatformRetrievalClient's own behavior,
    not wrapped into RagPlatformDocumentsError. Callers (the /documents endpoint) catch both."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/documents":
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(404)

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = StaticTokenAuth("stale-access", "stale-csrf")
        docs_client = RagPlatformDocumentsClient("http://rag.test", auth, client)

        with pytest.raises(RagPlatformAuthError):
            await docs_client.list_documents()
