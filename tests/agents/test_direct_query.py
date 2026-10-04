from unittest.mock import AsyncMock

import pytest

from app.agents.direct_query import run_direct_query
from app.rag_client.schemas import RetrievalResult, RetrievedChunk


@pytest.mark.asyncio
async def test_run_direct_query_returns_the_top_chunk_verbatim():
    chunk = RetrievedChunk(
        chunk_id="c1", document_id="d1", text="Paris is the capital of France.",
        section_path=["Intro"], page_start=1, page_end=1, source_filename="geo.pdf", score=0.95,
    )
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[chunk])

    result = await run_direct_query(fake_client, "What is the capital of France?")

    assert result.text == "Paris is the capital of France."
    assert result.source_filename == "geo.pdf"
    assert result.duration_seconds is None
    fake_client.search.assert_called_once_with("What is the capital of France?", top_k=1)


@pytest.mark.asyncio
async def test_run_direct_query_returns_none_when_nothing_matches():
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[])

    result = await run_direct_query(fake_client, "something not in the kb")

    assert result.text is None
    assert result.source_filename is None
