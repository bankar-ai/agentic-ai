"""Authentication against `enterprise-rag-platform`: login, cache, and refresh tokens.

That platform has no API-key/service-account mechanism -- every retrieval call needs a JWT
obtained via email+password login (see its `app/auth/router.py`). This client logs in once,
caches the access token, and rotates via the refresh endpoint rather than re-logging-in per call.
"""

from typing import Protocol

import httpx

from app.rag_client.schemas import TokenPair


class RagPlatformAuthError(RuntimeError):
    """Raised when login or token refresh against `enterprise-rag-platform` fails."""


class RagPlatformAuthProvider(Protocol):
    """What `RagPlatformRetrievalClient` needs from an auth source -- satisfied by both
    `RagPlatformAuth` (the fixed service account) and `StaticTokenAuth` (a per-user token,
    AGT-013), so the retrieval client doesn't need to know which one it was given.
    """

    async def get_access_token(self) -> str: ...
    async def refresh(self) -> str: ...


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


class StaticTokenAuth:
    """Wraps an already-issued end-user access token (AGT-013's multi-tenant path).

    Used when a caller supplies their own `enterprise-rag-platform` token (e.g. via this
    project's `Authorization` header) instead of the fixed service account `RagPlatformAuth`
    logs in as. Has no password, so it cannot actually refresh -- an expired token means the
    end user must log in again at the RAG platform, not something this adapter can recover
    from on its own. Satisfies the same interface `RagPlatformRetrievalClient` expects.
    """

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    async def get_access_token(self) -> str:
        return self._access_token

    async def refresh(self) -> str:
        raise RagPlatformAuthError("Supplied access token expired or was rejected; please log in again.")
