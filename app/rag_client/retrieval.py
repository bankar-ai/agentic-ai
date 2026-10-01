"""Retrieval client for `enterprise-rag-platform`'s `POST /retrieval/query` endpoint.

That endpoint does hybrid (FAISS + BM25, fused) retrieval as a single call -- there are no
separate keyword/semantic/chunk-level strategies to choose between, so this client exposes
exactly the parameters the real endpoint accepts: `top_k`, `rerank`, `expand_sections`,
`document_ids`.
"""

import httpx

from app.rag_client.auth import RagPlatformAuthProvider
from app.rag_client.schemas import RetrievalResult


class RagPlatformRetrievalError(RuntimeError):
    """Raised when a retrieval call fails after one refresh-and-retry, or on a network error."""


class RagPlatformRetrievalClient:
    """Calls `enterprise-rag-platform`'s retrieval API on behalf of this project's service user."""

    def __init__(self, base_url: str, auth: RagPlatformAuthProvider, http_client: httpx.AsyncClient) -> None:
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
