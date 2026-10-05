from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.agents.schemas import (
    DraftAnswer,
    Evidence,
    GatekeeperDecision,
    UserSession,
    VerificationResult,
)
from app.graph.build import build_graph

KB_EVIDENCE = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")]


def _initial_state(query: str, user_session: UserSession | None = None) -> dict:
    return {
        "query": query, "user_session": user_session, "gatekeeper_decision": None, "evidence": [],
        "draft": None, "verification": None, "retry_count": 0, "final_answer": None, "refused": False, "trace": [],
    }


@pytest.mark.asyncio
async def test_graph_happy_path_returns_grounded_answer():
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=KB_EVIDENCE))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="Paris [geo.pdf]", cited_evidence=KB_EVIDENCE))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="ok"))),
    ):
        graph = build_graph(model=MagicMock(), retrieval_client=MagicMock(), mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert final_state["refused"] is False
    assert final_state["final_answer"] == "Paris [geo.pdf]"
    assert len(final_state["trace"]) >= 4  # gatekeeper, research, writer, verifier each logged


@pytest.mark.asyncio
async def test_verifier_node_checks_draft_against_retrieved_evidence():
    """The Verifier must receive the evidence Research retrieved, not only the Writer's draft."""
    verify_mock = AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="ok"))
    draft = DraftAnswer(text="Paris [geo.pdf]", cited_evidence=KB_EVIDENCE)
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=KB_EVIDENCE))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=draft)),
        patch("app.graph.build.verify_answer", verify_mock),
    ):
        graph = build_graph(model=MagicMock(), retrieval_client=MagicMock(), mcp_server_command=[], max_retries=2)
        await graph.ainvoke(_initial_state("What is the capital of France?"))

    _, draft_arg, evidence_arg = verify_mock.await_args.args
    assert draft_arg == draft
    assert evidence_arg == KB_EVIDENCE


@pytest.mark.asyncio
async def test_verifier_node_traces_reasoning_and_unsupported_claims():
    """AGT-035: a rejection must be debuggable from the trace, not just `grounded: false`."""
    verification = VerificationResult(
        grounded=False, unsupported_claims=["falls are the leading cause..."], reasoning="not supported by evidence"
    )
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=KB_EVIDENCE))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="Paris [geo.pdf]", cited_evidence=KB_EVIDENCE))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=verification)),
    ):
        graph = build_graph(model=MagicMock(), retrieval_client=MagicMock(), mcp_server_command=[], max_retries=1)
        final_state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    verifier_steps = [step for step in final_state["trace"] if step["agent"] == "verifier"]
    assert verifier_steps[0]["reasoning"] == "not supported by evidence"
    assert verifier_steps[0]["unsupported_claims"] == ["falls are the leading cause..."]


@pytest.mark.asyncio
async def test_graph_refuses_after_exhausting_retries():
    ungrounded = VerificationResult(grounded=False, unsupported_claims=["made up fact"], reasoning="not supported")
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=KB_EVIDENCE))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="unsupported claim", cited_evidence=KB_EVIDENCE))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=ungrounded)),
    ):
        graph = build_graph(model=MagicMock(), retrieval_client=MagicMock(), mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert final_state["refused"] is True
    assert final_state["retry_count"] == 2


@pytest.mark.asyncio
async def test_research_node_forwards_user_session_from_state():
    """AGT-013: a logged-in user's session in state must reach research(), not just the fixed account."""
    research_mock = AsyncMock(return_value=AsyncMock(evidence=KB_EVIDENCE))
    session = UserSession(access_token="user-token-123", csrf_token="user-csrf-456")
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", research_mock),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="Paris [geo.pdf]", cited_evidence=KB_EVIDENCE))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="ok"))),
    ):
        graph = build_graph(model=MagicMock(), retrieval_client=MagicMock(), mcp_server_command=["cmd"], max_retries=2)
        await graph.ainvoke(_initial_state("What is the capital of France?", user_session=session))

    research_mock.assert_awaited_once_with(["cmd"], ANY, "What is the capital of France?", session)


@pytest.mark.asyncio
async def test_graph_refuse_route_skips_research_and_writer():
    with patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="refuse", reasoning="out of scope"))):
        graph = build_graph(model=MagicMock(), retrieval_client=MagicMock(), mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("What is your favorite color?"))

    assert final_state["refused"] is True


@pytest.mark.asyncio
async def test_research_and_writer_nodes_trace_citations():
    """AGT-046: before this, the trace only ever carried `evidence_count`/`text` -- no way to see
    which documents or URLs were actually used, not even for the Verifier's "grounded" claim to
    point back to."""
    web_evidence = [Evidence(text="A city in France.", source="web", citation="https://example.com/paris")]
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=web_evidence))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="Paris.", cited_evidence=web_evidence))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="ok"))),
    ):
        graph = build_graph(model=MagicMock(), retrieval_client=MagicMock(), mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("Where is Paris?"))

    research_step = next(s for s in final_state["trace"] if s["agent"] == "research")
    writer_step = next(s for s in final_state["trace"] if s["agent"] == "writer")
    assert research_step["citations"] == [{"source": "web", "citation": "https://example.com/paris"}]
    assert writer_step["citations"] == [{"source": "web", "citation": "https://example.com/paris"}]
