# Agentic RAG Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small (4-agent) self-correcting agentic RAG system — Gatekeeper, Research, Writer, Verifier — orchestrated with LangGraph, that calls the existing `enterprise-rag-platform` for retrieval via a real MCP tool server, with a FastAPI streaming endpoint and a two-tab Gradio demo comparing direct RAG vs. agentic RAG.

**Architecture:** A LangGraph state machine routes a query through Gatekeeper (grades retrieval sufficiency) → Research (calls `enterprise-rag-platform`'s `/retrieval/query` via an MCP tool, or falls back to web search when flagged) → Writer (synthesizes a cited answer) → Verifier (checks groundedness, loops back to Research on unsupported claims, bounded to 2 retries, else refuses). Each agent is a PydanticAI `Agent` running against a local Ollama model. FastAPI exposes `POST /query` streaming the graph's step-by-step trace via SSE; a Gradio app renders that trace live in one tab and a plain RAG call in a second tab.

**Tech Stack:** Python 3.12, uv, FastAPI, PydanticAI (with MCP support), LangGraph, the official `mcp` SDK (FastMCP for the tool server), httpx, Ollama (local inference), `ddgs` (free web search fallback), Gradio, pytest/pytest-asyncio/pytest-cov, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-28-agentic-rag-orchestration-design.md`

## Global Constraints

- Python 3.12, package management via `uv` (mirrors `enterprise-rag-platform`).
- No paid dependencies: Ollama for inference, `ddgs` for web fallback (free, no API key), Langfuse Cloud Hobby tier (free) for tracing — no other paid API calls.
- This project depends on `enterprise-rag-platform` running and reachable; it is not designed to degrade gracefully if that service is absent (confirmed decision) — only the Gatekeeper's own KB-insufficient signal triggers the web fallback, never a connection failure to the RAG platform being silently treated as "insufficient."
- Bounded retries: the Research↔Verifier correction loop is capped at 2 retries; after that, refuse rather than guess.
- External (web-fallback) evidence must always be labeled distinctly from trusted KB evidence in any answer text.
- Credentials for the dedicated `enterprise-rag-platform` user (email/password, refresh token) are read from environment variables only, documented in `.env.example`, never hardcoded or committed — per this portfolio's `D:\github-projects\credentials-policy.md`.
- Business logic never lives in API routes (FastAPI routes validate + call service/graph layer only), matching `enterprise-rag-platform`'s architecture principle.
- All dependencies must be open-source and free, per the same principle as `enterprise-rag-platform`.

## Review Focus

- `enterprise-rag-platform` unreachable (connection refused/timeout) when a query arrives — the system must surface a clear error to the caller, not hang or silently treat it as "KB has no evidence" (which would wrongly trigger the web fallback instead of an outage error).
- The cached access token expires mid-session — a 401 from `/retrieval/query` must trigger exactly one refresh-and-retry, not an infinite loop or an immediate hard failure.
- The RAG platform returns zero chunks for a query (empty `results` list, not an error) — the Gatekeeper must classify this as "insufficient evidence" correctly, not crash on an empty list or misread it as sufficient.
- The Verifier keeps flagging the answer as ungrounded after the retry cap is reached — the graph must terminate with an explicit refusal, not loop past the configured maximum.
- The web search fallback itself fails or returns nothing (network error, no results) when the Gatekeeper has already routed to it — the graph must refuse cleanly rather than crash or hand the Writer an empty/undefined evidence set.

---

## Task 1: Project Scaffolding & Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `app.core.config.Settings` (Pydantic `BaseSettings`) with fields: `rag_platform_base_url: str`, `rag_platform_email: str`, `rag_platform_password: str`, `ollama_base_url: str = "http://localhost:11434/v1"`, `ollama_model: str = "qwen3"`, `langfuse_public_key: str | None = None`, `langfuse_secret_key: str | None = None`, `langfuse_host: str = "https://cloud.langfuse.com"`, `max_verification_retries: int = 2`. Function `get_settings() -> Settings` (cached via `functools.lru_cache`).

- [ ] **Step 1: Initialize the uv project**

Run:
```bash
uv init --python 3.12 --no-readme
uv add fastapi "uvicorn[standard]" pydantic pydantic-settings httpx "pydantic-ai-slim[mcp,openai]" langgraph mcp ddgs gradio
uv add --dev pytest pytest-asyncio pytest-cov ruff mypy
```

- [ ] **Step 2: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
```

- [ ] **Step 3: Write `.env.example`**

```
RAG_PLATFORM_BASE_URL=http://localhost:8000
RAG_PLATFORM_EMAIL=agentic-ai-service@example.com
RAG_PLATFORM_PASSWORD=changeme
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
MAX_VERIFICATION_RETRIES=2
```

- [ ] **Step 4: Write the failing test**

```python
# tests/test_config.py
import os

from app.core.config import get_settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "secret123")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.rag_platform_base_url == "http://localhost:8000"
    assert settings.rag_platform_email == "svc@example.com"
    assert settings.ollama_model == "qwen3"
    assert settings.max_verification_retries == 2
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 6: Implement `app/core/config.py`**

```python
"""Application configuration, loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. See `.env.example` for every recognized variable."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    rag_platform_base_url: str
    rag_platform_email: str
    rag_platform_password: str

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3"

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    max_verification_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached settings instance."""
    return Settings()
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock .env.example .gitignore app/ tests/test_config.py
git commit -m "chore: scaffold project and add typed settings"
```

---

## Task 2: RAG Platform Auth Client

**Files:**
- Create: `app/rag_client/__init__.py`
- Create: `app/rag_client/schemas.py`
- Create: `app/rag_client/auth.py`
- Test: `tests/rag_client/test_auth.py`

**Interfaces:**
- Consumes: `app.core.config.Settings` (Task 1).
- Produces: `app.rag_client.schemas.TokenPair(access_token: str, refresh_token: str)`. Class `app.rag_client.auth.RagPlatformAuth(base_url: str, email: str, password: str, http_client: httpx.AsyncClient)` with async methods `async def get_access_token(self) -> str` (logs in on first call, reuses cached token thereafter) and `async def refresh(self) -> str` (rotates the refresh token, updates the cache, returns the new access token). Raises `app.rag_client.auth.RagPlatformAuthError` on login/refresh failure.

- [ ] **Step 1: Write the failing test**

```python
# tests/rag_client/test_auth.py
import httpx
import pytest

from app.rag_client.auth import RagPlatformAuth, RagPlatformAuthError


@pytest.fixture
def transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={
                "access_token": "access-1", "refresh_token": "refresh-1", "token_type": "bearer",
            })
        if request.url.path == "/auth/refresh":
            return httpx.Response(200, json={
                "access_token": "access-2", "refresh_token": "refresh-2", "token_type": "bearer",
            })
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_get_access_token_logs_in_once(transport):
    async with httpx.AsyncClient(base_url="http://rag.test", transport=transport) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)

        token1 = await auth.get_access_token()
        token2 = await auth.get_access_token()

        assert token1 == "access-1"
        assert token2 == "access-1"  # cached, no second login


@pytest.mark.asyncio
async def test_refresh_rotates_tokens(transport):
    async with httpx.AsyncClient(base_url="http://rag.test", transport=transport) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        await auth.get_access_token()

        new_token = await auth.refresh()

        assert new_token == "access-2"
        assert await auth.get_access_token() == "access-2"


@pytest.mark.asyncio
async def test_login_failure_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid email or password"})

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "wrong", client)

        with pytest.raises(RagPlatformAuthError):
            await auth.get_access_token()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rag_client/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.rag_client.auth'`

- [ ] **Step 3: Write `app/rag_client/schemas.py`**

```python
"""Schemas mirroring `enterprise-rag-platform`'s auth and retrieval API shapes."""

from pydantic import BaseModel


class TokenPair(BaseModel):
    """An access + refresh token pair, as issued by `enterprise-rag-platform`."""

    access_token: str
    refresh_token: str


class RetrievedChunk(BaseModel):
    """A single retrieved chunk, mirroring `enterprise-rag-platform`'s `RetrievedChunk`."""

    chunk_id: str
    document_id: str
    text: str
    section_path: list[str]
    page_start: int
    page_end: int
    source_filename: str
    score: float
```

- [ ] **Step 4: Implement `app/rag_client/auth.py`**

```python
"""Authentication against `enterprise-rag-platform`: login, cache, and refresh tokens.

That platform has no API-key/service-account mechanism -- every retrieval call needs a JWT
obtained via email+password login (see its `app/auth/router.py`). This client logs in once,
caches the access token, and rotates via the refresh endpoint rather than re-logging-in per call.
"""

import httpx

from app.rag_client.schemas import TokenPair


class RagPlatformAuthError(RuntimeError):
    """Raised when login or token refresh against `enterprise-rag-platform` fails."""


class RagPlatformAuth:
    """Holds and refreshes one user's token pair for `enterprise-rag-platform`."""

    def __init__(self, base_url: str, email: str, password: str, http_client: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._email = email
        self._password = password
        self._http = http_client
        self._tokens: TokenPair | None = None

    async def get_access_token(self) -> str:
        """Return a cached access token, logging in on first use."""
        if self._tokens is None:
            self._tokens = await self._login()
        return self._tokens.access_token

    async def refresh(self) -> str:
        """Rotate the refresh token and return the new access token."""
        if self._tokens is None:
            self._tokens = await self._login()
            return self._tokens.access_token
        response = await self._http.post(
            "/auth/refresh", json={"refresh_token": self._tokens.refresh_token}
        )
        if response.status_code != 200:
            raise RagPlatformAuthError(f"Token refresh failed: {response.status_code} {response.text}")
        self._tokens = TokenPair(**response.json())
        return self._tokens.access_token

    async def _login(self) -> TokenPair:
        response = await self._http.post(
            "/auth/login", json={"email": self._email, "password": self._password}
        )
        if response.status_code != 200:
            raise RagPlatformAuthError(f"Login failed: {response.status_code} {response.text}")
        return TokenPair(**response.json())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/rag_client/test_auth.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add app/rag_client/ tests/rag_client/test_auth.py
git commit -m "feat: add enterprise-rag-platform auth client with token refresh"
```

---

## Task 3: RAG Platform Retrieval Client

**Files:**
- Modify: `app/rag_client/schemas.py`
- Create: `app/rag_client/retrieval.py`
- Test: `tests/rag_client/test_retrieval.py`

**Interfaces:**
- Consumes: `app.rag_client.auth.RagPlatformAuth` (Task 2), `app.rag_client.schemas.RetrievedChunk` (Task 2).
- Produces: `app.rag_client.schemas.RetrievalResult(results: list[RetrievedChunk])`. Class `app.rag_client.retrieval.RagPlatformRetrievalClient(base_url: str, auth: RagPlatformAuth, http_client: httpx.AsyncClient)` with `async def search(self, query: str, top_k: int = 5, rerank: bool = False, expand_sections: bool = False, document_ids: list[str] | None = None) -> RetrievalResult`. On a 401, refreshes the token once and retries exactly once before raising `RagPlatformRetrievalError`.

- [ ] **Step 1: Add `RetrievalResult` to `app/rag_client/schemas.py`**

```python
class RetrievalResult(BaseModel):
    """Ranked retrieval results, mirroring `enterprise-rag-platform`'s `RetrievalResponse`."""

    results: list[RetrievedChunk]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/rag_client/test_retrieval.py
import httpx
import pytest

from app.rag_client.auth import RagPlatformAuth
from app.rag_client.retrieval import RagPlatformRetrievalClient, RagPlatformRetrievalError

CHUNK = {
    "chunk_id": "c1", "document_id": "d1", "text": "Paris is the capital of France.",
    "section_path": ["Intro"], "page_start": 1, "page_end": 1,
    "source_filename": "geo.pdf", "score": 0.92,
}


@pytest.mark.asyncio
async def test_search_returns_chunks():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1", "token_type": "bearer"})
        if request.url.path == "/retrieval/query":
            assert request.headers["authorization"] == "Bearer a1"
            return httpx.Response(200, json={"results": [CHUNK]})
        return httpx.Response(404)

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        retrieval = RagPlatformRetrievalClient("http://rag.test", auth, client)

        result = await retrieval.search("capital of France", top_k=5)

        assert len(result.results) == 1
        assert result.results[0].text == "Paris is the capital of France."


@pytest.mark.asyncio
async def test_search_refreshes_token_once_on_401():
    calls = {"query": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1", "token_type": "bearer"})
        if request.url.path == "/auth/refresh":
            return httpx.Response(200, json={"access_token": "a2", "refresh_token": "r2", "token_type": "bearer"})
        if request.url.path == "/retrieval/query":
            calls["query"] += 1
            if request.headers["authorization"] == "Bearer a1":
                return httpx.Response(401, json={"detail": "expired"})
            return httpx.Response(200, json={"results": [CHUNK]})
        return httpx.Response(404)

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        retrieval = RagPlatformRetrievalClient("http://rag.test", auth, client)

        result = await retrieval.search("capital of France")

        assert calls["query"] == 2
        assert len(result.results) == 1


@pytest.mark.asyncio
async def test_search_returns_empty_results_without_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1", "token_type": "bearer"})
        return httpx.Response(200, json={"results": []})

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        retrieval = RagPlatformRetrievalClient("http://rag.test", auth, client)

        result = await retrieval.search("something not in the kb")

        assert result.results == []


@pytest.mark.asyncio
async def test_connection_error_raises_retrieval_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1", "token_type": "bearer"})
        raise httpx.ConnectError("connection refused")

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        retrieval = RagPlatformRetrievalClient("http://rag.test", auth, client)

        with pytest.raises(RagPlatformRetrievalError):
            await retrieval.search("anything")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/rag_client/test_retrieval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.rag_client.retrieval'`

- [ ] **Step 4: Implement `app/rag_client/retrieval.py`**

```python
"""Retrieval client for `enterprise-rag-platform`'s `POST /retrieval/query` endpoint.

That endpoint does hybrid (FAISS + BM25, fused) retrieval as a single call -- there are no
separate keyword/semantic/chunk-level strategies to choose between, so this client exposes
exactly the parameters the real endpoint accepts: `top_k`, `rerank`, `expand_sections`,
`document_ids`.
"""

import httpx

from app.rag_client.auth import RagPlatformAuth
from app.rag_client.schemas import RetrievalResult


class RagPlatformRetrievalError(RuntimeError):
    """Raised when a retrieval call fails after one refresh-and-retry, or on a network error."""


class RagPlatformRetrievalClient:
    """Calls `enterprise-rag-platform`'s retrieval API on behalf of this project's service user."""

    def __init__(self, base_url: str, auth: RagPlatformAuth, http_client: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._auth = auth
        self._http = http_client

    async def search(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = False,
        expand_sections: bool = False,
        document_ids: list[str] | None = None,
    ) -> RetrievalResult:
        """Run one hybrid retrieval query, refreshing the token once on a 401."""
        payload = {
            "query": query, "top_k": top_k, "rerank": rerank,
            "expand_sections": expand_sections, "document_ids": document_ids,
        }
        try:
            response = await self._request(payload, await self._auth.get_access_token())
            if response.status_code == 401:
                response = await self._request(payload, await self._auth.refresh())
        except httpx.HTTPError as exc:
            raise RagPlatformRetrievalError(f"Retrieval request failed: {exc}") from exc

        if response.status_code != 200:
            raise RagPlatformRetrievalError(
                f"Retrieval query failed: {response.status_code} {response.text}"
            )
        return RetrievalResult(**response.json())

    async def _request(self, payload: dict, access_token: str) -> httpx.Response:
        return await self._http.post(
            "/retrieval/query", json=payload, headers={"Authorization": f"Bearer {access_token}"}
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/rag_client/test_retrieval.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add app/rag_client/ tests/rag_client/test_retrieval.py
git commit -m "feat: add enterprise-rag-platform retrieval client with 401 retry"
```

---

## Task 4: MCP Tool Server

**Files:**
- Create: `app/mcp_server/__init__.py`
- Create: `app/mcp_server/server.py`
- Test: `tests/mcp_server/test_server.py`

**Interfaces:**
- Consumes: `app.rag_client.retrieval.RagPlatformRetrievalClient`, `app.rag_client.auth.RagPlatformAuth` (Task 2/3), `app.core.config.get_settings` (Task 1).
- Produces: module-level `mcp_server: mcp.server.fastmcp.FastMCP` named `"rag-retrieval"`, exposing one tool `search_knowledge_base(query: str, top_k: int = 5, rerank: bool = False, expand_sections: bool = False) -> list[dict]` returning each chunk's `text`, `source_filename`, `section_path`, `score`. Runnable as `python -m app.mcp_server.server` (stdio transport).

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp_server/test_server.py
from unittest.mock import AsyncMock

import pytest

from app.mcp_server.server import _search_knowledge_base_impl
from app.rag_client.schemas import RetrievalResult, RetrievedChunk


@pytest.mark.asyncio
async def test_search_knowledge_base_returns_chunk_dicts():
    chunk = RetrievedChunk(
        chunk_id="c1", document_id="d1", text="Paris is the capital of France.",
        section_path=["Intro"], page_start=1, page_end=1, source_filename="geo.pdf", score=0.92,
    )
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[chunk])

    result = await _search_knowledge_base_impl(
        fake_client, query="capital of France", top_k=5, rerank=False, expand_sections=False
    )

    assert result == [{
        "text": "Paris is the capital of France.",
        "source_filename": "geo.pdf",
        "section_path": ["Intro"],
        "score": 0.92,
    }]
    fake_client.search.assert_awaited_once_with(
        "capital of France", top_k=5, rerank=False, expand_sections=False
    )


@pytest.mark.asyncio
async def test_search_knowledge_base_empty_results():
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[])

    result = await _search_knowledge_base_impl(
        fake_client, query="nothing relevant", top_k=5, rerank=False, expand_sections=False
    )

    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp_server/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mcp_server.server'`

- [ ] **Step 3: Implement `app/mcp_server/server.py`**

```python
"""MCP tool server exposing `enterprise-rag-platform`'s retrieval API as a `search_knowledge_base`
tool. Run standalone via `python -m app.mcp_server.server` (stdio transport); the Research agent
(Task 9) connects to this as an MCP client subprocess.
"""

import httpx
from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.rag_client.auth import RagPlatformAuth
from app.rag_client.retrieval import RagPlatformRetrievalClient

mcp_server = FastMCP("rag-retrieval")


async def _search_knowledge_base_impl(
    client: RagPlatformRetrievalClient, query: str, top_k: int, rerank: bool, expand_sections: bool
) -> list[dict]:
    result = await client.search(query, top_k=top_k, rerank=rerank, expand_sections=expand_sections)
    return [
        {
            "text": chunk.text,
            "source_filename": chunk.source_filename,
            "section_path": chunk.section_path,
            "score": chunk.score,
        }
        for chunk in result.results
    ]


def _build_retrieval_client() -> RagPlatformRetrievalClient:
    settings = get_settings()
    http_client = httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)
    auth = RagPlatformAuth(
        settings.rag_platform_base_url, settings.rag_platform_email, settings.rag_platform_password, http_client
    )
    return RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)


_retrieval_client = _build_retrieval_client()


@mcp_server.tool()
async def search_knowledge_base(
    query: str, top_k: int = 5, rerank: bool = False, expand_sections: bool = False
) -> list[dict]:
    """Search the enterprise knowledge base and return the top matching chunks.

    Each result has `text`, `source_filename`, `section_path`, and a fused relevance `score`
    in (0, 1]. Returns an empty list, not an error, when nothing relevant is found.
    """
    return await _search_knowledge_base_impl(_retrieval_client, query, top_k, rerank, expand_sections)


if __name__ == "__main__":
    mcp_server.run(transport="stdio")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp_server/test_server.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/mcp_server/ tests/mcp_server/
git commit -m "feat: add MCP tool server wrapping enterprise-rag-platform retrieval"
```

---

## Task 5: Agent State & Message Schemas

**Files:**
- Create: `app/agents/__init__.py`
- Create: `app/agents/schemas.py`
- Test: `tests/agents/test_schemas.py`

**Interfaces:**
- Produces (used by every later agent/graph task):
  - `EvidenceSource = Literal["knowledge_base", "web"]`
  - `Evidence(text: str, source: EvidenceSource, citation: str)`
  - `GatekeeperDecision(route: Literal["kb", "web_fallback", "refuse"], reasoning: str, top_k: int = 5, rerank: bool = False)`
  - `ResearchResult(evidence: list[Evidence])`
  - `DraftAnswer(text: str, cited_evidence: list[Evidence])`
  - `VerificationResult(grounded: bool, unsupported_claims: list[str], reasoning: str)`
  - `GraphState` (a `TypedDict`): `query: str`, `gatekeeper_decision: GatekeeperDecision | None`, `evidence: list[Evidence]`, `draft: DraftAnswer | None`, `verification: VerificationResult | None`, `retry_count: int`, `final_answer: str | None`, `refused: bool`, `trace: list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_schemas.py
from app.agents.schemas import Evidence, GatekeeperDecision, GraphState, VerificationResult


def test_evidence_requires_valid_source():
    evidence = Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")
    assert evidence.source == "knowledge_base"


def test_gatekeeper_decision_defaults():
    decision = GatekeeperDecision(route="kb", reasoning="strong KB match")
    assert decision.top_k == 5
    assert decision.rerank is False


def test_graph_state_initial_shape():
    state: GraphState = {
        "query": "What is the capital of France?",
        "gatekeeper_decision": None,
        "evidence": [],
        "draft": None,
        "verification": None,
        "retry_count": 0,
        "final_answer": None,
        "refused": False,
        "trace": [],
    }
    assert state["retry_count"] == 0
    assert state["refused"] is False


def test_verification_result_tracks_unsupported_claims():
    result = VerificationResult(grounded=False, unsupported_claims=["Paris has 5 million residents"], reasoning="no source for population figure")
    assert result.grounded is False
    assert len(result.unsupported_claims) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.schemas'`

- [ ] **Step 3: Implement `app/agents/schemas.py`**

```python
"""Structured (A2A-style) messages passed between agents, and the shared LangGraph state."""

from typing import Literal, TypedDict

from pydantic import BaseModel

EvidenceSource = Literal["knowledge_base", "web"]


class Evidence(BaseModel):
    """One piece of evidence gathered by the Research agent, always source-labeled."""

    text: str
    source: EvidenceSource
    citation: str


class GatekeeperDecision(BaseModel):
    """The Gatekeeper's grading of retrieval sufficiency and the route to take."""

    route: Literal["kb", "web_fallback", "refuse"]
    reasoning: str
    top_k: int = 5
    rerank: bool = False


class ResearchResult(BaseModel):
    """Evidence gathered by the Research agent for one routing decision."""

    evidence: list[Evidence]


class DraftAnswer(BaseModel):
    """The Writer's synthesized answer, with the evidence it drew on."""

    text: str
    cited_evidence: list[Evidence]


class VerificationResult(BaseModel):
    """The Verifier's groundedness check of a draft answer against its cited evidence."""

    grounded: bool
    unsupported_claims: list[str]
    reasoning: str


class GraphState(TypedDict):
    """Shared state threaded through every LangGraph node."""

    query: str
    gatekeeper_decision: GatekeeperDecision | None
    evidence: list[Evidence]
    draft: DraftAnswer | None
    verification: VerificationResult | None
    retry_count: int
    final_answer: str | None
    refused: bool
    trace: list[dict]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/test_schemas.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/agents/__init__.py app/agents/schemas.py tests/agents/test_schemas.py
git commit -m "feat: add agent message schemas and shared graph state"
```

---

## Task 6: Ollama Model Provider Helper

**Files:**
- Create: `app/agents/llm.py`
- Test: `tests/agents/test_llm.py`

**Interfaces:**
- Consumes: `app.core.config.Settings` (Task 1).
- Produces: `app.agents.llm.get_ollama_model(settings: Settings) -> pydantic_ai.models.openai.OpenAIModel`, pointed at Ollama's OpenAI-compatible endpoint.

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_llm.py
from pydantic_ai.models.openai import OpenAIModel

from app.agents.llm import get_ollama_model
from app.core.config import Settings


def test_get_ollama_model_uses_configured_base_url_and_name():
    settings = Settings(
        rag_platform_base_url="http://localhost:8000",
        rag_platform_email="svc@example.com",
        rag_platform_password="secret123",
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen3",
    )

    model = get_ollama_model(settings)

    assert isinstance(model, OpenAIModel)
    assert model.model_name == "qwen3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.llm'`

- [ ] **Step 3: Implement `app/agents/llm.py`**

```python
"""Shared PydanticAI model factory: every agent talks to the same local Ollama instance."""

from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import Settings


def get_ollama_model(settings: Settings) -> OpenAIModel:
    """Build a PydanticAI model pointed at Ollama's OpenAI-compatible endpoint.

    Ollama serves an OpenAI-compatible API at `/v1`; the `api_key` is required by the provider
    but unused by Ollama itself, so any non-empty placeholder value works.
    """
    return OpenAIModel(
        settings.ollama_model,
        provider=OpenAIProvider(base_url=settings.ollama_base_url, api_key="ollama"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/agents/llm.py tests/agents/test_llm.py
git commit -m "feat: add shared Ollama model factory for PydanticAI agents"
```

---

## Task 7: Web Search Fallback Tool

**Files:**
- Create: `app/agents/web_search.py`
- Test: `tests/agents/test_web_search.py`

**Interfaces:**
- Produces: `async def search_web(query: str, max_results: int = 3) -> list[Evidence]` (each `Evidence.source == "web"`). Returns `[]` on any search failure rather than raising, since the Review Focus item requires the graph to refuse cleanly, not crash, when web fallback is unavailable.

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_web_search.py
from unittest.mock import patch

import pytest

from app.agents.schemas import Evidence
from app.agents.web_search import search_web


@pytest.mark.asyncio
async def test_search_web_returns_labeled_evidence():
    fake_results = [
        {"title": "France - Wikipedia", "href": "https://en.wikipedia.org/wiki/France", "body": "Paris is the capital of France."},
    ]
    with patch("app.agents.web_search._run_ddgs_search", return_value=fake_results):
        results = await search_web("capital of France")

    assert len(results) == 1
    assert isinstance(results[0], Evidence)
    assert results[0].source == "web"
    assert results[0].citation == "https://en.wikipedia.org/wiki/France"
    assert "Paris" in results[0].text


@pytest.mark.asyncio
async def test_search_web_returns_empty_list_on_failure():
    with patch("app.agents.web_search._run_ddgs_search", side_effect=RuntimeError("network error")):
        results = await search_web("capital of France")

    assert results == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_web_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.web_search'`

- [ ] **Step 3: Implement `app/agents/web_search.py`**

```python
"""Web search fallback, used only when the Gatekeeper flags KB evidence as insufficient.

Uses `ddgs` (DuckDuckGo search) -- free, no API key. Any failure here degrades to an empty
result list rather than raising, so a flaky or rate-limited web search can never crash the
graph; the Gatekeeper/Verifier logic (Tasks 8/11) treats empty evidence as grounds to refuse.
"""

import asyncio
import logging

from ddgs import DDGS

from app.agents.schemas import Evidence

logger = logging.getLogger(__name__)


def _run_ddgs_search(query: str, max_results: int) -> list[dict]:
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def search_web(query: str, max_results: int = 3) -> list[Evidence]:
    """Run a web search and return source-labeled evidence, or `[]` on any failure."""
    try:
        raw_results = await asyncio.to_thread(_run_ddgs_search, query, max_results)
    except Exception:
        logger.exception("Web search fallback failed for query: %s", query)
        return []

    return [
        Evidence(text=result["body"], source="web", citation=result["href"])
        for result in raw_results
        if "body" in result and "href" in result
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/test_web_search.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/agents/web_search.py tests/agents/test_web_search.py
git commit -m "feat: add web search fallback tool for insufficient KB evidence"
```

---

## Task 8: Gatekeeper Agent

**Files:**
- Create: `app/agents/gatekeeper.py`
- Test: `tests/agents/test_gatekeeper.py`

**Interfaces:**
- Consumes: `app.agents.llm.get_ollama_model` (Task 6), `app.agents.schemas.GatekeeperDecision` (Task 5), `app.rag_client.retrieval.RagPlatformRetrievalClient` (Task 3).
- Produces: `async def grade_retrieval(model, retrieval_client: RagPlatformRetrievalClient, query: str) -> GatekeeperDecision`. Runs one exploratory KB search itself (`top_k=3`) to ground its own grading decision, then asks the LLM to decide `route` based on what came back.

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_gatekeeper.py
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.models.test import TestModel

from app.agents.gatekeeper import grade_retrieval
from app.agents.schemas import GatekeeperDecision
from app.rag_client.schemas import RetrievalResult, RetrievedChunk


@pytest.mark.asyncio
async def test_grade_retrieval_routes_to_kb_when_evidence_found():
    chunk = RetrievedChunk(
        chunk_id="c1", document_id="d1", text="Paris is the capital of France.",
        section_path=["Intro"], page_start=1, page_end=1, source_filename="geo.pdf", score=0.95,
    )
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[chunk])
    model = TestModel(custom_output_args=GatekeeperDecision(route="kb", reasoning="strong match", top_k=5))

    decision = await grade_retrieval(model, fake_client, "What is the capital of France?")

    assert isinstance(decision, GatekeeperDecision)
    assert decision.route == "kb"


@pytest.mark.asyncio
async def test_grade_retrieval_handles_empty_kb_results():
    fake_client = AsyncMock()
    fake_client.search.return_value = RetrievalResult(results=[])
    model = TestModel(custom_output_args=GatekeeperDecision(route="web_fallback", reasoning="no KB evidence found"))

    decision = await grade_retrieval(model, fake_client, "What is today's weather in Pune?")

    assert decision.route == "web_fallback"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_gatekeeper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.gatekeeper'`

- [ ] **Step 3: Implement `app/agents/gatekeeper.py`**

```python
"""Gatekeeper agent: grades KB retrieval sufficiency and decides the route.

This is the guardrail -- it decides whether the query gets answered from the trusted knowledge
base, falls back to a flagged web search, or gets refused outright, following the Corrective RAG
pattern (a retrieval evaluator gating what happens next, rather than always generating).
"""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.schemas import GatekeeperDecision
from app.rag_client.retrieval import RagPlatformRetrievalClient

_SYSTEM_PROMPT = """You are the Gatekeeper of a retrieval-augmented answering system.

You are given a user's question and the top results of an exploratory knowledge-base search.
Decide one of three routes:
- "kb": the KB results are relevant and sufficient to answer the question. Set top_k to how many
  results you'd want the Research agent to fetch (5-10), and rerank=true if the question is
  ambiguous enough that result ordering matters.
- "web_fallback": the KB results are empty, irrelevant, or clearly insufficient, but the question
  is answerable from general web knowledge.
- "refuse": the question cannot be reliably answered from the KB or a general web search.

Always explain your reasoning briefly."""


def _build_agent(model: Model) -> Agent[None, GatekeeperDecision]:
    return Agent(model, output_type=GatekeeperDecision, system_prompt=_SYSTEM_PROMPT)


async def grade_retrieval(
    model: Model, retrieval_client: RagPlatformRetrievalClient, query: str
) -> GatekeeperDecision:
    """Run an exploratory KB search and ask the Gatekeeper agent to grade it."""
    exploratory = await retrieval_client.search(query, top_k=3)
    chunk_summaries = "\n".join(f"- {chunk.text[:200]}" for chunk in exploratory.results) or "(no results)"

    agent = _build_agent(model)
    prompt = f"Question: {query}\n\nExploratory KB results:\n{chunk_summaries}"
    result = await agent.run(prompt)
    return result.output
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/test_gatekeeper.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/agents/gatekeeper.py tests/agents/test_gatekeeper.py
git commit -m "feat: add Gatekeeper agent for retrieval grading and routing"
```

---

## Task 9: Research Agent

**Files:**
- Create: `app/agents/research.py`
- Test: `tests/agents/test_research.py`

**Interfaces:**
- Consumes: `app.agents.schemas.{GatekeeperDecision, ResearchResult, Evidence}` (Task 5), `app.agents.web_search.search_web` (Task 7), `mcp.server.fastmcp` MCP server module path (Task 4, launched as a subprocess via `MCPServerStdio`).
- Produces: `async def research(model, mcp_server_command: list[str], decision: GatekeeperDecision, query: str) -> ResearchResult`. When `decision.route == "kb"`, connects to the MCP server and uses its `search_knowledge_base` tool; when `"web_fallback"`, calls `search_web` directly; when `"refuse"`, returns `ResearchResult(evidence=[])` without doing any research.

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_research.py
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.research import research
from app.agents.schemas import Evidence, GatekeeperDecision, ResearchResult


@pytest.mark.asyncio
async def test_research_web_fallback_route_uses_web_search():
    decision = GatekeeperDecision(route="web_fallback", reasoning="no KB match")
    fake_evidence = [Evidence(text="Sunny, 28C", source="web", citation="https://weather.example")]

    with patch("app.agents.research.search_web", AsyncMock(return_value=fake_evidence)):
        result = await research(model=None, mcp_server_command=[], decision=decision, query="weather in Pune today")

    assert isinstance(result, ResearchResult)
    assert result.evidence == fake_evidence


@pytest.mark.asyncio
async def test_research_refuse_route_returns_no_evidence():
    decision = GatekeeperDecision(route="refuse", reasoning="unanswerable")

    result = await research(model=None, mcp_server_command=[], decision=decision, query="anything")

    assert result.evidence == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_research.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.research'`

- [ ] **Step 3: Implement `app/agents/research.py`**

```python
"""Research agent: gathers evidence for the route the Gatekeeper chose.

For the "kb" route, this connects to the MCP tool server (Task 4) as an MCP client and calls its
`search_knowledge_base` tool -- a real MCP round-trip, not a direct Python function call. For
"web_fallback", it uses the plain web search tool (Task 7) directly, since that fallback is this
project's own capability, not something exposed over MCP. "refuse" does no research at all.
"""

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models import Model

from app.agents.schemas import Evidence, GatekeeperDecision, ResearchResult
from app.agents.web_search import search_web

_SYSTEM_PROMPT = """You are the Research agent. You have access to a `search_knowledge_base` tool.
Given the user's question and the requested top_k/rerank settings, call the tool, then return
every relevant result as evidence with its `source_filename` as the citation."""


async def _research_kb(model: Model, mcp_server_command: list[str], decision: GatekeeperDecision, query: str) -> list[Evidence]:
    mcp_server = MCPServerStdio(command=mcp_server_command[0], args=mcp_server_command[1:])
    agent = Agent(model, toolsets=[mcp_server], output_type=list[Evidence], system_prompt=_SYSTEM_PROMPT)
    async with agent:
        prompt = f"Question: {query}\nUse top_k={decision.top_k}, rerank={decision.rerank}."
        result = await agent.run(prompt)
    return result.output


async def research(
    model: Model | None, mcp_server_command: list[str], decision: GatekeeperDecision, query: str
) -> ResearchResult:
    """Gather evidence according to the Gatekeeper's chosen route."""
    if decision.route == "refuse":
        return ResearchResult(evidence=[])
    if decision.route == "web_fallback":
        evidence = await search_web(query)
        return ResearchResult(evidence=evidence)
    evidence = await _research_kb(model, mcp_server_command, decision, query)
    return ResearchResult(evidence=evidence)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/test_research.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/agents/research.py tests/agents/test_research.py
git commit -m "feat: add Research agent with MCP-backed KB search and web fallback"
```

---

## Task 10: Writer Agent

**Files:**
- Create: `app/agents/writer.py`
- Test: `tests/agents/test_writer.py`

**Interfaces:**
- Consumes: `app.agents.schemas.{Evidence, DraftAnswer}` (Task 5).
- Produces: `async def write_answer(model, query: str, evidence: list[Evidence]) -> DraftAnswer`. If `evidence` is empty, returns a `DraftAnswer` stating no answer could be produced, without calling the LLM.

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_writer.py
import pytest
from pydantic_ai.models.test import TestModel

from app.agents.schemas import DraftAnswer, Evidence
from app.agents.writer import write_answer


@pytest.mark.asyncio
async def test_write_answer_synthesizes_from_evidence():
    evidence = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")]
    model = TestModel(custom_output_args=DraftAnswer(
        text="The capital of France is Paris [geo.pdf].", cited_evidence=evidence,
    ))

    draft = await write_answer(model, "What is the capital of France?", evidence)

    assert isinstance(draft, DraftAnswer)
    assert "Paris" in draft.text


@pytest.mark.asyncio
async def test_write_answer_with_no_evidence_does_not_call_model():
    draft = await write_answer(model=None, query="anything", evidence=[])

    assert draft.cited_evidence == []
    assert "could not" in draft.text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_writer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.writer'`

- [ ] **Step 3: Implement `app/agents/writer.py`**

```python
"""Writer agent: synthesizes a cited answer from gathered evidence.

Never presents web-fallback evidence as if it were KB-grounded -- the system prompt requires the
source to be made explicit in the answer text itself, not just carried in the structured output.
"""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.schemas import DraftAnswer, Evidence

_SYSTEM_PROMPT = """You are the Writer agent. Synthesize a clear, cited answer from the given
evidence. Cite each claim with its source. If any evidence came from the web rather than the
knowledge base, say so explicitly in the answer text (e.g. "According to a web search...")."""


async def write_answer(model: Model | None, query: str, evidence: list[Evidence]) -> DraftAnswer:
    """Draft an answer from evidence, or a stock refusal if there's no evidence to draw on."""
    if not evidence:
        return DraftAnswer(text="I could not find enough evidence to answer this question.", cited_evidence=[])

    agent = Agent(model, output_type=DraftAnswer, system_prompt=_SYSTEM_PROMPT)
    evidence_block = "\n".join(f"[{item.source}] {item.citation}: {item.text}" for item in evidence)
    prompt = f"Question: {query}\n\nEvidence:\n{evidence_block}"
    result = await agent.run(prompt)
    return result.output
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/test_writer.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/agents/writer.py tests/agents/test_writer.py
git commit -m "feat: add Writer agent for evidence-grounded answer synthesis"
```

---

## Task 11: Verifier Agent

**Files:**
- Create: `app/agents/verifier.py`
- Test: `tests/agents/test_verifier.py`

**Interfaces:**
- Consumes: `app.agents.schemas.{DraftAnswer, VerificationResult}` (Task 5).
- Produces: `async def verify_answer(model, draft: DraftAnswer) -> VerificationResult`. Empty `cited_evidence` always yields `grounded=False`, without calling the LLM.

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_verifier.py
import pytest
from pydantic_ai.models.test import TestModel

from app.agents.schemas import DraftAnswer, Evidence, VerificationResult
from app.agents.verifier import verify_answer


@pytest.mark.asyncio
async def test_verify_answer_grounded():
    evidence = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")]
    draft = DraftAnswer(text="The capital of France is Paris [geo.pdf].", cited_evidence=evidence)
    model = TestModel(custom_output_args=VerificationResult(grounded=True, unsupported_claims=[], reasoning="matches source"))

    result = await verify_answer(model, draft)

    assert result.grounded is True


@pytest.mark.asyncio
async def test_verify_answer_with_no_cited_evidence_is_never_grounded():
    draft = DraftAnswer(text="I could not find enough evidence to answer this question.", cited_evidence=[])

    result = await verify_answer(model=None, draft=draft)

    assert result.grounded is False
    assert result.unsupported_claims == [draft.text]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_verifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.verifier'`

- [ ] **Step 3: Implement `app/agents/verifier.py`**

```python
"""Verifier agent: checks each claim in a draft answer against its cited evidence.

Self-RAG-style reflection step. A draft with no cited evidence (e.g. the Writer's own refusal
text) is never considered grounded, since there is nothing to check it against.
"""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.schemas import DraftAnswer, VerificationResult

_SYSTEM_PROMPT = """You are the Verifier agent. Given a draft answer and the evidence it cites,
check whether every factual claim in the answer is actually supported by that evidence. List any
unsupported claims verbatim. Be strict: an unsupported claim is worse than an admitted gap."""


async def verify_answer(model: Model | None, draft: DraftAnswer) -> VerificationResult:
    """Check a draft's groundedness against its own cited evidence."""
    if not draft.cited_evidence:
        return VerificationResult(grounded=False, unsupported_claims=[draft.text], reasoning="no cited evidence to verify against")

    agent = Agent(model, output_type=VerificationResult, system_prompt=_SYSTEM_PROMPT)
    evidence_block = "\n".join(f"[{item.source}] {item.citation}: {item.text}" for item in draft.cited_evidence)
    prompt = f"Draft answer: {draft.text}\n\nCited evidence:\n{evidence_block}"
    result = await agent.run(prompt)
    return result.output
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/test_verifier.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/agents/verifier.py tests/agents/test_verifier.py
git commit -m "feat: add Verifier agent for groundedness checking"
```

---

## Task 12: LangGraph Orchestration Graph

**Files:**
- Create: `app/graph/__init__.py`
- Create: `app/graph/build.py`
- Test: `tests/graph/test_build.py`

**Interfaces:**
- Consumes: `app.agents.schemas.GraphState` (Task 5), `app.agents.gatekeeper.grade_retrieval` (Task 8), `app.agents.research.research` (Task 9), `app.agents.writer.write_answer` (Task 10), `app.agents.verifier.verify_answer` (Task 11).
- Produces: `def build_graph(model, retrieval_client, mcp_server_command: list[str], max_retries: int) -> langgraph.graph.state.CompiledStateGraph`, invocable as `await graph.ainvoke(initial_state)`. Every node appends one dict to `state["trace"]` describing what it did (used later by the SSE endpoint, Task 13).

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_build.py
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.schemas import DraftAnswer, Evidence, GatekeeperDecision, VerificationResult
from app.graph.build import build_graph

KB_EVIDENCE = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="geo.pdf")]


def _initial_state(query: str) -> dict:
    return {
        "query": query, "gatekeeper_decision": None, "evidence": [], "draft": None,
        "verification": None, "retry_count": 0, "final_answer": None, "refused": False, "trace": [],
    }


@pytest.mark.asyncio
async def test_graph_happy_path_returns_grounded_answer():
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=KB_EVIDENCE))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="Paris [geo.pdf]", cited_evidence=KB_EVIDENCE))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="ok"))),
    ):
        graph = build_graph(model=None, retrieval_client=None, mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert final_state["refused"] is False
    assert final_state["final_answer"] == "Paris [geo.pdf]"
    assert len(final_state["trace"]) >= 4  # gatekeeper, research, writer, verifier each logged


@pytest.mark.asyncio
async def test_graph_refuses_after_exhausting_retries():
    ungrounded = VerificationResult(grounded=False, unsupported_claims=["made up fact"], reasoning="not supported")
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=KB_EVIDENCE))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="unsupported claim", cited_evidence=KB_EVIDENCE))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=ungrounded)),
    ):
        graph = build_graph(model=None, retrieval_client=None, mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert final_state["refused"] is True
    assert final_state["retry_count"] == 2


@pytest.mark.asyncio
async def test_graph_refuse_route_skips_research_and_writer():
    with patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="refuse", reasoning="out of scope"))):
        graph = build_graph(model=None, retrieval_client=None, mcp_server_command=[], max_retries=2)
        final_state = await graph.ainvoke(_initial_state("What is your favorite color?"))

    assert final_state["refused"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/graph/test_build.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.graph.build'`

- [ ] **Step 3: Implement `app/graph/build.py`**

```python
"""LangGraph orchestration: Gatekeeper -> Research -> Writer -> Verifier, with a bounded
groundedness-correction loop (Verifier -> Research -> Writer, capped at `max_retries`).
"""

from langgraph.graph import END, StateGraph

from app.agents.gatekeeper import grade_retrieval
from app.agents.research import research
from app.agents.schemas import GraphState
from app.agents.verifier import verify_answer
from app.agents.writer import write_answer


def build_graph(model, retrieval_client, mcp_server_command: list[str], max_retries: int):
    """Compile the agent orchestration graph. `model`/`retrieval_client` are threaded into every
    node via closures so each node stays a plain async function the tests can patch by name.
    """

    async def gatekeeper_node(state: GraphState) -> GraphState:
        decision = await grade_retrieval(model, retrieval_client, state["query"])
        state["gatekeeper_decision"] = decision
        state["trace"].append({"agent": "gatekeeper", "route": decision.route, "reasoning": decision.reasoning})
        if decision.route == "refuse":
            state["refused"] = True
        return state

    async def research_node(state: GraphState) -> GraphState:
        result = await research(model, mcp_server_command, state["gatekeeper_decision"], state["query"])
        state["evidence"] = result.evidence
        state["trace"].append({"agent": "research", "evidence_count": len(result.evidence)})
        return state

    async def writer_node(state: GraphState) -> GraphState:
        draft = await write_answer(model, state["query"], state["evidence"])
        state["draft"] = draft
        state["trace"].append({"agent": "writer", "text": draft.text})
        return state

    async def verifier_node(state: GraphState) -> GraphState:
        verification = await verify_answer(model, state["draft"])
        state["verification"] = verification
        state["trace"].append({"agent": "verifier", "grounded": verification.grounded})
        if verification.grounded:
            state["final_answer"] = state["draft"].text
        else:
            state["retry_count"] += 1
            if state["retry_count"] >= max_retries:
                state["refused"] = True
        return state

    def route_after_gatekeeper(state: GraphState) -> str:
        return "end" if state["refused"] else "research"

    def route_after_verifier(state: GraphState) -> str:
        if state["final_answer"] is not None:
            return "end"
        if state["refused"]:
            return "end"
        return "research"

    graph = StateGraph(GraphState)
    graph.add_node("gatekeeper", gatekeeper_node)
    graph.add_node("research", research_node)
    graph.add_node("writer", writer_node)
    graph.add_node("verifier", verifier_node)

    graph.set_entry_point("gatekeeper")
    graph.add_conditional_edges("gatekeeper", route_after_gatekeeper, {"research": "research", "end": END})
    graph.add_edge("research", "writer")
    graph.add_edge("writer", "verifier")
    graph.add_conditional_edges("verifier", route_after_verifier, {"research": "research", "end": END})

    return graph.compile()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/graph/test_build.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/graph/ tests/graph/
git commit -m "feat: wire agents into a bounded self-correcting LangGraph flow"
```

---

## Task 13: FastAPI SSE Query Endpoint

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/schemas.py`
- Create: `app/api/router.py`
- Create: `app/main.py`
- Test: `tests/api/test_router.py`

**Interfaces:**
- Consumes: `app.graph.build.build_graph` (Task 12), `app.core.config.get_settings` (Task 1).
- Produces: `POST /query` (body: `{"query": str}`) returning `text/event-stream`; one SSE `event: step` per trace entry, then a final `event: result` with `{"final_answer": str | None, "refused": bool}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_router.py
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_query_endpoint_streams_steps_and_result():
    fake_final_state = {
        "final_answer": "Paris [geo.pdf]", "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    fake_graph = AsyncMock()
    fake_graph.ainvoke.return_value = fake_final_state

    with patch("app.api.router.get_graph", return_value=fake_graph):
        client = TestClient(app)
        response = client.post("/query", json={"query": "What is the capital of France?"})

    assert response.status_code == 200
    assert "event: step" in response.text
    assert "event: result" in response.text
    assert "Paris" in response.text


def test_query_endpoint_rejects_empty_query():
    client = TestClient(app)
    response = client.post("/query", json={"query": ""})

    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Implement `app/api/schemas.py`**

```python
"""Request/response schemas for the query API."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
```

- [ ] **Step 4: Implement `app/api/router.py`**

```python
"""Query API: streams the agent graph's step-by-step trace, then the final result, as SSE."""

import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import QueryRequest
from app.core.config import get_settings
from app.graph.build import build_graph

router = APIRouter(tags=["query"])


def get_graph():
    """Build the compiled orchestration graph from current settings.

    A thin, separately-mockable seam: tests patch this function rather than the graph internals.
    """
    settings = get_settings()
    from app.agents.llm import get_ollama_model
    from app.rag_client.auth import RagPlatformAuth
    from app.rag_client.retrieval import RagPlatformRetrievalClient
    import httpx

    model = get_ollama_model(settings)
    http_client = httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)
    auth = RagPlatformAuth(settings.rag_platform_base_url, settings.rag_platform_email, settings.rag_platform_password, http_client)
    retrieval_client = RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)
    mcp_command = ["python", "-m", "app.mcp_server.server"]
    return build_graph(model, retrieval_client, mcp_command, settings.max_verification_retries)


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _event_stream(query: str) -> Iterator[str]:
    graph = get_graph()
    initial_state = {
        "query": query, "gatekeeper_decision": None, "evidence": [], "draft": None,
        "verification": None, "retry_count": 0, "final_answer": None, "refused": False, "trace": [],
    }
    final_state = await graph.ainvoke(initial_state)
    for step in final_state["trace"]:
        yield _format_sse("step", step)
    yield _format_sse("result", {"final_answer": final_state["final_answer"], "refused": final_state["refused"]})


@router.post("/query")
async def query(request: QueryRequest) -> StreamingResponse:
    """Run a query through the agent graph, streaming each agent's step live."""
    return StreamingResponse(_event_stream(request.query), media_type="text/event-stream")
```

- [ ] **Step 5: Implement `app/main.py`**

```python
"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.router import router as query_router

app = FastAPI(title="Agentic RAG Orchestration")
app.include_router(query_router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/api/test_router.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add app/api/ app/main.py tests/api/
git commit -m "feat: add FastAPI SSE query endpoint streaming the agent trace"
```

---

## Task 14: Fixture Knowledge Base & End-to-End Integration Test

**Files:**
- Create: `tests/fixtures/sample_kb.py`
- Create: `tests/integration/test_end_to_end.py`

**Interfaces:**
- Consumes: everything from Tasks 5-12.
- Produces: a reusable in-memory fixture (`SAMPLE_KB_CHUNKS: list[RetrievedChunk]`) and integration tests covering the four Review Focus paths that unit tests alone don't exercise end-to-end: KB-sufficient, web-fallback, refusal (unreachable-equivalent empty evidence), and retry-then-refuse.

- [ ] **Step 1: Write `tests/fixtures/sample_kb.py`**

```python
"""A small, synthetic fixture knowledge base for integration tests -- not real ingested
documents. Mirrors `enterprise-rag-platform`'s `RetrievedChunk` shape exactly.
"""

from app.rag_client.schemas import RetrievedChunk

SAMPLE_KB_CHUNKS = [
    RetrievedChunk(
        chunk_id="c1", document_id="d1", text="Paris is the capital of France.",
        section_path=["Geography", "Europe"], page_start=1, page_end=1,
        source_filename="world-facts.pdf", score=0.95,
    ),
    RetrievedChunk(
        chunk_id="c2", document_id="d1", text="France's population was approximately 68 million in 2023.",
        section_path=["Geography", "Europe"], page_start=2, page_end=2,
        source_filename="world-facts.pdf", score=0.81,
    ),
]
```

- [ ] **Step 2: Write the integration tests**

```python
# tests/integration/test_end_to_end.py
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.schemas import DraftAnswer, Evidence, GatekeeperDecision, VerificationResult
from app.graph.build import build_graph


def _initial_state(query: str) -> dict:
    return {
        "query": query, "gatekeeper_decision": None, "evidence": [], "draft": None,
        "verification": None, "retry_count": 0, "final_answer": None, "refused": False, "trace": [],
    }


@pytest.mark.asyncio
async def test_kb_sufficient_path_produces_grounded_answer():
    kb_evidence = [Evidence(text="Paris is the capital of France.", source="knowledge_base", citation="world-facts.pdf")]
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="strong KB match"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=kb_evidence))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="Paris [world-facts.pdf]", cited_evidence=kb_evidence))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="matches"))),
    ):
        graph = build_graph(None, None, [], max_retries=2)
        state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert state["final_answer"] == "Paris [world-facts.pdf]"
    assert state["refused"] is False


@pytest.mark.asyncio
async def test_web_fallback_path_labels_evidence_as_web():
    web_evidence = [Evidence(text="Sunny, 28C", source="web", citation="https://weather.example")]
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="web_fallback", reasoning="not in KB"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=web_evidence))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(
            text="According to a web search, it is sunny and 28C in Pune today.", cited_evidence=web_evidence,
        ))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(grounded=True, unsupported_claims=[], reasoning="matches"))),
    ):
        graph = build_graph(None, None, [], max_retries=2)
        state = await graph.ainvoke(_initial_state("What's the weather in Pune today?"))

    assert "web search" in state["final_answer"].lower()
    assert state["refused"] is False


@pytest.mark.asyncio
async def test_out_of_scope_query_is_refused_without_research():
    research_mock = AsyncMock()
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="refuse", reasoning="nonsensical question"))),
        patch("app.graph.build.research", research_mock),
    ):
        graph = build_graph(None, None, [], max_retries=2)
        state = await graph.ainvoke(_initial_state("asdkjaslkdj?"))

    assert state["refused"] is True
    research_mock.assert_not_called()


@pytest.mark.asyncio
async def test_web_fallback_with_no_results_refuses_cleanly():
    """Review Focus: web search fallback itself fails/returns nothing -- must refuse, not crash."""
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="web_fallback", reasoning="not in KB"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=[]))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(
            text="I could not find enough evidence to answer this question.", cited_evidence=[],
        ))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=VerificationResult(
            grounded=False, unsupported_claims=["I could not find enough evidence to answer this question."],
            reasoning="no cited evidence to verify against",
        ))),
    ):
        graph = build_graph(None, None, [], max_retries=2)
        state = await graph.ainvoke(_initial_state("What's the weather on Mars right now?"))

    assert state["refused"] is True
    assert state["final_answer"] is None


@pytest.mark.asyncio
async def test_persistent_ungrounded_answer_refuses_after_max_retries():
    kb_evidence = [Evidence(text="unrelated text", source="knowledge_base", citation="world-facts.pdf")]
    ungrounded = VerificationResult(grounded=False, unsupported_claims=["fabricated claim"], reasoning="not supported")
    with (
        patch("app.graph.build.grade_retrieval", AsyncMock(return_value=GatekeeperDecision(route="kb", reasoning="ok"))),
        patch("app.graph.build.research", AsyncMock(return_value=AsyncMock(evidence=kb_evidence))),
        patch("app.graph.build.write_answer", AsyncMock(return_value=DraftAnswer(text="fabricated claim", cited_evidence=kb_evidence))),
        patch("app.graph.build.verify_answer", AsyncMock(return_value=ungrounded)),
    ):
        graph = build_graph(None, None, [], max_retries=2)
        state = await graph.ainvoke(_initial_state("What is the capital of France?"))

    assert state["refused"] is True
    assert state["final_answer"] is None
    assert state["retry_count"] == 2
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_end_to_end.py -v`
Expected: PASS (5 tests)

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/ tests/integration/
git commit -m "test: add fixture KB and end-to-end integration tests for all graph paths"
```

---

## Task 15: Langfuse Tracing (Graceful No-Op Without Credentials)

**Files:**
- Create: `app/core/tracing.py`
- Modify: `app/graph/build.py`
- Test: `tests/core/test_tracing.py`

**Interfaces:**
- Consumes: `app.core.config.Settings` (Task 1).
- Produces: `def get_tracer(settings: Settings) -> Tracer` where `Tracer` has `def trace_step(self, step: dict) -> None`. When `settings.langfuse_public_key`/`langfuse_secret_key` are unset (e.g. `ERP-112` not yet landed in `enterprise-rag-platform`), `get_tracer` returns a no-op tracer instead of raising — this project's core flow must never be blocked on Langfuse being configured.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_tracing.py
from app.core.config import Settings
from app.core.tracing import NoOpTracer, get_tracer


def test_get_tracer_returns_noop_without_credentials():
    settings = Settings(
        rag_platform_base_url="http://localhost:8000",
        rag_platform_email="svc@example.com",
        rag_platform_password="secret123",
    )

    tracer = get_tracer(settings)

    assert isinstance(tracer, NoOpTracer)
    tracer.trace_step({"agent": "gatekeeper", "route": "kb"})  # must not raise


def test_get_tracer_returns_langfuse_tracer_with_credentials():
    settings = Settings(
        rag_platform_base_url="http://localhost:8000",
        rag_platform_email="svc@example.com",
        rag_platform_password="secret123",
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
    )

    tracer = get_tracer(settings)

    assert not isinstance(tracer, NoOpTracer)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_tracing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.tracing'`

- [ ] **Step 3: Implement `app/core/tracing.py`**

```python
"""Evaluation tracing via Langfuse Cloud (Hobby/free tier) -- gracefully degrades to a no-op
when no credentials are configured, so this project's core flow is never blocked on
`enterprise-rag-platform`'s ERP-112 (its own Langfuse setup) having landed first.
"""

from typing import Protocol

from app.core.config import Settings


class Tracer(Protocol):
    def trace_step(self, step: dict) -> None: ...


class NoOpTracer:
    """Used whenever Langfuse credentials are absent."""

    def trace_step(self, step: dict) -> None:
        return None


class LangfuseTracer:
    """Sends each agent step as a Langfuse observation, sharing the account
    `enterprise-rag-platform`'s ERP-112 sets up, as a separate project within it."""

    def __init__(self, public_key: str, secret_key: str, host: str) -> None:
        from langfuse import Langfuse

        self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    def trace_step(self, step: dict) -> None:
        self._client.event(name=step.get("agent", "unknown"), metadata=step)


def get_tracer(settings: Settings) -> Tracer:
    """Return a `LangfuseTracer` if credentials are configured, else a `NoOpTracer`."""
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        return LangfuseTracer(settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_host)
    return NoOpTracer()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_tracing.py -v`
Expected: PASS (2 tests) — note: `test_get_tracer_returns_langfuse_tracer_with_credentials` requires the `langfuse` package installed (Step 5 adds it) but does not require real, valid credentials, since the `Langfuse` client only validates lazily on first flush.

- [ ] **Step 5: Add the `langfuse` dependency and wire tracing into the graph**

Run: `uv add langfuse`

Modify `app/graph/build.py`: add a `tracer: Tracer` parameter to `build_graph`, and call `tracer.trace_step(...)` alongside every existing `state["trace"].append(...)` call in each node (four call sites: gatekeeper, research, writer, verifier nodes) — passed as an added positional/keyword argument to `build_graph`, defaulting to `NoOpTracer()` when not supplied, and update `app/api/router.py`'s `get_graph()` to construct it via `get_tracer(settings)` and pass it through.

- [ ] **Step 6: Run the full test suite to confirm nothing regressed**

Run: `uv run pytest -v`
Expected: PASS (all tests from Tasks 1-15)

- [ ] **Step 7: Commit**

```bash
git add app/core/tracing.py app/graph/build.py app/api/router.py tests/core/
git commit -m "feat: add Langfuse tracing with graceful no-op fallback"
```

---

## Task 16: Gradio Two-Tab Demo UI

**Files:**
- Create: `app/ui/__init__.py`
- Create: `app/ui/app.py`
- Test: `tests/ui/test_app.py`

**Interfaces:**
- Consumes: `app.api.router.get_graph` (Task 13), `app.core.config.get_settings` (Task 1), `app.rag_client.retrieval.RagPlatformRetrievalClient` (Task 3, for the Direct-RAG tab's plain call).
- Produces: `def build_ui() -> gradio.Blocks` with two tabs, "Direct RAG" and "Agentic RAG". Runnable via `python -m app.ui.app`.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_app.py
from unittest.mock import AsyncMock, patch

import gradio as gr
import pytest

from app.ui.app import build_ui, run_agentic_query, run_direct_query


def test_build_ui_returns_blocks_with_two_tabs():
    demo = build_ui()

    assert isinstance(demo, gr.Blocks)


@pytest.mark.asyncio
async def test_run_direct_query_returns_plain_answer_text():
    fake_client = AsyncMock()
    fake_client.search.return_value = AsyncMock(
        results=[AsyncMock(text="Paris is the capital of France.", source_filename="world-facts.pdf")]
    )

    with patch("app.ui.app._get_retrieval_client", return_value=fake_client):
        answer = await run_direct_query("What is the capital of France?")

    assert "Paris" in answer


@pytest.mark.asyncio
async def test_run_agentic_query_returns_trace_and_answer():
    fake_state = {
        "final_answer": "Paris [world-facts.pdf]", "refused": False,
        "trace": [{"agent": "gatekeeper", "route": "kb", "reasoning": "ok"}],
    }
    fake_graph = AsyncMock()
    fake_graph.ainvoke.return_value = fake_state

    with patch("app.ui.app.get_graph", return_value=fake_graph):
        trace_text, answer_text = await run_agentic_query("What is the capital of France?")

    assert "gatekeeper" in trace_text
    assert "Paris" in answer_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ui/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ui.app'`

- [ ] **Step 3: Implement `app/ui/app.py`**

```python
"""Two-tab Gradio demo: Direct RAG (single retrieval pass, no correction) side by side with
Agentic RAG (the full Gatekeeper->Research->Writer->Verifier trace, streamed live), so the
value of the correction loop is shown, not just explained. Not a production UI.
"""

import gradio as gr
import httpx

from app.api.router import get_graph
from app.core.config import get_settings
from app.rag_client.auth import RagPlatformAuth
from app.rag_client.retrieval import RagPlatformRetrievalClient


def _get_retrieval_client() -> RagPlatformRetrievalClient:
    settings = get_settings()
    http_client = httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)
    auth = RagPlatformAuth(settings.rag_platform_base_url, settings.rag_platform_email, settings.rag_platform_password, http_client)
    return RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)


async def run_direct_query(query: str) -> str:
    """Direct-RAG tab: one retrieval pass, top chunk's text returned as-is, no synthesis."""
    client = _get_retrieval_client()
    result = await client.search(query, top_k=1)
    if not result.results:
        return "No matching results found in the knowledge base."
    top = result.results[0]
    return f"{top.text}\n\n(source: {top.source_filename})"


async def run_agentic_query(query: str) -> tuple[str, str]:
    """Agentic-RAG tab: run the full graph, render the trace and the final (possibly refused) answer."""
    graph = get_graph()
    initial_state = {
        "query": query, "gatekeeper_decision": None, "evidence": [], "draft": None,
        "verification": None, "retry_count": 0, "final_answer": None, "refused": False, "trace": [],
    }
    final_state = await graph.ainvoke(initial_state)
    trace_lines = [f"{step.get('agent', '?')}: {step}" for step in final_state["trace"]]
    trace_text = "\n".join(trace_lines)
    answer_text = final_state["final_answer"] or "The system could not produce a grounded answer and refused to guess."
    return trace_text, answer_text


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Agentic RAG Orchestration") as demo:
        with gr.Tab("Direct RAG"):
            direct_input = gr.Textbox(label="Question")
            direct_output = gr.Textbox(label="Answer (single retrieval pass, no correction)")
            direct_input.submit(run_direct_query, inputs=direct_input, outputs=direct_output)

        with gr.Tab("Agentic RAG"):
            agentic_input = gr.Textbox(label="Question")
            trace_output = gr.Textbox(label="Agent trace", lines=10)
            answer_output = gr.Textbox(label="Final answer")
            agentic_input.submit(run_agentic_query, inputs=agentic_input, outputs=[trace_output, answer_output])

    return demo


if __name__ == "__main__":
    build_ui().launch()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/ui/test_app.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/ui/ tests/ui/
git commit -m "feat: add two-tab Gradio demo comparing direct RAG and agentic RAG"
```

---

## Task 17: CI-Style Quality Gate

**Files:**
- Modify: `pyproject.toml` (ruff/mypy config, if not already present from Task 1's `uv add --dev`)
- Create: `docs/README.md` section is out of scope here — this task only runs the gate, no new source files.

**Interfaces:**
- N/A — this task verifies, it does not add new interfaces.

- [ ] **Step 1: Run the full test suite with coverage**

Run: `uv run pytest --cov=app --cov-report=term-missing -v`
Expected: All tests from Tasks 1-16 PASS.

- [ ] **Step 2: Run ruff**

Run: `uv run ruff check app tests`
Expected: No errors. Fix any that appear (formatting/import-order issues are the most likely; fix in place, do not disable rules).

- [ ] **Step 3: Run mypy**

Run: `uv run mypy app`
Expected: No errors. If PydanticAI/LangGraph's stub coverage produces false positives on the `model`/`retrieval_client` untyped parameters used in Task 12/13, add precise local type aliases rather than blanket `# type: ignore`.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore: fix lint/type issues found by the quality gate"
```

(Skip this commit if Steps 2-3 found nothing to fix.)
