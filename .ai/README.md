# .ai/ — Repository AI Engineering Operating System

This directory is the working system that `CLAUDE.md` points to. It complements `docs/`:

- `docs/` holds durable reference documentation (architecture, engineering guidelines, roadmap).
- `.ai/` holds the operating system itself — work management, decisions, session history, and living project context.

## Subdirectories

- `tickets/` — work management, one file per ticket (prefix `AGT-`).
- `adr/` — accepted architecture decisions, one file per decision.
- `sessions/` — immutable per-session/milestone summaries.
- `memory/` — living, updated-in-place project context (current state, glossary, known issues, in-progress decisions), distinct from the immutable history in `sessions/`.
- `templates/` — shared templates (ticket, ADR, session).

This scaffolding mirrors the same `.ai/` operating system used in the sibling
`enterprise-rag-platform` (aka self-hosted-rag-platform) repo — see that repo's own `.ai/README.md`
and `CLAUDE.md` for the fuller rationale. Ported here on 2026-09-28 so this project starts with the
same discipline from day one rather than bolting it on later.
