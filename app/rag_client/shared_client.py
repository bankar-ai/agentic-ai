"""One process-wide `httpx.AsyncClient` for talking to `enterprise-rag-platform` (AGT-009).

Safe to share across concurrent requests for *different* users only because, since the
`StaticTokenAuth`/`RagPlatformAuth` refactor in `app/rag_client/auth.py`, nothing in this
package relies on this client's own cookie jar for per-caller session state anymore -- every
auth value travels as an explicit per-request header instead. This client holds connections
(pooling), never session state.

Before this, `get_graph()` and `_get_retrieval_client()` built (and never closed) a fresh client
on every single request -- a fresh TCP connection per query, never reused, never cleaned up.
"""

from functools import lru_cache

import httpx

from app.core.config import get_settings


@lru_cache
def get_shared_rag_platform_client() -> httpx.AsyncClient:
    """Return the one shared client for this process, creating it on first use."""
    settings = get_settings()
    return httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0)


async def close_shared_rag_platform_client() -> None:
    """Close the shared client, if one was ever created. Call on process/app shutdown."""
    if get_shared_rag_platform_client.cache_info().currsize:
        await get_shared_rag_platform_client().aclose()
    get_shared_rag_platform_client.cache_clear()
