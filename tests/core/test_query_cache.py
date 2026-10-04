import base64
import json

import pytest

from app.core.query_cache import QueryCache, decode_user_id, normalize_question


def _fake_jwt(payload: dict) -> str:
    def b64(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS256'})}.{b64(payload)}.fakesignature"


def test_normalize_question_is_case_and_whitespace_insensitive():
    assert normalize_question("  What IS   the capital?  ") == "what is the capital?"
    assert normalize_question("What is the capital?") == normalize_question("what   is the capital?")


def test_decode_user_id_reads_the_sub_claim():
    token = _fake_jwt({"sub": "989196ec-b5f7-4cbc-8acf-8506cf4ffcfc", "role": "user"})
    assert decode_user_id(token) == "989196ec-b5f7-4cbc-8acf-8506cf4ffcfc"


def test_decode_user_id_returns_none_for_malformed_token():
    assert decode_user_id("not-a-jwt") is None
    assert decode_user_id("") is None


def test_decode_user_id_returns_none_when_sub_is_missing():
    token = _fake_jwt({"role": "user"})
    assert decode_user_id(token) is None


class _FakePool:
    """Stands in for `asyncpg.Pool` -- records every call so tests can assert on the exact SQL
    parameters without a real Postgres connection."""

    def __init__(self, fetchrow_result=None):
        self.fetchrow_result = fetchrow_result
        self.fetchrow_calls: list[tuple] = []
        self.execute_calls: list[tuple] = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self.fetchrow_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


@pytest.mark.asyncio
async def test_lookup_returns_none_on_a_miss():
    pool = _FakePool(fetchrow_result=None)
    cache = QueryCache(pool)
    result = await cache.lookup("user-1", "agentic", "What is X?")
    assert result is None


@pytest.mark.asyncio
async def test_lookup_scopes_by_user_mode_and_normalized_question():
    pool = _FakePool(fetchrow_result=None)
    cache = QueryCache(pool)
    await cache.lookup("user-1", "agentic", "  What IS X?  ")
    _query, args = pool.fetchrow_calls[0]
    # user_id, mode, normalized question, cutoff timestamp -- in that order (AGT-041: per-user
    # isolation comes from user_id being part of this exact lookup, not a separate filter step).
    assert args[0] == "user-1"
    assert args[1] == "agentic"
    assert args[2] == "what is x?"


@pytest.mark.asyncio
async def test_lookup_parses_a_cache_hit_row():
    row = {
        "answer": "Paris is the capital of France.",
        "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb"}],
        "source_filename": None,
    }
    pool = _FakePool(fetchrow_result=row)
    cache = QueryCache(pool)
    result = await cache.lookup("user-1", "agentic", "What is the capital of France?")
    assert result is not None
    assert result.answer == "Paris is the capital of France."
    assert result.refused is False
    assert result.trace == [{"agent": "gatekeeper", "route": "kb"}]


@pytest.mark.asyncio
async def test_lookup_parses_trace_stored_as_a_json_string():
    # asyncpg can hand back JSONB either already decoded or as a raw string depending on codec
    # setup -- both must work.
    row = {
        "answer": "x",
        "refused": False,
        "trace": json.dumps([{"agent": "writer", "text": "x"}]),
        "source_filename": None,
    }
    pool = _FakePool(fetchrow_result=row)
    cache = QueryCache(pool)
    result = await cache.lookup("user-1", "agentic", "x")
    assert result is not None
    assert result.trace == [{"agent": "writer", "text": "x"}]


@pytest.mark.asyncio
async def test_record_inserts_with_the_normalized_question_and_given_fields():
    pool = _FakePool()
    cache = QueryCache(pool)
    await cache.record(
        user_id="user-1",
        mode="direct",
        question="  What IS X?  ",
        answer="x",
        refused=False,
        trace=[],
        source_filename="doc.pdf",
        duration_seconds=1.5,
        served_from_cache=False,
    )
    _query, args = pool.execute_calls[0]
    assert args[0] == "user-1"
    assert args[1] == "direct"
    assert args[2] == "what is x?"
    assert args[3] == "  What IS X?  "
    assert args[7] == "doc.pdf"
    assert args[9] is False
