"""AGT-011: evaluation milestone -- a small, hand-built Q&A eval set (known-correct answers and
known-should-refuse cases) run against the *real* agent graph (real LLM calls through the
configured provider), scored and logged via Langfuse when credentials are configured, with a
local pass/fail report either way.

Why KB retrieval is a fixture here, not a live `enterprise-rag-platform` account: AGT-006
deliberately removed the shared/anonymous demo account, so there is no fixed KB content this
repeatable regression check could rely on without requiring whoever runs it to have their own
account with specific content already ingested. The fixture below (`tests/fixtures/sample_kb.py`,
already used by the integration test suite) stands in for the Gatekeeper's exploratory search and
Research's KB retrieval, deterministically. The web-fallback and refuse cases exercise the real
`search_web` (a live DuckDuckGo call) and the real Gatekeeper/Writer/Verifier reasoning -- nothing
about those paths is faked.

Usage:
    uv run python scripts/run_eval.py

Verified against the installed `langfuse` SDK (4.16.0) API directly (`Langfuse.run_experiment`,
`langfuse.Evaluation`) rather than assumed -- this repo's own "don't guess" convention for
fast-moving library integrations.
"""

import sys
from pathlib import Path
from unittest.mock import patch

from langfuse import Evaluation, Langfuse
from langfuse.experiment import LocalExperimentItem

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.llm import get_model
from app.agents.schemas import Evidence, GraphState
from app.agents.web_search import search_web
from app.core.config import get_settings
from app.core.tracing import get_tracer
from app.graph.build import build_graph
from app.rag_client.schemas import RetrievalResult
from tests.fixtures.sample_kb import SAMPLE_KB_CHUNKS

# A query "hits" the fixture KB if it mentions one of these -- anything else gets zero KB
# results, same shape a real empty-KB account would return.
_KB_TOPICS = ("france", "paris")

EVAL_CASES: list[LocalExperimentItem] = [
    {
        "input": "What is the capital of France?",
        "expected_output": {"refused": False, "answer_contains": "paris"},
        "metadata": {"id": "kb-hit-capital", "case": "KB-grounded, known-correct"},
    },
    {
        "input": "What was France's population in 2023?",
        "expected_output": {"refused": False, "answer_contains": "68 million"},
        "metadata": {"id": "kb-hit-population", "case": "KB-grounded, known-correct"},
    },
    {
        "input": "What is the capital of Japan?",
        "expected_output": {"refused": False, "answer_contains": "tokyo"},
        "metadata": {"id": "web-fallback-capital", "case": "web-fallback, known-correct"},
    },
    {
        # Grammatically fine, but no real-world referent at all -- unlike a famous nonsense
        # sentence (e.g. Chomsky's "colorless green ideas sleep furiously", tried first and
        # rejected: the system correctly found and reported real grounded facts *about* that
        # sentence instead of refusing, which is the right call, just not what this case needs).
        "input": "How many siblings does the taste of Tuesday have?",
        "expected_output": {"refused": True},
        "metadata": {"id": "refuse-nonsense", "case": "known-should-refuse"},
    },
]


class _FixtureRetrievalClient:
    """Stands in for `RagPlatformRetrievalClient` in the Gatekeeper's exploratory search only --
    deterministic, no live RAG-platform account needed (see module docstring)."""

    async def search(self, query: str, top_k: int = 5, **_kwargs) -> RetrievalResult:
        if any(topic in query.lower() for topic in _KB_TOPICS):
            return RetrievalResult(results=SAMPLE_KB_CHUNKS[:top_k])
        return RetrievalResult(results=[])


async def _fixture_research(_mcp_server_command, decision, query, _user_session=None):
    """Replaces `app.graph.build.research` for this eval run: "kb" route reads the same fixture
    instead of spawning a real MCP subprocess; "web_fallback" and "refuse" behave exactly as in
    production (real web search, or no research at all)."""
    from app.agents.schemas import ResearchResult

    if decision.route == "refuse":
        return ResearchResult(evidence=[])
    if decision.route == "web_fallback":
        return ResearchResult(evidence=await search_web(query))
    chunks = [c for c in SAMPLE_KB_CHUNKS if any(topic in query.lower() for topic in _KB_TOPICS)]
    evidence = [Evidence(text=c.text, source="knowledge_base", citation=c.source_filename) for c in chunks]
    return ResearchResult(evidence=evidence)


async def _run_case(query: str) -> dict:
    settings = get_settings()
    model = get_model(settings)
    tracer = get_tracer(settings)
    graph = build_graph(model, _FixtureRetrievalClient(), [], settings.max_verification_retries, tracer)  # type: ignore[arg-type]
    initial_state: GraphState = {
        "query": query, "user_session": None, "gatekeeper_decision": None, "evidence": [],
        "draft": None, "verification": None, "retry_count": 0, "final_answer": None, "refused": False,
        "trace": [],
    }
    with patch("app.graph.build.research", _fixture_research):
        final_state = await graph.ainvoke(initial_state)
    route = final_state["gatekeeper_decision"].route if final_state["gatekeeper_decision"] else None
    return {"final_answer": final_state["final_answer"], "refused": final_state["refused"], "route": route}


async def _task(*, item: LocalExperimentItem, **_kwargs) -> dict:
    return await _run_case(item["input"])


def _refusal_evaluator(*, output: dict, expected_output: dict, **_kwargs) -> Evaluation:
    expected_refused = expected_output.get("refused", False)
    passed = output["refused"] == expected_refused
    return Evaluation(
        name="refusal_matches_expected",
        value=passed,
        comment=f"expected refused={expected_refused}, got refused={output['refused']}",
    )


def _groundedness_evaluator(*, output: dict, expected_output: dict, **_kwargs) -> Evaluation:
    must_contain = expected_output.get("answer_contains")
    if must_contain is None:
        return Evaluation(name="answer_contains_expected_text", value=True, comment="no expectation set")
    answer = (output["final_answer"] or "").lower()
    passed = must_contain.lower() in answer
    return Evaluation(
        name="answer_contains_expected_text",
        value=passed,
        comment=f"expected to find {must_contain!r} in the answer" if not passed else "matched",
    )


def main() -> int:
    # Windows' default console codepage (cp1252) can't encode the emoji `result.format()` uses;
    # reconfigure rather than let a successful run crash on its own summary print.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    settings = get_settings()
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        client = Langfuse(
            public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key, host=settings.langfuse_host
        )
    else:
        # No Langfuse credentials configured: run and score locally, no remote calls at all.
        # Mirrors app.core.tracing's own no-op-when-unconfigured degradation.
        client = Langfuse(tracing_enabled=False)

    result = client.run_experiment(
        name="agentic-rag-regression",
        data=EVAL_CASES,
        # Protocol wants item: LocalExperimentItem | DatasetItem; this task only ever runs
        # against the local EVAL_CASES above, never a Langfuse-hosted dataset.
        task=_task,  # type: ignore[arg-type]
        evaluators=[_refusal_evaluator, _groundedness_evaluator],
        max_concurrency=1,  # free-tier OpenRouter rate limits -- sequential, not parallel
    )

    print(result.format())

    if len(result.item_results) != len(EVAL_CASES):
        print(f"\n{len(EVAL_CASES) - len(result.item_results)} case(s) errored before producing a result.")
        return 1
    failed = [
        (item, evaluation) for item in result.item_results
        for evaluation in item.evaluations
        if evaluation.value is False
    ]
    if failed:
        print(f"\n{len(failed)} evaluation(s) failed:")
        for item, evaluation in failed:
            # item.item is always one of this script's own EVAL_CASES (a plain dict), never a
            # Langfuse-hosted DatasetItem -- the Protocol's wider type just doesn't know that.
            case_id = item.item.get("metadata", {}).get("id", "?")  # type: ignore[union-attr]
            print(f"  - [{case_id}] {evaluation.name}: {evaluation.comment}")
            print(f"    output: {item.output}")
        return 1
    print("\nAll evaluations passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
