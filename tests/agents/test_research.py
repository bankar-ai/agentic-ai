from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.research import _research_kb, research
from app.agents.schemas import Evidence, GatekeeperDecision, ResearchResult


@pytest.mark.asyncio
async def test_research_web_fallback_route_uses_web_search():
    decision = GatekeeperDecision(route="web_fallback", reasoning="no KB match")
    fake_evidence = [Evidence(text="Sunny, 28C", source="web", citation="https://weather.example")]

    with patch("app.agents.research.search_web", AsyncMock(return_value=fake_evidence)):
        result = await research(model=None, mcp_server_command=[], decision=decision, query="weather in Pune today")

    assert isinstance(result, ResearchResult)
    assert result.evidence == fake_evidence


@pytest.mark.asyncio
async def test_research_refuse_route_returns_no_evidence():
    decision = GatekeeperDecision(route="refuse", reasoning="unanswerable")

    result = await research(model=None, mcp_server_command=[], decision=decision, query="anything")

    assert result.evidence == []


@pytest.mark.asyncio
async def test_research_kb_route_wires_stdio_transport_toolset_and_agent():
    """Construction-level test for the "kb" route's MCP wiring, without a live model or a real
    subprocess: patches StdioTransport, MCPToolset, and Agent, then asserts each wiring step --
    the command/args split, the transport-into-toolset wrap, and the toolset-into-Agent(toolsets=)
    pass-through -- happened exactly as `_research_kb` intends. A regression in any of these three
    steps (e.g. swapping command/args, forgetting to wrap in MCPToolset, or passing toolsets under
    a different kwarg) would fail this test, even though none of it touches a live Ollama model or
    spawns the real `python -m app.mcp_server.server` subprocess.
    """
    decision = GatekeeperDecision(route="kb", reasoning="kb has the answer", top_k=3, rerank=True)
    fake_evidence = [Evidence(text="answer text", source="knowledge_base", citation="doc.pdf")]
    fake_transport = MagicMock(name="fake_transport")
    fake_toolset = MagicMock(name="fake_toolset")
    fake_model = MagicMock(name="fake_model")

    fake_agent = MagicMock(name="fake_agent")
    fake_agent.__aenter__ = AsyncMock(return_value=fake_agent)
    fake_agent.__aexit__ = AsyncMock(return_value=None)
    fake_agent.run = AsyncMock(return_value=MagicMock(output=fake_evidence))

    with (
        patch("app.agents.research.StdioTransport", return_value=fake_transport) as mock_transport_cls,
        patch("app.agents.research.MCPToolset", return_value=fake_toolset) as mock_toolset_cls,
        patch("app.agents.research.Agent", return_value=fake_agent) as mock_agent_cls,
    ):
        result = await _research_kb(
            model=fake_model,
            mcp_server_command=["python", "-m", "app.mcp_server.server"],
            decision=decision,
            query="what is the refund policy?",
        )

    mock_transport_cls.assert_called_once_with(command="python", args=["-m", "app.mcp_server.server"])
    mock_toolset_cls.assert_called_once_with(fake_transport)
    _, agent_kwargs = mock_agent_cls.call_args
    assert mock_agent_cls.call_args.args[0] is fake_model
    assert agent_kwargs["toolsets"] == [fake_toolset]
    fake_agent.run.assert_awaited_once()
    assert result == fake_evidence
