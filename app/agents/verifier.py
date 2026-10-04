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

AGT-012 (decision, not a gap): this code-level check only covers the structured `cited_evidence`
field, not inline markers the Writer might also write directly into `draft.text` prose (e.g.
"[some-file.pdf]"). Deliberately not cross-checked deterministically: free-text citation markers
have no fixed format to parse reliably (bracketed, parenthetical, a bare filename, ...), so a
regex-based check would itself be a source of false negatives/positives for marginal benefit over
what already exists -- the LLM content check above re-reads the full draft text against the real
retrieved evidence, which catches a prose citation pointing at unsupported content as an
unsupported claim, just not by name-matching the marker itself. Revisit only if this is observed
to actually let a fabricated inline citation through in practice.
"""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.schemas import DraftAnswer, Evidence, VerificationResult
from app.core.llm_metrics import measure_llm_call

_SYSTEM_PROMPT = """You are the Verifier agent. Given a draft answer and the evidence that was
actually retrieved for it, check whether every factual claim in the answer is supported by that
evidence. List any unsupported claims verbatim. Be strict: an unsupported claim is worse than an
admitted gap.

You MUST respond by calling the structured output tool with your verdict -- never reply with plain
prose. Do not describe your verdict in free text outside the tool call."""

# See writer.py's identical constant and note for why: raised retries help smaller local models
# self-correct into the structured tool call; `tool_choice="required"` was tried and reverted
# there for the same PydanticAI limitation (no function tools alongside output_type).
_OUTPUT_RETRIES = 3


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

    agent = Agent(model, output_type=VerificationResult, system_prompt=_SYSTEM_PROMPT, retries=_OUTPUT_RETRIES)
    evidence_block = "\n".join(f"[{item.source}] {item.citation}: {item.text}" for item in evidence)
    prompt = f"Draft answer: {draft.text}\n\nRetrieved evidence:\n{evidence_block}"
    with measure_llm_call("verifier"):
        result = await agent.run(prompt)
    return result.output
