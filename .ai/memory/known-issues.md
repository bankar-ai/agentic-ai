# Known Issues

Living list of known problems, gaps, or rough edges in the project. Update in place — remove an
entry once it's resolved, don't just mark it done.

## Current

- **`mcp.search_knowledge_base` span still unexercised live**: `AGT-021`'s other three node spans
  (`research_node`/`writer_node`/`verifier_node`) and `AGT-022`'s retry metric are now fully
  verified (2026-10-04, after switching the primary model to `google/gemma-3-27b-it` — see
  `AGT-021`'s Final Verification notes), but that one successful query took the `web_fallback`
  route, not `kb`, so the MCP tool-call span specifically has never fired live. Not a bug — just
  needs one query that actually has KB content to retrieve (the test account used so far has none
  ingested). Re-verify next time a query against an account with real ingested content succeeds.
- **AGT-024/026/027's frontend features aren't browser-verified**: the about page, session-expiry
  warning, draft-query preservation, and history panel were verified by code review, a clean
  build, and confirming the deployed bundle contains each feature's strings — not by an actual
  click-through in a browser (none was available this session). Worth doing a real click-through
  next time one is.
- **AGT-033 (Backlog): web search intermittently returns zero results.** `ddgs`'s underlying
  search backends sometimes reject Cloud Run's outbound traffic (403/429 from Google, Mojeek,
  Brave specifically observed), causing a correct-but-unwanted refusal when it happens on both
  Research retry attempts. Not characterized for real frequency yet — see the ticket.
