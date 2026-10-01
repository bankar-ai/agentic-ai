# Session — Deployment Planning

Date: 2026-10-01
Tickets Touched: AGT-002 through AGT-012 (created)

## Decisions

- Investigated what's actually needed to deploy this project to the portfolio's existing shared
  GCP infra (`enterprise-rag-platform`'s live deployment, per `gcp-deployment-tracker.md`), rather
  than assuming "point `.env` at the live URL" would be sufficient.
- **Key finding**: the existing GCP VM (`rag-platform-host`, `e2-micro`, ~958MB RAM) cannot run
  Ollama plus a tool-capable model — there's no realistic room, and that VM already had a real
  outage (`ERP-047` in the sibling repo) from a much smaller in-process memory spike. This confirms
  why `infrastructure-options.md` named OpenRouter (not local Ollama) as this project's LLM
  provider before any of this project's code existed — that call was correct and this project's
  own design hadn't yet caught up to it.
- Scoped the full deployment chain into ordered tickets (`AGT-004` hosted LLM provider → `AGT-005`
  hosting decision / `AGT-006` live service user+content (parallel) → `AGT-007` actual go-live),
  plus non-blocking improvement tickets for previously-known gaps that didn't yet have tickets
  (`AGT-002` Gitleaks, `AGT-008` true streaming, `AGT-009` client lifecycle, `AGT-010`
  Writer/Verifier reliability, `AGT-011` evaluation milestone, `AGT-012` final-review polish).
- Wrote a real `docs/architecture.md` (`AGT-003`, done same session) — it had said "scaffolding
  only" since before any implementation existed, despite the full system being built and merged.
- Four decisions identified as needing the project owner's input, not something to decide
  unilaterally: OpenRouter account sharing (reuse `enterprise-rag-platform`'s funded account vs.
  separate), which OpenRouter model to use, hosting target (co-host the VM vs. Cloud Run), and
  what content to ingest for the live demo. Recorded in `decisions-in-progress.md`, not decided
  here.

## Implementation Summary

Planning/documentation only — no application code changed. Files touched: `docs/architecture.md`
(rewritten), `.ai/tickets/AGT-002.md` through `AGT-012.md` (new), `.ai/memory/current-state.md`
and `decisions-in-progress.md` (updated to reference the new tickets/decisions).

## Blockers

The four decisions listed above block `AGT-004`/`AGT-005`/`AGT-006` specifically. Everything else
(`AGT-002`, `AGT-008` through `AGT-012`) is unblocked and can be picked up independently.

## Next Steps

- Project owner decides the four open items in `decisions-in-progress.md`.
- Then: `AGT-004` (hosted LLM provider) first, since both `AGT-005` and the practical value of
  `AGT-006` depend on it being done first (no point registering live demo content against a
  deployment target that can't yet run without local Ollama).
