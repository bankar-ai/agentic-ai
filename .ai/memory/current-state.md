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
  `enterprise-rag-platform` access token — via `Authorization: Bearer <token>` on the API, or the
  Gradio demo's new login accordion — and the whole request (Gatekeeper's exploratory search *and*
  Research's MCP subprocess call) runs as that user, seeing their own documents. `agentic-ai` never
  owns passwords. New `StaticTokenAuth` adapter + `RagPlatformAuthProvider` Protocol in
  `app/rag_client/auth.py`; the MCP subprocess receives the active identity per-call via a
  `RAG_PLATFORM_ACCESS_TOKEN` env override, never baked into its own `.env`. 16 new tests (70
  total), 92.62% coverage. **Live-verified against the real RAG platform deployment**, not just
  mocks: a real user-supplied token retrieved real content; a bad token failed cleanly.

## Known Gaps / Follow-ups

Tracked as tickets in `.ai/tickets/` rather than duplicated here in full — this section is a quick
index, read the ticket for detail.

**Blocking a real deployment** (in dependency order):
- `AGT-004` — no hosted-LLM provider exists yet; the live GCP VM (958MB RAM) cannot run Ollama.
- `AGT-005` — hosting target for this project's own service not yet decided (needs the project
  owner's input: co-host the existing VM vs. Cloud Run).
- `AGT-006` — no service user or ingested content exists against the *live* RAG platform yet, only
  a local one.
- `AGT-007` — the actual go-live (credentials, routing, tracker entry), blocked on the three above.

**Not blocking deployment, worth doing:**
- `AGT-008` — SSE/UI deliver the trace only after the graph completes, not per-step as the spec
  describes.
- `AGT-009` — `get_graph()`'s clients (httpx, auth) are rebuilt and never reused/closed per request.
- `AGT-010` — Writer/Verifier structured-output reliability with small local models is improved
  (prompt + retry fix, `917e8ef`) but not fully solved; may be moot once `AGT-004` lands if a
  hosted model proves more reliable.
- `AGT-011` — evaluation milestone (Langfuse datasets/scores), soft-blocked on
  `enterprise-rag-platform`'s `ERP-112`.
- `AGT-012` — small polish items from the final review (friendlier MCP error messages, an
  unclosed httpx client in the MCP server, inline-citation cross-checking).

**Done** (`AGT-002`, `AGT-003`, `AGT-013`, `AGT-014`, `AGT-015`) — see each ticket for detail.

## Next Planned Work

- Resolve the four open decisions in `.ai/memory/decisions-in-progress.md` that block `AGT-004`
  through `AGT-006` (OpenRouter account/model choice, hosting target, demo content) — these need
  the project owner's input, not further engineering.
- Then work the deployment chain (`AGT-004` → `AGT-005`/`AGT-006` → `AGT-007`) to get a real,
  live, demoable deployment.
