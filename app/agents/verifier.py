"""Verifier agent: checks each claim in a draft answer against its cited evidence.

Self-RAG-style reflection step. A draft with no cited evidence (e.g. the Writer's own refusal
text) is never considered grounded, since there is nothing to check it against.
"""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.schemas import DraftAnswer, VerificationResult

_SYSTEM_PROMPT = """You are the Verifier agent. Given a draft answer and the evidence it cites,
check whether every factual claim in the answer is actually supported by that evidence. List any
unsupported claims verbatim. Be strict: an unsupported claim is worse than an admitted gap."""


async def verify_answer(model: Model | None, draft: DraftAnswer) -> VerificationResult:
    """Check a draft's groundedness against its own cited evidence."""
    if not draft.cited_evidence:
        return VerificationResult(grounded=False, unsupported_claims=[draft.text], reasoning="no cited evidence to verify against")

    agent = Agent(model, output_type=VerificationResult, system_prompt=_SYSTEM_PROMPT)
    evidence_block = "\n".join(f"[{item.source}] {item.citation}: {item.text}" for item in draft.cited_evidence)
    prompt = f"Draft answer: {draft.text}\n\nCited evidence:\n{evidence_block}"
    result = await agent.run(prompt)
    return result.output
