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
- **Per-node/MCP/LLM latency instrumentation added (`AGT-021`, 2026-10-04):** OTel spans around
  each graph node (`app/graph/build.py`) and the MCP tool call (`app/agents/research.py`), plus a
  new `llm_generation_duration_seconds` histogram (`app/core/llm_metrics.py`) around each
  PydanticAI `agent.run()` call. Deployed as `agentic-ai-00014-n5c`. Live verification found and
  fixed a real bug along the way: `OPENROUTER_MODEL` had drifted to an invalid slug
  (`nvidia/nemotron-3-nano-30b-a3b:free`, 404 on every call) -- corrected to
  `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`, redeployed as `agentic-ai-00015-bfs`.
  Verification is **partial**: `gatekeeper_node`s span and the new metric are confirmed live
  (including recording correctly on failure), but `research_node`/`writer_node`/`verifier_node`/
  the MCP span could not be exercised this session -- the shared OpenRouter key's *daily*
  free-model quota was already exhausted by the time of the last attempt (confirmed directly
  against OpenRouter's own `/api/v1/auth/key`, not inferred). See `AGT-021`s Resolution notes.
- **Grafana dashboards split into one per project, for real this time (`AGT-021`, 2026-10-04):**
  after trying (and reverting) a shared single-dashboard picker and a `conditionalRendering`
  per-panel approach earlier the same day, the project owner asked directly whether fully separate
  project-specific dashboards were possible -- yes, and simpler. `pav87rr` repurposed into
  `self-hosted-rag-platform -- Service Observability` (same uid/URL, hardcoded, no picker); a new
  `agentic-ai -- Service Observability` (`uid arxchd`) created with the cross-project panels plus
  AGT-021's new per-node/MCP/LLM-duration panels. Both live-verified via the render API (actual
  screenshots showing real data, not just that the dashboard JSON was accepted).
- **Service-status probe + query outcome/retry metrics added (`AGT-022`, 2026-10-04):** closed two
  gaps found comparing `agentic-ai`'s dashboard against `enterprise-rag-platform`'s and researching
  what a multi-agent system should track -- new `GET /health` (no auth/LLM calls), a Grafana Cloud
  Synthetic Monitoring check against it (`agentic-ai-health`, 5-min frequency), a query-outcome
  counter (`agentic_ai_query_outcome_total`, labeled completed/refused/error), and a
  verifier-retry histogram (`agentic_ai_verifier_retry_count`). Deployed as
  `agentic-ai-00020-9d6`. Found and fixed a real deployment-config bug along the way (unrelated to
  this ticket's own code): an earlier redeploy had left the service's env-var template pointing
  `OTEL_EXPORTER_OTLP_HEADERS` at a nonexistent secret and dropped the `LANGFUSE_*` vars entirely
  -- fixed via `gcloud run services update`, verified clean before redeploying; the live-serving
  revision was never actually affected, since every broken attempt failed before creating a new
  revision. Live-verified: the new probe is green, the error-outcome counter has a real sample,
  the retry histogram is correctly empty (no query has completed end-to-end yet), and all three
  new dashboard panels confirmed via the render API.
- **Frontend UX improvements added (`AGT-024`/`025`/`026`/`027`, 2026-10-04):** came from the
  project owner reviewing the live demo directly and asking five pointed questions. New
  `GET /documents` (proxies `enterprise-rag-platform`'s own `GET /documents`/ERP-103) lets a
  user see what's in their knowledge base before asking. Frontend gained an `/about` page, a
  documents panel, client-side-only `localStorage` query history (no new backend dependency --
  deliberate scope call, `agentic-ai` has no database of its own), and a session-expiry warning
  + draft-query preservation on forced logout. Deployed as `agentic-ai-00021-pmn`. **Real
  limitation found investigating true silent session refresh (`AGT-026`)**: can't be done without
  a real architecture change -- `StaticTokenAuth` deliberately has no password and can't refresh
  (`AGT-013`), so `agentic-ai`'s backend would have to start holding per-user refresh-token state
  it doesn't have today. Scoped down to UX-only (warning + draft preservation) instead of
  defaulting into that trust-model change.
- **Vercel URL rename attempted and blocked (`AGT-023`, 2026-10-04)**: tried the same fix
  `enterprise-rag-platform` used (`ERP-057`, `vercel alias set`) for a readable URL. The new
  alias (`bankar-ai-agentic-ai.vercel.app`) is gated by Vercel's own SSO deployment protection,
  for reasons not fully root-caused (both projects report identical protection settings).
  Disabling that protection is a real security-posture change, correctly blocked by the session's
  own safety guard pending the project owner's explicit say-so.  `agentic-ai-psi-mauve.vercel.app`
  remains the one working public URL.
- **Verification gap, named honestly**: `AGT-026`/`027`'s frontend features (session-expiry
  warning, draft preservation, history panel) were verified by code review, a clean build, and
  confirming the deployed JS bundle contains the feature strings -- not by an actual browser
  click-through, since no browser tool was available this session. Worth a real click-through next
  time one is.

## Known Gaps / Follow-ups

Tracked as tickets in `.ai/tickets/` rather than duplicated here in full — this section is a quick
index, read the ticket for detail.

Every `AGT-*` ticket (`001`-`020`) is resolved — `AGT-019` as **Won't Do** (see below), everything
else **Done**. See each ticket for detail; `AGT-008`/`AGT-009`/`AGT-012` (2026-10-03/04) landed
together with a real concurrency bug found and fixed along the way (`StaticTokenAuth` was unsafe
to share across concurrent different-user requests); `AGT-011` (2026-10-04) added
`scripts/run_eval.py`, a 4-case regression check against the real LLM, scoring to Langfuse;
`AGT-018`/`AGT-020` (2026-10-04) wired full observability (traces, logs, metrics) into Grafana
Cloud, reusing `enterprise-rag-platform`'s existing stack/token — three real bugs found and fixed
along the way, not assumed away: (1) `HttpOTLPSpanExporter()`'s default timeout resolving to 0 on
Cloud Run, fixed with an explicit `timeout=10`; (2) Cloud Run's own frontend injecting a
`traceparent` header into every request, making every span a child of an un-exported parent in
Google's internal tracing (`<root span not yet received>` on the dashboard) — fixed with a real
no-op propagator (`CompositePropagator([])` looked right but is actually broken for zero
propagators, returning `None` instead of a valid `Context` and crashing 12 unrelated tests before
the real fix was found); (3) trace export broke *again* after adding logs/metrics, while those
two worked immediately on the same redeploy — diagnosed as a payload-size-sensitive quirk
(FastAPI's attribute-heavy spans are a bigger POST body than log lines or metric points), fixed
by shrinking `BatchSpanProcessor`'s export batch size to 1. All three signals confirmed live via
direct queries against Tempo/Loki/Prometheus, not inferred from an absence of errors.

**Usage/eval tracking separation decided (2026-10-04):** Langfuse gets its own dedicated
`agentic-ai` project (separate keys, live-wired into Cloud Run, verified via the real API that
real observations land there) — not shared with `enterprise-rag-platform`'s project. OpenRouter
stays deliberately shared (the project owner's explicit call, not an oversight) — same account
and key as `enterprise-rag-platform`, usage/billing mixed. Grafana Cloud isn't a separate
"project" at all (that stack has no such concept) — `agentic-ai` is tagged with its own
`OTEL_SERVICE_NAME` within the one shared stack (`AGT-018`).

**`AGT-019` (CI/CD) decided: manual deploys only (2026-10-04).** The project owner's call after
reviewing the draft — `gcloud run deploy` stays the process, matching `enterprise-rag-platform`'s
own fully-manual deployment (SSH to the VM, `vercel deploy --prod` for its frontend). The drafted
`deploy` job was removed from `.github/workflows/ci.yml`; CI is back to a pure test/lint gate, the
same shape as `enterprise-rag-platform`'s own `ci.yml`. No GCP Workload Identity Federation
resources were ever created.

## Next Planned Work

Nothing open. Anyone demoing this project live needs their own `enterprise-rag-platform` account
with real content already ingested on it — that's the demo's only precondition, and it's a
per-demo setup step, not a standing gap in the project itself.
