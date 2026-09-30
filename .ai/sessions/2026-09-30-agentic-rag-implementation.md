# Session: Agentic RAG Orchestration Implementation

Date: 2026-09-30
Tickets Touched: None (work was tracked against the 17-task plan in
`docs/superpowers/plans/2026-09-28-agentic-rag-orchestration.md`, not against `AGT-` tickets)

## Decisions

- **The MCP tool server lives in this repo** (`app/mcp_server/`) and is launched by the Research
  agent as a stdio subprocess. This settles the "MCP tool server location" open item.
- **Adaptations to installed library versions**, each checked against the installed package:
  - `mcp` 2.x renamed `FastMCP` to `MCPServer`.
  - `pydantic-ai-slim` 2.52.0 has no `MCPServerStdio`, so the code uses FastMCP's
    `StdioTransport` wrapped in `MCPToolset`.
  - `OpenAIModel` was replaced by `OpenAIChatModel` + `OllamaProvider`.
  - In langfuse 4.x, `.event()` became `.create_event()`.
- **The MCP server's retrieval client is built lazily** (`lru_cache` accessor) so that importing
  the module doesn't require credentials.
- **Groundedness is anchored in retrieved data, not LLM output** (final-review fix I-4):
  - The KB Research path no longer calls an LLM. It calls `search_knowledge_base` directly via
    `MCPToolset.direct_call_tool` and builds `Evidence(source="knowledge_base", ...)` in code.
  - The Verifier takes the real retrieved evidence as input. A cited `(source, citation)` pair
    that isn't in that evidence is rejected before any LLM call, and the LLM check reads the real
    retrieved text rather than the Writer's copy of it.
- **The MCP subprocess gets `RAG_PLATFORM_*` env vars and the repo-root `cwd`** (I-3). The `mcp`
  SDK's `get_default_environment()` allow-list excludes those variables, so without this the KB
  route only worked when a `.env` file happened to be present. It runs under `sys.executable`.
- **Outages are surfaced, not swallowed** (I-2): the graph is built before the SSE stream opens,
  so config errors become a 5xx, and failures during a run produce an `event: error`.
- **Empty exploratory KB results always go to web fallback** (I-5): a code-level override stops
  an LLM `kb` choice with no results from using up every retry.

## Implementation Summary

- All 17 plan tasks are implemented. In order: scaffolding/config, RAG platform auth client,
  retrieval client, MCP tool server, agent schemas, Ollama provider, web search fallback,
  Gatekeeper, Research, Writer, Verifier, LangGraph graph, FastAPI SSE endpoint, fixture KB with
  E2E tests, Langfuse tracing, Gradio two-tab demo, and the quality gate.
- Every task was reviewed. Tasks 9 and 17 needed fix rounds.
- A final whole-branch review raised 7 Important findings (I-1 to I-7), and all were fixed in one
  wave: the ruff regression, outage surfacing, MCP subprocess env, evidence grounding, the empty-KB
  route override, docstring accuracy about "live" streaming, and these docs.
- Final gate: 54 tests passing at 92% coverage, with ruff and mypy both clean.

## Blockers

None. ERP-112 (the shared Langfuse account) is still a soft dependency, but only for the
evaluation milestone.

## Next Steps

- Final re-review, then merge `worktree-agentic-rag-orchestration` into `main`.
- Live smoke test against Ollama and `enterprise-rag-platform`. It hasn't been run yet; all
  verification so far used tests with mocks or `TestModel`.
- Fast-follow: true per-step SSE streaming via `graph.astream`.
- Write up `docs/architecture.md` properly and set up Gitleaks.
