from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from app.agents.research import (
    KnowledgeBaseToolError,
    KnowledgeBaseUnavailable,
    _research_kb,
    research,
)
from app.agents.schemas import Evidence, GatekeeperDecision, ResearchResult, UserSession

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_COMMAND = ["C:/venv/python.exe", "-m", "app.mcp_server.server"]


@pytest.mark.asyncio
async def test_research_web_fallback_route_uses_web_search():
    decision = GatekeeperDecision(route="web_fallback", reasoning="no KB match")
    fake_evidence = [Evidence(text="Sunny, 28C", source="web", citation="https://weather.example")]

    with patch("app.agents.research.search_web", AsyncMock(return_value=fake_evidence)):
        result = await research(mcp_server_command=[], decision=decision, query="weather in Pune today")

    assert isinstance(result, ResearchResult)
    assert result.evidence == fake_evidence


@pytest.mark.asyncio
async def test_research_refuse_route_returns_no_evidence():
    decision = GatekeeperDecision(route="refuse", reasoning="unanswerable")

    result = await research(mcp_server_command=[], decision=decision, query="anything")

    assert result.evidence == []


def _patched_mcp(tool_result: object):
    """Patch StdioTransport and MCPToolset so no subprocess is spawned; the toolset's
    `direct_call_tool` returns `tool_result` as the MCP tool's raw (unwrapped) return value.
    """
    fake_transport = MagicMock(name="fake_transport")
    fake_toolset = MagicMock(name="fake_toolset")
    fake_toolset.direct_call_tool = AsyncMock(return_value=tool_result)
    transport_patch = patch("app.agents.research.StdioTransport", return_value=fake_transport)
    toolset_patch = patch("app.agents.research.MCPToolset", return_value=fake_toolset)
    return fake_transport, fake_toolset, transport_patch, toolset_patch


@pytest.mark.asyncio
async def test_research_kb_route_wires_stdio_transport_and_calls_tool_directly(monkeypatch):
    """Construction-level test for the "kb" route's MCP wiring, without a real subprocess:
    asserts the command/args split, that RAG_PLATFORM_* credentials are forwarded to the child
    via `env` (the MCP SDK's default env allow-list excludes them), that `cwd` is the repo root,
    that the transport is wrapped in an MCPToolset with errors raised rather than retried, and
    that the tool is called directly with the Gatekeeper's search parameters.
    """
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "agent@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "s3cret")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-leak")
    decision = GatekeeperDecision(route="kb", reasoning="kb has the answer", top_k=3, rerank=True)
    chunks = [{"text": "answer text", "source_filename": "doc.pdf", "section_path": ["A"], "score": 0.9}]
    fake_transport, fake_toolset, transport_patch, toolset_patch = _patched_mcp(chunks)

    with transport_patch as mock_transport_cls, toolset_patch as mock_toolset_cls:
        result = await _research_kb(mcp_server_command=MCP_COMMAND, decision=decision, query="what is the refund policy?")

    _, transport_kwargs = mock_transport_cls.call_args
    assert transport_kwargs["command"] == "C:/venv/python.exe"
    assert transport_kwargs["args"] == ["-m", "app.mcp_server.server"]
    env = transport_kwargs["env"]
    assert env["RAG_PLATFORM_BASE_URL"] == "http://rag.example"
    assert env["RAG_PLATFORM_EMAIL"] == "agent@example.com"
    assert env["RAG_PLATFORM_PASSWORD"] == "s3cret"
    assert "UNRELATED_SECRET" not in env
    assert Path(transport_kwargs["cwd"]) == REPO_ROOT
    mock_toolset_cls.assert_called_once_with(fake_transport, tool_error_behavior="error")
    fake_toolset.direct_call_tool.assert_awaited_once_with(
        "search_knowledge_base", {"query": "what is the refund policy?", "top_k": 3, "rerank": True}
    )
    assert result == [Evidence(text="answer text", source="knowledge_base", citation="doc.pdf")]


@pytest.mark.asyncio
async def test_research_kb_route_forwards_user_session_to_subprocess_env(monkeypatch):
    """AGT-013: a logged-in user's session overrides the fixed service account for this one call,
    forwarded to the MCP subprocess as RAG_PLATFORM_ACCESS_TOKEN/CSRF_TOKEN (see
    mcp_server.server._build_auth).
    """
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "agent@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "s3cret")
    decision = GatekeeperDecision(route="kb", reasoning="ok")
    chunks = [{"text": "answer", "source_filename": "doc.pdf", "section_path": [], "score": 0.9}]
    _, _, transport_patch, toolset_patch = _patched_mcp(chunks)
    session = UserSession(access_token="user-token-123", csrf_token="user-csrf-456")

    with transport_patch as mock_transport_cls, toolset_patch:
        await _research_kb(mcp_server_command=MCP_COMMAND, decision=decision, query="q", user_session=session)

    _, transport_kwargs = mock_transport_cls.call_args
    env = transport_kwargs["env"]
    assert env["RAG_PLATFORM_ACCESS_TOKEN"] == "user-token-123"
    assert env["RAG_PLATFORM_CSRF_TOKEN"] == "user-csrf-456"
    # The fixed service-account credentials are still forwarded too -- mcp_server.server's
    # _build_auth prioritizes the session when present, but doesn't require the caller to
    # omit the others.
    assert env["RAG_PLATFORM_EMAIL"] == "agent@example.com"


@pytest.mark.asyncio
async def test_research_kb_route_omits_session_env_when_not_logged_in(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://rag.example")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "agent@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "s3cret")
    decision = GatekeeperDecision(route="kb", reasoning="ok")
    chunks = [{"text": "answer", "source_filename": "doc.pdf", "section_path": [], "score": 0.9}]
    _, _, transport_patch, toolset_patch = _patched_mcp(chunks)

    with transport_patch as mock_transport_cls, toolset_patch:
        await _research_kb(mcp_server_command=MCP_COMMAND, decision=decision, query="q")

    _, transport_kwargs = mock_transport_cls.call_args
    assert "RAG_PLATFORM_ACCESS_TOKEN" not in transport_kwargs["env"]


@pytest.mark.asyncio
async def test_research_kb_route_labels_every_result_knowledge_base_in_code():
    """Evidence is built from the tool's structured result, not transcribed by an LLM: every item
    is labeled "knowledge_base" and cited by its real source filename, whatever else the chunk says.
    """
    decision = GatekeeperDecision(route="kb", reasoning="ok")
    chunks = [
        {"text": "one", "source_filename": "a.pdf", "section_path": [], "score": 0.8, "source": "web"},
        {"text": "two", "source_filename": "b.pdf", "section_path": [], "score": 0.7},
    ]
    _, _, transport_patch, toolset_patch = _patched_mcp(chunks)

    with transport_patch, toolset_patch:
        result = await research(mcp_server_command=MCP_COMMAND, decision=decision, query="q")

    assert [item.source for item in result.evidence] == ["knowledge_base", "knowledge_base"]
    assert [item.citation for item in result.evidence] == ["a.pdf", "b.pdf"]
    assert [item.text for item in result.evidence] == ["one", "two"]


@pytest.mark.asyncio
async def test_research_kb_route_with_no_results_returns_empty_evidence():
    decision = GatekeeperDecision(route="kb", reasoning="ok")
    _, _, transport_patch, toolset_patch = _patched_mcp([])

    with transport_patch, toolset_patch:
        result = await research(mcp_server_command=MCP_COMMAND, decision=decision, query="q")

    assert result.evidence == []


@pytest.mark.asyncio
async def test_research_kb_route_rejects_malformed_tool_result():
    decision = GatekeeperDecision(route="kb", reasoning="ok")
    _, _, transport_patch, toolset_patch = _patched_mcp("not a list")

    with transport_patch, toolset_patch, pytest.raises(KnowledgeBaseToolError):
        await _research_kb(mcp_server_command=MCP_COMMAND, decision=decision, query="q")


@pytest.mark.asyncio
async def test_research_kb_route_maps_tool_error_to_knowledge_base_unavailable():
    """AGT-012: a raw fastmcp ToolError (e.g. the RAG platform unreachable from inside the MCP
    subprocess) must surface as this project's own KnowledgeBaseUnavailable, not leak the raw
    MCP-library exception type up to the API layer."""
    decision = GatekeeperDecision(route="kb", reasoning="ok")
    fake_transport = MagicMock(name="fake_transport")
    fake_toolset = MagicMock(name="fake_toolset")
    fake_toolset.direct_call_tool = AsyncMock(side_effect=ToolError("RAG platform unreachable"))
    transport_patch = patch("app.agents.research.StdioTransport", return_value=fake_transport)
    toolset_patch = patch("app.agents.research.MCPToolset", return_value=fake_toolset)

    with transport_patch, toolset_patch, pytest.raises(KnowledgeBaseUnavailable):
        await _research_kb(mcp_server_command=MCP_COMMAND, decision=decision, query="q")
