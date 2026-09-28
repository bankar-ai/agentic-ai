# Session — Agentic RAG Orchestration Brainstorming

Date: 2026-09-28
Tickets Touched: None yet (design phase only; tickets to be created from the implementation plan)

## Decisions

- **Target role resolved**: Senior Python Developer with genuine GenAI/LLM backend ownership, per
  the signed-off "Next Role Requirements — Pankajkumar Bankar" (v3, Aug 2026). Non-negotiable:
  real multi-agent/agentic work (not single-shot LLM calls), protocols (MCP/A2A), technical
  leadership signal via documented architecture reasoning.
- **Standalone vs. integrated with `enterprise-rag-platform`**: reversed mid-session from
  "standalone" to "depends on it via MCP" — the agentic layer calls the RAG platform's retrieval
  API as a tool, reusing its existing FAISS/Ollama infra rather than rebuilding retrieval.
- **Use case pivoted twice** before landing: (1) generic "deep research agent" -> (2) rejected
  after user pushback that a simple "retrieve or don't" router doesn't need multi-agent and
  belongs in the RAG platform itself -> (3) settled on a **self-correcting agentic RAG accuracy
  layer** (Self-RAG / Corrective RAG / Adaptive RAG patterns), justified by the cyclic
  grade-retrieve-verify-retry loop, which a linear router genuinely cannot express.
- **Agent roles**: Gatekeeper/Retrieval-Grader, Research (multi-strategy retrieval), Writer,
  Verifier (groundedness check) — 4 agents, LangGraph state machine, PydanticAI for structured I/O.
- **Evaluation**: Langfuse Cloud (Hobby/free tier), same account as `enterprise-rag-platform`'s
  backlogged `ERP-112`, as a separate project within that account — not a new eval stack.
- Full design recorded in `docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md`.

## Implementation Summary

Design/brainstorming only — no code written. Spec document written and committed.

## Blockers

- `ERP-112` (Langfuse integration) is still Backlog in `enterprise-rag-platform`. This project's
  evaluation milestone assumes that ticket lands first (or in parallel) so the Langfuse account
  can be shared rather than duplicated — soft dependency, not a hard blocker on other work.

## Next Steps

- User to review the written spec (`docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md`).
- Once approved, invoke the writing-plans skill to turn the spec into an implementation plan.
- Open items deferred to planning time (see spec's "Open Items" section): ERP-112 sequencing,
  fixture KB content, where the MCP tool server for the RAG platform physically lives.
