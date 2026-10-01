# Session — Require RAG-Platform Login, Remove the Anonymous Demo-Account Path

Date: 2026-10-01
Tickets Touched: AGT-006

## Decisions

- The project owner rejected AGT-006's original plan (register a service user, ingest demo
  content so an anonymous visitor sees something in the KB-hit path). Explicit direction: "we will
  only allow the user to use this if he or she has the rag account" — no shared/anonymous demo
  account at all, ever. Multi-tenancy (`AGT-013`/`AGT-014`) becomes the *only* way in, not an
  optional nicety on top of a default account.

## Implementation Summary

- `app/api/router.py`: `get_graph()` now takes a mandatory `UserSession` (no `| None` fallback to
  `RagPlatformAuth`/the fixed service account). `POST /query` raises `HTTPException(401, ...)`
  when `extract_user_session()` returns `None`, before the graph is ever built.
- `app/ui/app.py`: `_get_retrieval_client()` likewise requires a real session.
  `run_direct_query`/`run_agentic_query` short-circuit with a "please log in" message instead of
  calling it when no session is present. Login accordion copy changed from "optional" to
  "required -- there is no demo account".
- Tests: added `test_query_endpoint_returns_401_when_not_logged_in` and
  `test_query_endpoint_does_not_call_get_graph_when_not_logged_in` (replacing the old
  "passes None to get_graph" test); added `test_run_direct_query_without_session_returns_login_required_message`
  and `test_run_agentic_query_without_session_returns_login_required_message`. 79 tests passing,
  ruff/mypy clean.
- `docs/architecture.md`'s diagram and `README.md` updated: auth is mandatory, not optional; the
  diagram no longer shows LLM/auth as "planned" (both are built) and now shows the 401 rejection
  path explicitly.
- `.ai/tickets/AGT-006.md` rewritten to describe the superseding decision and marked Done.
- Redeployed to the live Cloud Run service (`gcloud run deploy agentic-ai --source . ...`, same
  command as the original deploy) and live-verified: an unauthenticated `POST /query` now returns
  `401` against `https://agentic-ai-167676028188.us-central1.run.app`.
- Updated `D:\github-projects\gcp-deployment-tracker.md`'s `agentic-ai` entry to reflect that the
  live service no longer has any anonymous/service-account path.

## Blockers

None.

## Next Steps

None outstanding from this change. Anyone demoing this project live now needs their own
`enterprise-rag-platform` account with real content already ingested on it — that's the demo's
precondition now, not something `agentic-ai` provisions.
