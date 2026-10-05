"""Shared `asyncpg` connection pool for `agentic-ai`'s own Postgres (AGT-041/AGT-051).

One pool per process, reused by every module that needs this database (`query_cache.py`,
`session_store.py`) -- a separate pool per table would multiply connection count against Neon's
free-tier limit for no benefit, since every table here lives in the same database.
"""

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
