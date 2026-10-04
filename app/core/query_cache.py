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
        row = await self._pool.fetchrow(
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
        await self._pool.execute(
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


_pool: asyncpg.Pool | None = None


async def get_query_cache(database_url: str | None) -> QueryCache | None:
    """Lazily creates the connection pool (and the table, idempotently) on first real use --
    never at import time or on `/health`, so a cold Cloud Run instance that never actually serves
    a `/query` call never opens a database connection at all. Returns `None` when `DATABASE_URL`
    isn't configured, making caching/history an opt-in capability, not a hard dependency.
    """
    global _pool
    if not database_url:
        return None
    if _pool is None:
        _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
        async with _pool.acquire() as conn:
            await conn.execute(_SCHEMA)
    return QueryCache(_pool)
