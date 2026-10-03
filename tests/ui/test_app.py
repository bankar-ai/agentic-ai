from unittest.mock import AsyncMock, MagicMock, patch

import gradio as gr
import httpx
import pytest

from app.agents.schemas import UserSession
from app.core.config import get_settings
from app.ui.app import build_ui, login, run_agentic_query, run_direct_query


def test_build_ui_returns_blocks_with_two_tabs():
    demo = build_ui()

    assert isinstance(demo, gr.Blocks)


_SESSION = UserSession(access_token="user-token-123", csrf_token="user-csrf-456")


async def _astream(chunks: list[dict]):
    """Stands in for `graph.astream(..., stream_mode='updates')` -- each entry is a
    `{node_name: full_state_dict}` pair, same shape LangGraph's "updates" mode yields."""
    for chunk in chunks:
        yield chunk


def _graph(chunks: list[dict]) -> MagicMock:
    fake_graph = MagicMock()
    fake_graph.astream = MagicMock(return_value=_astream(chunks))
    return fake_graph


async def _collect(async_gen):
    """Drain an async generator, returning every yielded item in order."""
    return [item async for item in async_gen]


@pytest.mark.asyncio
async def test_run_direct_query_returns_plain_answer_text():
    fake_client = AsyncMock()
    fake_client.search.return_value = AsyncMock(
        results=[AsyncMock(text="Paris is the capital of France.", source_filename="world-facts.pdf")]
    )

    with patch("app.ui.app._get_retrieval_client", return_value=fake_client):
        answer = await run_direct_query("What is the capital of France?", user_session=_SESSION)

    assert "Paris" in answer


@pytest.mark.asyncio
async def test_run_direct_query_without_session_returns_login_required_message():
    """AGT-006: no demo account -- querying without a session must not reach the retrieval client."""
    with patch("app.ui.app._get_retrieval_client") as mock_get_client:
        answer = await run_direct_query("What is the capital of France?")

    mock_get_client.assert_not_called()
    assert "log in" in answer.lower()


@pytest.mark.asyncio
async def test_run_agentic_query_returns_trace_and_answer():
    fake_state = {
        "final_answer": "Paris [world-facts.pdf]", "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    fake_graph = _graph([{"gatekeeper": fake_state}])

    with patch("app.ui.app.get_graph", return_value=fake_graph):
        yielded = await _collect(run_agentic_query("What is the capital of France?", user_session=_SESSION))

    trace_text, answer_text = yielded[-1]
    assert "gatekeeper" in trace_text
    assert "Paris" in answer_text


@pytest.mark.asyncio
async def test_run_agentic_query_yields_progressively_as_each_node_finishes():
    """AGT-008: the trace fills in live -- each node's completion is its own yielded update,
    not one final batch at the end."""
    gatekeeper_state = {
        "final_answer": None, "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    verifier_state = {
        "final_answer": "Paris [world-facts.pdf]", "refused": False,
        "trace": [gatekeeper_state["trace"][0], {"agent": "verifier", "grounded": True}],
    }
    fake_graph = _graph([{"gatekeeper": gatekeeper_state}, {"verifier": verifier_state}])

    with patch("app.ui.app.get_graph", return_value=fake_graph):
        yielded = await _collect(run_agentic_query("What is the capital of France?", user_session=_SESSION))

    assert len(yielded) == 3  # one per node, plus the final answer update
    assert "gatekeeper" in yielded[0][0]
    assert "verifier" not in yielded[0][0]
    assert "verifier" in yielded[1][0]
    assert yielded[-1][1] == "Paris [world-facts.pdf]"


@pytest.mark.asyncio
async def test_run_agentic_query_without_session_returns_login_required_message():
    """AGT-006: no demo account -- querying without a session must not reach get_graph()."""
    with patch("app.ui.app.get_graph") as mock_get_graph:
        yielded = await _collect(run_agentic_query("What is the capital of France?"))

    mock_get_graph.assert_not_called()
    trace_text, answer_text = yielded[-1]
    assert trace_text == ""
    assert "log in" in answer_text.lower()


@pytest.mark.asyncio
async def test_run_agentic_query_forwards_user_session_to_get_graph():
    """AGT-013/014: a logged-in visitor's session must actually reach get_graph(), not be dropped."""
    fake_graph = _graph([{"gatekeeper": {"final_answer": "answer", "refused": False, "trace": [{"agent": "gatekeeper"}]}}])
    session = UserSession(access_token="user-token-123", csrf_token="user-csrf-456")

    with patch("app.ui.app.get_graph", return_value=fake_graph) as mock_get_graph:
        await _collect(run_agentic_query("What is the capital of France?", user_session=session))

    mock_get_graph.assert_called_once_with(session)


@pytest.mark.asyncio
async def test_run_direct_query_forwards_user_session_to_retrieval_client():
    fake_client = AsyncMock()
    fake_client.search.return_value = AsyncMock(results=[])
    session = UserSession(access_token="user-token-123", csrf_token="user-csrf-456")

    with patch("app.ui.app._get_retrieval_client", return_value=fake_client) as mock_get_client:
        await run_direct_query("What is the capital of France?", user_session=session)

    mock_get_client.assert_called_once_with(session)


def _login_transport(csrf_token: str = "csrf-456", access_token: str = "issued-token-456"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            response = httpx.Response(200, json={"user_id": "u1", "csrf_token": csrf_token})
            response.headers["set-cookie"] = f"access_token={access_token}; Path=/; HttpOnly"
            return response
        return httpx.Response(401, json={"detail": "Invalid email or password"})
    return httpx.MockTransport(handler)


_RealAsyncClient = httpx.AsyncClient


@pytest.mark.asyncio
async def test_login_succeeds_and_returns_session(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "svc-secret")
    get_settings.cache_clear()
    transport = _login_transport()

    with patch("app.ui.app.httpx.AsyncClient", lambda **kwargs: _RealAsyncClient(base_url=kwargs["base_url"], transport=transport)):
        session, status = await login("user@example.com", "correct-password")

    assert session == UserSession(access_token="issued-token-456", csrf_token="csrf-456")
    assert "user@example.com" in status


@pytest.mark.asyncio
async def test_login_failure_returns_no_session_and_clear_message(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "svc-secret")
    get_settings.cache_clear()

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid email or password"})

    transport = httpx.MockTransport(failing_handler)

    with patch("app.ui.app.httpx.AsyncClient", lambda **kwargs: _RealAsyncClient(base_url=kwargs["base_url"], transport=transport)):
        session, status = await login("user@example.com", "wrong-password")

    assert session is None
    assert "failed" in status.lower()


@pytest.mark.asyncio
async def test_login_rejects_empty_fields_without_a_network_call():
    token, status = await login("", "")

    assert token is None
    assert "enter" in status.lower()
