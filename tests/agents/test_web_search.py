from unittest.mock import patch

import pytest

from app.agents.schemas import Evidence
from app.agents.web_search import search_web


@pytest.mark.asyncio
async def test_search_web_returns_labeled_evidence():
    fake_results = [
        {"title": "France - Wikipedia", "href": "https://en.wikipedia.org/wiki/France", "body": "Paris is the capital of France."},
    ]
    with patch("app.agents.web_search._run_ddgs_search", return_value=fake_results):
        results = await search_web("capital of France")

    assert len(results) == 1
    assert isinstance(results[0], Evidence)
    assert results[0].source == "web"
    assert results[0].citation == "https://en.wikipedia.org/wiki/France"
    assert "Paris" in results[0].text


@pytest.mark.asyncio
async def test_search_web_returns_empty_list_on_failure():
    with patch("app.agents.web_search._run_ddgs_search", side_effect=RuntimeError("network error")):
        results = await search_web("capital of France")

    assert results == []
