"""Server-side refresh-token storage for silent session renewal (AGT-051).

A separate table from `AGT-041`'s `query_history` -- a refresh token is a materially different
kind of data (a long-lived credential for another platform, not a cache of this app's own
answers), so keeping it in its own table keeps that boundary clear even though both live in the
same Neon database, sharing the one process-wide pool (`app/core/db.py`).

Deliberately optional, same pattern as `query_cache.py`: `DATABASE_URL` unset means
`get_session_store` returns `None` and `StaticTokenAuth.refresh()` falls back to its original
"please log in again" behavior -- no hard dependency on this existing. Approved by the project
owner 2026-10-05 after an explicit trade-off discussion (`AGT-051`): storing another platform's
refresh token is a trust-model decision, not just an engineering one.
"""

import asyncpg

from app.core.db import get_pool, tenant_scoped

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_sessions (
    user_id TEXT PRIMARY KEY,
    refresh_token TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- AGT-059: same database-level defense in depth as query_history -- see that table's schema for
-- the full rationale (FORCE is required, fail-closed by construction).
ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_sessions_tenant_isolation ON user_sessions;
CREATE POLICY user_sessions_tenant_isolation ON user_sessions
    USING (user_id = current_setting('app.current_user_id', true));
"""


class SessionStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def save_refresh_token(self, user_id: str, refresh_token: str) -> None:
        """Upsert -- a fresh login or a rotated refresh token both just replace whatever was
        stored, there is only ever one live refresh token per user."""
        async with tenant_scoped(self._pool, user_id) as conn:
            await conn.execute(
                """
                INSERT INTO user_sessions (user_id, refresh_token, updated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (user_id) DO UPDATE SET refresh_token = $2, updated_at = now()
                """,
                user_id,
                refresh_token,
            )

    async def get_refresh_token(self, user_id: str) -> str | None:
        async with tenant_scoped(self._pool, user_id) as conn:
            return await conn.fetchval("SELECT refresh_token FROM user_sessions WHERE user_id = $1", user_id)

    async def delete(self, user_id: str) -> None:
        """Called when a stored refresh token turns out to be invalid/revoked server-side --
        no point keeping a dead credential around for the next attempt to fail on again."""
        async with tenant_scoped(self._pool, user_id) as conn:
            await conn.execute("DELETE FROM user_sessions WHERE user_id = $1", user_id)


_schema_ready = False


async def get_session_store(database_url: str | None) -> SessionStore | None:
    global _schema_ready
    pool = await get_pool(database_url)
    if pool is None:
        return None
    if not _schema_ready:
        async with pool.acquire() as conn:
            await conn.execute(_SCHEMA)
        _schema_ready = True
    return SessionStore(pool)
