"""Shared `asyncpg` connection pool for `agentic-ai`'s own Postgres (AGT-041/AGT-051).

One pool per process, reused by every module that needs this database (`query_cache.py`,
`session_store.py`) -- a separate pool per table would multiply connection count against Neon's
free-tier limit for no benefit, since every table here lives in the same database.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool(database_url: str | None) -> asyncpg.Pool | None:
    """Lazily creates the pool on first real use -- never at import time or on `/health`.
    Returns `None` when `DATABASE_URL` isn't configured.
    """
    global _pool
    if not database_url:
        return None
    if _pool is None:
        _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    return _pool


@asynccontextmanager
async def tenant_scoped(pool: asyncpg.Pool, user_id: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection with `app.current_user_id` set as a transaction-local Postgres session
    variable (AGT-059), for the RLS policies on `query_history`/`user_sessions` to filter by --
    `set_config(..., true)` is `SET LOCAL`'s functional equivalent, usable with parameter binding
    (`SET LOCAL` itself doesn't support bound parameters). Scoped to one transaction, so it
    can't leak into a later query on the same pooled connection once this block exits.

    Defense in depth, not a replacement for each query's own `WHERE user_id = $1` -- both layers
    stay in place, each independently sufficient to prevent one user's row from being visible to
    another.
    """
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT set_config('app.current_user_id', $1, true)", user_id)
        yield conn
