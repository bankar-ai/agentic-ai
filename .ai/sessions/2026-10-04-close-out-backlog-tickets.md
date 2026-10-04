# Session — Close Out AGT-008/009/011/012

Date: 2026-10-03 to 2026-10-04
Tickets Touched: AGT-008, AGT-009, AGT-011, AGT-012

## Decisions

- User asked to complete all remaining backlog tickets and two un-ticketed concepts
  (Grafana Cloud observability, CI/CD), one by one, reporting back only once actually done.
- Order chosen: AGT-009 (foundational client-lifecycle fix) first, then AGT-012 (small,
  independent polish), then AGT-008 (streaming, touches the same router code), then AGT-011
  (eval harness, independent of the others).

## Implementation Summary

- **AGT-009**: `app/rag_client/shared_client.py`'s `get_shared_rag_platform_client()` is now
  reused across every request (`get_graph()`, `_get_retrieval_client()`), closed on FastAPI
  shutdown via a new `lifespan` in `app/main.py`. Found and fixed a real concurrency hazard along
  the way: `StaticTokenAuth` mutating a shared client's cookie jar would leak one user's session
  into another's concurrent in-flight request. Fixed by removing all cookie-jar reliance from
  `app/rag_client/auth.py`/`retrieval.py` — every auth value now travels as an explicit
  per-request header/cookie string. The MCP server's own standalone client is now closed on
  process exit too (`_close_retrieval_client()` in a `try`/`finally` around
  `mcp_server.run_stdio_async()`).
- **AGT-012**: a raw `ToolError`/`MCPError` from the MCP subprocess now surfaces as this
  project's own `KnowledgeBaseUnavailable`, mapped to a legible SSE error event
  (`app/agents/research.py`, `app/api/router.py`). Documented (not implemented) the decision not
  to add a deterministic inline-citation cross-check (`app/agents/verifier.py`'s docstring).
- **AGT-008**: `app/api/router.py`'s `_event_stream` and `app/ui/app.py`'s `run_agentic_query`
  now iterate `graph.astream(initial_state, stream_mode="updates")` instead of `ainvoke()`,
  yielding each agent's step as it actually finishes. Verified the exact LangGraph stream-mode
  shape interactively against this real graph before changing any code (this repo's own
  "don't guess" convention). Live-verified with per-line timestamps: steps arrived incrementally
  over ~21s, not batched at the end.
- **AGT-011**: `scripts/run_eval.py`, a 4-case hand-built eval set (2 KB-grounded, 1
  web-fallback, 1 should-refuse) run against the real configured LLM via
  `langfuse.Langfuse.run_experiment()` — verified against the installed SDK (4.16.0) directly,
  since the original spec's score/dataset-run API no longer exists in this version. Scores to
  Langfuse when credentials are configured, otherwise runs and reports locally with no remote
  calls. KB retrieval uses the existing `tests/fixtures/sample_kb.py` fixture, not a live
  `enterprise-rag-platform` account (no shared demo account exists post-`AGT-006`).
  Found and fixed a flawed eval case while running it live: the original "nonsense" refuse-case
  query closely paraphrased Chomsky's famous example sentence, so the system correctly
  researched and answered it instead of refusing — correct system behavior, bad eval case.
- Redeployed Cloud Run with the AGT-008/009/012 fixes (correctness-affecting); AGT-011 doesn't
  touch runtime code, so no redeploy was needed for it.
- 99 tests passing (up from 90), ruff/mypy clean on `app`, `tests`, and `scripts`.

## Blockers

None.

## Next Steps

Two concepts remain, not yet ticketed: Grafana Cloud observability (reusing
`enterprise-rag-platform`'s existing stack/dashboard) and CI/CD for Cloud Run deploys (currently
all manual `gcloud run deploy`). Tickets to be written before any implementation, per standing
instruction.
