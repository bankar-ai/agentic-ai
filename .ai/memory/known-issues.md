# Known Issues

Living list of known problems, gaps, or rough edges in the project. Update in place — remove an
entry once it's resolved, don't just mark it done.

## Current

- **AGT-021 live verification is partial**: `research_node`/`writer_node`/`verifier_node`/
  `mcp.search_knowledge_base` spans, and `AGT-022`'s `agentic_ai_verifier_retry_count` metric,
  haven't been exercised live — every query attempt has failed before reaching them, currently
  because the OpenRouter workspace's daily free-model quota is exhausted (shared across both
  `enterprise-rag-platform` and `agentic-ai`'s testing; a dedicated `agentic-ai` API key generated
  2026-10-04 does not get its own separate quota — confirmed live, the cap is workspace-scoped).
  Resets once per UTC day. Not a code bug; `gatekeeper_node`'s span and the `llm_generation_duration_seconds`
  metric are both confirmed working, including correctly on failure. Re-verify with one live query
  once the quota resets — see `AGT-021`/`AGT-022`'s own resolution notes.
