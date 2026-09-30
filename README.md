# Agentic RAG Orchestration

A self-correcting agentic RAG accuracy layer, built as a portfolio project. It sits in front of
[`enterprise-rag-platform`](../enterprise-rag-platform)'s retrieval API and answers questions only
when it can ground the answer in evidence, falling back to a clearly-labeled web search or refusing
outright otherwise.

Four agents run as a LangGraph state machine, each with PydanticAI-typed structured I/O:

1. **Gatekeeper**: runs an exploratory knowledge-base search and grades it, choosing a route:
   `kb`, `web_fallback`, or `refuse` (Corrective RAG). If the exploratory search returns nothing,
   a `kb` choice is overridden to `web_fallback` in code.
2. **Research**: for `kb`, calls the `search_knowledge_base` tool on this repo's MCP server
   (`app/mcp_server/`) over stdio and builds source-labeled evidence directly from the tool's
   result. For `web_fallback`, it runs a web search, and that evidence is labeled `web`.
3. **Writer**: drafts a cited answer. It must say so explicitly when evidence came from the web.
4. **Verifier**: checks the draft against the evidence Research actually retrieved, not the
   Writer's own citations (Self-RAG). An ungrounded draft loops back to Research until
   `MAX_VERIFICATION_RETRIES` is reached, and then the system refuses instead of guessing.

Design: `docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md`.
Implementation plan: `docs/superpowers/plans/2026-09-28-agentic-rag-orchestration.md`.

## Runtime dependencies

- **Python 3.12** and [uv](https://docs.astral.sh/uv/).
- **Ollama** running locally with the configured model pulled (default `qwen3`):
  `ollama pull qwen3`. The agents use its OpenAI-compatible endpoint (`OLLAMA_BASE_URL`,
  default `http://localhost:11434/v1`).
- **`enterprise-rag-platform`** running and reachable at `RAG_PLATFORM_BASE_URL`, with a user
  account for `RAG_PLATFORM_EMAIL` / `RAG_PLATFORM_PASSWORD`. If the platform is down or rejects
  the credentials, the API returns an explicit `event: error` rather than an answer.
- **Langfuse** (optional): set `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` to trace each agent
  step. If they're left empty, tracing is a no-op.
- **Internet access**, only for the web-search fallback route.

## Setup

```bash
uv sync
cp .env.example .env   # then fill in the real RAG platform credentials
```

Configuration comes from environment variables, with `.env` as a fallback (see `.env.example` for
every recognized variable). Never commit `.env`. Environment variables alone work too: the MCP
server subprocess receives every `RAG_PLATFORM_*` variable from the parent process.

## Running

API (FastAPI, Server-Sent Events):

```bash
uv run uvicorn app.main:app --reload
curl -N -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is our refund policy?"}'
```

The response is a `text/event-stream` with one `event: step` per agent step, then
`event: result` (`final_answer`, `refused`), or `event: error` if the run failed. The stream
starts only after the graph finishes, so steps are not delivered one at a time as they happen.

Demo UI (Gradio, two tabs comparing single-pass Direct RAG with the full Agentic RAG trace):

```bash
uv run python -m app.ui.app
```

You don't need to start the MCP server yourself. The Research agent launches it on demand as a
subprocess (`python -m app.mcp_server.server`), using the same interpreter as the app.

## Development

```bash
uv run pytest -q --cov=app   # unit + integration tests (no live Ollama/RAG platform needed)
uv run ruff check app tests
uv run mypy app
```

Project conventions (tickets, ADRs, session logs, memory) live in `.ai/`. See `CLAUDE.md`.
