# Session — Grafana Root-Span Fix, AGT-019 Decided Manual, AGT-020 Logs+Metrics

Date: 2026-10-04
Tickets Touched: AGT-018 (follow-up fix), AGT-019 (decision), AGT-020 (new, done)

## Decisions

- User reviewed the live Grafana dashboard and found every `agentic-ai` trace showing
  `<root span not yet received>` with a blank Service column — a real regression from what
  AGT-018 had verified as working. Diagnosed and fixed live rather than assumed intermittent.
- User decided: AGT-019 (CI/CD) stays manual-only, matching `enterprise-rag-platform`'s own fully
  manual deployment process. The drafted GitHub Actions deploy job was removed, not just left
  unmerged.
- User asked for the CI gate to mirror `enterprise-rag-platform`'s own `ci.yml` shape — confirmed
  it already did once the deploy job was removed (test/lint gate only).
- User asked for logs + metrics in addition to the traces AGT-018 already shipped — scoped as a
  new ticket (AGT-020) before implementing, per the standing "ticket first" instruction.

## Implementation Summary

- **Root-span fix (AGT-018 follow-up):** Cloud Run's own frontend (GFE) injects a `traceparent`
  header into every proxied request. OTel's default propagator extracted it, making every server
  span a child of a parent that lives only in Google's internal Cloud Trace — never exported to
  us, so Tempo waited forever for a root that would never arrive. Fixed with `_NoExtractPropagator`
  in `app/core/telemetry.py`, a real no-op `TextMapPropagator`. First attempt
  (`CompositePropagator([])`) looked like the obvious fix but is actually broken for the
  zero-propagator case — its `extract()` returns whatever `context` it was passed (`None` from
  FastAPI's ASGI middleware) instead of a valid `Context`, crashing 12 unrelated tests the moment
  it ran against real HTTP requests. Caught by the test suite before reaching production.
- **AGT-019:** removed the drafted `deploy` job from `.github/workflows/ci.yml` entirely. CI is
  back to a pure test/lint gate matching `enterprise-rag-platform`'s own shape. Ticket marked
  Won't Do with the full reasoning recorded.
- **AGT-020 (logs + metrics):** `app/core/logging_config.py` added (mirrors
  `enterprise-rag-platform`'s `TraceIdFilter` + OTLP `LoggingHandler` pattern exactly).
  `app/core/telemetry.py` extended with a `MeterProvider` + push-based
  `PeriodicExportingMetricReader`. No new dependencies needed — confirmed the OTLP log/metric
  exporter sub-packages were already present transitively before writing any code.
- **A real regression, diagnosed not hand-waved:** right after the AGT-020 redeploy, trace export
  broke again with the identical "read timeout=0" signature AGT-018 had already fixed — but logs
  and metrics, deployed in the same redeploy, worked immediately (confirmed via direct Loki and
  Prometheus API queries, not just "no error logged"). Same container, same export code path, two
  signals succeeding and one failing pointed at payload size: FastAPI's attribute-heavy spans
  produce a larger POST body per batch than log lines or metric points. Fixed with
  `BatchSpanProcessor(max_export_batch_size=1, export_timeout_millis=30000)`. Live-verified after
  redeploy: zero timeout errors across three real requests, fresh Tempo traces all showing
  `rootServiceName: "agentic-ai"`.
- All three signals (traces, logs, metrics) confirmed live via direct queries against Grafana
  Cloud's own backend APIs (Tempo `/api/search`, Loki `query_range`, Prometheus `query`) — real
  data returned each time, not inferred from the absence of errors.
- 108 tests passing, ruff/mypy clean.

## Blockers

None.

## Next Steps

None outstanding. Every ticket in the backlog (AGT-001 through AGT-020) is resolved — Done or,
for AGT-019, an explicit Won't Do.
