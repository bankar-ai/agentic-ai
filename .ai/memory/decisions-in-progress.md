# Decisions in Progress

Living list of open questions or trade-offs being considered but not yet resolved into an ADR.
Once a decision is made, remove it from here and write it up in `.ai/adr/`.

## Open

- **ERP-112 sequencing**: whether `enterprise-rag-platform`'s Langfuse integration ticket
  (currently Backlog) is completed before this project's evaluation milestone, or whether this
  project stands up the shared Langfuse account itself if ERP-112 is still pending. This project's
  own Langfuse tracer (`app/core/tracing.py`, built in implementation) already degrades gracefully
  to a no-op when credentials are absent, so this is no longer a blocker on anything — it's purely
  about whether the two projects end up sharing one Langfuse Cloud account or each stand up their
  own.

## Resolved

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
