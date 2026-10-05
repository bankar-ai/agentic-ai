import pytest

from app.core.session_store import SessionStore
from tests.core._fake_pool import FakePool


@pytest.mark.asyncio
async def test_get_refresh_token_returns_none_when_nothing_stored():
    pool = FakePool(fetchval_result=None)
    store = SessionStore(pool)

    assert await store.get_refresh_token("user-1") is None


@pytest.mark.asyncio
async def test_get_refresh_token_returns_the_stored_value():
    pool = FakePool(fetchval_result="a-refresh-token")
    store = SessionStore(pool)

    result = await store.get_refresh_token("user-1")

    assert result == "a-refresh-token"
    _query, args = pool.fetchval_calls[0]
    assert args == ("user-1",)


@pytest.mark.asyncio
async def test_save_refresh_token_upserts_with_user_id_and_token():
    pool = FakePool()
    store = SessionStore(pool)

    await store.save_refresh_token("user-1", "a-refresh-token")

    _query, args = pool.execute_calls[0]
    assert args == ("user-1", "a-refresh-token")


@pytest.mark.asyncio
async def test_delete_removes_by_user_id():
    pool = FakePool()
    store = SessionStore(pool)

    await store.delete("user-1")

    _query, args = pool.execute_calls[0]
    assert args == ("user-1",)


@pytest.mark.asyncio
async def test_every_method_sets_the_tenant_scoping_session_variable():
    """AGT-059: database-level defense in depth -- every call sets `app.current_user_id` as a
    transaction-local session variable for the RLS policy to filter on."""
    pool = FakePool(fetchval_result=None)
    store = SessionStore(pool)

    await store.get_refresh_token("user-1")
    await store.save_refresh_token("user-1", "token")
    await store.delete("user-1")

    assert pool.set_config_calls == [("user-1",), ("user-1",), ("user-1",)]
