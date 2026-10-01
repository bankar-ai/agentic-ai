# Session — Cloud Run Deployment, OpenRouter, and the ERP-116 Auth Rewrite

Date: 2026-10-01
Tickets Touched: AGT-004, AGT-005, AGT-007, AGT-010

## Decisions

- Branch workflow: `develop` for ongoing work, `main` reserved for what's actually deployed
  (mirrors `enterprise-rag-platform`'s existing convention).
- Hosting: Cloud Run (AGT-005's Option B) — zero free-tier cost, isolated from
  `rag-platform-host`'s thin resource budget.
- LLM provider: OpenRouter, reusing `enterprise-rag-platform`'s existing funded API key rather
  than a separate account/Workspace (Workspace creation is dashboard-only, not worth blocking on).
  Model: `nvidia/nemotron-3-nano-30b-a3b:free` primary, `nvidia/nemotron-3.5-lightning:free`
  fallback via PydanticAI's `FallbackModel`.

## Implementation Summary

- `app/agents/llm.py`: added `get_openrouter_model()` / `get_model()` provider selection
  (`LLM_PROVIDER=ollama|openrouter`), new `Settings` fields in `app/core/config.py`.
- New `Dockerfile` for Cloud Run (`uv sync --frozen --no-dev` at build time, venv used directly at
  runtime — `uv run` was found to re-sync and pull dev deps at container startup, defeating the
  build-time optimization).
- Deployed to Cloud Run via `--source .`; fixed an initial `Permission denied on secret` failure
  by granting `roles/secretmanager.secretAccessor` to the revision service account on both new
  secrets (`agentic-ai-rag-platform-password`, `agentic-ai-openrouter-api-key`), then redeployed
  successfully. Live at `https://agentic-ai-167676028188.us-central1.run.app`.
- **Major unplanned finding**: the first live query failed with a `pydantic_core.ValidationError`.
  Root-caused via `gcloud logging read` to the live `enterprise-rag-platform` deployment already
  running `ERP-116` (cookie + CSRF double-submit auth hardening) — a contract the local dev
  instance this project had been tested against did not reflect. `/auth/login`/`/auth/refresh`
  return `{"user_id", "csrf_token"}` only; access/refresh tokens arrive as httpOnly cookies; CSRF
  token must be echoed as `X-CSRF-Token` on state-changing requests; there is no
  `Authorization: Bearer` support at all in the live platform.
  Rewrote to match: `app/rag_client/schemas.py` (`AuthSession` replaces `TokenPair`),
  `app/rag_client/auth.py` (`RagPlatformAuth`/`StaticTokenAuth` now track a CSRF token, not a
  bearer token; cookies ride the shared `httpx.AsyncClient` cookie jar automatically),
  `app/rag_client/retrieval.py` (retry-once on 401 *and* 403 — a stale CSRF after a refresh
  elsewhere surfaces as 403), `app/agents/schemas.py` (`UserSession` replaces the old bearer-token
  field), `app/mcp_server/server.py`, `app/api/router.py` (`X-RAG-CSRF-Token` header), and
  `app/ui/app.py` (login flow reads the cookie jar after `/auth/login`). All affected tests
  rewritten to mock realistic `Set-Cookie` responses instead of bearer-token JSON bodies.
  Live-verified end-to-end against the real deployment after the fix.
- Verified OpenRouter's reliability empirically: 3/3 successful on the exact Writer task that was
  flaky (~1/3 format-failure rate) under local Ollama models — resolves `AGT-010`.
- Recorded the full deployment (resources, secrets, IAM grants, how-to-check/redeploy/teardown) in
  `D:\github-projects\gcp-deployment-tracker.md`.
- Updated tickets AGT-004, AGT-005, AGT-007, AGT-010 to Done with resolution notes; updated
  `.ai/memory/current-state.md` and `decisions-in-progress.md` to match.

## Blockers

None for this session's own scope. `AGT-006` (live service user + real ingested content) remains
the one open item before the deployment is fully demo-ready — explicitly out of scope here, since
it's a content/product decision independent of hosting or LLM provider.

## Next Steps

- `AGT-006`: register a service user against the live `enterprise-rag-platform` deployment, ingest
  real representative content, verify a real end-to-end query through the live Cloud Run service.
- Update `C:\Users\Pankaj\.credentials\agentic-ai-credentials.md` with the live-platform service
  account and the Cloud Run secret names (both reuse existing credential values).
- Commit this session's doc/ticket/memory updates to `develop`, then merge `develop` → `main` per
  the newly-established branch workflow.
