from unittest.mock import AsyncMock

import pytest

from app.mcp_server.server import _search_knowledge_base_impl
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
