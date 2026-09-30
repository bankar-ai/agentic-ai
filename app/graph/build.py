"""LangGraph orchestration: Gatekeeper -> Research -> Writer -> Verifier, with a bounded
groundedness-correction loop (Verifier -> Research -> Writer, capped at `max_retries`).
"""

from langgraph.graph import END, StateGraph

from app.agents.gatekeeper import grade_retrieval
from app.agents.research import research
from app.agents.schemas import GraphState
from app.agents.verifier import verify_answer
from app.agents.writer import write_answer
from app.core.tracing import NoOpTracer, Tracer


def build_graph(
    model,
    retrieval_client,
    mcp_server_command: list[str],
    max_retries: int,
    tracer: Tracer | None = None,
):
    """Compile the agent orchestration graph. `model`/`retrieval_client` are threaded into every
    node via closures so each node stays a plain async function the tests can patch by name.
    `tracer` receives each node's step alongside the in-memory `state["trace"]` list, defaulting
    to a no-op so callers that don't pass one (or don't configure Langfuse) are unaffected.
    """
    tracer = tracer or NoOpTracer()

    async def gatekeeper_node(state: GraphState) -> GraphState:
        decision = await grade_retrieval(model, retrieval_client, state["query"])
        state["gatekeeper_decision"] = decision
        step = {"agent": "gatekeeper", "route": decision.route, "reasoning": decision.reasoning}
        state["trace"].append(step)
        tracer.trace_step(step)
        if decision.route == "refuse":
            state["refused"] = True
        return state

    async def research_node(state: GraphState) -> GraphState:
        result = await research(model, mcp_server_command, state["gatekeeper_decision"], state["query"])
        state["evidence"] = result.evidence
        step = {"agent": "research", "evidence_count": len(result.evidence)}
        state["trace"].append(step)
        tracer.trace_step(step)
        return state

    async def writer_node(state: GraphState) -> GraphState:
        draft = await write_answer(model, state["query"], state["evidence"])
        state["draft"] = draft
        step = {"agent": "writer", "text": draft.text}
        state["trace"].append(step)
        tracer.trace_step(step)
        return state

    async def verifier_node(state: GraphState) -> GraphState:
        verification = await verify_answer(model, state["draft"])
        state["verification"] = verification
        step = {"agent": "verifier", "grounded": verification.grounded}
        state["trace"].append(step)
        tracer.trace_step(step)
        if verification.grounded:
            state["final_answer"] = state["draft"].text
        else:
            state["retry_count"] += 1
            if state["retry_count"] >= max_retries:
                state["refused"] = True
        return state

    def route_after_gatekeeper(state: GraphState) -> str:
        return "end" if state["refused"] else "research"

    def route_after_verifier(state: GraphState) -> str:
        if state["final_answer"] is not None:
            return "end"
        if state["refused"]:
            return "end"
        return "research"

    graph = StateGraph(GraphState)
    graph.add_node("gatekeeper", gatekeeper_node)
    graph.add_node("research", research_node)
    graph.add_node("writer", writer_node)
    graph.add_node("verifier", verifier_node)

    graph.set_entry_point("gatekeeper")
    graph.add_conditional_edges("gatekeeper", route_after_gatekeeper, {"research": "research", "end": END})
    graph.add_edge("research", "writer")
    graph.add_edge("writer", "verifier")
    graph.add_conditional_edges("verifier", route_after_verifier, {"research": "research", "end": END})

    return graph.compile()
