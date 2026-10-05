import pytest

from app.core.session_store import SessionStore


class _FakePool:
    """Stands in for `asyncpg.Pool` -- records calls so tests can assert on the exact SQL
    parameters without a real Postgres connection."""

    def __init__(self, fetchval_result=None):
        self.fetchval_result = fetchval_result
        self.execute_calls: list[tuple] = []
        self.fetchval_calls: list[tuple] = []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))

    async def fetchval(self, query, *args):
        self.fetchval_calls.append((query, args))
        return self.fetchval_result


@pytest.mark.asyncio
async def test_get_refresh_token_returns_none_when_nothing_stored():
    pool = _FakePool(fetchval_result=None)
    store = SessionStore(pool)

    assert await store.get_refresh_token("user-1") is None


@pytest.mark.asyncio
async def test_get_refresh_token_returns_the_stored_value():
    pool = _FakePool(fetchval_result="a-refresh-token")
    store = SessionStore(pool)

    result = await store.get_refresh_token("user-1")

    assert result == "a-refresh-token"
    _query, args = pool.fetchval_calls[0]
    assert args == ("user-1",)


@pytest.mark.asyncio
async def test_save_refresh_token_upserts_with_user_id_and_token():
    pool = _FakePool()
    store = SessionStore(pool)

    await store.save_refresh_token("user-1", "a-refresh-token")

    _query, args = pool.execute_calls[0]
    assert args == ("user-1", "a-refresh-token")


@pytest.mark.asyncio
async def test_delete_removes_by_user_id():
    pool = _FakePool()
    store = SessionStore(pool)

    await store.delete("user-1")

    _query, args = pool.execute_calls[0]
    assert args == ("user-1",)
