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
- **Real architecture write-up** (2026-10-01, `AGT-003`): `docs/architecture.md` now reflects the
  actual system, including the deployment-blocking discovery below. The README has setup/run
  instructions.
- **Live smoke test done** (2026-09-30), against a local `enterprise-rag-platform` instance — not
  yet against the live GCP deployment (see `AGT-006`). Found and partially fixed real
  Writer/Verifier structured-output reliability issues with small local models (`AGT-010`); found
  and fixed an unrelated issue in `enterprise-rag-platform`'s local Docker setup (its
  Postgres/Redis containers were stopped while its server kept running, hanging every auth call —
  not an `agentic-ai` bug, just worth remembering if that platform's auth seems to hang again).
- **Deployment is scoped but not done** (2026-10-01): deploying this project to the portfolio's
  already-live GCP infra turns out to need real new work first, not just copying credentials — see
  "Known Gaps / Follow-ups" and `AGT-004` through `AGT-007`.
- A live service user (`agentic-ai-service@example.com`) is registered in the **local**
  `enterprise-rag-platform` instance (not the live deployment) with one small synthetic test
  document ingested, for smoke testing. Credentials saved to
  `C:\Users\Pankaj\.credentials\agentic-ai-credentials.md` per this portfolio's credentials policy,
  and to this repo's local (gitignored) `.env`.
- **Secrets hygiene verified and automated** (2026-10-01, `AGT-002`): Gitleaks pre-commit hook +
  CI backstop added (this repo had no CI workflow at all before this). A full 36-commit history
  scan found no leaked secrets ever.
- **Architecture diagram added** (2026-10-01, `AGT-015`): a Mermaid flowchart in
  `docs/architecture.md` (not draw.io — no GUI tool available to produce/verify one reliably;
  Mermaid renders natively on GitHub and is plain-text-reviewable).
- **Multi-tenant auth implemented** (2026-10-01, `AGT-013`/`AGT-014`): by default every query still
  uses the fixed service account (unchanged), but a caller can now supply their own already-issued
  `enterprise-rag-platform` session — via `Authorization: Bearer <token>` + `X-RAG-CSRF-Token` on
  the API, or the Gradio demo's new login accordion — and the whole request (Gatekeeper's
  exploratory search *and* Research's MCP subprocess call) runs as that user, seeing their own
  documents. `agentic-ai` never owns passwords. New `StaticTokenAuth` adapter +
  `RagPlatformAuthProvider` Protocol in `app/rag_client/auth.py`; the MCP subprocess receives the
  active identity per-call via `RAG_PLATFORM_ACCESS_TOKEN`/`RAG_PLATFORM_CSRF_TOKEN` env overrides,
  never baked into its own `.env`. **Live-verified against the real RAG platform deployment**, not
  just mocks: a real user-supplied session retrieved real content; a bad one failed cleanly.
- **ERP-116 auth-contract rewrite** (2026-10-01, discovered and fixed during live Cloud Run
  verification, not planned as its own ticket): the live `enterprise-rag-platform` deployment had
  already shipped `ERP-116` (cookie + CSRF double-submit auth, no `Authorization: Bearer` support
  at all), which the local dev instance this project had been tested against did not reflect. The
  first live query failed with a `pydantic_core.ValidationError` on the old `TokenPair` schema.
  Fixed by rewriting `app/rag_client/schemas.py`/`auth.py`/`retrieval.py`, `app/agents/schemas.py`
  (`UserSession` replaces the old bearer-token field), `app/mcp_server/server.py`, `app/api/router.py`,
  and `app/ui/app.py` to the real contract: login/refresh return `{user_id, csrf_token}`, tokens
  arrive as httpOnly cookies carried automatically by a shared `httpx.AsyncClient` cookie jar, and
  state-changing requests need `X-CSRF-Token` matching the `csrf_token` cookie (401 *and* 403 both
  trigger one retry-with-refresh). All affected tests rewritten to mock realistic `Set-Cookie`
  responses. This is the single most significant correctness finding of the project to date, and it
  was only caught because the team tested against the real live deployment rather than stopping at
  local/mocked verification.
- **OpenRouter LLM provider live** (2026-10-01, `AGT-004`): `get_openrouter_model()` in
  `app/agents/llm.py`, selected via `LLM_PROVIDER=openrouter`. Reuses
  `enterprise-rag-platform`'s existing funded OpenRouter API key (no separate account/Workspace —
  Workspace creation is dashboard-only). Model: `nvidia/nemotron-3-nano-30b-a3b:free` primary +
  `nvidia/nemotron-3.5-lightning:free` fallback via PydanticAI's `FallbackModel`. Live-verified 3/3
  successful on the Writer task that was flaky under local Ollama models — resolves `AGT-010`.
- **Deployed to Cloud Run** (2026-10-01, `AGT-005`/`AGT-007`): live at
  `https://agentic-ai-167676028188.us-central1.run.app` (512Mi/1cpu, scale-to-zero, free tier).
  Secrets (`agentic-ai-rag-platform-password`, `agentic-ai-openrouter-api-key`) in GCP Secret
  Manager, reusing existing credential values. `POST /query` verified end-to-end against the live
  RAG platform. Recorded in `D:\github-projects\gcp-deployment-tracker.md`.
- **Branch workflow established** (2026-10-01): `develop` for ongoing work, `main` reserved for
  what's actually deployed — mirrors `enterprise-rag-platform`'s existing convention.
- **Anonymous/service-account fallback removed** (2026-10-01, `AGT-006`, superseding its original
  "ingest demo content" plan): the project owner decided there is no shared demo account — every
  caller must bring their own `enterprise-rag-platform` login. `POST /query` now returns 401
  without a valid `Authorization` + `X-RAG-CSRF-Token` session; `get_graph()` and
  `_get_retrieval_client()` require a real `UserSession` (no more `| None` fallback to the fixed
  service account); both Gradio tabs refuse to query until logged in. `RAG_PLATFORM_EMAIL`/
  `PASSWORD` remain only as a local-dev convenience for running the MCP server standalone.
- **Standalone frontend with a real login page, deployed to Vercel** (2026-10-02, `AGT-016`/
  `AGT-017`): `app/api/auth.py`'s `POST /auth/login` proxies a login against
  `enterprise-rag-platform` and returns `{access_token, csrf_token}` as plain JSON (needed because
  that platform's own tokens arrive as httpOnly cookies no browser JS can read). `frontend/`
  (Vite + React + TS) has a login page and a query page, live at
  `https://agentic-ai-psi-mauve.vercel.app`. `app/main.py` gained `CORSMiddleware`
  (`app/core/cors.py`), and the Cloud Run deployment's `CORS_ALLOWED_ORIGINS` was set to that
  origin. The Gradio UI is unchanged and still exists for its original Direct-vs-Agentic
  comparison purpose.
- **Fixed a real multi-tenant auth bug found integration-testing the above** (2026-10-02):
  `StaticTokenAuth` (since `AGT-013`) only ever set the `access_token` cookie, never the matching
  `csrf_token` cookie the live platform's CSRF double-submit check compares the `X-CSRF-Token`
  header against — every forwarded per-user session (API header path, Gradio login, and the new
  frontend) was failing every retrieval call with `403 Missing or invalid CSRF token`. Fixed in
  `app/rag_client/auth.py`; live-verified end-to-end afterward (login -> `/query` ->
  `web_fallback` -> grounded answer) from the actual deployed Vercel origin.

## Known Gaps / Follow-ups

Tracked as tickets in `.ai/tickets/` rather than duplicated here in full — this section is a quick
index, read the ticket for detail.

**No open tickets remain** — every `AGT-*` ticket (`001`-`017`) is Done. See each ticket for
detail; `AGT-008`/`AGT-009`/`AGT-012` (2026-10-03/04) landed together with a real concurrency bug
found and fixed along the way (`StaticTokenAuth` was unsafe to share across concurrent
different-user requests); `AGT-011` (2026-10-04) added `scripts/run_eval.py`, a 4-case regression
check against the real LLM, scoring to Langfuse when configured.

**Not yet ticketed, flagged for the project owner (2026-10-03):**
- Grafana Cloud observability — `enterprise-rag-platform` already has a reusable stack/dashboard
  ("AI Platforms — Service Observability") built to accept a second project via a `service_name`
  picker; `agentic-ai` isn't wired into it yet.
- CI/CD for Cloud Run — every deploy so far has been a manual `gcloud run deploy`; no pipeline
  deploys on merge to `main`.

## Next Planned Work

- No blocking items remain in the original deployment chain. Anyone demoing this project live
  needs their own `enterprise-rag-platform` account with real content already ingested on it —
  that's now the demo's precondition, not something `agentic-ai` provisions for them.
- Grafana Cloud observability and CI/CD (above) are the only remaining known work, and neither
  has a ticket yet.
