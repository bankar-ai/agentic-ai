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

**Multi-tenant, login required**: there is no anonymous or shared-demo-account path. Every caller
must supply their own already-issued `enterprise-rag-platform` session (`Authorization: Bearer
<token>` + `X-RAG-CSRF-Token` on the API, or the login box in the demo UI) and every query runs
against that account's own documents — see "Multi-tenant auth" below.

Design: `docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md`.
Implementation plan: `docs/superpowers/plans/2026-09-28-agentic-rag-orchestration.md`.

## Architecture

<img src="docs/diagrams/system-flow.svg" alt="A React frontend and API callers send REST and SSE requests to a FastAPI service on Cloud Run. The service checks the caller session, consults a Neon Postgres query cache, then runs a LangGraph state machine of four agents: Gatekeeper, Research, Writer, and Verifier, with a retry loop from Verifier back to Research. Research calls enterprise-rag-platform through an MCP stdio server, or a web search fallback. The agents call Ollama or OpenRouter. The service exports traces to Langfuse and traces, metrics, and logs to Grafana Cloud." width="100%" />

The agent graph in more detail, and the reasoning behind each choice, is in
[`docs/architecture.md`](docs/architecture.md).

## Runtime dependencies

- **Python 3.12** and [uv](https://docs.astral.sh/uv/).
- **An LLM provider**, chosen with `LLM_PROVIDER`:
  - `ollama` (default, local dev): a local Ollama with the configured model pulled (default
    `qwen3`): `ollama pull qwen3`. The agents use its OpenAI-compatible endpoint
    (`OLLAMA_BASE_URL`, default `http://localhost:11434/v1`). Small local models are unreliable at
    structured output; see "Known Model-Reliability Gap" in `docs/architecture.md`.
  - `openrouter` (used for the deployment): set `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` and
    `OPENROUTER_FALLBACK_MODEL`.
- **`enterprise-rag-platform`** running and reachable at `RAG_PLATFORM_BASE_URL`. Every caller
  brings their own account (see "Multi-tenant auth" below) — `RAG_PLATFORM_EMAIL` /
  `RAG_PLATFORM_PASSWORD` are only used as a local-dev fallback when running the MCP server
  standalone (`python -m app.mcp_server.server`, outside the API/UI's per-caller session flow). If
  the platform is down or rejects a session, the API returns an explicit `event: error` rather
  than an answer.
- **Langfuse** (optional): set `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` to trace each agent
  step. If they're left empty, tracing is a no-op.
- **Postgres** (optional): set `DATABASE_URL` to enable the server-side query cache and history
  (see "Query cache and history"). Unset, both query endpoints work without them.
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
`event: result` (`final_answer`, `refused`, `duration_seconds`), or `event: error` if the run
failed. The stream starts only after the graph finishes, so steps are not delivered one at a time
as they happen.

| Endpoint | Purpose |
|---|---|
| `POST /query` | Full agentic pipeline (SSE) |
| `POST /query/direct` | Single retrieval pass with no synthesis, for comparison against `/query` |
| `GET /documents` | The caller's own ingested documents (read-only proxy of the RAG platform) |
| `GET /history` | The caller's most recent queries, from the server-side history |
| `POST /auth/login` | Proxies a login to the RAG platform and returns `{access_token, csrf_token}` as JSON |
| `GET /health` | Liveness probe: no auth, no LLM or RAG-platform calls |

Every endpoint except `/health` and `/auth/login` requires the session headers described in
"Multi-tenant auth".

Local Gradio demo (not deployed; the frontend below has the same Direct vs. Agentic comparison via its mode toggle):

```bash
uv run python -m app.ui.app
```

Frontend (Vite + React + TypeScript, in `frontend/`): a login page, a query page with an Agentic
or Direct mode toggle, a collapsible agent trace, query history, a documents panel, and an `/about`
page. See [`frontend/README.md`](frontend/README.md) for local development. The session lives in
memory only, so a page refresh requires logging in again.

```bash
cd frontend && npm install && npm run dev
```

You don't need to start the MCP server yourself. The Research agent launches it on demand as a
subprocess (`python -m app.mcp_server.server`), using the same interpreter as the app.

## Multi-tenant auth

`agentic-ai` never owns passwords or a user database — it only ever forwards a session
`enterprise-rag-platform` already issued. **There is no anonymous or shared-demo-account
fallback**: a request without a valid session is rejected, not served against someone else's
documents. Two ways to supply one:

- **API**: add `Authorization: Bearer <rag-platform-access-token>` *and* `X-RAG-CSRF-Token:
  <csrf-token>` to `POST /query` (both required together). Get them either by calling the RAG
  platform's own `POST /auth/login` directly, or (AGT-016, needed by any browser-based client,
  since that platform's tokens arrive as httpOnly cookies no browser JS can read) via this
  project's own `POST /auth/login` — `{email, password}` in, `{access_token, csrf_token}` back,
  ready to drop straight into the headers above. Missing or malformed, `/query` returns
  `401 Unauthorized` before the graph ever runs.
- **Demo UI**: the "Log in" accordion above the two tabs calls the RAG platform's login for you
  and holds the resulting session for the rest of your browser session — nothing is written to
  disk. Both tabs refuse to query ("Please log in...") until you do.

An expired or rejected session surfaces as a clear error (API: `event: error` in the SSE stream;
UI: "please log in again"), never a silent wrong answer or someone else's data.

## Query cache and history

When `DATABASE_URL` is set, one `query_history` table does double duty: a 24-hour cache (the same
question from the same user in the same mode returns the stored answer instantly instead of
re-running the pipeline) and a durable audit log that backs `GET /history`. Rows are keyed on the
`sub` claim of the caller's session token, which is decoded but not signature-verified: it is used
only as a grouping key, never for an auth decision. Details are in `app/core/query_cache.py`.

## Observability

- **Langfuse**: per-agent tracing and eval scores (no-op without credentials).
- **OpenTelemetry**: spans per graph node and per MCP call, plus metrics for query duration,
  outcome (completed, refused, error), verifier retries, LLM latency, and token and cost usage.
  Exported with the standard `OTEL_EXPORTER_OTLP_*` variables (Grafana Cloud in the deployment);
  see `.env.example`.

## Deployment

The backend runs on Google Cloud Run (`Dockerfile`, scale-to-zero) and the frontend on Vercel, with
`CORS_ALLOWED_ORIGINS` set to the frontend's origin. Deploys are manual (`gcloud run deploy`,
`vercel deploy`); CI (`.github/workflows/ci.yml`) is a test and lint gate, with Gitleaks as a
secrets backstop. `develop` is the working branch and `main` holds what is deployed. Why this
project uses Cloud Run and OpenRouter rather than the RAG platform's VM and a local Ollama is in the
"Deployment" section of `docs/architecture.md`.

## Development

```bash
uv run pytest -q --cov=app   # unit + integration tests (no live Ollama/RAG platform needed)
uv run ruff check app tests
uv run mypy app
```

## Evaluation

```bash
uv run python scripts/run_eval.py
```

A small hand-built Q&A regression check (known-correct + known-should-refuse cases) against the
*real* configured LLM provider -- needs real credentials in `.env`, same as manual smoke testing.
Scores to Langfuse Cloud when `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` are set; otherwise runs and
reports locally with no remote calls. KB-route cases use a small fixture, not a live
`enterprise-rag-platform` account (there is no shared demo account -- see "Multi-tenant auth"
above); web-fallback and refusal cases exercise the real reasoning and a real web search.

Project conventions (tickets, ADRs, session logs, memory) live in `.ai/`. See `CLAUDE.md`.
