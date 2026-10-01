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

from app.agents.schemas import GraphState, UserSession
from app.api.schemas import QueryRequest
from app.core.config import get_settings
from app.core.tracing import get_tracer
from app.graph.build import build_graph
from app.rag_client.auth import RagPlatformAuthError
from app.rag_client.retrieval import RagPlatformRetrievalError

_BEARER_PREFIX = "Bearer "


def extract_user_session(authorization: str | None, csrf_token: str | None) -> UserSession | None:
    """Build a `UserSession` from the request's headers, or None if either is absent/malformed
    (AGT-013) -- a logged-in caller needs BOTH `Authorization: Bearer <access-token>` and
    `X-RAG-CSRF-Token: <csrf-token>` (the platform's post-ERP-116 cookie+CSRF contract requires
    both; see `app/rag_client/auth.py`'s module docstring). Missing either is not an error here,
    it just means "use the fixed service account", so callers that never log in keep working
    exactly as before.
    """
    if authorization and authorization.startswith(_BEARER_PREFIX) and csrf_token:
        return UserSession(access_token=authorization[len(_BEARER_PREFIX) :], csrf_token=csrf_token)
    return None

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])

# `sys.executable`, not a bare "python": the MCP server subprocess must run under the same
# interpreter/venv as this app, not whatever `python` happens to be first on PATH.
MCP_SERVER_COMMAND = [sys.executable, "-m", "app.mcp_server.server"]


def get_graph(user_session: UserSession | None = None):
    """Build the compiled orchestration graph from current settings.

    `user_session` (AGT-013): a logged-in end user's RAG-platform session. When present, the
    Gatekeeper's own exploratory search runs as that user (via `StaticTokenAuth`) instead of the
    fixed service account -- consistent with Research's MCP subprocess call, which separately
    receives the same session through `GraphState` (see `app/graph/build.py`'s `research_node`).

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
        StaticTokenAuth(user_session.access_token, user_session.csrf_token, http_client, settings.rag_platform_base_url)
        if user_session
        else RagPlatformAuth(settings.rag_platform_base_url, settings.rag_platform_email, settings.rag_platform_password, http_client)
    )
    retrieval_client = RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)
    tracer = get_tracer(settings)
    return build_graph(model, retrieval_client, MCP_SERVER_COMMAND, settings.max_verification_retries, tracer)


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _event_stream(
    graph: CompiledStateGraph, query: str, user_session: UserSession | None = None
) -> AsyncIterator[str]:
    initial_state: GraphState = {
        "query": query, "user_session": user_session, "gatekeeper_decision": None, "evidence": [],
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
async def query(
    request: QueryRequest,
    authorization: str | None = Header(default=None),
    x_rag_csrf_token: str | None = Header(default=None),
) -> StreamingResponse:
    """Run a query through the agent graph and stream back its full trace and result as SSE.

    The trace is sent after the graph completes, not incrementally per step. The graph is built
    before the stream opens, so configuration errors (missing settings, etc.) propagate as a normal
    5xx response rather than a 200 with an empty body.

    AGT-013: optional `Authorization: Bearer <rag-platform-access-token>` + `X-RAG-CSRF-Token`
    headers (both required together) run the query as that logged-in end user (their own
    documents) instead of the fixed service account. Absent or malformed, behavior is unchanged
    from before these headers existed.
    """
    user_session = extract_user_session(authorization, x_rag_csrf_token)
    graph = get_graph(user_session)
    return StreamingResponse(_event_stream(graph, request.query, user_session), media_type="text/event-stream")
