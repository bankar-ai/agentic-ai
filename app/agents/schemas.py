"""Structured (A2A-style) messages passed between agents, and the shared LangGraph state."""

from typing import Literal, TypedDict

from pydantic import BaseModel

EvidenceSource = Literal["knowledge_base", "web"]


class Evidence(BaseModel):
    """One piece of evidence gathered by the Research agent, always source-labeled."""

    text: str
    source: EvidenceSource
    citation: str


class GatekeeperDecision(BaseModel):
    """The Gatekeeper's grading of retrieval sufficiency and the route to take."""

    route: Literal["kb", "web_fallback", "refuse"]
    reasoning: str
    top_k: int = 5
    rerank: bool = False


class ResearchResult(BaseModel):
    """Evidence gathered by the Research agent for one routing decision."""

    evidence: list[Evidence]


class DraftAnswer(BaseModel):
    """The Writer's synthesized answer, with the evidence it drew on."""

    text: str
    cited_evidence: list[Evidence]


class VerificationResult(BaseModel):
    """The Verifier's groundedness check of a draft answer against the retrieved evidence."""

    grounded: bool
    unsupported_claims: list[str]
    reasoning: str


class GraphState(TypedDict):
    """Shared state threaded through every LangGraph node."""

    query: str
    # AGT-013: the logged-in end user's RAG-platform access token, if any -- threaded through to
    # Research's MCP subprocess call so retrieval runs as that user. None means the fixed service
    # account is used instead (today's single-tenant behavior, unchanged).
    user_access_token: str | None
    gatekeeper_decision: GatekeeperDecision | None
    evidence: list[Evidence]
    draft: DraftAnswer | None
    verification: VerificationResult | None
    retry_count: int
    final_answer: str | None
    refused: bool
    trace: list[dict]
