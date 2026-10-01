"""Query API: runs the agent graph, then returns its step-by-step trace and final result as SSE.

Not incremental: the graph runs to completion first, and every trace step is then sent at once.
True per-step streaming (via `graph.astream`) is a planned follow-up.
"""

import json
import logging
import sys
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph

from app.agents.schemas import GraphState
from app.api.schemas import QueryRequest
from app.core.config import get_settings
from app.core.tracing import get_tracer
from app.graph.build import build_graph
from app.rag_client.auth import RagPlatformAuthError
from app.rag_client.retrieval import RagPlatformRetrievalError

_BEARER_PREFIX = "Bearer "


def extract_bearer_token(authorization: str | None) -> str | None:
    """Pull the token out of an `Authorization: Bearer <token>` header, or None if absent/malformed
    (AGT-013) -- a missing/malformed header is not an error here, it just means "use the fixed
    service account", so callers that never log in keep working exactly as before.
    """
    if authorization and authorization.startswith(_BEARER_PREFIX):
        return authorization[len(_BEARER_PREFIX) :]
    return None

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])

# `sys.executable`, not a bare "python": the MCP server subprocess must run under the same
# interpreter/venv as this app, not whatever `python` happens to be first on PATH.
MCP_SERVER_COMMAND = [sys.executable, "-m", "app.mcp_server.server"]


def get_graph(user_token: str | None = None):
    """Build the compiled orchestration graph from current settings.

    `user_token` (AGT-013): a logged-in end user's RAG-platform access token. When present, the
    Gatekeeper's own exploratory search runs as that user (via `StaticTokenAuth`) instead of the
    fixed service account -- consistent with Research's MCP subprocess call, which separately
    receives the same token through `GraphState` (see `app/graph/build.py`'s `research_node`).

    A thin, separately-mockable seam: tests patch this function rather than the graph internals.
    """
    settings = get_settings()
    import httpx

    from app.agents.llm import get_model
    from app.rag_client.auth import RagPlatformAuth, StaticTokenAuth
    from app.rag_client.retrieval import RagPlatformRetrievalClient

    model = get_model(settings)
    http_client = httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)
    auth = (
        StaticTokenAuth(user_token)
        if user_token
        else RagPlatformAuth(settings.rag_platform_base_url, settings.rag_platform_email, settings.rag_platform_password, http_client)
    )
    retrieval_client = RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)
    tracer = get_tracer(settings)
    return build_graph(model, retrieval_client, MCP_SERVER_COMMAND, settings.max_verification_retries, tracer)


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _event_stream(graph: CompiledStateGraph, query: str, user_token: str | None = None) -> AsyncIterator[str]:
    initial_state: GraphState = {
        "query": query, "user_access_token": user_token, "gatekeeper_decision": None, "evidence": [],
        "draft": None, "verification": None, "retry_count": 0, "final_answer": None, "refused": False,
        "trace": [],
    }
    # The 200 status and headers are already sent once this generator starts, so a failure here
    # can't become an HTTP error status -- it must surface as an explicit `error` event instead of
    # the stream ending silently with an empty body.
    try:
        final_state = await graph.ainvoke(initial_state)
    except (RagPlatformRetrievalError, RagPlatformAuthError) as exc:
        # Upstream response bodies stay in the server log, not in the client-facing message.
        logger.exception("RAG platform unavailable while answering query")
        yield _format_sse("error", {
            "type": type(exc).__name__,
            "message": "The knowledge base (enterprise-rag-platform) is unavailable or rejected authentication.",
        })
        return
    except Exception as exc:
        # Unexpected failures: report the type only; details stay in the server log.
        logger.exception("Agent graph failed while answering query")
        yield _format_sse("error", {"type": type(exc).__name__, "message": "Query failed; see server logs for details."})
        return
    for step in final_state["trace"]:
        yield _format_sse("step", step)
    yield _format_sse("result", {"final_answer": final_state["final_answer"], "refused": final_state["refused"]})


@router.post("/query")
async def query(request: QueryRequest, authorization: str | None = Header(default=None)) -> StreamingResponse:
    """Run a query through the agent graph and stream back its full trace and result as SSE.

    The trace is sent after the graph completes, not incrementally per step. The graph is built
    before the stream opens, so configuration errors (missing settings, etc.) propagate as a normal
    5xx response rather than a 200 with an empty body.

    AGT-013: an optional `Authorization: Bearer <rag-platform-token>` header runs the query as
    that logged-in end user (their own documents) instead of the fixed service account. Absent
    or malformed, behavior is unchanged from before this header existed.
    """
    user_token = extract_bearer_token(authorization)
    graph = get_graph(user_token)
    return StreamingResponse(_event_stream(graph, request.query, user_token), media_type="text/event-stream")
