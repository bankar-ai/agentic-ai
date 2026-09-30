from unittest.mock import AsyncMock, patch

import pytest

from app.agents.research import research
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
