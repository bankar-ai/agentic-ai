"""Writer agent: synthesizes a cited answer from gathered evidence.

Never presents web-fallback evidence as if it were KB-grounded -- the system prompt requires the
source to be made explicit in the answer text itself, not just carried in the structured output.
"""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.schemas import DraftAnswer, Evidence

_SYSTEM_PROMPT = """You are the Writer agent. Synthesize a clear, cited answer from the given
evidence. Cite each claim with its source. If any evidence came from the web rather than the
knowledge base, say so explicitly in the answer text (e.g. "According to a web search...")."""


async def write_answer(model: Model | None, query: str, evidence: list[Evidence]) -> DraftAnswer:
    """Draft an answer from evidence, or a stock refusal if there's no evidence to draw on."""
    if not evidence:
        return DraftAnswer(text="I could not find enough evidence to answer this question.", cited_evidence=[])

    agent = Agent(model, output_type=DraftAnswer, system_prompt=_SYSTEM_PROMPT)
    evidence_block = "\n".join(f"[{item.source}] {item.citation}: {item.text}" for item in evidence)
    prompt = f"Question: {query}\n\nEvidence:\n{evidence_block}"
    result = await agent.run(prompt)
    return result.output
