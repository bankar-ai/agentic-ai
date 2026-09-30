from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.schemas import (
    DraftAnswer,
    Evidence,
    GatekeeperDecision,
    VerificationResult,
)
from app.graph.build import build_graph


def _initial_state(query: str) -> dict:
    return {
        "query": query, "gatekeeper_decision": None, "evidence": [], "draft": None,
        "verification": None, "retry_count": 0, "final_answer": None, "refused": False, "trace": [],
    }


@pytest.mark.asyncio
async def test_kb_sufficient_path_produces_grounded_answer():
    kb_evidence = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="world-facts.pdf")]
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="strong KB match"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=kb_evidence))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="Paris [world-facts.pdf]", cited_evidence=kb_evidence))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="matches"))),
    ):
        graph = build_graph(MagicMock(), MagicMock(), [], max_retries=2)
        state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert state["final_answer"] == "Paris [world-facts.pdf]"
    assert state["refused"] is False


@pytest.mark.asyncio
async def test_web_fallback_path_labels_evidence_as_web():
    web_evidence = [Evidence(text="Sunny, 28C", source="web", citation="https://weather.example")]
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="web_fallback", reasoning="not in KB"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=web_evidence))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(
            text="According to a web search, it is sunny and 28C in Pune today.", cited_evidence=web_evidence,
        ))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="matches"))),
    ):
        graph = build_graph(MagicMock(), MagicMock(), [], max_retries=2)
        state = await graph.ainvoke(_initial_state("What's the weather in Pune today?"))

    assert "web search" in state["final_answer"].lower()
    assert state["refused"] is False


@pytest.mark.asyncio
async def test_out_of_scope_query_is_refused_without_research():
    research_mock = AsyncMock()
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="refuse", reasoning="nonsensical question"))),
        patch("app.graph.build.research", research_mock),
    ):
        graph = build_graph(MagicMock(), MagicMock(), [], max_retries=2)
        state = await graph.ainvoke(_initial_state("asdkjaslkdj?"))

    assert state["refused"] is True
    research_mock.assert_not_called()


@pytest.mark.asyncio
async def test_web_fallback_with_no_results_refuses_cleanly():
    """Review Focus: web search fallback itself fails/returns nothing -- must refuse, not crash."""
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="web_fallback", reasoning="not in KB"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=[]))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(
            text="I could not find enough evidence to answer this question.", cited_evidence=[],
        ))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(
            grounded=False, unsupported_claims=["I could not find enough evidence to answer this question."],
            reasoning="no cited evidence to verify against",
        ))),
    ):
        graph = build_graph(MagicMock(), MagicMock(), [], max_retries=2)
        state = await graph.ainvoke(_initial_state("What's the weather on Mars right now?"))

    assert state["refused"] is True
    assert state["final_answer"] is None


@pytest.mark.asyncio
async def test_persistent_ungrounded_answer_refuses_after_max_retries():
    kb_evidence = [Evidence(text="unrelated text", source="knowledge_base", citation="world-facts.pdf")]
    ungrounded = VerificationResult(grounded=False, unsupported_claims=["fabricated claim"], reasoning="not supported")
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=kb_evidence))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="fabricated claim", cited_evidence=kb_evidence))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=ungrounded)),
    ):
        graph = build_graph(MagicMock(), MagicMock(), [], max_retries=2)
        state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert state["refused"] is True
    assert state["final_answer"] is None
    assert state["retry_count"] == 2
