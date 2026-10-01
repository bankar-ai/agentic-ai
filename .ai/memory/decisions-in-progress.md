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
  own. See `AGT-011`.
- **OpenRouter account: shared with `enterprise-rag-platform`, or a separate one for this
  project?** (`AGT-004`) `enterprise-rag-platform` already has a funded OpenRouter account
  ($5 pay-as-you-go credit, per `gcp-deployment-tracker.md`). Reusing it means zero new cost/setup
  but mixes two projects' usage/billing on one account; a separate account is cleaner but needs its
  own funding. **Needs the project owner's call** — not decided here.
- **Which OpenRouter model for the deployed path** (`AGT-004`, `AGT-010`): needs a real research
  pass (same "don't trust cached knowledge for fast-moving LLM-API choices" rule this project has
  followed throughout) — specifically whether a `:free` tier model is reliable enough at
  tool-calling for this project's 4-agent structured-output needs, or a cheap-but-paid model is
  worth the (likely small) cost.
- **Hosting target for this project's own service** (`AGT-005`): co-host on the existing
  `rag-platform-host` VM (zero new resources, but adds load to an already-thin 958MB-RAM host) vs.
  Cloud Run (isolated, matches the portfolio's established "offload to serverless" pattern already
  proven for `enterprise-rag-platform`'s docling service, new resource to track). **Needs the
  project owner's call.**
- **What content to ingest for the live demo** (`AGT-006`): a product/demo decision — what should
  the live, deployed system actually be queried about in an interview walkthrough? Not yet decided;
  see `AGT-006`'s Notes for the shape of the decision (ideally content that can demonstrate the
  KB-hit, web-fallback, and refusal paths all in one coherent walkthrough).

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
