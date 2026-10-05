"""Shared fake standing in for `asyncpg.Pool` across `app/core/*_store.py`/`*_cache.py` tests --
supports the `pool.acquire()` -> `conn.transaction()` -> query pattern `app.core.db.tenant_scoped`
uses, recording every call (including the `set_config` tenant-scoping call) so tests can assert
on exact SQL parameters without a real Postgres connection.
"""


class _FakeConnection:
    def __init__(self, pool: "FakePool"):
        self._pool = pool

    async def execute(self, query, *args):
        if "set_config" in query:
            self._pool.set_config_calls.append(args)
            return
        self._pool.execute_calls.append((query, args))

    async def fetchrow(self, query, *args):
        self._pool.fetchrow_calls.append((query, args))
        return self._pool.fetchrow_result

    async def fetch(self, query, *args):
        self._pool.fetch_calls.append((query, args))
        return self._pool.fetch_result

    async def fetchval(self, query, *args):
        self._pool.fetchval_calls.append((query, args))
        return self._pool.fetchval_result

    def transaction(self):
        return _FakeTransaction()


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeAcquireContext:
    def __init__(self, pool: "FakePool"):
        self._pool = pool

    async def __aenter__(self) -> _FakeConnection:
        return _FakeConnection(self._pool)

    async def __aexit__(self, *exc_info):
        return False


class FakePool:
    def __init__(self, fetchrow_result=None, fetch_result=None, fetchval_result=None):
        self.fetchrow_result = fetchrow_result
        self.fetch_result = fetch_result or []
        self.fetchval_result = fetchval_result
        self.fetchrow_calls: list[tuple] = []
        self.fetch_calls: list[tuple] = []
        self.fetchval_calls: list[tuple] = []
        self.execute_calls: list[tuple] = []
        self.set_config_calls: list[tuple] = []

    def acquire(self):
        return _FakeAcquireContext(self)

    # Also usable directly (schema-init calls `pool.acquire()...execute(_SCHEMA)`, same path).
    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
