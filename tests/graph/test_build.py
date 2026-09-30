from unittest.mock import AsyncMock, patch

import pytest

from app.agents.schemas import (
    DraftAnswer,
    Evidence,
    GatekeeperDecision,
    VerificationResult,
)
from app.graph.build import build_graph

KB_EVIDENCE = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")]


def _initial_state(query: str) -> dict:
    return {
        "query": query, "gatekeeper_decision": None, "evidence": [], "draft": None,
        "verification": None, "retry_count": 0, "final_answer": None, "refused": False, "trace": [],
    }


@pytest.mark.asyncio
async def test_graph_happy_path_returns_grounded_answer():
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=KB_EVIDENCE))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="Paris [geo.pdf]", cited_evidence=KB_EVIDENCE))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="ok"))),
    ):
        graph = build_graph(model=None, retrieval_client=None, mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert final_state["refused"] is False
    assert final_state["final_answer"] == "Paris [geo.pdf]"
    assert len(final_state["trace"]) >= 4  # gatekeeper, research, writer, verifier each logged


@pytest.mark.asyncio
async def test_graph_refuses_after_exhausting_retries():
    ungrounded = VerificationResult(grounded=False, unsupported_claims=["made up fact"], reasoning="not supported")
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=KB_EVIDENCE))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="unsupported claim", cited_evidence=KB_EVIDENCE))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=ungrounded)),
    ):
        graph = build_graph(model=None, retrieval_client=None, mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert final_state["refused"] is True
    assert final_state["retry_count"] == 2


@pytest.mark.asyncio
async def test_graph_refuse_route_skips_research_and_writer():
    with patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="refuse", reasoning="out of scope"))):
        graph = build_graph(model=None, retrieval_client=None, mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("What is your favorite color?"))

    assert final_state["refused"] is True
