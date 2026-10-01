import sys
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.agents.schemas import UserSession
from app.api.router import MCP_SERVER_COMMAND, extract_user_session
from app.main import app
from app.rag_client.retrieval import RagPlatformRetrievalError


def test_query_endpoint_streams_steps_and_result():
    fake_final_state = {
        "final_answer": "Paris [geo.pdf]", "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    fake_graph = AsyncMock()
    fake_graph.ainvoke.return_value = fake_final_state

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"})

    assert response.status_code == 200
    assert "event: step" in response.text
    assert "event: result" in response.text
    assert "Paris" in response.text


def test_query_endpoint_surfaces_rag_platform_outage_as_error_event():
    """An outage during the run must not be a silent 200 with an empty body."""
    fake_graph = AsyncMock()
    fake_graph.ainvoke.side_effect = RagPlatformRetrievalError("Retrieval request failed: connection refused")

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"})

    assert response.text != ""
    assert "event: error" in response.text
    assert "RagPlatformRetrievalError" in response.text
    assert "event: result" not in response.text


def test_query_endpoint_surfaces_unexpected_failure_as_error_event():
    fake_graph = AsyncMock()
    fake_graph.ainvoke.side_effect = ValueError("internal detail")

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"})

    assert "event: error" in response.text
    assert "internal detail" not in response.text


def test_query_endpoint_returns_5xx_when_graph_cannot_be_built():
    """Configuration errors are raised before the stream opens, so they become a real 5xx."""
    with patch("app.api.router.get_graph", side_effect=RuntimeError("missing RAG_PLATFORM_BASE_URL")):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/query", json={"query": "What is the capital of France?"})

    assert response.status_code == 500


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
    fake_final_state = {"final_answer": "answer", "refused": False, "trace": []}
    fake_graph = AsyncMock()
    fake_graph.ainvoke.return_value = fake_final_state

    with patch("app.api.router.get_graph", return_value=fake_graph) as mock_get_graph:
        client = TestClient(app)
        client.post(
            "/query", json={"query": "What is the capital of France?"},
            headers={"Authorization": "Bearer user-token-123", "X-RAG-CSRF-Token": "user-csrf-456"},
        )

    mock_get_graph.assert_called_once_with(UserSession(access_token="user-token-123", csrf_token="user-csrf-456"))


def test_query_endpoint_passes_none_to_get_graph_when_not_logged_in():
    fake_final_state = {"final_answer": "answer", "refused": False, "trace": []}
    fake_graph = AsyncMock()
    fake_graph.ainvoke.return_value = fake_final_state

    with patch("app.api.router.get_graph", return_value=fake_graph) as mock_get_graph:
        client = TestClient(app)
        client.post("/query", json={"query": "What is the capital of France?"})

    mock_get_graph.assert_called_once_with(None)
