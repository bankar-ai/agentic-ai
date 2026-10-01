# Session — Secrets Hygiene, Multi-Tenant Auth, Architecture Diagram

Date: 2026-10-01
Tickets Touched: AGT-002 (done), AGT-003 (done, prior session), AGT-013 (done), AGT-014 (done),
AGT-015 (done)

## Decisions

- **Secrets first**: set up Gitleaks pre-commit + CI backstop (`AGT-002`), per `CLAUDE.md`'s
  Security section — this repo had no CI workflow at all before this. Full 36-commit history scan
  confirmed no secret has ever been committed.
- **Multi-tenant auth gap surfaced and closed**: a conversation question ("why can't it reuse the
  RAG platform's own login?") revealed `agentic-ai` had no end-user auth concept at all — every
  query used one fixed service account. Decided and implemented an additive fix (`AGT-013`/
  `AGT-014`): an optional per-request RAG-platform access token overrides the fixed account,
  threaded all the way through to the MCP subprocess (not just the API layer) via a
  `RAG_PLATFORM_ACCESS_TOKEN` env override set per-call. `agentic-ai` never owns passwords.
  Live-verified against the real RAG platform, not just mocked tests.
- **Architecture diagram** (`AGT-015`): Mermaid, not draw.io, since no GUI drawing tool is
  available in this environment to produce or verify a `.drawio` file reliably — Mermaid renders
  natively on GitHub and stays plain-text-reviewable.

## Implementation Summary

- `.pre-commit-config.yaml`, `.github/workflows/ci.yml` (new) — gitleaks + ruff + mypy + pytest
  with a 90% coverage gate, mirroring `enterprise-rag-platform`'s pattern.
- `docs/architecture.md` — Mermaid flowchart added.
- `app/rag_client/auth.py` — new `StaticTokenAuth` adapter + `RagPlatformAuthProvider` Protocol.
- `app/core/config.py` — new optional `rag_platform_access_token` setting.
- `app/mcp_server/server.py` — new `_build_auth`, prioritizes the per-call token over the fixed
  service account.
- `app/agents/research.py` — `_mcp_subprocess_env`/`_research_kb`/`research` all gained an
  optional `user_access_token` parameter, forwarded to the subprocess.
- `app/agents/schemas.py` — `GraphState` gained `user_access_token`.
- `app/graph/build.py` — `research_node` forwards `state["user_access_token"]`.
- `app/api/router.py` — new `extract_bearer_token`, `get_graph`/`_event_stream`/`query` all
  thread the token through.
- `app/ui/app.py` — new `login()` function, a login `Accordion` in `build_ui()`, both query
  functions accept and use `user_token`.
- 16 new tests across 7 test files (70 total, up from 54), 92.62% coverage.
- `.env.example`, `README.md` updated to document the new auth path.

## Blockers

None for this session's scope. The deployment chain (`AGT-004`–`AGT-007`) from the prior session
remains blocked on the project owner's decisions (OpenRouter model choice, hosting target, live
demo content) — see `decisions-in-progress.md`.

## Next Steps

- Resolve the deployment-chain decisions still open from the prior session.
- Consider whether `AGT-006`'s live-demo-content work should also register additional real users
  now that multi-tenancy exists, or keep one shared demo account for the interview walkthrough.
