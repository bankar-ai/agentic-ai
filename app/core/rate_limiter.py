"""Per-user rate limiting on the LLM/retrieval-calling endpoints (AGT-058).

Backed by the existing shared Neon Postgres pool (`app/core/db.py`), not an in-memory counter --
Cloud Run can run multiple instances, and an in-memory counter would miss requests that happen to
land on a different instance, silently defeating the limit. A simple fixed-window counter is
enough at this scale; no need for a more sophisticated sliding-window/token-bucket algorithm.

Deliberately optional, same pattern as `query_cache.py`/`session_store.py`: `DATABASE_URL` unset
means `get_rate_limiter` returns `None` and callers skip the check entirely -- no hard dependency
on this existing.
"""

from datetime import UTC, datetime, timedelta

import asyncpg

from app.core.db import get_pool

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rate_limit_events (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rate_limit_events_user_window
    ON rate_limit_events (user_id, created_at DESC);
"""

# 20 requests per 10 minutes per user -- a reasonable default for a demo-scale app (comfortably
# above normal interactive use, low enough to blunt a scripted burst). Adjustable if it proves too
# strict or too loose in practice.
WINDOW = timedelta(minutes=10)
MAX_REQUESTS_PER_WINDOW = 20


class RateLimiter:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def check_and_record(self, user_id: str) -> bool:
        """Returns `True` if this request is allowed (and records it), `False` if the user is
        over the limit for the current window (the request is NOT recorded in that case -- an
        already-blocked user retrying doesn't count further against themselves).
        """
        cutoff = datetime.now(UTC) - WINDOW
        count = await self._pool.fetchval(
            "SELECT count(*) FROM rate_limit_events WHERE user_id = $1 AND created_at > $2",
            user_id,
            cutoff,
        )
        if count >= MAX_REQUESTS_PER_WINDOW:
            return False
        await self._pool.execute("INSERT INTO rate_limit_events (user_id) VALUES ($1)", user_id)
        # Piggybacked cleanup -- cheap, keeps the table from growing unbounded without a separate
        # scheduled job. Deletes this user's own old rows only, not a table-wide scan.
        await self._pool.execute(
            "DELETE FROM rate_limit_events WHERE user_id = $1 AND created_at <= $2", user_id, cutoff
        )
        return True


_schema_ready = False


async def get_rate_limiter(database_url: str | None) -> RateLimiter | None:
    global _schema_ready
    pool = await get_pool(database_url)
    if pool is None:
        return None
    if not _schema_ready:
        async with pool.acquire() as conn:
            await conn.execute(_SCHEMA)
        _schema_ready = True
    return RateLimiter(pool)
