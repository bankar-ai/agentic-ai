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


_RETRY_DELAY_SECONDS = 1.0


async def search_web(query: str, max_results: int = 3) -> list[Evidence]:
    """Run a web search and return source-labeled evidence, or `[]` if both attempts come back
    empty.

    AGT-033: a live query found `ddgs` (which itself already tries several underlying search
    backends per call -- google/mojeek/brave/yahoo/duckduckgo, confirmed via logs) returning zero
    results for an ordinary factual question, even with some of those backends responding `200`
    -- consistent with public search engines soft-blocking (a `200` with an empty/CAPTCHA page,
    not an outright error) automated traffic from cloud-provider IP ranges. A later identical
    query succeeded cleanly, so this is intermittent, not constant -- one retry, not a paid
    fallback provider, is the proportionate fix: cheap, no new dependency, and directly targets
    "transient block this one time" rather than "this search engine is unusable."
    """
    raw_results: list[dict] = []
    for attempt in range(2):
        try:
            raw_results = await asyncio.to_thread(_run_ddgs_search, query, max_results)
        except Exception:
            logger.exception("Web search fallback failed for query: %s (attempt %d)", query, attempt + 1)
            raw_results = []
        if raw_results:
            break
        if attempt == 0:
            logger.warning("Web search returned zero results on first attempt, retrying once: %s", query)
            await asyncio.sleep(_RETRY_DELAY_SECONDS)

    # AGT-029: web content is the least trusted input this system handles -- strip HTML, control
    # characters, and invisible/bidi-override unicode before it ever reaches a prompt.
    return [
        Evidence(text=sanitize_evidence_text(result["body"]), source="web", citation=result["href"])
        for result in raw_results
        if "body" in result and "href" in result
    ]
