# Session — Standalone Frontend with a Real Login Page (Vercel)

Date: 2026-10-02
Tickets Touched: AGT-016, AGT-017

## Decisions

- User flagged a real gap: `enterprise-rag-platform` has a dedicated frontend (Vite + React + TS,
  deployed to Vercel, `ERP-043`) with its own login page; `agentic-ai` had only the Gradio demo's
  embedded login accordion. Direction: note it, create tickets, implement by priority, finish,
  report back.
- Split into two tickets since a frontend literally cannot exist without the first: `AGT-016`
  (backend login proxy) then `AGT-017` (the frontend itself + Vercel deploy).

## Implementation Summary

- **AGT-016**: `login_and_extract_session()` added to `app/rag_client/auth.py`, shared by the
  Gradio UI's `login()` and a new `POST /auth/login` route (`app/api/auth.py`, `{email,password}`
  in, `{access_token,csrf_token}` out). Needed because `enterprise-rag-platform`'s own
  `/auth/login` delivers tokens as httpOnly cookies a browser SPA can never read.
- **AGT-017**: scaffolded `frontend/` (Vite + React + TS, `npm create vite`), with a login page
  (`src/pages/LoginPage.tsx`), a query page (`src/pages/QueryPage.tsx`), an in-memory-only session
  context (`src/session.tsx`), and a thin API client (`src/api.ts`) that parses the batch-delivered
  SSE response from `POST /query`. `app/main.py` gained `CORSMiddleware` + a new
  `app/core/cors.py` (mirroring `enterprise-rag-platform`'s own `CORS_ALLOWED_ORIGINS` pattern).
  Had to add `extra="ignore"` to the main `Settings` class once a second settings class
  (`CorsSettings`) started sharing the same `.env` file — pydantic-settings' dotenv loader
  defaults to rejecting any key it doesn't recognize as one of its own fields.
- **Real bug found and fixed during integration testing, not part of either ticket's original
  scope**: `StaticTokenAuth` only set the `access_token` cookie, never the matching `csrf_token`
  cookie the live platform's CSRF double-submit check requires. Every forwarded per-user session
  (the API's own header path since `AGT-013`, the Gradio UI's login, and this new frontend) was
  failing every retrieval call with `403 Missing or invalid CSRF token`. Found via a direct curl
  reproduction against the live platform (isolating the exact cookie needed), fixed in
  `app/rag_client/auth.py`, confirmed live.
- A stale local Python process (running since 2026-09-18, unrelated to today's work) was found
  squatting on port 8000 during local testing, shadowing the real backend and returning a
  pre-`ERP-116` response shape that briefly looked like a regression. Not killed (unfamiliar,
  long-running, not mine to assume dead) — worked around by running the test backend on port 8001
  instead.
- Deployed `frontend/` to Vercel (`vercel link` + `vercel deploy --prod`; GitHub auto-connect on
  `link` failed, worked around with a direct CLI deploy) — live at
  `https://agentic-ai-psi-mauve.vercel.app`. Redeployed the Cloud Run backend with
  `CORS_ALLOWED_ORIGINS` set to that origin.
- **Live-verified end-to-end, exactly as the deployed frontend would call it**: CORS preflight,
  `POST /auth/login`, and `POST /query` (Gatekeeper -> web_fallback -> Writer -> Verifier ->
  grounded answer) all succeed from `https://agentic-ai-psi-mauve.vercel.app`'s origin against the
  live Cloud Run backend, live RAG platform, and OpenRouter.
- 86 tests passing (new: `tests/api/test_auth.py`, `tests/core/test_cors.py`; updated:
  `tests/rag_client/test_auth.py`), ruff/mypy clean. Frontend type-checks (`tsc -b`), lints
  (`oxlint`), and builds cleanly.

## Blockers

None.

## Next Steps

None outstanding from this work. `AGT-006`'s precondition still applies: whoever uses either UI
needs their own `enterprise-rag-platform` account with real content already ingested on it.
