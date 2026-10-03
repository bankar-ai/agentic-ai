import httpx
import pytest

from app.rag_client.auth import RagPlatformAuth
from app.rag_client.retrieval import (
    RagPlatformRetrievalClient,
    RagPlatformRetrievalError,
)

CHUNK = {
    "chunk_id": "c1", "document_id": "d1", "text": "Paris is the capital of France.",
    "section_path": ["Intro"], "page_start": 1, "page_end": 1,
    "source_filename": "geo.pdf", "score": 0.92,
}


def _login_response(csrf_token: str = "csrf-1", access_token: str = "access-1") -> httpx.Response:
    response = httpx.Response(200, json={"user_id": "u1", "csrf_token": csrf_token})
    response.headers["set-cookie"] = f"access_token={access_token}; Path=/; HttpOnly"
    return response


@pytest.mark.asyncio
async def test_search_returns_chunks():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _login_response()
        if request.url.path == "/retrieval/query":
            assert request.headers["x-csrf-token"] == "csrf-1"
            assert request.headers["cookie"] == "access_token=access-1; csrf_token=csrf-1"
            return httpx.Response(200, json={"results": [CHUNK]})
        return httpx.Response(404)

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        retrieval = RagPlatformRetrievalClient("http://rag.test", auth, client)

        result = await retrieval.search("capital of France", top_k=5)

        assert len(result.results) == 1
        assert result.results[0].text == "Paris is the capital of France."


@pytest.mark.asyncio
async def test_search_refreshes_session_once_on_401():
    calls = {"query": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _login_response(csrf_token="csrf-1", access_token="access-1")
        if request.url.path == "/auth/refresh":
            return _login_response(csrf_token="csrf-2", access_token="access-2")
        if request.url.path == "/retrieval/query":
            calls["query"] += 1
            if request.headers["x-csrf-token"] == "csrf-1":
                return httpx.Response(401, json={"detail": "expired"})
            return httpx.Response(200, json={"results": [CHUNK]})
        return httpx.Response(404)

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        retrieval = RagPlatformRetrievalClient("http://rag.test", auth, client)

        result = await retrieval.search("capital of France")

        assert calls["query"] == 2
        assert len(result.results) == 1


@pytest.mark.asyncio
async def test_search_refreshes_session_once_on_403():
    """A stale CSRF token after a session was refreshed elsewhere surfaces as 403, not 401 --
    both must trigger the same retry-once behavior."""
    calls = {"query": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _login_response(csrf_token="csrf-1", access_token="access-1")
        if request.url.path == "/auth/refresh":
            return _login_response(csrf_token="csrf-2", access_token="access-2")
        if request.url.path == "/retrieval/query":
            calls["query"] += 1
            if request.headers["x-csrf-token"] == "csrf-1":
                return httpx.Response(403, json={"detail": "Missing or invalid CSRF token"})
            return httpx.Response(200, json={"results": [CHUNK]})
        return httpx.Response(404)

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        retrieval = RagPlatformRetrievalClient("http://rag.test", auth, client)

        result = await retrieval.search("capital of France")

        assert calls["query"] == 2
        assert len(result.results) == 1


@pytest.mark.asyncio
async def test_search_returns_empty_results_without_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _login_response()
        return httpx.Response(200, json={"results": []})

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        retrieval = RagPlatformRetrievalClient("http://rag.test", auth, client)

        result = await retrieval.search("something not in the kb")

        assert result.results == []


@pytest.mark.asyncio
async def test_connection_error_raises_retrieval_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _login_response()
        raise httpx.ConnectError("connection refused")

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        retrieval = RagPlatformRetrievalClient("http://rag.test", auth, client)

        with pytest.raises(RagPlatformRetrievalError):
            await retrieval.search("anything")
