# Decisions in Progress

Living list of open questions or trade-offs being considered but not yet resolved into an ADR.
Once a decision is made, remove it from here and write it up in `.ai/adr/`.

## Open

- **ERP-112 sequencing**: whether `enterprise-rag-platform`'s Langfuse integration ticket
  (currently Backlog) is completed before this project's evaluation milestone, or whether this
  project stands up the shared Langfuse account itself if ERP-112 is still pending when
  implementation reaches that point. Deferred to implementation planning
  (`docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md`, "Open Items").
- **MCP tool server location**: whether the MCP server wrapping `enterprise-rag-platform`'s
  retrieval API lives in this repo or is contributed back to `enterprise-rag-platform` as a
  reusable interface. Leaning toward this repo; final call at planning time.
- **Fixture knowledge base content**: what small, synthetic KB to use for integration/eval tests
  (not the RAG platform's real indexed documents) — not yet designed.

## Resolved (2026-09-28)

The three questions previously open here — target role/interview type, framework-vs-from-scratch,
and concrete use case/scope — were resolved in the 2026-09-28 brainstorming session. See
`docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md` for the full design and
`.ai/sessions/2026-09-28-agentic-rag-brainstorming.md` for the decision trail (including two use-case
pivots before landing on the final scope).

## Context Carried Over From `enterprise-rag-platform`

- Cross-project infra reference: `D:\github-projects\infrastructure-options.md` (see
  `enterprise-rag-platform`'s ADR-008) tracks hosting/compute/database/GPU/LLM-API options
  evaluated against a "live 2-3 months, then torn down" constraint shared by this project too —
  reference it rather than re-deriving hosting decisions from scratch.
- `enterprise-rag-platform`'s `ERP-112` (Langfuse integration, Backlog) is the source of the
  shared Langfuse Cloud account this project's evaluation layer depends on — see ERP-112 sequencing
  above.
