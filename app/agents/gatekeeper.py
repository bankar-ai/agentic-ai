"""Gatekeeper agent: grades KB retrieval sufficiency and decides the route.

This is the guardrail -- it decides whether the query gets answered from the trusted knowledge
base, falls back to a flagged web search, or gets refused outright, following the Corrective RAG
pattern (a retrieval evaluator gating what happens next, rather than always generating).
"""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.schemas import GatekeeperDecision
from app.rag_client.retrieval import RagPlatformRetrievalClient

_SYSTEM_PROMPT = """You are the Gatekeeper of a retrieval-augmented answering system.

You are given a user's question and the top results of an exploratory knowledge-base search.
Decide one of three routes:
- "kb": the KB results are relevant and sufficient to answer the question. Set top_k to how many
  results you'd want the Research agent to fetch (5-10), and rerank=true if the question is
  ambiguous enough that result ordering matters.
- "web_fallback": the KB results are empty, irrelevant, or clearly insufficient, but the question
  is answerable from general web knowledge.
- "refuse": the question cannot be reliably answered from the KB or a general web search.

Always explain your reasoning briefly."""


def _build_agent(model: Model) -> Agent[None, GatekeeperDecision]:
    return Agent(model, output_type=GatekeeperDecision, system_prompt=_SYSTEM_PROMPT)


async def grade_retrieval(
    model: Model, retrieval_client: RagPlatformRetrievalClient, query: str
) -> GatekeeperDecision:
    """Run an exploratory KB search and ask the Gatekeeper agent to grade it."""
    exploratory = await retrieval_client.search(query, top_k=3)
    chunk_summaries = "\n".join(f"- {chunk.text[:200]}" for chunk in exploratory.results) or "(no results)"

    agent = _build_agent(model)
    prompt = f"Question: {query}\n\nExploratory KB results:\n{chunk_summaries}"
    result = await agent.run(prompt)
    decision = result.output

    # Code-level guard: with zero exploratory results, a "kb" route can only find nothing again,
    # burn every retry, and refuse -- without ever trying the web fallback. Don't trust a (small,
    # local) model to always notice the "(no results)" marker.
    if not exploratory.results and decision.route == "kb":
        return decision.model_copy(update={
            "route": "web_fallback",
            "reasoning": f"{decision.reasoning} [Overridden: exploratory KB search returned no results, "
                         "so routing to web_fallback instead of kb.]",
        })
    return decision
