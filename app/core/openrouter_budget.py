"""Live OpenRouter account credit balance, surfaced on the dashboard (AGT-031).

The project owner wanted to see the *live, authoritative* shared budget -- not a number this app
estimates, but what OpenRouter's own `/api/v1/credits` endpoint reports right now. Checked at most
once per `_CHECK_INTERVAL_SECONDS`, piggybacked onto real query traffic (no new scheduler, no
change to `/health`'s own "zero external dependencies" design from AGT-022) -- best-effort and
never allowed to affect the query it rode in on.
"""

import logging
import time

import httpx

# `Gauge` is still an experimental export in the installed opentelemetry-api version -- re-exported
# as `_Gauge` there, not `Gauge` (confirmed via opentelemetry/metrics/__init__.py's own imports).
from opentelemetry.metrics import _Gauge as Gauge

from app.core.telemetry import get_meter

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 600  # 10 minutes -- a live number, not a real-time one; cheap either way
_CREDITS_URL = "https://openrouter.ai/api/v1/credits"

_last_checked_at: float = 0.0
_credits_gauge: Gauge | None = None
_usage_gauge: Gauge | None = None


def _get_gauges() -> tuple[Gauge, Gauge]:
    global _credits_gauge, _usage_gauge
    if _credits_gauge is None:
        _credits_gauge = get_meter().create_gauge(
            name="agentic_ai_openrouter_account_total_credits_usd",
            unit="USD",
            description="OpenRouter account's total funded credits, shared across every key in the workspace",
        )
    if _usage_gauge is None:
        _usage_gauge = get_meter().create_gauge(
            name="agentic_ai_openrouter_account_total_usage_usd",
            unit="USD",
            description="OpenRouter account's total lifetime usage, shared across every key in the workspace",
        )
    return _credits_gauge, _usage_gauge


async def maybe_record_openrouter_budget(api_key: str) -> None:
    """Refresh the live account-credit gauges if the throttle window has elapsed. Never raises --
    a failed budget check must never affect the query that triggered it.
    """
    global _last_checked_at
    now = time.monotonic()
    logger.info("openrouter_budget: entered, now=%s last_checked_at=%s", now, _last_checked_at)
    if now - _last_checked_at < _CHECK_INTERVAL_SECONDS:
        logger.info("openrouter_budget: throttled, skipping")
        return
    _last_checked_at = now

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(_CREDITS_URL, headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        data = response.json()["data"]
        credits_gauge, usage_gauge = _get_gauges()
        credits_gauge.set(data["total_credits"])
        usage_gauge.set(data["total_usage"])
    except Exception:
        logger.exception("Failed to refresh OpenRouter account budget gauges; continuing")
