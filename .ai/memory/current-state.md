# Current State

Living summary of what exists in this repository right now. Update it in place as things change.
History belongs in `.ai/sessions/`, not here.

## What Exists

- **Repo scaffolding** (2026-09-28): the `.ai/` operating system (tickets/adr/sessions/memory/templates,
  mirroring `enterprise-rag-platform`'s structure), `CLAUDE.md`, and a `docs/architecture.md` skeleton.
- **Design spec** (2026-09-28): `docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md`.
  **Implementation plan**: `docs/superpowers/plans/2026-09-28-agentic-rag-orchestration.md` (17 tasks).
- **The agentic RAG orchestration system is implemented and merged to `main`** (2026-09-30, PR #1
  at `bankar-ai/agentic-ai`). All 17 plan tasks are done and the final whole-branch review findings
  are fixed. Components:
  - `app/rag_client/`: auth and retrieval clients for `enterprise-rag-platform`.
  - `app/mcp_server/`: MCP stdio server exposing `search_knowledge_base`. It lives in this repo,
    which resolves the earlier open question about where the server should go.
  - `app/agents/`: Gatekeeper (route grading, with a code-level override from an empty KB to
    `web_fallback`), Research (KB evidence built in code from the MCP tool result, and a web
    fallback labeled `web`), Writer, and Verifier (checks drafts against the evidence that was
    actually retrieved and rejects fabricated citations in code). All agents use a local Ollama
    model through PydanticAI.
  - `app/graph/build.py`: the LangGraph state machine, with a bounded verify-and-retry loop
    (`MAX_VERIFICATION_RETRIES`) that ends in a refusal.
  - `app/api/router.py`: `POST /query` returns SSE (the whole trace once the graph finishes, not
    per step), and an outage surfaces as `event: error` or a 5xx.
  - `app/core/tracing.py`: Langfuse tracing that falls back to a no-op when there are no credentials.
  - `app/ui/app.py`: a two-tab Gradio demo (Direct RAG vs. Agentic RAG).
  - `tests/`: unit and integration tests with a fixture KB. None of them need a live Ollama
    instance or RAG platform.
- **Quality gate**: `uv run pytest -q --cov=app` (54 passed, 92% coverage), and
  `uv run ruff check app tests` and `uv run mypy app` are both clean.
- The README has setup and run instructions.

## Known Gaps / Follow-ups

- The SSE endpoint and the UI deliver the trace only after the graph completes. True per-step
  streaming (`graph.astream`) is a planned fast-follow.
- `get_graph()` rebuilds its httpx client, auth, and graph on every request, and the httpx
  client's lifecycle isn't managed. This is fine for a demo; a long-lived service would need an ADR.
- `docs/architecture.md` still says "scaffolding only" and needs a real architecture write-up.
- Gitleaks pre-commit/CI hooks (per `CLAUDE.md`) aren't set up yet.
- **Model choice is a hard compatibility gate, not a preference**: every agent needs a model with
  Ollama's `tools` capability. `gemma3:4b` (this machine's other pulled model) does NOT support
  tools and cannot run any agent here at all -- confirmed via a live 400 from Ollama
  (`does not support tools`). `qwen3:8b` and `granite4:tiny-h` (4.2GB, MoE, 7B total/1B active)
  both support tools and both work, but see the next point.
- **Writer/Verifier structured-output reliability with small local models is real but incomplete**
  (2026-09-30 live smoke test, `agentic-ai-service` user against a locally ingested test doc): both
  `qwen3:8b` and `granite4:tiny-h` initially failed 4/4 live attempts at the Writer step -- the
  model generated the correct, well-cited answer but replied in plain prose instead of making the
  required structured tool call. Root cause confirmed by isolated testing (`write_answer`/
  `verify_answer` called directly, bypassing the graph): it's a genuine model-reliability issue,
  not a bug in the agent code. Fixed partially: strengthened system prompts (explicit "you must
  call the tool") + raised `retries` from PydanticAI's default (1) to 3 for Writer and Verifier.
  `model_settings=ModelSettings(tool_choice="required")` was tried as a stronger fix and reverted
  -- PydanticAI raises `UserError` for it on agents with only `output_type` and no function tools
  (forcing tool_choice would exclude the output tool itself; that mechanism only applies alongside
  real function tools). Post-fix, format failures dropped to roughly 1/3 of live attempts -- a
  real improvement, not a full fix. This is now a documented characteristic of small (<10B) local
  models under this architecture, not a known bug to "finish fixing" -- a materially more reliable
  fix would mean a larger/more thoroughly tool-tuned model, which is a cost/quality tradeoff for
  whoever runs this, not something further prompt engineering alone will solve.
- While debugging the above, found and fixed an unrelated live-environment issue:
  `enterprise-rag-platform`'s Postgres/Redis Docker containers were stopped (37h) even though its
  uvicorn server was still running -- auth endpoints hung indefinitely as a result (read-only
  routes worked fine since they don't touch the DB). Not an `agentic-ai` bug; worth remembering if
  that platform's auth seems to hang again.
- A live service user (`agentic-ai-service@example.com`) is registered in the local
  `enterprise-rag-platform` instance with one small synthetic test document ingested, for smoke
  testing. Credentials saved to `C:\Users\Pankaj\.credentials\agentic-ai-credentials.md` per this
  portfolio's credentials policy, and to this repo's local (gitignored) `.env`.

## Next Planned Work

- Evaluation milestone: Langfuse datasets/scores, which depends on ERP-112 sequencing (see
  `decisions-in-progress.md`).
- Consider whether a materially more reliable model (see the Writer/Verifier gap above) is worth
  the disk/VRAM cost before treating this as demo-ready for a real interview walkthrough.
