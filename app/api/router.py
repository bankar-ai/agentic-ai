"""Query API: runs the agent graph and streams its trace as SSE, one `step` event per agent as
it actually finishes (AGT-008: via `graph.astream(..., stream_mode="updates")`), followed by one
`result` event once the graph reaches an end state.
"""

import json
import logging
import sys
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph

from app.agents.direct_query import DirectQueryResult, run_direct_query
from app.agents.research import KnowledgeBaseUnavailable
from app.agents.schemas import GraphState, UserSession
from app.api.schemas import QueryRequest
from app.core.config import get_settings
from app.core.openrouter_budget import maybe_record_openrouter_budget
from app.core.query_metrics import (
    record_query_duration,
    record_query_outcome,
    record_retry_count,
)
from app.core.tracing import get_tracer
from app.graph.build import build_graph
from app.rag_client.auth import RagPlatformAuthError, StaticTokenAuth
from app.rag_client.documents import (
    DocumentListResult,
    RagPlatformDocumentsClient,
    RagPlatformDocumentsError,
)
from app.rag_client.retrieval import (
    RagPlatformRetrievalClient,
    RagPlatformRetrievalError,
)
from app.rag_client.shared_client import get_shared_rag_platform_client

_BEARER_PREFIX = "Bearer "


def extract_user_session(authorization: str | None, csrf_token: str | None) -> UserSession | None:
    """Build a `UserSession` from the request's headers, or None if either is absent/malformed
    (AGT-013/AGT-006) -- a logged-in caller needs BOTH `Authorization: Bearer <access-token>` and
    `X-RAG-CSRF-Token: <csrf-token>` (the platform's post-ERP-116 cookie+CSRF contract requires
    both; see `app/rag_client/auth.py`'s module docstring). There is no anonymous fallback: every
    caller must bring their own `enterprise-rag-platform` account, so a missing/malformed header
    here means the caller is not logged in, and the endpoint below rejects the request.
    """
    if authorization and authorization.startswith(_BEARER_PREFIX) and csrf_token:
        return UserSession(access_token=authorization[len(_BEARER_PREFIX) :], csrf_token=csrf_token)
    return None

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])

# `sys.executable`, not a bare "python": the MCP server subprocess must run under the same
# interpreter/venv as this app, not whatever `python` happens to be first on PATH.
MCP_SERVER_COMMAND = [sys.executable, "-m", "app.mcp_server.server"]


def get_graph(user_session: UserSession):
    """Build the compiled orchestration graph from current settings, scoped to `user_session`.

    `user_session` (AGT-013/AGT-006): a logged-in end user's RAG-platform session. There is no
    anonymous/service-account fallback -- every query runs as a real `enterprise-rag-platform`
    account, via `StaticTokenAuth`. The Gatekeeper's own exploratory search and Research's MCP
    subprocess call both use this same identity (see `app/graph/build.py`'s `research_node`).

    A thin, separately-mockable seam: tests patch this function rather than the graph internals.
    """
    settings = get_settings()

    from app.agents.llm import get_model
    from app.rag_client.auth import StaticTokenAuth
    from app.rag_client.retrieval import RagPlatformRetrievalClient
    from app.rag_client.shared_client import get_shared_rag_platform_client

    model = get_model(settings)
    # AGT-009: one client reused across every request, not a fresh one per call -- safe only
    # because StaticTokenAuth no longer stores per-user state on it (see app/rag_client/auth.py).
    http_client = get_shared_rag_platform_client()
    auth = StaticTokenAuth(user_session.access_token, user_session.csrf_token)
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
    # AGT-036: start of this generator to the final event -- the authoritative, server-side
    # duration (excludes client network overhead a browser-side stopwatch would include).
    start_time = time.monotonic()
    # The 200 status and headers are already sent once this generator starts, so a failure here
    # can't become an HTTP error status -- it must surface as an explicit `error` event instead of
    # the stream ending silently with an empty body. Any `step` events already yielded before the
    # failure stay sent -- that's the point of streaming: partial progress is still progress.
    final_state = initial_state
    try:
        async for chunk in graph.astream(initial_state, stream_mode="updates"):
            for node_state in chunk.values():
                final_state = node_state
                yield _format_sse("step", node_state["trace"][-1])
    except (RagPlatformRetrievalError, RagPlatformAuthError) as exc:
        # Upstream response bodies stay in the server log, not in the client-facing message.
        logger.exception("RAG platform unavailable while answering query")
        record_query_outcome("error")
        record_query_duration("error", "agentic", time.monotonic() - start_time)
        yield _format_sse("error", {
            "type": type(exc).__name__,
            "message": "The knowledge base (enterprise-rag-platform) is unavailable or rejected authentication.",
        })
        return
    except KnowledgeBaseUnavailable:
        # AGT-012: the MCP subprocess's own ToolError/MCPError, mapped to a legible type/message
        # instead of leaking "ToolError" (or similar) straight to the client.
        logger.exception("Knowledge-base MCP tool call failed while answering query")
        record_query_outcome("error")
        record_query_duration("error", "agentic", time.monotonic() - start_time)
        yield _format_sse("error", {
            "type": "KnowledgeBaseUnavailable",
            "message": "The knowledge base is temporarily unavailable. Please try again shortly.",
        })
        return
    except Exception as exc:
        # Unexpected failures: report the type only; details stay in the server log.
        logger.exception("Agent graph failed while answering query")
        record_query_outcome("error")
        record_query_duration("error", "agentic", time.monotonic() - start_time)
        yield _format_sse("error", {"type": type(exc).__name__, "message": "Query failed; see server logs for details."})
        return
    outcome = "refused" if final_state["refused"] else "completed"
    duration_seconds = time.monotonic() - start_time
    record_query_outcome(outcome)
    record_retry_count(final_state.get("retry_count", 0))
    record_query_duration(outcome, "agentic", duration_seconds)
    yield _format_sse("result", {
        "final_answer": final_state["final_answer"],
        "refused": final_state["refused"],
        "duration_seconds": duration_seconds,
    })


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness check for Grafana Cloud Synthetic Monitoring (AGT-022) -- deliberately does
    nothing but confirm the process is up: no auth, no LLM call, no RAG-platform round trip, so
    probing it every 5 minutes costs nothing against either's quota.
    """
    return {"status": "ok"}


@router.get("/documents")
async def documents(
    authorization: str | None = Header(default=None),
    x_rag_csrf_token: str | None = Header(default=None),
    limit: int = 50,
    offset: int = 0,
) -> DocumentListResult:
    """List the caller's own successfully ingested `enterprise-rag-platform` documents (AGT-025)
    -- lets them see what's actually in their knowledge base before asking a question. Read-only
    proxy of that platform's own `GET /documents`; no upload/delete capability here.
    """
    user_session = extract_user_session(authorization, x_rag_csrf_token)
    if user_session is None:
        raise HTTPException(
            status_code=401,
            detail="Log in with your enterprise-rag-platform account (Authorization + X-RAG-CSRF-Token headers) to use this service.",
        )
    settings = get_settings()
    auth = StaticTokenAuth(user_session.access_token, user_session.csrf_token)
    client = RagPlatformDocumentsClient(settings.rag_platform_base_url, auth, get_shared_rag_platform_client())
    try:
        return await client.list_documents(limit=limit, offset=offset)
    except (RagPlatformDocumentsError, RagPlatformAuthError) as exc:
        raise HTTPException(status_code=502, detail=f"enterprise-rag-platform is unavailable: {exc}") from None


@router.post("/query/direct")
async def query_direct(
    request: QueryRequest,
    authorization: str | None = Header(default=None),
    x_rag_csrf_token: str | None = Header(default=None),
) -> DirectQueryResult:
    """Run one retrieval pass and return the top chunk verbatim, no synthesis (AGT-034).

    The baseline the full Gatekeeper->Research->Writer->Verifier pipeline (`POST /query`) is
    compared against -- same auth contract, same shared retrieval logic as the local Gradio demo
    (`app/agents/direct_query.py`), just without the agent graph around it.
    """
    user_session = extract_user_session(authorization, x_rag_csrf_token)
    if user_session is None:
        raise HTTPException(
            status_code=401,
            detail="Log in with your enterprise-rag-platform account (Authorization + X-RAG-CSRF-Token headers) to use this service.",
        )
    settings = get_settings()
    auth = StaticTokenAuth(user_session.access_token, user_session.csrf_token)
    client = RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, get_shared_rag_platform_client())
    start_time = time.monotonic()
    try:
        result = await run_direct_query(client, request.query)
    except (RagPlatformRetrievalError, RagPlatformAuthError) as exc:
        record_query_duration("error", "direct", time.monotonic() - start_time)
        raise HTTPException(status_code=502, detail=f"enterprise-rag-platform is unavailable: {exc}") from None
    duration_seconds = time.monotonic() - start_time
    outcome = "completed" if result.text is not None else "refused"
    record_query_outcome(outcome)
    record_query_duration(outcome, "direct", duration_seconds)
    return result.model_copy(update={"duration_seconds": duration_seconds})


@router.post("/query")
async def query(
    request: QueryRequest,
    authorization: str | None = Header(default=None),
    x_rag_csrf_token: str | None = Header(default=None),
) -> StreamingResponse:
    """Run a query through the agent graph and stream back its trace and result as SSE.

    Each `step` event is sent as that agent actually finishes (AGT-008), not batched until the
    graph completes. The graph is built before the stream opens, so configuration errors
    (missing settings, etc.) propagate as a normal 5xx response rather than a 200 with an empty
    body.

    AGT-013/AGT-006: requires `Authorization: Bearer <rag-platform-access-token>` +
    `X-RAG-CSRF-Token` headers together, identifying a real `enterprise-rag-platform` account.
    There is no anonymous/service-account fallback -- a caller who isn't logged in gets 401, not a
    demo account's results.
    """
    user_session = extract_user_session(authorization, x_rag_csrf_token)
    if user_session is None:
        raise HTTPException(
            status_code=401,
            detail="Log in with your enterprise-rag-platform account (Authorization + X-RAG-CSRF-Token headers) to use this service.",
        )
    settings = get_settings()
    # AGT-031: awaited inline, not backgrounded -- Cloud Run only guarantees CPU while a request is
    # actively being handled (the default `cpu-throttling` setting this service runs under); a
    # `StreamingResponse(background=...)` task races the sandbox freezing CPU right after the last
    # SSE chunk is sent and reliably lost that race in practice (confirmed live: zero
    # `openrouter.ai/api/v1/credits` calls ever logged despite no exception either). Already
    # throttled to once per 10 minutes internally, so the added latency on the rare request that
    # actually triggers it is one lightweight GET, not an LLM call.
    if settings.llm_provider == "openrouter" and settings.openrouter_api_key:
        await maybe_record_openrouter_budget(settings.openrouter_api_key)
    graph = get_graph(user_session)
    return StreamingResponse(_event_stream(graph, request.query, user_session), media_type="text/event-stream")
