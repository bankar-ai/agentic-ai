# Session — Frontend UX: About Page, Documents, History, Session UX

Date: 2026-10-04
Tickets Touched: AGT-023, AGT-024, AGT-025, AGT-026, AGT-027

## Decisions

- Query history (`AGT-027`) implemented as browser `localStorage` only, deliberately not a new
  backend database — `agentic-ai` has no database of its own today, and adding one for "see my
  past few queries" is a real infra decision not worth defaulting into without discussion.
- True silent session refresh (`AGT-026`'s original ask) was investigated and explicitly **not**
  built: `StaticTokenAuth` has no password and can't refresh by design (`AGT-013`, "agentic-ai
  never owns passwords"). Building real refresh would mean the backend starting to hold per-user
  refresh-token state, a trust-model change that's the project owner's call, not a default.
  Scoped down to UX-only: an expiry warning and draft-query preservation on forced logout.
- Disabling Vercel's SSO deployment protection (the one fix that would make the new readable URL
  work, `AGT-023`) was correctly refused by the session's safety guard as a security-weakening
  change. Did not pursue a workaround — left the ticket blocked and reported the finding, keeping
  the existing working URL as canonical.
- Named real verification gaps honestly rather than claiming full completion: `AGT-024`/`026`/
  `027`'s frontend features were verified by code review, a clean build, and confirming the
  deployed bundle contains the right strings — not by an actual browser click-through, since no
  browser tool was available this session.

## Implementation Summary

- `app/rag_client/documents.py` (new): `RagPlatformDocumentsClient`, mirroring
  `RagPlatformRetrievalClient`'s exact auth pattern (Cookie + X-CSRF-Token, refresh-once-on-
  401/403). New `GET /documents` on `app/api/router.py`, proxying `enterprise-rag-platform`'s own
  `GET /documents` (ERP-103).
- `frontend/src/pages/AboutPage.tsx` (new), routed at `/about`, linked from the login page and the
  query page.
- `frontend/src/history.ts` (new): `localStorage`-backed query history (capped at 20, append/
  delete/clear, all wrapped in try/catch) and draft-query save/restore across a forced logout.
- `frontend/src/jwt.ts` (new): client-side-only JWT `exp` decode (never trusted for anything but
  reading a timestamp for the UI warning).
- `frontend/src/pages/QueryPage.tsx`: wired in a documents panel, a history panel, and the
  expiry-warning banner; forced-logout path now saves the draft query first.
- `tests/rag_client/test_documents.py` (new, 4 tests) and 3 new tests in `tests/api/test_router.py`
  for the `/documents` endpoint. Full backend suite: 123 passed. Frontend: `tsc -b && vite build`
  and `oxlint` both clean (no new warnings).
- Deployed backend as `agentic-ai-00021-pmn` (then `-00022-zl6` for the CORS update), frontend via
  `vercel deploy --prod`.
- `vercel alias set` created `bankar-ai-agentic-ai.vercel.app`, matching `enterprise-rag-platform`'s
  own `ERP-057` precedent — but unlike that precedent, the new alias is gated by Vercel's SSO
  deployment protection. Root-caused as far as possible (both projects report identical
  `ssoProtection` settings; the difference isn't in that config) but not further pursued since the
  actual fix is a security-protection change requiring explicit authorization.

## Blockers

`AGT-023` (readable URL) is blocked on a project-owner decision: disable Vercel SSO protection for
`agentic-ai`, or accept `agentic-ai-psi-mauve.vercel.app` as the canonical URL.

## Next Steps

- Project owner decides `AGT-023`'s SSO-protection question.
- A real browser click-through of `AGT-024`/`026`/`027`'s features, next time a browser tool is
  available — ask a question, see it land in history, delete it; let a session sit past 25 minutes
  and confirm the expiry warning appears; let one expire fully and confirm the draft survives.
- `AGT-021`/`022`'s own deferred re-verification (OpenRouter daily quota reset) is still open,
  unrelated to this session's work.
