from unittest.mock import AsyncMock, patch

import gradio as gr
import pytest

from app.core.config import get_settings
from app.rag_client.auth import RagPlatformAuthError
from app.ui.app import build_ui, login, run_agentic_query, run_direct_query


def test_build_ui_returns_blocks_with_two_tabs():
    demo = build_ui()

    assert isinstance(demo, gr.Blocks)


@pytest.mark.asyncio
async def test_run_direct_query_returns_plain_answer_text():
    fake_client = AsyncMock()
    fake_client.search.return_value = AsyncMock(
        results=[AsyncMock(text="Paris is the capital of France.", source_filename="world-facts.pdf")]
    )

    with patch("app.ui.app._get_retrieval_client", return_value=fake_client):
        answer = await run_direct_query("What is the capital of France?")

    assert "Paris" in answer


@pytest.mark.asyncio
async def test_run_agentic_query_returns_trace_and_answer():
    fake_state = {
        "final_answer": "Paris [world-facts.pdf]", "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    fake_graph = AsyncMock()
    fake_graph.ainvoke.return_value = fake_state

    with patch("app.ui.app.get_graph", return_value=fake_graph):
        trace_text, answer_text = await run_agentic_query("What is the capital of France?")

    assert "gatekeeper" in trace_text
    assert "Paris" in answer_text


@pytest.mark.asyncio
async def test_run_agentic_query_forwards_user_token_to_get_graph():
    """AGT-013/014: a logged-in visitor's token must actually reach get_graph(), not be dropped."""
    fake_state = {"final_answer": "answer", "refused": False, "trace": []}
    fake_graph = AsyncMock()
    fake_graph.ainvoke.return_value = fake_state

    with patch("app.ui.app.get_graph", return_value=fake_graph) as mock_get_graph:
        await run_agentic_query("What is the capital of France?", user_token="user-token-123")

    mock_get_graph.assert_called_once_with("user-token-123")


@pytest.mark.asyncio
async def test_run_direct_query_forwards_user_token_to_retrieval_client():
    fake_client = AsyncMock()
    fake_client.search.return_value = AsyncMock(results=[])

    with patch("app.ui.app._get_retrieval_client", return_value=fake_client) as mock_get_client:
        await run_direct_query("What is the capital of France?", user_token="user-token-123")

    mock_get_client.assert_called_once_with("user-token-123")


@pytest.mark.asyncio
async def test_login_succeeds_and_returns_token(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "svc-secret")
    get_settings.cache_clear()
    fake_auth = AsyncMock()
    fake_auth.get_access_token.return_value = "issued-token-456"

    with patch("app.ui.app.RagPlatformAuth", return_value=fake_auth):
        token, status = await login("user@example.com", "correct-password")

    assert token == "issued-token-456"
    assert "user@example.com" in status


@pytest.mark.asyncio
async def test_login_failure_returns_no_token_and_clear_message(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "svc-secret")
    get_settings.cache_clear()
    fake_auth = AsyncMock()
    fake_auth.get_access_token.side_effect = RagPlatformAuthError("Login failed: 401")

    with patch("app.ui.app.RagPlatformAuth", return_value=fake_auth):
        token, status = await login("user@example.com", "wrong-password")

    assert token is None
    assert "failed" in status.lower()


@pytest.mark.asyncio
async def test_login_rejects_empty_fields_without_a_network_call():
    token, status = await login("", "")

    assert token is None
    assert "enter" in status.lower()
