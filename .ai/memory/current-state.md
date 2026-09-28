# Current State

Living summary of what exists in this repository right now. Update in place as state changes — do
not append history here (that belongs in `.ai/sessions/`).

## What Exists

- Repo scaffolding (2026-09-28): `.ai/` operating system (tickets/adr/sessions/memory/templates,
  mirroring `enterprise-rag-platform`'s structure), `CLAUDE.md`, `docs/architecture.md` skeleton.
- Design spec written and committed (2026-09-28):
  `docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md`. Scope: a self-correcting
  agentic RAG accuracy layer (Gatekeeper/Research/Writer/Verifier agents, LangGraph + PydanticAI,
  MCP against `enterprise-rag-platform`'s retrieval API, Langfuse Cloud evaluation sharing
  `enterprise-rag-platform`'s ERP-112 account). See `.ai/sessions/2026-09-28-agentic-rag-brainstorming.md`
  for the full decision trail. No application code yet.

## Next Planned Work

- User to review the written spec, then invoke writing-plans to produce an implementation plan.
- Open items to resolve at planning time: ERP-112 (Langfuse) sequencing dependency on
  `enterprise-rag-platform`, fixture KB content for tests, where the MCP tool server wrapping the
  RAG platform's retrieval API should live.
