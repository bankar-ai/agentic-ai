"""Verifier agent: checks each claim in a draft answer against the evidence actually retrieved.

Self-RAG-style reflection step. The ground truth is the evidence the Research step gathered
(`GraphState["evidence"]`), never the Writer's own `cited_evidence`: that list is LLM output, so a
Writer that invents or alters a citation would otherwise be checked against its own invention.

Before any LLM call, each cited item is matched on its (source, citation) pair against the
retrieved evidence. A citation that doesn't match -- an invented document, or a web result
relabeled as "knowledge_base" -- is fabricated by definition, and the draft is rejected in code
without asking a model. Matching deliberately ignores the cited `text`, which a Writer may
legitimately abbreviate; the content check is the LLM step below, which is given the real
retrieved text, not the Writer's copy of it. A draft that cites nothing (e.g. the Writer's own refusal
text) is never considered grounded, since there is nothing to check it against.
"""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.schemas import DraftAnswer, Evidence, VerificationResult

_SYSTEM_PROMPT = """You are the Verifier agent. Given a draft answer and the evidence that was
actually retrieved for it, check whether every factual claim in the answer is supported by that
evidence. List any unsupported claims verbatim. Be strict: an unsupported claim is worse than an
admitted gap."""


def _evidence_key(item: Evidence) -> tuple[str, str]:
    return (item.source, item.citation)


async def verify_answer(model: Model | None, draft: DraftAnswer, evidence: list[Evidence]) -> VerificationResult:
    """Check a draft's groundedness against the evidence that was actually retrieved."""
    if not draft.cited_evidence:
        return VerificationResult(grounded=False, unsupported_claims=[draft.text], reasoning="no cited evidence to verify against")

    retrieved = {_evidence_key(item) for item in evidence}
    fabricated = [item for item in draft.cited_evidence if _evidence_key(item) not in retrieved]
    if fabricated:
        return VerificationResult(
            grounded=False,
            unsupported_claims=[f"[{item.source}] {item.citation}" for item in fabricated],
            reasoning=f"{len(fabricated)} cited evidence item(s) do not match any retrieved evidence",
        )

    agent = Agent(model, output_type=VerificationResult, system_prompt=_SYSTEM_PROMPT)
    evidence_block = "\n".join(f"[{item.source}] {item.citation}: {item.text}" for item in evidence)
    prompt = f"Draft answer: {draft.text}\n\nRetrieved evidence:\n{evidence_block}"
    result = await agent.run(prompt)
    return result.output
