"""Documents client for `enterprise-rag-platform`'s `GET /documents` endpoint (AGT-025).

Lets a logged-in user see what's actually in their knowledge base before asking a question,
instead of guessing. Pure read access -- no upload/delete capability here, that stays on
`enterprise-rag-platform` directly (out of scope, see AGT-025's own ticket).

Auth pattern mirrors `RagPlatformRetrievalClient` exactly (`app/rag_client/retrieval.py`): Cookie +
X-CSRF-Token headers built explicitly per request, refresh-once-on-401/403.
"""

from datetime import datetime

import httpx
from pydantic import BaseModel

from app.rag_client.auth import RagPlatformAuthProvider


class DocumentSummary(BaseModel):
    """One of the caller's successfully ingested documents, mirroring
    `enterprise-rag-platform`'s `DocumentSummary`."""

    document_id: str
    filename: str
    created_at: datetime


class DocumentListResult(BaseModel):
    documents: list[DocumentSummary]
    has_more: bool


class RagPlatformDocumentsError(RuntimeError):
    """Raised when a documents-list call fails after one refresh-and-retry, or on a network error."""


class RagPlatformDocumentsClient:
    """Calls `enterprise-rag-platform`'s `GET /documents` on behalf of the logged-in caller."""

    def __init__(self, base_url: str, auth: RagPlatformAuthProvider, http_client: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._auth = auth
        self._http = http_client

    async def list_documents(self, limit: int = 50, offset: int = 0) -> DocumentListResult:
        """List the caller's successfully ingested documents, newest first, refreshing the
        session once on a 401/403 (same retry-once signal as `RagPlatformRetrievalClient`).
        """
        try:
            access_token, csrf_token = await self._auth.get_access_token(), await self._auth.get_csrf_token()
            response = await self._request(limit, offset, access_token, csrf_token)
            if response.status_code in (401, 403):
                access_token, csrf_token = await self._auth.refresh()
                response = await self._request(limit, offset, access_token, csrf_token)
        except httpx.HTTPError as exc:
            raise RagPlatformDocumentsError(f"Documents request failed: {exc}") from exc

        if response.status_code != 200:
            raise RagPlatformDocumentsError(
                f"Documents list failed: {response.status_code} {response.text}"
            )
        return DocumentListResult(**response.json())

    async def _request(self, limit: int, offset: int, access_token: str, csrf_token: str) -> httpx.Response:
        return await self._http.get(
            "/documents",
            params={"limit": limit, "offset": offset},
            headers={
                "X-CSRF-Token": csrf_token,
                "Cookie": f"access_token={access_token}; csrf_token={csrf_token}",
            },
        )
