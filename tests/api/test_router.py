import sys
from unittest.mock import MagicMock, patch

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

    mock_get_graph.assert_called_once_with(UserSession(access_token="user-token-123", csrf_token="user-csrf-456"))


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
