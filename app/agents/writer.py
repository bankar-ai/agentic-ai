"""Writer agent: synthesizes a cited answer from gathered evidence.

Never presents web-fallback evidence as if it were KB-grounded -- the system prompt requires the
source to be made explicit in the answer text itself, not just carried in the structured output.
"""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.schemas import DraftAnswer, Evidence

_SYSTEM_PROMPT = """You are the Writer agent. Synthesize a clear, cited answer from the given
evidence. Cite each claim with its source. If any evidence came from the web rather than the
knowledge base, say so explicitly in the answer text (e.g. "According to a web search...").

You MUST respond by calling the structured output tool with your answer -- never reply with plain
prose. Put your full written answer in the tool's `text` field and list the evidence you drew on
in `cited_evidence`. Do not describe your answer in free text outside the tool call."""

# Smaller local models (observed: qwen3:8b, granite4:tiny-h) reliably produce the right, well-cited
# content but sometimes reply in plain prose instead of the structured tool call. A raised retry
# budget gives PydanticAI's built-in retry-prompt loop more chances to self-correct.
# NOTE: `model_settings=ModelSettings(tool_choice="required")` was tried as a stronger fix and
# reverted -- PydanticAI raises `UserError` for agents with only `output_type` and no function
# tools ("`tool_choice='required'` prevents the agent from producing a final response because
# output tools are excluded"). That forcing mechanism only applies when real function tools exist
# alongside structured output; it isn't available for a pure-output agent like this one.
_OUTPUT_RETRIES = 3


async def write_answer(model: Model | None, query: str, evidence: list[Evidence]) -> DraftAnswer:
    """Draft an answer from evidence, or a stock refusal if there's no evidence to draw on."""
    if not evidence:
        return DraftAnswer(text="I could not find enough evidence to answer this question.", cited_evidence=[])

    agent = Agent(model, output_type=DraftAnswer, system_prompt=_SYSTEM_PROMPT, retries=_OUTPUT_RETRIES)
    evidence_block = "\n".join(f"[{item.source}] {item.citation}: {item.text}" for item in evidence)
    prompt = f"Question: {query}\n\nEvidence:\n{evidence_block}"
    result = await agent.run(prompt)
    return result.output
