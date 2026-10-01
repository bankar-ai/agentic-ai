# Architecture

## Project Overview

Portfolio project demonstrating agentic AI fundamentals, built for **interview preparation** —
depth and correctness on core agent concepts (tool use, grounding/verification, multi-agent
orchestration, evaluation) for a Senior Python Developer role with genuine GenAI/agentic
ownership. See `docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md` for the
full design rationale and `.ai/sessions/2026-09-28-agentic-rag-brainstorming.md` for the decision
trail (including two use-case pivots before landing on the final scope).

## What This Is

A small, self-correcting agentic RAG accuracy layer sitting in front of
`enterprise-rag-platform`'s retrieval API — not a RAG system of its own. Four agents run as a
LangGraph state machine (Gatekeeper, Research, Writer, Verifier — see the sibling `README.md` for
the per-agent breakdown), following the Corrective RAG / Self-RAG pattern: grade retrieval
sufficiency, gather evidence, draft an answer, verify it against what was *actually* retrieved
(not what the Writer claims it cited), and loop back or refuse rather than guess. The RAG
platform's retrieval API is wrapped as a real MCP tool server (`app/mcp_server/`), called over
stdio by the Research agent — a genuine protocol round-trip, not a direct function call.

## Architecture Diagram

As of `AGT-004`/`AGT-006`/`AGT-013`/`AGT-014`, every piece below is built and live — there is no
longer a planned/not-yet-built tier. Auth is **mandatory**, not optional: there is no
anonymous/service-account fallback, so a caller must bring their own `enterprise-rag-platform`
login (`Authorization: Bearer <token>` + `X-RAG-CSRF-Token` on the API, or the Gradio demo's login
form) or the request is rejected with 401 before the graph ever runs.

```mermaid
flowchart TB
    Client["API caller / Gradio UI"]

    subgraph svc["agentic-ai service"]
        API["FastAPI POST /query<br/>(SSE response)"]
        Auth["Required user session<br/>(Authorization + X-RAG-CSRF-Token)<br/>401 if absent"]

        subgraph graph["LangGraph state machine"]
            GK["Gatekeeper<br/>grades retrieval, picks route"]
            RS["Research<br/>kb: MCP tool call<br/>web_fallback: web search"]
            WR["Writer<br/>drafts cited answer"]
            VF["Verifier<br/>checks against real evidence"]

            GK -->|kb / web_fallback| RS
            RS --> WR
            WR --> VF
            VF -->|ungrounded, retries left| RS
            VF -->|grounded| Done(["final answer"])
            GK -->|refuse| Refuse(["refusal"])
            VF -->|retries exhausted| Refuse
        end

        MCP["MCP tool server<br/>(stdio subprocess)<br/>search_knowledge_base"]
        Tracer["Langfuse tracer<br/>(no-op if unconfigured)"]
    end

    RagPlatform[("enterprise-rag-platform<br/>auth + retrieval API<br/>(caller's own account)")]
    LLM["LLM provider<br/>Ollama (local dev) /<br/>OpenRouter (deployed)"]
    Web[("Web search<br/>(ddgs, free)")]

    Client -->|query + required user session| API
    API --> Auth
    Auth -->|session valid| graph
    Auth -.->|session missing/invalid| Reject(["401 Unauthorized"])

    GK -.->|exploratory search, as the caller| RagPlatform
    RS --> MCP
    MCP -->|search_knowledge_base, as the caller| RagPlatform
    RS -.->|web_fallback only| Web

    GK -.-> LLM
    WR -.-> LLM
    VF -.-> LLM

    graph -.-> Tracer
    Tracer -.-> LangfuseCloud[("Langfuse Cloud")]
```

## Relationship to Sibling Projects

Part of a portfolio also including `enterprise-rag-platform` (self-hosted RAG platform) and a
future **LLMOps & Evaluation Platform** and **PEFT/LoRA** project. Shared cross-project references:

- `D:\github-projects\infrastructure-options.md` — hosting/compute/database/GPU/LLM-API options
  researched against a "live cheaply for a bounded window, then tear down" constraint shared by
  every project in this portfolio (see `enterprise-rag-platform`'s ADR-008). This document already
  named **OpenRouter** as the pick for this project's hosted LLM inference, before this repo had
  any code — see "Deployment" below for why that call was correct.
- `D:\github-projects\gcp-deployment-tracker.md` — what's actually running for
  `enterprise-rag-platform`'s live test deployment (the GCP VM, Neon, Upstash, Modal, Grafana
  Cloud). This project's own deployment entries will be added there, not duplicated here.
- The future LLMOps & Evaluation Platform is intended to be a standalone service this project can
  integrate with as a client, not something built bespoke here — see
  `enterprise-rag-platform/docs/architecture.md`'s 2026-09-06 note for the full constraint.

## Technology Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12, `uv` |
| Orchestration | LangGraph (cyclic state machine — the correction loop is the reason this isn't a simpler linear framework) |
| Structured I/O | PydanticAI |
| Tool protocol | MCP (`search_knowledge_base`, wrapping `enterprise-rag-platform`'s retrieval API) |
| Backend | FastAPI, Server-Sent Events |
| Demo UI | Gradio (two tabs: Direct RAG vs. Agentic RAG) |
| LLM inference (local dev) | Ollama — see "Known model-reliability gap" below |
| LLM inference (deployment) | OpenRouter (planned — `AGT-004`; local Ollama isn't viable on the deployment target, see "Deployment") |
| Evaluation/tracing | Langfuse Cloud (Hobby tier), sharing `enterprise-rag-platform`'s account once `ERP-112` lands there; no-op fallback when unconfigured |
| Testing | Pytest, ruff, mypy |

## Known Model-Reliability Gap

Small local models (tested: `qwen3:8b`, `granite4:tiny-h`) generate correct, well-cited answers
but sometimes reply in plain prose instead of making the structured tool call PydanticAI needs —
confirmed via live testing, not a code defect (see `.ai/memory/current-state.md` for the full
diagnosis). Mitigated (stronger prompts + raised retry budget), not eliminated. This is a hard
constraint of small (<10B) local models under this architecture, not something further prompt
engineering alone fixes — a materially more reliable fix means a larger or more thoroughly
tool-tuned model, which is a cost/quality tradeoff, not a bug to close out.

## Deployment

**The existing `enterprise-rag-platform` GCP VM (`rag-platform-host`) cannot run this project's
agents as designed.** It's an `e2-micro` with ~958MB total RAM, already thin enough that the RAG
platform itself had a real outage (`ERP-047`) from an in-process parser needing ~4GB and had to
move that work to Cloud Run. Ollama plus any tool-capable model (minimum observed: `granite4:tiny-h`
at 4.2GB on disk, several GB resident at runtime) has no realistic room there. This is exactly why
`infrastructure-options.md` named OpenRouter — not local Ollama — as this project's LLM provider
before any of this project's code existed: hosted inference was always the right call for
anything beyond local dev on a real machine with a GPU.

Deploying this project for real therefore needs, in order:

1. A hosted-LLM model provider alongside the existing local-Ollama one (`AGT-004`) — OpenRouter,
   reusing `enterprise-rag-platform`'s already-funded account rather than provisioning a new one,
   pending confirmation that's acceptable (shared billing across two projects).
2. A hosting decision for *this* project's own service (`AGT-005`) — once it no longer needs to
   run Ollama itself, the service is just a thin FastAPI app plus a lightweight MCP subprocess, so
   it could co-habit the existing VM (simplest, zero new resources, but adds load to an already
   constrained host) or run on Cloud Run (isolated, matches the portfolio's established "keep the
   host thin, offload to serverless" pattern already proven for `enterprise-rag-platform`'s own
   docling service, free within Cloud Run's tier at this traffic scale). Not yet decided — see
   the ticket for the tradeoffs and `.ai/memory/decisions-in-progress.md`.
3. A registered service user and representative ingested content on the *live* RAG platform
   (`AGT-006`) — the current smoke-test user and single synthetic document only exist against a
   local dev instance (`localhost:8000`), not the live deployment.
4. Wiring the chosen host's credentials, routing (Caddy route or Cloud Run URL), and firewall
   rule if co-hosting, then recording all of it in `gcp-deployment-tracker.md` (`AGT-007`), per
   that doc's own established format — not duplicated here.

See `.ai/tickets/` for the full breakdown and current status of each piece.
