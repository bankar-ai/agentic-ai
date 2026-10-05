"""Server-side query result cache + durable history (AGT-041).

`agentic-ai` had no database of its own until now (a deliberate AGT-024-era scope call --
client-side `localStorage` only). One table, `query_history`, does double duty: a 24h cache (a
repeat question from the same user, same mode, returns the stored answer instantly instead of
re-running the pipeline -- real money/time for Agentic mode's ~100s LLM pipeline) and a durable
audit log (every completed/refused query is inserted, cache hit or miss). A genuinely new
dependency (`asyncpg`) and new infrastructure (a dedicated Neon Postgres project, separate from
`enterprise-rag-platform`'s own, per this portfolio's "separate database per product" convention)
-- see `.ai/tickets/AGT-041.md` for the approved approach.

Entirely optional: `DATABASE_URL` unset means `get_query_cache` returns `None` and both
`/query`/`/query/direct` behave exactly as before this ticket -- no hard dependency on this
database existing.
"""

import base64
import json
from datetime import UTC, datetime, timedelta

import asyncpg
from pydantic import BaseModel

from app.core.db import get_pool, tenant_scoped

CACHE_TTL = timedelta(hours=24)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS query_history (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    question_normalized TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    refused BOOLEAN NOT NULL,
    trace JSONB NOT NULL DEFAULT '[]',
    source_filename TEXT,
    duration_seconds DOUBLE PRECISION,
    served_from_cache BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS query_history_cache_lookup
    ON query_history (user_id, mode, question_normalized, created_at DESC);

-- AGT-059: database-level defense in depth, on top of (not instead of) every query's own
-- `WHERE user_id = $1`. FORCE is required: without it, RLS policies are silently bypassed for
-- the table owner role, which is exactly the role this app connects as -- making the policy
-- cosmetic rather than enforced. Fail-closed: `current_setting(..., true)` returns NULL when
-- app.current_user_id was never set for this transaction, and `user_id = NULL` is never true, so
-- a query that somehow runs without `tenant_scoped` sees zero rows, not every user's rows.
ALTER TABLE query_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE query_history FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS query_history_tenant_isolation ON query_history;
CREATE POLICY query_history_tenant_isolation ON query_history
    USING (user_id = current_setting('app.current_user_id', true));
"""


def normalize_question(question: str) -> str:
    """Case/whitespace-insensitive dedup key -- "What is X?" and "what is x?" hit the same cache
    entry, but no semantic/embedding matching (YAGNI: a literal repeat is the common case this
    was asked for, not near-duplicate detection)."""
    return " ".join(question.strip().lower().split())


def decode_user_id(access_token: str) -> str | None:
    """Best-effort decode of the JWT's `sub` claim -- deliberately NOT signature-verified.
    `agentic-ai` doesn't hold `enterprise-rag-platform`'s signing key, and doesn't need to: that
    platform already validated this token when it issued it and when it serves the actual
    retrieval request this token is forwarded to. Used here only as a cache/history grouping key,
    never as an auth decision -- a malformed or tampered token just means no cache key (falls
    back to always-miss), not a security gap, since forwarded requests still live or die on that
    platform's own validation. Returns None on any malformed input.
    """
    try:
        payload_b64 = access_token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        sub = payload.get("sub")
        return sub if isinstance(sub, str) else None
    except (IndexError, ValueError):
        return None


class CachedQueryResult(BaseModel):
    answer: str
    refused: bool
    trace: list[dict]
    source_filename: str | None


class HistoryEntry(BaseModel):
    """One row of the caller's own query history (AGT-044 part 2) -- the durable, server-side
    source of truth a second device/tab can read, unlike the original `localStorage`-only list
    (AGT-027), which only the browser that made each query could ever see."""

    question: str
    answer: str
    refused: bool
    mode: str
    trace: list[dict]
    source_filename: str | None
    duration_seconds: float | None
    created_at: datetime


class QueryCache:
    """Thin wrapper around an `asyncpg.Pool` -- a class (not bare module functions) so tests can
    construct one against a fake/mocked pool without touching the module-level singleton below.
    """

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def lookup(self, user_id: str, mode: str, question: str) -> CachedQueryResult | None:
        """A cache hit requires a non-refused row for this exact user+mode+normalized-question
        within the last 24h -- isolated by `user_id` in the query itself, so one user's cache can
        never serve another user's cached answer regardless of how similar their questions are.
        """
        cutoff = datetime.now(UTC) - CACHE_TTL
        async with tenant_scoped(self._pool, user_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT answer, refused, trace, source_filename
                FROM query_history
                WHERE user_id = $1 AND mode = $2 AND question_normalized = $3
                  AND refused = FALSE AND created_at > $4
                ORDER BY created_at DESC
                LIMIT 1
                """,
                user_id,
                mode,
                normalize_question(question),
                cutoff,
            )
        if row is None:
            return None
        trace = row["trace"]
        return CachedQueryResult(
            answer=row["answer"],
            refused=row["refused"],
            trace=json.loads(trace) if isinstance(trace, str) else trace,
            source_filename=row["source_filename"],
        )

    async def list_recent(self, user_id: str, limit: int = 5) -> list[HistoryEntry]:
        """The caller's own most recent queries across both modes, newest first (AGT-044 part 2)
        -- the server-side source of truth that makes two devices (or a second tab reading this
        instead of its own `localStorage`) agree on the same recent history, not just the one
        browser that happened to ask each question."""
        async with tenant_scoped(self._pool, user_id) as conn:
            rows = await conn.fetch(
                """
                SELECT question, answer, refused, mode, trace, source_filename, duration_seconds, created_at
                FROM query_history
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
        entries = []
        for row in rows:
            trace = row["trace"]
            entries.append(
                HistoryEntry(
                    question=row["question"],
                    answer=row["answer"],
                    refused=row["refused"],
                    mode=row["mode"],
                    trace=json.loads(trace) if isinstance(trace, str) else trace,
                    source_filename=row["source_filename"],
                    duration_seconds=row["duration_seconds"],
                    created_at=row["created_at"],
                )
            )
        return entries

    async def record(
        self,
        *,
        user_id: str,
        mode: str,
        question: str,
        answer: str,
        refused: bool,
        trace: list[dict],
        source_filename: str | None,
        duration_seconds: float | None,
        served_from_cache: bool,
    ) -> None:
        """Inserted on every completed/refused query, hit or miss -- the audit-log half of this
        table's double duty. Never raised to the caller: a history-write failure must not break
        the query response the user is actually waiting on (see call sites in `app/api/router.py`
        for the try/except wrapping this)."""
        async with tenant_scoped(self._pool, user_id) as conn:
            await conn.execute(
                """
                INSERT INTO query_history
                    (user_id, mode, question_normalized, question, answer, refused, trace,
                     source_filename, duration_seconds, served_from_cache)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                user_id,
                mode,
                normalize_question(question),
                question,
                answer,
                refused,
                json.dumps(trace),
                source_filename,
                duration_seconds,
                served_from_cache,
            )


_schema_ready = False


async def get_query_cache(database_url: str | None) -> QueryCache | None:
    """Lazily creates this table (idempotently, on the process-wide shared pool -- see
    `app/core/db.py`) on first real use, never at import time or on `/health`, so a cold Cloud Run
    instance that never actually serves a `/query` call never opens a database connection at all.
    Returns `None` when `DATABASE_URL` isn't configured, making caching/history an opt-in
    capability, not a hard dependency.
    """
    global _schema_ready
    pool = await get_pool(database_url)
    if pool is None:
        return None
    if not _schema_ready:
        async with pool.acquire() as conn:
            await conn.execute(_SCHEMA)
        _schema_ready = True
    return QueryCache(pool)
