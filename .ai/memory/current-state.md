# Current State

Living summary of what exists in this repository right now. Update it in place as things change.
History belongs in `.ai/sessions/`, not here.

## What Exists

- **Repo scaffolding** (2026-09-28): the `.ai/` operating system (tickets/adr/sessions/memory/templates,
  mirroring `enterprise-rag-platform`'s structure), `CLAUDE.md`, and a `docs/architecture.md` skeleton.
- **Design spec** (2026-09-28): `docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md`.
  **Implementation plan**: `docs/superpowers/plans/2026-09-28-agentic-rag-orchestration.md` (17 tasks).
- **The agentic RAG orchestration system is implemented and merged to `main`** (2026-09-30, PR #1
  at `bankar-ai/agentic-ai`). All 17 plan tasks are done and the final whole-branch review findings
  are fixed. Components:
  - `app/rag_client/`: auth and retrieval clients for `enterprise-rag-platform`.
  - `app/mcp_server/`: MCP stdio server exposing `search_knowledge_base`. It lives in this repo,
    which resolves the earlier open question about where the server should go.
  - `app/agents/`: Gatekeeper (route grading, with a code-level override from an empty KB to
    `web_fallback`), Research (KB evidence built in code from the MCP tool result, and a web
    fallback labeled `web`), Writer, and Verifier (checks drafts against the evidence that was
    actually retrieved and rejects fabricated citations in code). All agents use a local Ollama
    model through PydanticAI.
  - `app/graph/build.py`: the LangGraph state machine, with a bounded verify-and-retry loop
    (`MAX_VERIFICATION_RETRIES`) that ends in a refusal.
  - `app/api/router.py`: `POST /query` returns SSE (the whole trace once the graph finishes, not
    per step), and an outage surfaces as `event: error` or a 5xx.
  - `app/core/tracing.py`: Langfuse tracing that falls back to a no-op when there are no credentials.
  - `app/ui/app.py`: a two-tab Gradio demo (Direct RAG vs. Agentic RAG).
  - `tests/`: unit and integration tests with a fixture KB. None of them need a live Ollama
    instance or RAG platform.
- **Quality gate**: `uv run pytest -q --cov=app` (54 passed, 92% coverage), and
  `uv run ruff check app tests` and `uv run mypy app` are both clean.
- The README has setup and run instructions.

## Known Gaps / Follow-ups

- The SSE endpoint and the UI deliver the trace only after the graph completes. True per-step
  streaming (`graph.astream`) is a planned fast-follow.
- `get_graph()` rebuilds its httpx client, auth, and graph on every request, and the httpx
  client's lifecycle isn't managed. This is fine for a demo; a long-lived service would need an ADR.
- No live end-to-end run has been done against a real Ollama instance and `enterprise-rag-platform`
  in this pass. All verification used tests with mocks or `TestModel`.
- `docs/architecture.md` still says "scaffolding only" and needs a real architecture write-up.
- Gitleaks pre-commit/CI hooks (per `CLAUDE.md`) aren't set up yet.

## Next Planned Work

- Run an end-to-end smoke test against live Ollama and `enterprise-rag-platform`.
- Evaluation milestone: Langfuse datasets/scores, which depends on ERP-112 sequencing (see
  `decisions-in-progress.md`).
