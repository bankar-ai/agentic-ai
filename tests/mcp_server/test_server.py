from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.config import Settings
from app.mcp_server.server import _build_auth, _search_knowledge_base_impl
from app.rag_client.auth import RagPlatformAuth, StaticTokenAuth
from app.rag_client.schemas import RetrievalResult, RetrievedChunk


@pytest.mark.asyncio
async def test_search_knowledge_base_returns_chunk_dicts():
    chunk = RetrievedChunk(
        chunk_id="c1", document_id="d1", text="Paris is the capital of France.",
        section_path=["Intro"], page_start=1, page_end=1, source_filename="geo.pdf", score=0.92,
    )
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[chunk])

    result = await _search_knowledge_base_impl(
        fake_client, query="capital of France", top_k=5, rerank=False, expand_sections=False
    )

    assert result == [{
        "text": "Paris is the capital of France.",
        "source_filename": "geo.pdf",
        "section_path": ["Intro"],
        "score": 0.92,
    }]
    fake_client.search.assert_awaited_once_with(
        "capital of France", top_k=5, rerank=False, expand_sections=False
    )


@pytest.mark.asyncio
async def test_search_knowledge_base_empty_results():
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[])

    result = await _search_knowledge_base_impl(
        fake_client, query="nothing relevant", top_k=5, rerank=False, expand_sections=False
    )

    assert result == []


def test_build_auth_uses_static_token_when_session_set():
    settings = Settings(
        rag_platform_base_url="http://localhost:8000",
        rag_platform_email="svc@example.com",
        rag_platform_password="secret123",
        rag_platform_access_token="user-supplied-token",
        rag_platform_csrf_token="user-supplied-csrf",
    )

    auth = _build_auth(settings, MagicMock(spec=httpx.AsyncClient))

    assert isinstance(auth, StaticTokenAuth)


def test_build_auth_falls_back_to_service_account_when_only_access_token_set():
    """Both-or-neither: a partial session (e.g. a missing CSRF token) must not be treated as
    a usable per-user session."""
    settings = Settings(
        rag_platform_base_url="http://localhost:8000",
        rag_platform_email="svc@example.com",
        rag_platform_password="secret123",
        rag_platform_access_token="user-supplied-token",
    )

    auth = _build_auth(settings, MagicMock(spec=httpx.AsyncClient))

    assert isinstance(auth, RagPlatformAuth)


def test_build_auth_falls_back_to_service_account_when_no_access_token():
    settings = Settings(
        rag_platform_base_url="http://localhost:8000",
        rag_platform_email="svc@example.com",
        rag_platform_password="secret123",
    )

    auth = _build_auth(settings, MagicMock(spec=httpx.AsyncClient))

    assert isinstance(auth, RagPlatformAuth)
