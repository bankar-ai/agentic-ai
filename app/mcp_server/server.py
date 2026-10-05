"""MCP tool server exposing `enterprise-rag-platform`'s retrieval API as a `search_knowledge_base`
tool. Run standalone via `python -m app.mcp_server.server` (stdio transport); the Research agent
(Task 9) connects to this as an MCP client subprocess.
"""

import asyncio

import httpx
from mcp.server.mcpserver import MCPServer

from app.core.config import Settings, get_settings
from app.core.session_store import get_session_store
from app.rag_client.auth import (
    RagPlatformAuth,
    RagPlatformAuthProvider,
    StaticTokenAuth,
)
from app.rag_client.retrieval import RagPlatformRetrievalClient

mcp_server = MCPServer("rag-retrieval")


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


async def _build_auth(settings: Settings, http_client: httpx.AsyncClient) -> RagPlatformAuthProvider:
    """AGT-013: a per-user session (forwarded via RAG_PLATFORM_ACCESS_TOKEN/CSRF_TOKEN env) takes
    priority over the fixed service account, so this subprocess retrieves as the end user when
    one is logged in, and as the configured service account otherwise.

    AGT-051: `DATABASE_URL` is also forwarded to this subprocess (`app/agents/research.py`'s
    `_FORWARDED_ENV_PREFIXES`) so the `kb`-route path -- the dominant real retrieval path -- gets
    the same silent-refresh capability as the endpoints that call `RagPlatformRetrievalClient`
    directly, not just `/query/direct`/`/documents`.
    """
    if settings.rag_platform_access_token and settings.rag_platform_csrf_token:
        session_store = await get_session_store(settings.database_url)
        return StaticTokenAuth(
            settings.rag_platform_access_token, settings.rag_platform_csrf_token, session_store, http_client
        )
    return RagPlatformAuth(
        settings.rag_platform_base_url, settings.rag_platform_email, settings.rag_platform_password, http_client
    )


async def _build_retrieval_client() -> RagPlatformRetrievalClient:
    settings = get_settings()
    http_client = httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)
    auth = await _build_auth(settings, http_client)
    return RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)


_client: RagPlatformRetrievalClient | None = None


async def _get_retrieval_client() -> RagPlatformRetrievalClient:
    """Lazily construct and cache the retrieval client for this subprocess's one lifetime."""
    global _client
    if _client is None:
        _client = await _build_retrieval_client()
    return _client


async def _close_retrieval_client() -> None:
    """AGT-009/AGT-012: close the cached client's underlying httpx connection on process exit --
    this subprocess is short-lived (spawned fresh per Research call), but was never explicitly
    cleaning up its one connection.
    """
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


@mcp_server.tool()
async def search_knowledge_base(
    query: str, top_k: int = 5, rerank: bool = False, expand_sections: bool = False
) -> list[dict]:
    """Search the enterprise knowledge base and return the top matching chunks.

    Each result has `text`, `source_filename`, `section_path`, and a fused relevance `score`
    in (0, 1]. Returns an empty list, not an error, when nothing relevant is found.
    """
    return await _search_knowledge_base_impl(await _get_retrieval_client(), query, top_k, rerank, expand_sections)


async def _run() -> None:
    try:
        await mcp_server.run_stdio_async()
    finally:
        await _close_retrieval_client()


if __name__ == "__main__":
    asyncio.run(_run())
