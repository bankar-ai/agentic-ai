"""Custom LLM-call duration metric (AGT-021).

Named `llm_generation_duration_seconds` to match `enterprise-rag-platform`'s own hand-instrumented
metric convention -- not because the two projects share data, but so the existing "LLM generation
duration" panel pattern could in principle be reused for either project's dashboard without
renaming anything. FastAPI/httpx auto-instrumentation (AGT-018) gives HTTP-level timing for free;
this is the one thing it can't see -- how long a PydanticAI `agent.run()` call itself took.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.metrics import Histogram

from app.core.telemetry import get_meter

_histogram: Histogram | None = None


def _get_histogram() -> Histogram:
    global _histogram
    if _histogram is None:
        _histogram = get_meter().create_histogram(
            name="llm_generation_duration_seconds",
            unit="s",
            description="Duration of a single PydanticAI agent.run() call, by agent name",
        )
    return _histogram


@contextmanager
def measure_llm_call(agent_name: str) -> Iterator[None]:
    """Record how long the wrapped `agent.run()` call took, tagged with which agent it was."""
    start = time.monotonic()
    try:
        yield
    finally:
        _get_histogram().record(time.monotonic() - start, attributes={"agent": agent_name})
