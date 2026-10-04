# Session — Per-Node Latency Instrumentation and Split Dashboards

Date: 2026-10-04
Tickets Touched: AGT-021

## Decisions

- Grafana dashboards split into one per project for real, superseding the same-day earlier
  revert. The project owner asked directly whether fully separate project-specific dashboards
  (no shared picker) were possible; confirmed yes and simpler than the picker/conditional-render
  approaches tried earlier in the day, since each dashboard's queries are hardcoded to one
  service instead of trying to make one dashboard behave differently per selection.
- `AGT-021`'s new panels live on the new `agentic-ai`-only dashboard, not the old shared one.
- Found a real `OPENROUTER_MODEL` misconfiguration (invalid slug, 404 on every call) while trying
  to live-verify AGT-021; fixed and redeployed rather than left broken, per explicit approval.
- Accepted partial live verification for AGT-021 rather than blocking on it further, once the
  remaining failures were confirmed to be a daily OpenRouter free-tier quota (external, not
  fixable by retrying) rather than a code bug.

## Implementation Summary

- `app/core/telemetry.py`: added `get_tracer()`/`get_meter()` helpers.
- `app/core/llm_metrics.py` (new): `measure_llm_call()` context manager recording
  `llm_generation_duration_seconds`, correctly on both success and failure (`finally` block).
- `app/graph/build.py`: each of the four node functions wrapped in its own OTel span.
- `app/agents/research.py`: the MCP `direct_call_tool` call wrapped in its own
  `mcp.search_knowledge_base` span.
- `app/agents/gatekeeper.py`/`writer.py`/`verifier.py`: each `agent.run()` call wrapped in
  `measure_llm_call(<agent name>)`.
- `tests/core/test_llm_metrics.py` (new): 2 tests, both using a real `InMemoryMetricReader`.
- Deployed as `agentic-ai-00014-n5c`, then `agentic-ai-00015-bfs` after the OpenRouter model-slug
  fix (`OPENROUTER_MODEL` updated via `gcloud run services update`).
- Grafana: `pav87rr` repurposed in place into `self-hosted-rag-platform -- Service Observability`
  (same uid/URL, `service_name` variable removed, all 20 panels hardcoded to that one service).
  New dashboard `agentic-ai -- Service Observability` (`uid arxchd`) created with the 5
  cross-project panels (log volume, traces, errors, logs, HTTP latency) hardcoded to `agentic-ai`,
  plus 3 new AGT-021 panels: per-node duration, MCP round-trip duration, LLM generation duration
  by agent. Both live-verified via Grafana's render API (actual screenshots, not just a
  successful API response).

## Blockers

None blocking. AGT-021's live verification is partial: `gatekeeper_node`'s span and the
`llm_generation_duration_seconds` metric are confirmed live (including on failure), but
`research_node`/`writer_node`/`verifier_node`/`mcp.search_knowledge_base` were never exercised
this session because the shared OpenRouter key's daily free-model quota was already exhausted
(confirmed directly against OpenRouter's `/api/v1/auth/key`, 51/50 used) by the time the 404 bug
was fixed. Resets the next UTC day.

## Next Steps

Re-verify the remaining three node spans and the MCP span once the OpenRouter quota resets —
send one live query, check Tempo for `research_node`/`writer_node`/`verifier_node`/
`mcp.search_knowledge_base`, confirm the "MCP knowledge-base round-trip duration" panel on the
`agentic-ai` dashboard stops showing "No data". Not treated as a blocking gap in the meantime
since the instrumentation code itself is reviewed, tested, and deployed.
