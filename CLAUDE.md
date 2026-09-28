# CLAUDE.md

Operational guide for Claude Code in this repository. This file stays short and is read every
turn — durable knowledge lives in `docs/` and `.ai/`.

## Repository Map

- `docs/architecture.md` — project overview, goals, philosophy, architecture principles, technology stack
- `.ai/` — the repository's AI Engineering Operating System: `tickets/` (work management, prefix `AGT-`), `adr/` (accepted architecture decisions), `sessions/` (immutable session history), `memory/` (living project context), `templates/`. See `.ai/README.md`.

This structure mirrors the sibling `enterprise-rag-platform` repo (`D:\github-projects\enterprise-rag-platform`) — see that repo's own `CLAUDE.md` for the fuller rationale behind each convention below. Ported here on 2026-09-28 rather than re-derived, per that repo's own precedent for shared portfolio conventions (see its ADR-008).

## Security

Never hardcode API keys, passwords, secrets, or tokens. Always load configuration from environment
variables. Never commit secrets to Git. Set up the same Gitleaks pre-commit + CI backstop pattern
`enterprise-rag-platform` uses (ADR-004 there) once this repo has real code and a remote.

Real credential storage follows the same cross-project policy as every other repo in this
portfolio: `D:\github-projects\credentials-policy.md`.

## Research Before Recommending

Before recommending a library, framework, or methodology for anything in a fast-evolving domain
(agent frameworks, LLM APIs, orchestration tooling, evaluation tooling), research current options
and benchmarks (e.g. via web search) rather than relying solely on prior/cached knowledge. Present
findings with sources, trade-offs, and a recommendation, then let the user decide.

## Git Workflow

Commit frequently. Each commit represents one logical change. Use Conventional Commits (`feat:`,
`fix:`, `docs:`, `refactor:`, `test:`, `chore:`). Never commit broken code.

## Tool Usage Rules

- Only use tools Claude Code explicitly exposes for the current session. Never assume the
  existence of tools, MCP servers, workflows, plugins, or IDE integrations.
- During planning: do not create, modify, or delete files.
- During implementation: only modify files explicitly requested by the task. Never create
  temporary files unless explicitly requested. Do not introduce new dependencies without
  explaining why and waiting for approval.

When uncertain, state assumptions clearly and ask for clarification instead of making
architectural assumptions.

## Planning & Workflow

Start most work in Plan Mode. Before implementing any feature:

1. Read this file and the relevant `docs/` and `.ai/` content.
2. Understand the current repository structure.
3. Interview the user to resolve ambiguity before proposing an approach.
4. Explain the implementation plan and wait for approval.
5. Implement only the approved scope.
6. Make verification explicit — state how the change was checked, don't just assert it works.
7. Summarize every modified file after implementation.
8. Suggest further improvements, but do not implement them without approval.

## Session & Context Continuity

Before assuming anything about prior work — especially at the start of a new conversation, or
after a long one — read `.ai/memory/current-state.md` and `.ai/memory/decisions-in-progress.md`
first. Treat them as authoritative over assumed continuity from chat history alone.

At natural checkpoints — finishing a feature, before a merge, end of a significant piece of work —
do two things, not one:
1. Write a new file in `.ai/sessions/` (`YYYY-MM-DD-<slug>.md`, using `.ai/templates/session.md`).
2. Update `.ai/memory/current-state.md` in place to match reality.

## AI Assistant Behaviour

Always: produce production-quality code, explain architectural decisions, use modern language
idioms and type hints where applicable, keep functions focused, minimize dependencies, write
maintainable code.

Never: generate tutorial-style code, introduce unnecessary complexity, create placeholder
implementations, create unused files, duplicate logic, invent APIs or library behavior.

If requirements are ambiguous, ask questions before implementing.

---

End of file.
