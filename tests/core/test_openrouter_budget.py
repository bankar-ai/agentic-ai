import time

import httpx
import pytest

from app.core import openrouter_budget
from app.core.openrouter_budget import maybe_record_openrouter_budget


def _reset():
    openrouter_budget._last_checked_at = None
    openrouter_budget._credits_gauge = None
    openrouter_budget._usage_gauge = None


@pytest.mark.asyncio
async def test_records_gauges_from_a_successful_response(monkeypatch):
    """Regression test for a real live bug: `_last_checked_at` defaulting to `0.0` meant a fresh
    container (where `time.monotonic()` itself starts near 0, since its reference epoch resets
    per-process) always looked "recently checked" and silently skipped every single time. The
    sentinel is `None` now specifically so the very first call -- exactly this test's scenario --
    always proceeds regardless of what `now` happens to be."""
    _reset()
    set_calls = []

    class _FakeGauge:
        def set(self, amount, attributes=None):
            set_calls.append((amount, attributes))

    monkeypatch.setattr(openrouter_budget, "_get_gauges", lambda: (_FakeGauge(), _FakeGauge()))

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"total_credits": 5, "total_usage": 0.0017}}

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=5.0: _FakeAsyncClient())

    await maybe_record_openrouter_budget("fake-key")

    assert (5, None) in set_calls
    assert (0.0017, None) in set_calls
    _reset()


@pytest.mark.asyncio
async def test_skips_the_check_within_the_throttle_window(monkeypatch):
    _reset()
    openrouter_budget._last_checked_at = time.monotonic()
    call_count = {"n": 0}

    class _FakeAsyncClient:
        async def __aenter__(self):
            call_count["n"] += 1
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=5.0: _FakeAsyncClient())

    await maybe_record_openrouter_budget("fake-key")

    assert call_count["n"] == 0
    _reset()


@pytest.mark.asyncio
async def test_never_raises_on_a_failed_request(monkeypatch):
    _reset()

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=5.0: _FakeAsyncClient())

    await maybe_record_openrouter_budget("fake-key")  # must not raise
    _reset()
