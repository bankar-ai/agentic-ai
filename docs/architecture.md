# Architecture

## Project Overview

Portfolio project demonstrating agentic AI fundamentals, built for **interview preparation** —
the goal is depth and correctness on core agent concepts (tool use, memory, planning, multi-agent
orchestration, evaluation) rather than solving a specific novel business problem. See
`.ai/memory/decisions-in-progress.md` for the open scoping questions (target role/interview type,
framework-vs-from-scratch, concrete use case) still to be resolved in the first real design
session.

## Relationship to Sibling Projects

Part of a portfolio also including `enterprise-rag-platform` (self-hosted RAG platform) and a
future **LLMOps & Evaluation Platform** and **PEFT/LoRA** project. Shared cross-project references:

- `D:\github-projects\infrastructure-options.md` — hosting/compute/database/GPU/LLM-API options
  researched against a "live cheaply for a bounded window, then tear down" constraint shared by
  every project in this portfolio (see `enterprise-rag-platform`'s ADR-008).
- The future LLMOps & Evaluation Platform is intended to be a standalone service this project can
  integrate with as a client, not something built bespoke here — see
  `enterprise-rag-platform/docs/architecture.md`'s 2026-09-06 note for the full constraint.

## Status

Scaffolding only as of 2026-09-28 — no architecture decisions have been made yet. This file will
be filled in once the first design/brainstorming session (scope, approach, tech stack) happens.
