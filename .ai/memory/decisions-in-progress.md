# Decisions in Progress

Living list of open questions or trade-offs being considered but not yet resolved into an ADR.
Once a decision is made, remove it from here and write it up in `.ai/adr/`.

## Open

- **Target role/interview type**: is this project aimed at an AI/ML engineer role (deep agent
  architecture questions expected — tool-calling, memory, planning/ReAct, multi-agent
  orchestration, evaluation), a general backend/software engineer role (agentic AI as one topic
  among several), or a more specialized LLM/applied-AI research role? Changes how deep vs. broad
  the project needs to go.
- **Framework vs. from-scratch**: use an existing agent framework (LangGraph, CrewAI, AutoGen,
  etc.) to demonstrate familiarity with what's actually used in industry, or build core agent loop
  primitives from scratch to demonstrate first-principles understanding (often stronger for
  interviews, since it proves understanding rather than library usage)? Possibly both, at
  different depths.
- **Scope/use case**: no specific application domain has been chosen (the earlier
  "Agentic Insurance Assistant" framing was explicitly dropped in the sibling RAG repo's own
  history — insurance-domain framing removed in favor of "general-purpose", scope otherwise
  undecided). Needs a concrete first use case to build against, even if the deeper goal is
  demonstrating fundamentals rather than solving that specific problem.

## Context Carried Over From `enterprise-rag-platform`

- Purpose (confirmed by user, 2026-09-28): **interview preparation** — the project should
  demonstrate the fundamentals of agentic AI thoroughly enough to support technical interview
  discussion, not solve a novel business problem.
- Cross-project infra reference: `D:\github-projects\infrastructure-options.md` (see
  `enterprise-rag-platform`'s ADR-008) tracks hosting/compute/database/GPU/LLM-API options
  evaluated against a "live 2-3 months, then torn down" constraint shared by this project too —
  reference it rather than re-deriving hosting decisions from scratch.
- `enterprise-rag-platform`'s `docs/architecture.md` (2026-09-06 note) flags that a future
  **LLMOps & Evaluation Platform** project is meant to be a standalone, generalized platform other
  projects (including this one) integrate with as a client for tracing/evaluation, rather than each
  project rolling its own. Worth keeping in mind when this project's own evaluation/observability
  approach is designed — may be scoped as a stub/interim solution if LLMOps doesn't exist yet by
  the time this needs it.
