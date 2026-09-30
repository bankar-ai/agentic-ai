"""Query API: streams the agent graph's step-by-step trace, then the final result, as SSE."""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import QueryRequest
from app.core.config import get_settings
from app.core.tracing import get_tracer
from app.graph.build import build_graph

router = APIRouter(tags=["query"])


def get_graph():
    """Build the compiled orchestration graph from current settings.

    A thin, separately-mockable seam: tests patch this function rather than the graph internals.
    """
    settings = get_settings()
    import httpx

    from app.agents.llm import get_ollama_model
    from app.rag_client.auth import RagPlatformAuth
    from app.rag_client.retrieval import RagPlatformRetrievalClient

    model = get_ollama_model(settings)
    http_client = httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)
    auth = RagPlatformAuth(settings.rag_platform_base_url, settings.rag_platform_email, settings.rag_platform_password, http_client)
    retrieval_client = RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)
    mcp_command = ["python", "-m", "app.mcp_server.server"]
    tracer = get_tracer(settings)
    return build_graph(model, retrieval_client, mcp_command, settings.max_verification_retries, tracer)


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _event_stream(query: str) -> AsyncIterator[str]:
    graph = get_graph()
    initial_state = {
        "query": query, "gatekeeper_decision": None, "evidence": [], "draft": None,
        "verification": None, "retry_count": 0, "final_answer": None, "refused": False, "trace": [],
    }
    final_state = await graph.ainvoke(initial_state)
    for step in final_state["trace"]:
        yield _format_sse("step", step)
    yield _format_sse("result", {"final_answer": final_state["final_answer"], "refused": final_state["refused"]})


@router.post("/query")
async def query(request: QueryRequest) -> StreamingResponse:
    """Run a query through the agent graph, streaming each agent's step live."""
    return StreamingResponse(_event_stream(request.query), media_type="text/event-stream")
