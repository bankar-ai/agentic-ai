import pytest

from app.core.config import get_settings
from app.rag_client.shared_client import (
    close_shared_rag_platform_client,
    get_shared_rag_platform_client,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.test")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "secret123")
    get_settings.cache_clear()
    get_shared_rag_platform_client.cache_clear()
    yield
    get_shared_rag_platform_client.cache_clear()


def test_get_shared_rag_platform_client_returns_the_same_instance_every_call():
    first = get_shared_rag_platform_client()
    second = get_shared_rag_platform_client()

    assert first is second


@pytest.mark.asyncio
async def test_close_shared_rag_platform_client_is_a_noop_when_never_built():
    await close_shared_rag_platform_client()  # must not raise


@pytest.mark.asyncio
async def test_close_shared_rag_platform_client_closes_and_allows_a_fresh_one_after():
    first = get_shared_rag_platform_client()

    await close_shared_rag_platform_client()

    assert first.is_closed is True
    second = get_shared_rag_platform_client()
    assert second is not first
    assert second.is_closed is False
