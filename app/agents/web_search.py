"""Web search fallback, used only when the Gatekeeper flags KB evidence as insufficient.

Uses `ddgs` (DuckDuckGo search) -- free, no API key. Any failure here degrades to an empty
result list rather than raising, so a flaky or rate-limited web search can never crash the
graph; the Gatekeeper/Verifier logic (Tasks 8/11) treats empty evidence as grounds to refuse.
"""

import asyncio
import logging

from ddgs import DDGS

from app.agents.sanitize import sanitize_evidence_text
from app.agents.schemas import Evidence

logger = logging.getLogger(__name__)


def _run_ddgs_search(query: str, max_results: int) -> list[dict]:
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def search_web(query: str, max_results: int = 3) -> list[Evidence]:
    """Run a web search and return source-labeled evidence, or `[]` on any failure."""
    try:
        raw_results = await asyncio.to_thread(_run_ddgs_search, query, max_results)
    except Exception:
        logger.exception("Web search fallback failed for query: %s", query)
        return []

    # AGT-029: web content is the least trusted input this system handles -- strip HTML, control
    # characters, and invisible/bidi-override unicode before it ever reaches a prompt.
    return [
        Evidence(text=sanitize_evidence_text(result["body"]), source="web", citation=result["href"])
        for result in raw_results
        if "body" in result and "href" in result
    ]
