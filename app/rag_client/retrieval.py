"""Retrieval client for `enterprise-rag-platform`'s `POST /retrieval/query` endpoint.

That endpoint does hybrid (FAISS + BM25, fused) retrieval as a single call -- there are no
separate keyword/semantic/chunk-level strategies to choose between, so this client exposes
exactly the parameters the real endpoint accepts: `top_k`, `rerank`, `expand_sections`,
`document_ids`.

ERP-116: auth travels as a `Cookie: access_token=...` header plus an `X-CSRF-Token` header, both
built explicitly per request from whatever `auth` hands back (AGT-009: never via `self._http`'s
own cookie jar -- that client may be shared across concurrent requests for *different* users, and
a shared mutable jar would leak one user's session into another's in-flight request). See
`app/rag_client/auth.py`'s module docstring for the full contract.
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
        """Run one hybrid retrieval query, refreshing the session once on a 401/403.

        A 403 (not just 401) can mean "CSRF token stale after a refresh elsewhere", so both are
        treated as the same retry-once signal here.
        """
        payload = {
            "query": query, "top_k": top_k, "rerank": rerank,
            "expand_sections": expand_sections, "document_ids": document_ids,
        }
        try:
            access_token, csrf_token = await self._auth.get_access_token(), await self._auth.get_csrf_token()
            response = await self._request(payload, access_token, csrf_token)
            if response.status_code in (401, 403):
                access_token, csrf_token = await self._auth.refresh()
                response = await self._request(payload, access_token, csrf_token)
        except httpx.HTTPError as exc:
            raise RagPlatformRetrievalError(f"Retrieval request failed: {exc}") from exc

        if response.status_code != 200:
            raise RagPlatformRetrievalError(
                f"Retrieval query failed: {response.status_code} {response.text}"
            )
        return RetrievalResult(**response.json())

    async def aclose(self) -> None:
        """Close the underlying http client. Callers that built their own client (rather than
        using the process-wide shared one, AGT-009) are responsible for calling this.
        """
        await self._http.aclose()

    async def _request(self, payload: dict, access_token: str, csrf_token: str) -> httpx.Response:
        # The platform's CSRF check is a double-submit: the `X-CSRF-Token` header must match a
        # `csrf_token` *cookie*, not just a per-session server-side value (found live
        # 2026-10-02) -- so csrf_token travels as both a cookie and a header here, not just one.
        return await self._http.post(
            "/retrieval/query", json=payload,
            headers={
                "X-CSRF-Token": csrf_token,
                "Cookie": f"access_token={access_token}; csrf_token={csrf_token}",
            },
        )
