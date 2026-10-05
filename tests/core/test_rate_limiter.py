import pytest

from app.core.rate_limiter import MAX_REQUESTS_PER_WINDOW, RateLimiter


class _FakePool:
    def __init__(self, fetchval_result=0):
        self.fetchval_result = fetchval_result
        self.execute_calls: list[tuple] = []

    async def fetchval(self, query, *args):
        return self.fetchval_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


@pytest.mark.asyncio
async def test_check_and_record_allows_a_request_under_the_limit():
    pool = _FakePool(fetchval_result=0)
    limiter = RateLimiter(pool)

    allowed = await limiter.check_and_record("user-1")

    assert allowed is True
    insert_calls = [c for c in pool.execute_calls if "INSERT" in c[0]]
    assert len(insert_calls) == 1
    assert insert_calls[0][1] == ("user-1",)


@pytest.mark.asyncio
async def test_check_and_record_blocks_a_request_at_the_limit():
    pool = _FakePool(fetchval_result=MAX_REQUESTS_PER_WINDOW)
    limiter = RateLimiter(pool)

    allowed = await limiter.check_and_record("user-1")

    assert allowed is False
    # Not recorded -- an already-blocked user retrying doesn't count further against themselves.
    assert pool.execute_calls == []


@pytest.mark.asyncio
async def test_check_and_record_scopes_the_count_query_by_user():
    pool = _FakePool(fetchval_result=0)
    limiter = RateLimiter(pool)

    await limiter.check_and_record("user-1")

    # fetchval's args aren't recorded by this fake, but execute's INSERT confirms scoping --
    # re-check via a second fake that does record fetchval calls too.
    class _RecordingPool(_FakePool):
        def __init__(self, fetchval_result=0):
            super().__init__(fetchval_result)
            self.fetchval_calls: list[tuple] = []

        async def fetchval(self, query, *args):
            self.fetchval_calls.append((query, args))
            return self.fetchval_result

    recording_pool = _RecordingPool(fetchval_result=0)
    recording_limiter = RateLimiter(recording_pool)
    await recording_limiter.check_and_record("user-1")
    _query, args = recording_pool.fetchval_calls[0]
    assert args[0] == "user-1"
