# Agentic RAG Orchestration — Design Spec

Status: Approved for planning
Date: 2026-09-28

## Purpose

Portfolio project for interview preparation, targeting a **Senior Python Developer role with
genuine GenAI/LLM backend ownership** (per the signed-off "Next Role Requirements — Pankajkumar
Bankar", v3, Aug 2026, provided in conversation). That doc requires, as non-negotiable "must
include" items:

- Real GenAI/LLM engineering (RAG, agents, prompt engineering) in production services, not a
  legacy backend with no AI component
- **Agentic AI / multi-agent ecosystem work** — agent orchestration, multi-agent systems,
  protocols like MCP/A2A — explicitly not single-shot LLM calls
- Technical leadership scope (architecture input, code review judgment) — demonstrated here via
  documented, defensible design decisions (this spec, ADRs), not just working code

This project is scoped to satisfy those requirements directly, alongside the existing
`enterprise-rag-platform` project (RAG retrieval engine) and the still-hypothetical LLMOps &
Evaluation Platform.

## Relationship to `enterprise-rag-platform`

This project **depends on `enterprise-rag-platform`** at runtime: it calls that platform's
retrieval API as a tool via MCP. It does not reimplement retrieval, indexing, or ingestion.

This is a deliberate dependency (not a fallback-tolerant integration) — demos require the RAG
platform to be running. Confirmed acceptable given both projects share the portfolio's
"live cheaply for a bounded window, then tear down" deployment pattern
(`D:\github-projects\infrastructure-options.md`).

## What This Project Is — and Isn't

**Is:** an agentic correction/accuracy layer on top of RAG retrieval — decomposition, retrieval
quality grading, multi-strategy retrieval, groundedness verification, and bounded self-correction
loops, following the published **Self-RAG / Corrective RAG (CRAG) / Adaptive RAG** patterns.

**Isn't:** a simple router that decides "retrieve or don't" — that pattern is a single agent with
conditional tool-calling, and belongs inside `enterprise-rag-platform` itself, not as a separate
project. The reason this warrants a standalone multi-agent system is the **cyclic correction
loop** (retrieve → grade → reformulate-if-weak → generate → verify → retry-or-refuse), which is
qualitatively different from a linear pipeline and is what genuinely requires distinct agent roles
and a graph-based orchestrator rather than one tool-calling agent.

## Agents & Responsibilities

| Agent | Responsibility | Notes |
|---|---|---|
| **Gatekeeper / Retrieval-Grader** | Grades retrieved evidence quality/relevance. Decides: answer from trusted KB, fall back to web search (flagged as external, per CRAG), or refuse outright. | The guardrail — decides what gets answered at all. |
| **Research** | Retrieves evidence. Chooses retrieval strategy (keyword / semantic / chunk-level, each exposed as a distinct MCP tool against `enterprise-rag-platform`), per the A-RAG finding that strategy choice (not just flat retrieval) meaningfully improves accuracy. Falls back to web search only when the Gatekeeper flags KB evidence as insufficient. | Multi-strategy retrieval is exposed as separate tools, not a single opaque "search" call. |
| **Writer** | Synthesizes a cited answer from gathered evidence. Preserves source labeling (trusted KB vs. flagged external) in the output — never presents web-fallback evidence as if it were KB-grounded. | |
| **Verifier** | Checks each claim in the draft against retrieved sources (groundedness check, Self-RAG-style reflection). Unsupported claims trigger a loop back to Research; exhausted retries trigger refusal rather than shipping an ungrounded answer. | |

## Orchestration (LangGraph state machine)

```
query -> Gatekeeper (grade initial retrieval)
           |- sufficient KB evidence -> Research (multi-strategy KB retrieval) -> Writer
           |- insufficient -> Research (web fallback, flagged) -> Writer
           `- out of scope / low confidence -> refuse (no Writer call)

Writer -> Verifier
           |- grounded -> return answer (streamed via SSE)
           `- unsupported claims -> loop back to Research (bounded retries, max 2)
                                      -> still ungrounded after retries -> refuse, don't guess
```

Framework: **LangGraph** — chosen for explicit cyclic state and conditional routing, matching the
correction-loop shape above; a linear chain framework would not naturally express the
retry/refuse branches.

Structured I/O: **PydanticAI** for agent boundaries and tool outputs — validated, typed messages
between agents and tools rather than free-text parsing. Matches the specific tooling named in the
target role's JDs.

## Protocols

- **MCP**: `enterprise-rag-platform`'s retrieval API is exposed as an MCP tool server, with
  keyword/semantic/chunk-level retrieval as distinct tools.
- **A2A-style handoff**: structured (Pydantic) messages between Gatekeeper -> Research -> Writer
  -> Verifier, carrying evidence, confidence scores, and source labels — not raw text.

## Evaluation

**Langfuse Cloud (Hobby tier, free)** — same account as `enterprise-rag-platform`'s
`ERP-112` (LLM-level observability, currently Backlog there), as a **separate project** within
that account, per ERP-112's own notes anticipating this repo. Self-hosting Langfuse is out of
scope (requires 2-4 CPU / 4-16GB RAM, incompatible with this portfolio's thin-host budget
constraint).

Each agent hop is traced: Gatekeeper decisions (grade + rationale), Research tool calls and
strategy chosen, Verifier groundedness verdicts, refusal outcomes. This is the project's answer to
the target role's "AI evaluation pipelines... traceability and auditability of AI behavior"
requirement.

**Sequencing dependency, not a design gap:** `ERP-112` is Backlog in `enterprise-rag-platform` as
of this writing. Confirmed with the project owner that ERP-112 will be completed (Langfuse account
+ RAG-platform instrumentation) before or alongside this project's evaluation work, so this
project's Langfuse setup reuses that account rather than standing one up independently. The
implementation plan should treat ERP-112 as a soft prerequisite for this project's evaluation
milestone, not block all other work on it.

## Error Handling & Guardrails

- Bounded retry loops: Research<->Verifier correction cycle capped (max 2 retries) — no infinite
  looping.
- Explicit refusal is a valid, traced outcome, not a failure state to hide or work around.
- External (web-fallback) evidence is always labeled distinctly from trusted KB evidence in the
  final answer — never silently merged.

## Serving

- **FastAPI** `POST /query`, streaming the agent trace (plan/grading/retrieval/verification steps,
  not just the final answer) via Server-Sent Events — doubles as a stronger interview demo and as
  the natural hook for evaluation tracing.
- **Demo UI lives in this repo, not `enterprise-rag-platform`**, deliberately: this project
  consumes the RAG platform as a decoupled service over MCP, and the two systems staying
  independently deployable (not merged into one UI) is itself part of what the project
  demonstrates. Two tabs:
  - **Tab 1 — Direct RAG**: calls `enterprise-rag-platform`'s plain query endpoint directly, shows
    the single-pass answer with no correction loop.
  - **Tab 2 — Agentic RAG**: the same question through the full
    Gatekeeper→Research→Writer→Verifier flow, streaming each step live via the SSE endpoint above.
  - Side-by-side, this *is* the answer to "what does agentic add over plain RAG" — shown, not
    explained.
  - MVP: minimal **Gradio** app (same tool already used in `enterprise-rag-platform`, no new
    dependency to justify), rendering the live trace as a step-by-step text/card log (e.g.
    "Gatekeeper: KB evidence sufficient → Research: semantic search → Verifier: grounded ✓").
  - **Stretch goal, not MVP**: an animated flow-diagram view (nodes lighting up as each agent
    runs) — Gradio doesn't support custom graph animation well, so this would mean a small custom
    HTML/JS front-end instead. Revisit only once the core system works; do not let this block or
    scope-creep the MVP.
- **Ollama** for local/free LLM inference, matching the RAG platform's stack and this portfolio's
  zero-cost constraint.
- Deployment follows the shared portfolio pattern in `D:\github-projects\infrastructure-options.md`
  (thin always-on host, "live cheaply for a bounded window, then tear down") — stood up only when
  a live link is actually needed (e.g. a live interview stage), torn down otherwise.

## Testing

- Unit tests per agent, with mocked tool/LLM calls (Gatekeeper grading logic, Research strategy
  selection, Writer synthesis, Verifier claim-checking) — mirrors `enterprise-rag-platform`'s
  testing philosophy (pytest, high coverage bar).
- Integration tests for the full LangGraph flow against a small fixture knowledge base (covering:
  sufficient-KB path, web-fallback path, refusal path, groundedness-retry path).
- A small hand-built eval set (Q&A pairs with known-correct answers and known-should-refuse cases)
  to regression-test groundedness and refusal behavior over time — feeds into the Langfuse-tracked
  evaluation loop above.

## Technology Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 (matches `enterprise-rag-platform`) |
| Orchestration | LangGraph |
| Structured I/O | PydanticAI |
| Tool protocol | MCP |
| Agent-to-agent | A2A-style structured messages |
| Backend | FastAPI, Server-Sent Events for streaming |
| Demo UI | Gradio |
| LLM inference | Ollama (local, free) |
| Evaluation/tracing | Langfuse Cloud (Hobby tier), shared account with `enterprise-rag-platform` |
| Testing | Pytest |
| Package manager | uv (matches `enterprise-rag-platform`) |

## Open Items Deferred to Implementation Planning

- Whether ERP-112 (Langfuse setup in `enterprise-rag-platform`) is completed first, or this
  project's plan includes standing up the shared Langfuse account itself if ERP-112 is still
  pending when implementation starts.
- Exact fixture knowledge base content for integration/eval tests (small, synthetic, not the RAG
  platform's real indexed documents).
- Whether the MCP tool server for `enterprise-rag-platform` lives in this repo or is contributed
  back to `enterprise-rag-platform` itself as a reusable interface — leaning toward this repo,
  final call at planning time.
