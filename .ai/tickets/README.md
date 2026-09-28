# .ai/tickets/

Purpose: work management. One file per ticket (e.g. `AGT-001.md`).

Use the template at `.ai/templates/ticket.md` to create new tickets.

Status lifecycle: `Backlog` -> `In Progress` -> `Done`. Tickets may declare a `Depends On` field
listing blocking ticket IDs.

## Category (optional field)

Ported from the sibling `enterprise-rag-platform` repo's convention:

- **Bug** — the code doesn't do what it was already supposed to do; a defect against the existing
  spec/design.
- **Improvement** — the code works exactly as designed; this is a new capability or a better
  version of an existing one, not a defect.
- **Lapse** — the code works exactly as designed, and nothing is "wrong" against that design, but
  the design itself missed a case that matters in practice. Distinct from a Bug (no spec is being
  violated) and from an Improvement (not optional polish — a gap worth closing).
