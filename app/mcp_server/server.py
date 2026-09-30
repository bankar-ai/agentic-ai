"""MCP tool server exposing `enterprise-rag-platform`'s retrieval API as a `search_knowledge_base`
tool. Run standalone via `python -m app.mcp_server.server` (stdio transport); the Research agent
(Task 9) connects to this as an MCP client subprocess.
"""

from functools import lru_cache

import httpx
from mcp.server.mcpserver import MCPServer

from app.core.config import get_settings
from app.rag_client.auth import RagPlatformAuth
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


def _build_retrieval_client() -> RagPlatformRetrievalClient:
    settings = get_settings()
    http_client = httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)
    auth = RagPlatformAuth(
        settings.rag_platform_base_url, settings.rag_platform_email, settings.rag_platform_password, http_client
    )
    return RagPlatformRetrievalClient(settings.rag_platform_base_url, auth, http_client)


@lru_cache
def _get_retrieval_client() -> RagPlatformRetrievalClient:
    """Lazily construct and cache the retrieval client on first access."""
    return _build_retrieval_client()


@mcp_server.tool()
async def search_knowledge_base(
    query: str, top_k: int = 5, rerank: bool = False, expand_sections: bool = False
) -> list[dict]:
    """Search the enterprise knowledge base and return the top matching chunks.

    Each result has `text`, `source_filename`, `section_path`, and a fused relevance `score`
    in (0, 1]. Returns an empty list, not an error, when nothing relevant is found.
    """
    return await _search_knowledge_base_impl(_get_retrieval_client(), query, top_k, rerank, expand_sections)


if __name__ == "__main__":
    mcp_server.run(transport="stdio")
