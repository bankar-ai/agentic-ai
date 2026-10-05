import sys
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.agents.research import KnowledgeBaseUnavailable
from app.agents.schemas import UserSession
from app.api.router import MCP_SERVER_COMMAND, extract_user_session
from app.main import app
from app.rag_client.retrieval import RagPlatformRetrievalError

_AUTH_HEADERS = {"Authorization": "Bearer user-token-123", "X-RAG-CSRF-Token": "user-csrf-456"}


async def _astream(chunks: list[dict]):
    """Build an async generator standing in for `graph.astream(..., stream_mode='updates')`:
    each `chunks` entry is a `{node_name: full_state_dict}` pair, same shape LangGraph's
    "updates" mode actually yields (AGT-008)."""
    for chunk in chunks:
        yield chunk


async def _astream_then_raise(chunks: list[dict], exc: Exception):
    for chunk in chunks:
        yield chunk
    raise exc


def _graph(chunks: list[dict] | None = None, raises: Exception | None = None) -> MagicMock:
    fake_graph = MagicMock()
    if raises is not None:
        fake_graph.astream = MagicMock(return_value=_astream_then_raise(chunks or [], raises))
    else:
        fake_graph.astream = MagicMock(return_value=_astream(chunks or []))
    return fake_graph


def test_query_endpoint_streams_steps_and_result():
    gatekeeper_state = {
        "final_answer": None, "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    verifier_state = {
        "final_answer": "Paris [geo.pdf]", "refused": False,
        "trace": [gatekeeper_state["trace"][0], {"agent": "verifier", "grounded": True}],
    }
    fake_graph = _graph([{"gatekeeper": gatekeeper_state}, {"verifier": verifier_state}])

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert response.status_code == 200
    assert response.text.count("event: step") == 2
    assert "event: result" in response.text
    assert "Paris" in response.text
    assert '"duration_seconds"' in response.text


def test_query_endpoint_surfaces_rag_platform_outage_as_error_event():
    """An outage during the run must not be a silent 200 with an empty body."""
    fake_graph = _graph(raises=RagPlatformRetrievalError("Retrieval request failed: connection refused"))

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert response.text != ""
    assert "event: error" in response.text
    assert "RagPlatformRetrievalError" in response.text
    assert "event: result" not in response.text


def test_query_endpoint_sends_steps_already_yielded_before_a_later_failure():
    """AGT-008: partial progress sent before a mid-stream failure must stay sent, not be
    discarded just because the overall run didn't finish."""
    gatekeeper_state = {
        "final_answer": None, "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    fake_graph = _graph(
        chunks=[{"gatekeeper": gatekeeper_state}],
        raises=RagPlatformRetrievalError("Retrieval request failed: timed out"),
    )

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert "event: step" in response.text
    assert "event: error" in response.text


def test_query_endpoint_maps_knowledge_base_unavailable_to_a_legible_error_event():
    """AGT-012: a raw MCP ToolError/MCPError must not leak its exception type name to the
    client -- it's mapped to KnowledgeBaseUnavailable with a legible message instead."""
    fake_graph = _graph(raises=KnowledgeBaseUnavailable("The knowledge base tool call failed: boom"))

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert "event: error" in response.text
    assert '"type": "KnowledgeBaseUnavailable"' in response.text
    assert "boom" not in response.text


def test_query_endpoint_surfaces_unexpected_failure_as_error_event():
    fake_graph = _graph(raises=ValueError("internal detail"))

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert "event: error" in response.text
    assert "internal detail" not in response.text


def test_query_endpoint_returns_5xx_when_graph_cannot_be_built():
    """Configuration errors are raised before the stream opens, so they become a real 5xx."""
    with patch("app.api.router.get_graph", side_effect=RuntimeError("missing RAG_PLATFORM_BASE_URL")):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert response.status_code == 500


def test_query_endpoint_returns_401_when_not_logged_in():
    """AGT-006: there is no anonymous/service-account fallback -- a caller without a valid
    RAG-platform session must be rejected, not served a demo account's results."""
    client = TestClient(app)
    response = client.post("/query", json={"query": "What is the capital of France?"})

    assert response.status_code == 401


def test_mcp_server_command_uses_running_interpreter():
    assert MCP_SERVER_COMMAND[0] == sys.executable
    assert MCP_SERVER_COMMAND[1:] == ["-m", "app.mcp_server.server"]


def test_query_endpoint_rejects_empty_query():
    client = TestClient(app)
    response = client.post("/query", json={"query": ""})

    assert response.status_code == 422


def test_extract_user_session_parses_both_headers():
    session = extract_user_session("Bearer abc123", "csrf-456")
    assert session == UserSession(access_token="abc123", csrf_token="csrf-456")


def test_extract_user_session_returns_none_when_either_header_absent_or_malformed():
    assert extract_user_session(None, "csrf-456") is None
    assert extract_user_session("Bearer abc123", None) is None
    assert extract_user_session("", "csrf-456") is None
    assert extract_user_session("abc123", "csrf-456") is None  # missing "Bearer " prefix


def test_query_endpoint_passes_user_session_to_get_graph_when_logged_in():
    """AGT-013: both auth headers must actually reach get_graph(), not be silently dropped."""
    fake_graph = _graph([{"gatekeeper": {"final_answer": "answer", "refused": False, "trace": []}}])

    with patch("app.api.router.get_graph", return_value=fake_graph) as mock_get_graph:
        client = TestClient(app)
        client.post(
            "/query", json={"query": "What is the capital of France?"},
            headers={"Authorization": "Bearer user-token-123", "X-RAG-CSRF-Token": "user-csrf-456"},
        )

    # AGT-051: get_graph also receives a session_store (None in this test env, since
    # DATABASE_URL isn't configured) -- positional, not a kwarg the old assertion would still match.
    mock_get_graph.assert_called_once_with(
        UserSession(access_token="user-token-123", csrf_token="user-csrf-456"), None
    )


def test_query_endpoint_does_not_call_get_graph_when_not_logged_in():
    """AGT-006: no session must never reach get_graph() at all -- it's rejected before that."""
    with patch("app.api.router.get_graph") as mock_get_graph:
        client = TestClient(app)
        client.post("/query", json={"query": "What is the capital of France?"})

    mock_get_graph.assert_not_called()


def test_health_endpoint_requires_no_auth_and_returns_ok():
    """AGT-022: the Synthetic Monitoring probe target must work with no headers at all."""
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_query_endpoint_records_completed_outcome():
    fake_graph = _graph([{
        "verifier": {
            "final_answer": "Paris", "refused": False, "retry_count": 0,
            "trace": [{"agent": "verifier", "grounded": True}],
        }
    }])

    with (
        patch("app.api.router.get_graph", return_value=fake_graph),
        patch("app.api.router.record_query_outcome") as mock_outcome,
        patch("app.api.router.record_retry_count") as mock_retry,
    ):
        client = TestClient(app)
        client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    mock_outcome.assert_called_once_with("completed")
    mock_retry.assert_called_once_with(0)


def test_query_endpoint_records_refused_outcome():
    fake_graph = _graph([{
        "verifier": {
            "final_answer": None, "refused": True, "retry_count": 2,
            "trace": [{"agent": "verifier", "grounded": False}],
        }
    }])

    with (
        patch("app.api.router.get_graph", return_value=fake_graph),
        patch("app.api.router.record_query_outcome") as mock_outcome,
        patch("app.api.router.record_retry_count") as mock_retry,
    ):
        client = TestClient(app)
        client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    mock_outcome.assert_called_once_with("refused")
    mock_retry.assert_called_once_with(2)


def test_query_direct_endpoint_requires_auth():
    client = TestClient(app)
    response = client.post("/query/direct", json={"query": "What is the capital of France?"})

    assert response.status_code == 401


def test_query_direct_endpoint_returns_the_top_chunk_and_duration():
    from app.agents.direct_query import DirectQueryResult

    async def fake_run_direct_query(client, query):
        return DirectQueryResult(text="Paris is the capital of France.", source_filename="geo.pdf")

    with patch("app.api.router.run_direct_query", fake_run_direct_query):
        client = TestClient(app)
        response = client.post("/query/direct", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Paris is the capital of France."
    assert body["source_filename"] == "geo.pdf"
    assert isinstance(body["duration_seconds"], float)


def test_query_direct_endpoint_surfaces_rag_platform_outage_as_502():
    async def fake_run_direct_query(client, query):
        raise RagPlatformRetrievalError("connection refused")

    with patch("app.api.router.run_direct_query", fake_run_direct_query):
        client = TestClient(app)
        response = client.post("/query/direct", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert response.status_code == 502


def test_documents_endpoint_requires_auth():
    client = TestClient(app)
    response = client.get("/documents")

    assert response.status_code == 401


def test_documents_endpoint_returns_documents_when_logged_in():
    fake_result = {
        "documents": [{"document_id": "d1", "filename": "geo.pdf", "created_at": "2026-10-01T12:00:00Z"}],
        "has_more": False,
    }

    async def fake_list_documents(self, limit=50, offset=0):
        from app.rag_client.documents import DocumentListResult

        return DocumentListResult(**fake_result)

    with patch("app.rag_client.documents.RagPlatformDocumentsClient.list_documents", fake_list_documents):
        client = TestClient(app)
        response = client.get("/documents", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["documents"][0]["filename"] == "geo.pdf"


def test_documents_endpoint_surfaces_rag_platform_outage_as_502():
    from app.rag_client.documents import RagPlatformDocumentsError

    async def fake_list_documents(self, limit=50, offset=0):
        raise RagPlatformDocumentsError("connection refused")

    with patch("app.rag_client.documents.RagPlatformDocumentsClient.list_documents", fake_list_documents):
        client = TestClient(app)
        response = client.get("/documents", headers=_AUTH_HEADERS)

    assert response.status_code == 502


def test_query_endpoint_records_error_outcome_on_failure():
    fake_graph = _graph(raises=ValueError("internal detail"))

    with (
        patch("app.api.router.get_graph", return_value=fake_graph),
        patch("app.api.router.record_query_outcome") as mock_outcome,
        patch("app.api.router.record_retry_count") as mock_retry,
    ):
        client = TestClient(app)
        client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    mock_outcome.assert_called_once_with("error")
    mock_retry.assert_not_called()


class _FakeCache:
    """Stands in for `QueryCache` (AGT-041) -- records every `record()` call and returns a fixed
    `lookup()` result, so tests can assert on cache-hit/-miss behavior without a real database."""

    def __init__(self, lookup_result=None):
        self.lookup_result = lookup_result
        self.record_calls: list[dict] = []

    async def lookup(self, user_id, mode, question):
        return self.lookup_result

    async def record(self, **kwargs):
        self.record_calls.append(kwargs)


def _jwt_with_sub(sub: str) -> str:
    import base64
    import json

    def b64(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS256'})}.{b64({'sub': sub})}.sig"


_CACHE_AUTH_HEADERS = {"Authorization": f"Bearer {_jwt_with_sub('user-abc')}", "X-RAG-CSRF-Token": "csrf"}


def test_query_endpoint_serves_a_cache_hit_without_running_the_graph():
    from app.core.query_cache import CachedQueryResult

    cached = CachedQueryResult(
        answer="Paris is the capital of France.",
        refused=False,
        trace=[{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
        source_filename=None,
    )
    fake_cache = _FakeCache(lookup_result=cached)
    fake_graph = MagicMock()
    fake_graph.astream = MagicMock(side_effect=AssertionError("graph should not run on a cache hit"))

    with (
        patch("app.api.router.get_graph", return_value=fake_graph),
        patch("app.api.router.get_query_cache", AsyncMock(return_value=fake_cache)),
    ):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_CACHE_AUTH_HEADERS)

    assert response.status_code == 200
    assert "Paris" in response.text
    assert '"duration_seconds": 0.0' in response.text
    assert len(fake_cache.record_calls) == 1
    assert fake_cache.record_calls[0]["served_from_cache"] is True


def test_query_endpoint_records_history_on_a_cache_miss():
    gatekeeper_state = {
        "final_answer": None, "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    verifier_state = {
        "final_answer": "Paris [geo.pdf]", "refused": False,
        "trace": [gatekeeper_state["trace"][0], {"agent": "verifier", "grounded": True}],
    }
    fake_graph = _graph([{"gatekeeper": gatekeeper_state}, {"verifier": verifier_state}])
    fake_cache = _FakeCache(lookup_result=None)

    with (
        patch("app.api.router.get_graph", return_value=fake_graph),
        patch("app.api.router.get_query_cache", AsyncMock(return_value=fake_cache)),
    ):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_CACHE_AUTH_HEADERS)

    assert response.status_code == 200
    assert len(fake_cache.record_calls) == 1
    assert fake_cache.record_calls[0]["served_from_cache"] is False
    assert fake_cache.record_calls[0]["answer"] == "Paris [geo.pdf]"


def test_query_direct_endpoint_serves_a_cache_hit_without_calling_run_direct_query():
    from app.core.query_cache import CachedQueryResult

    cached = CachedQueryResult(answer="Paris.", refused=False, trace=[], source_filename="geo.pdf")
    fake_cache = _FakeCache(lookup_result=cached)

    async def fake_run_direct_query(client, query):
        raise AssertionError("should not run retrieval on a cache hit")

    with (
        patch("app.api.router.run_direct_query", fake_run_direct_query),
        patch("app.api.router.get_query_cache", AsyncMock(return_value=fake_cache)),
    ):
        client = TestClient(app)
        response = client.post("/query/direct", json={"query": "What is the capital of France?"}, headers=_CACHE_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Paris."
    assert body["source_filename"] == "geo.pdf"
    assert body["duration_seconds"] == 0.0


# Every test above this point in the file runs with no `get_query_cache` patch at all, exercising
# the real function against this test environment's `DATABASE_URL`-less `.env` -- they already
# confirm an unconfigured deploy behaves exactly as it did before this ticket (`get_query_cache`
# returns `None`, no database touched), so no separate test duplicates that here.


def test_history_endpoint_requires_auth():
    client = TestClient(app)
    response = client.get("/history")
    assert response.status_code == 401


def test_history_endpoint_returns_empty_list_without_database_configured():
    """`get_query_cache` returns `None` when `DATABASE_URL` is unset -- real (unpatched)
    function, confirming this endpoint degrades to an empty list rather than erroring."""
    client = TestClient(app)
    response = client.get("/history", headers=_AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json() == []


def test_history_endpoint_returns_the_callers_recent_entries():
    from app.core.query_cache import HistoryEntry

    entry = HistoryEntry(
        question="What is the capital of France?",
        answer="Paris.",
        refused=False,
        mode="agentic",
        trace=[{"agent": "gatekeeper"}],
        source_filename=None,
        duration_seconds=1.5,
        created_at="2026-10-04T12:00:00Z",
    )

    class _FakeCacheWithHistory(_FakeCache):
        async def list_recent(self, user_id, limit=5):
            return [entry]

    with patch("app.api.router.get_query_cache", AsyncMock(return_value=_FakeCacheWithHistory())):
        client = TestClient(app)
        response = client.get("/history", headers=_CACHE_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["question"] == "What is the capital of France?"
    assert body[0]["mode"] == "agentic"


def test_history_endpoint_returns_empty_list_when_token_has_no_sub_claim():
    with patch("app.api.router.get_query_cache", AsyncMock(return_value=_FakeCache())):
        client = TestClient(app)
        # _AUTH_HEADERS' bearer token ("user-token-123") isn't a JWT, so decode_user_id returns
        # None -- confirms this degrades gracefully instead of raising.
        response = client.get("/history", headers=_AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json() == []


# AGT-052: an expired/rejected session (RagPlatformAuthError) must surface as 401 with a
# "log in again" message, distinct from a genuine outage (RagPlatformRetrievalError/
# RagPlatformDocumentsError -> 502) -- previously both were caught in the same except clause and
# flattened into an indistinguishable 502, so the frontend's existing 401-triggered logout flow
# never fired for the actual common case (a token that simply expired).


def test_query_endpoint_surfaces_expired_session_as_a_distinct_sse_error():
    from app.rag_client.auth import RagPlatformAuthError

    fake_graph = _graph(raises=RagPlatformAuthError("Supplied session expired or was rejected; please log in again."))

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "RagPlatformAuthError" in response.text
    assert "expired" in response.text
    # Distinct from a genuine outage's message -- never says "unavailable" for this case.
    assert "unavailable" not in response.text


def test_query_endpoint_still_surfaces_a_genuine_outage_as_retrieval_error():
    fake_graph = _graph(raises=RagPlatformRetrievalError("connection refused"))

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert "RagPlatformRetrievalError" in response.text
    assert "unavailable" in response.text
    assert "expired" not in response.text


def test_query_direct_endpoint_surfaces_expired_session_as_401():
    from app.rag_client.auth import RagPlatformAuthError

    async def fake_run_direct_query(client, query):
        raise RagPlatformAuthError("Supplied session expired or was rejected; please log in again.")

    with patch("app.api.router.run_direct_query", fake_run_direct_query):
        client = TestClient(app)
        response = client.post("/query/direct", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_query_direct_endpoint_still_surfaces_a_genuine_outage_as_502():
    async def fake_run_direct_query(client, query):
        raise RagPlatformRetrievalError("connection refused")

    with patch("app.api.router.run_direct_query", fake_run_direct_query):
        client = TestClient(app)
        response = client.post("/query/direct", json={"query": "What is the capital of France?"}, headers=_AUTH_HEADERS)

    assert response.status_code == 502


def test_documents_endpoint_surfaces_expired_session_as_401():
    from app.rag_client.auth import RagPlatformAuthError

    async def fake_list_documents(self, limit=50, offset=0):
        raise RagPlatformAuthError("Supplied session expired or was rejected; please log in again.")

    with patch("app.rag_client.documents.RagPlatformDocumentsClient.list_documents", fake_list_documents):
        client = TestClient(app)
        response = client.get("/documents", headers=_AUTH_HEADERS)

    assert response.status_code == 401
    assert "expired" in response.json()["detail"]
