from app.agents.schemas import (
    Evidence,
    GatekeeperDecision,
    GraphState,
    VerificationResult,
)


def test_evidence_requires_valid_source():
    evidence = Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")
    assert evidence.source == "knowledge_base"


def test_gatekeeper_decision_defaults():
    decision = GatekeeperDecision(route="kb", reasoning="strong KB match")
    assert decision.top_k == 5
    assert decision.rerank is False


def test_graph_state_initial_shape():
    state: GraphState = {
        "query": "What is the capital of France?",
        "user_access_token": None,
        "gatekeeper_decision": None,
        "evidence": [],
        "draft": None,
        "verification": None,
        "retry_count": 0,
        "final_answer": None,
        "refused": False,
        "trace": [],
    }
    assert state["retry_count"] == 0
    assert state["refused"] is False


def test_verification_result_tracks_unsupported_claims():
    result = VerificationResult(grounded=False, unsupported_claims=["Paris has 5 million residents"], reasoning="no source for population figure")
    assert result.grounded is False
    assert len(result.unsupported_claims) == 1
