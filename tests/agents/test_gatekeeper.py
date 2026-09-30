from unittest.mock import AsyncMock

import pytest
from pydantic_ai.models.test import TestModel

from app.agents.gatekeeper import grade_retrieval
from app.agents.schemas import GatekeeperDecision
from app.rag_client.schemas import RetrievalResult, RetrievedChunk


@pytest.mark.asyncio
async def test_grade_retrieval_routes_to_kb_when_evidence_found():
    chunk = RetrievedChunk(
        chunk_id="c1", document_id="d1", text="Paris is the capital of France.",
        section_path=["Intro"], page_start=1, page_end=1, source_filename="geo.pdf", score=0.95,
    )
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[chunk])
    model = TestModel(custom_output_args=GatekeeperDecision(route="kb", reasoning="strong match", top_k=5))

    decision = await grade_retrieval(model, fake_client, "What is the capital of France?")

    assert isinstance(decision, GatekeeperDecision)
    assert decision.route == "kb"


@pytest.mark.asyncio
async def test_grade_retrieval_handles_empty_kb_results():
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[])
    model = TestModel(custom_output_args=GatekeeperDecision(route="web_fallback", reasoning="no KB evidence found"))

    decision = await grade_retrieval(model, fake_client, "What is today's weather in Pune?")

    assert decision.route == "web_fallback"


@pytest.mark.asyncio
async def test_grade_retrieval_overrides_kb_route_when_kb_results_are_empty():
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[])
    model = TestModel(custom_output_args=GatekeeperDecision(route="kb", reasoning="looks answerable"))

    decision = await grade_retrieval(model, fake_client, "What is today's weather in Pune?")

    assert decision.route == "web_fallback"
    assert "Overridden" in decision.reasoning


@pytest.mark.asyncio
async def test_grade_retrieval_does_not_override_refuse_when_kb_results_are_empty():
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[])
    model = TestModel(custom_output_args=GatekeeperDecision(route="refuse", reasoning="nonsense"))

    decision = await grade_retrieval(model, fake_client, "asdkjaslkdj?")

    assert decision.route == "refuse"
