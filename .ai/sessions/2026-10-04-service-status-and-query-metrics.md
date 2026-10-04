# Session — Service Status Probe and Query Outcome/Retry Metrics

Date: 2026-10-04
Tickets Touched: AGT-022

## Decisions

- Scoped AGT-022 to observability only, matching AGT-021's own boundary: no change to graph
  behavior, retry logic, or refusal logic.
- Deliberately excluded retrieval-quality/groundedness-rate metrics from this ticket — `agentic-ai`
  doesn't own retrieval quality (that's `enterprise-rag-platform`'s), and groundedness is already
  a per-query Langfuse event; aggregating it into a dashboard metric is a separate, smaller
  follow-up if ever wanted.
- When a deployment-config bug blocked shipping (broken `OTEL_EXPORTER_OTLP_HEADERS` secret
  reference, dropped `LANGFUSE_*` vars), fixed the config rather than working around it or leaving
  it broken — matching this project's standing practice of fixing root causes found along the way.
- The fix required handling a real credential value; the sandbox's auto-mode classifier correctly
  blocked every way of doing that without explicit permission. Rather than attempting a workaround,
  stopped and asked the project owner, who switched the session to manual mode to authorize the
  one `gcloud` command needed.

## Implementation Summary

- `app/api/router.py`: new `GET /health` (no auth, no LLM/RAG-platform calls); `_event_stream`
  now calls `record_query_outcome()` on every exit path (all three `except` blocks plus normal
  completion) and `record_retry_count()` on completion/refusal.
- `app/core/query_metrics.py` (new): `agentic_ai_query_outcome_total` counter (labeled
  `completed`/`refused`/`error`), `agentic_ai_verifier_retry_count` histogram.
- `tests/core/test_query_metrics.py` (new, 2 tests) and `tests/api/test_router.py` (4 new tests:
  `/health`, and outcome/retry recording for completed/refused/error paths). Full suite: 116
  passed.
- Fixed a real deployment-config bug found while trying to ship this: an earlier redeploy attempt
  (chasing AGT-021's live verification) had left the Cloud Run service's env-var template pointing
  `OTEL_EXPORTER_OTLP_HEADERS` at a Secret Manager secret that was never created, and had dropped
  the `LANGFUSE_*` vars entirely (`--set-env-vars`/`--set-secrets` replace the whole set, not
  merge). The live-serving revision itself was never affected — every broken deploy attempt failed
  before `Creating Revision` completed. Fixed via
  `gcloud run services update --remove-secrets=OTEL_EXPORTER_OTLP_HEADERS` (separate call first,
  since removing a secret and adding the same key as a plain env var in one call conflicts), then
  `--update-env-vars`/`--update-secrets` to restore the original values; verified clean via
  `gcloud run services describe` before redeploying.
- Deployed as `agentic-ai-00020-9d6`.
- New Grafana Cloud Synthetic Monitoring check `agentic-ai-health` (id `4548`, 5-minute frequency,
  same shape as `vm-app-health`) against `/health`.
- Three new panels added to the `agentic-ai -- Service Observability` dashboard (`uid arxchd`):
  service up/down, query outcome rate, verifier retry count.

## Blockers

None remaining. Live-verified via direct Prometheus queries and the render API:
`probe_success{job="agentic-ai-health"}` = 1; `agentic_ai_query_outcome_total{outcome="error"}` =
1 (from a real failed live query — an expired test-session token); `agentic_ai_verifier_retry_count`
correctly empty, since no query has reached a completed/refused result yet this session (same
underlying OpenRouter-availability gap noted in `AGT-021`'s own resolution notes).

## Next Steps

Once a query completes end-to-end (pending OpenRouter's daily free-tier quota reset, per
`AGT-021`), re-check `agentic_ai_verifier_retry_count` and the "completed"/"refused" outcome
labels to confirm they populate as expected — not treated as a blocking gap in the meantime since
the code itself is reviewed, tested, and deployed.
