"""Query outcome + verifier-retry metrics (AGT-022).

`AGT-021` added *duration* histograms but nothing that counts outcomes -- there was no way to ask
"how many queries failed today" or "what's the refusal rate" without reading raw logs/traces one
at a time. This fills that gap: one counter for how each `/query` call ended, one histogram for
how many Verifier->Research retries it took to get there.
"""

from opentelemetry.metrics import Counter, Histogram

from app.core.telemetry import get_meter

_outcome_counter: Counter | None = None
_retry_histogram: Histogram | None = None


def _get_outcome_counter() -> Counter:
    global _outcome_counter
    if _outcome_counter is None:
        _outcome_counter = get_meter().create_counter(
            name="agentic_ai_query_outcome_total",
            description="Count of /query calls by how they ended (completed, refused, error)",
        )
    return _outcome_counter


def _get_retry_histogram() -> Histogram:
    global _retry_histogram
    if _retry_histogram is None:
        _retry_histogram = get_meter().create_histogram(
            name="agentic_ai_verifier_retry_count",
            unit="1",
            description="Number of Verifier -> Research retries a query took before reaching a result",
        )
    return _retry_histogram


def record_query_outcome(outcome: str) -> None:
    """Record how a `/query` call ended. `outcome` is one of completed/refused/error."""
    _get_outcome_counter().add(1, attributes={"outcome": outcome})


def record_retry_count(retry_count: int) -> None:
    """Record how many Verifier -> Research retries a completed/refused query took."""
    _get_retry_histogram().record(retry_count)
