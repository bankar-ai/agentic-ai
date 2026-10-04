# Decisions in Progress

Living list of open questions or trade-offs being considered but not yet resolved into an ADR.
Once a decision is made, remove it from here and write it up in `.ai/adr/`.

## Open

None currently.

## Resolved

- **ERP-112 sequencing** (2026-10-04, `AGT-011`): resolved by the project owner creating a
  dedicated `agentic-ai` project in the same Langfuse account/org as `enterprise-rag-platform`'s
  own, with its own key pair — not waiting on `ERP-112`, and not sharing a single project either.
  Live-verified that real observations land scoped to `agentic-ai` only.

- **Whether anonymous visitors get a shared demo account** (2026-10-01, `AGT-006`): no. The
  project owner rejected ingesting demo content under a shared service account; there is no
  anonymous path at all now, so this also makes "what content to ingest for the demo" moot — every
  caller demos against their own already-ingested `enterprise-rag-platform` content.

- **OpenRouter account and model choice** (2026-10-01, `AGT-004`; key ownership revised
  2026-10-04): originally reused `enterprise-rag-platform`'s existing funded OpenRouter API key
  rather than a separate account/Workspace (Workspace creation is dashboard-only, no unattended
  API — not worth blocking on). **2026-10-04**: project owner generated `agentic-ai` its own
  dedicated key in that same workspace (separates usage/cost attribution; does NOT grant a
  separate free-model daily quota — that cap is workspace-scoped, confirmed live). Model:
  `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` primary (corrected 2026-10-04, `AGT-021`
  — the original slug had drifted to one that no longer exists), `nvidia/nemotron-3.5-lightning:free`
  fallback.
- **Hosting target for this project's own service** (2026-10-01, `AGT-005`): Cloud Run, decided by
  the project owner — zero free-tier cost, isolated from `rag-platform-host`'s thin resource
  budget. Live at `https://agentic-ai-167676028188.us-central1.run.app`.
- **Target role/interview type, framework-vs-from-scratch, concrete use case/scope** (2026-09-28
  brainstorming session). See
  `docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md` for the full design and
  `.ai/sessions/2026-09-28-agentic-rag-brainstorming.md` for the decision trail (including two
  use-case pivots before landing on the final scope).
- **MCP tool server location** (2026-09-28, spec revision): lives in this repo, calling
  `enterprise-rag-platform`'s existing HTTP API as an external client — no changes to that repo
  required. Implemented in `app/mcp_server/server.py`.
- **Fixture knowledge base content** (implementation, Task 14): a small synthetic fixture
  (`tests/fixtures/sample_kb.py`) mirroring the real `RetrievedChunk` schema, used for
  integration-test mocking — not real ingested documents.

## Context Carried Over From `enterprise-rag-platform`

- Cross-project infra reference: `D:\github-projects\infrastructure-options.md` (see
  `enterprise-rag-platform`'s ADR-008) tracks hosting/compute/database/GPU/LLM-API options
  evaluated against a "live 2-3 months, then torn down" constraint shared by this project too —
  reference it rather than re-deriving hosting decisions from scratch.
- `enterprise-rag-platform`'s `ERP-112` (Langfuse integration, Backlog) is the source of the
  shared Langfuse Cloud account this project's evaluation layer depends on — see ERP-112 sequencing
  above.
