"""Authentication against `enterprise-rag-platform`: login, cache, and refresh session tokens.

ERP-116 (discovered live 2026-10-01): that platform delivers access/refresh tokens as httpOnly
cookies now, not in the login/refresh response body or accepted via an `Authorization` header --
see `app/rag_client/schemas.py`'s module docstring for the full contract. The CSRF check is a
genuine double-submit: the `X-CSRF-Token` header must match a `csrf_token` cookie, not just a
per-session server-side value (found live 2026-10-02, AGT-017's integration testing).

AGT-009 (2026-10-03): this file used to lean on a shared `httpx.AsyncClient`'s own cookie jar to
carry the access-token cookie automatically. That's unsafe once that client is reused across
*concurrent requests from different users* (AGT-009's whole point) -- one jar, mutated per
request, would leak one user's cookies into another's in-flight request. So every auth provider
here now hands back the access token and CSRF token as plain values, and
`RagPlatformRetrievalClient` attaches them as explicit per-request headers instead of relying on
any client-level jar state. This makes a single shared `http_client` safe to reuse across
requests: it holds connections, never per-caller session state.
"""

from typing import Protocol

import httpx

from app.rag_client.schemas import AuthSession


class RagPlatformAuthError(RuntimeError):
    """Raised when login or token refresh against `enterprise-rag-platform` fails."""


class RagPlatformAuthProvider(Protocol):
    """What `RagPlatformRetrievalClient` needs from an auth source -- satisfied by both
    `RagPlatformAuth` (a real login) and `StaticTokenAuth` (a per-user session, AGT-013), so the
    retrieval client doesn't need to know which one it was given.
    """

    async def get_access_token(self) -> str: ...
    async def get_csrf_token(self) -> str: ...
    async def refresh(self) -> tuple[str, str]: ...


class RagPlatformAuth:
    """Logs in once (lazily) and refreshes `enterprise-rag-platform`'s session on demand.

    Uses its own `http_client` to perform the actual login/refresh HTTP calls -- that client's
    cookie jar is where the platform's `Set-Cookie`s land, read back out explicitly below rather
    than relied on implicitly by later requests (see this module's docstring for why).
    """

    def __init__(self, base_url: str, email: str, password: str, http_client: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._email = email
        self._password = password
        self._http = http_client
        self._csrf_token: str | None = None

    async def get_access_token(self) -> str:
        """Return the current access token, logging in on first use if needed."""
        await self.get_csrf_token()
        access_token = self._http.cookies.get("access_token")
        if not access_token:
            raise RagPlatformAuthError("Login succeeded but no session cookie was issued.")
        return access_token

    async def get_csrf_token(self) -> str:
        """Return a cached CSRF token, logging in on first use."""
        if self._csrf_token is None:
            self._csrf_token = await self._login()
        return self._csrf_token

    async def refresh(self) -> tuple[str, str]:
        """Rotate the refresh-token cookie (sent automatically by this instance's own http
        client) and return the new `(access_token, csrf_token)`. The refresh call is itself
        CSRF-protected, so it needs the *current* token as a header even though it's about to
        issue a new one.
        """
        if self._csrf_token is None:
            self._csrf_token = await self._login()
            return await self.get_access_token(), self._csrf_token
        response = await self._http.post("/auth/refresh", headers={"X-CSRF-Token": self._csrf_token})
        if response.status_code != 200:
            raise RagPlatformAuthError(f"Token refresh failed: {response.status_code} {response.text}")
        self._csrf_token = AuthSession(**response.json()).csrf_token
        return await self.get_access_token(), self._csrf_token

    async def _login(self) -> str:
        response = await self._http.post(
            "/auth/login", json={"email": self._email, "password": self._password}
        )
        if response.status_code != 200:
            raise RagPlatformAuthError(f"Login failed: {response.status_code} {response.text}")
        return AuthSession(**response.json()).csrf_token


async def login_and_extract_session(
    base_url: str, email: str, password: str, http_client: httpx.AsyncClient
) -> tuple[str, str]:
    """Log in against `enterprise-rag-platform` and return `(access_token, csrf_token)`.

    Shared by every caller that needs a usable session handed back as plain values (AGT-016):
    the Gradio UI's own login flow and the `POST /auth/login` proxy endpoint both call this
    instead of duplicating the `RagPlatformAuth` dance.
    """
    auth = RagPlatformAuth(base_url, email, password, http_client)
    access_token = await auth.get_access_token()
    return access_token, await auth.get_csrf_token()


class StaticTokenAuth:
    """Wraps an already-established end-user session (AGT-013's multi-tenant path): the access
    token and CSRF token a caller already has, handed back as plain values on request.

    Used when a caller supplies their own `enterprise-rag-platform` session (e.g. via this
    project's `Authorization`/`X-RAG-CSRF-Token` headers) instead of logging in as a service
    account. Has no password, so it cannot actually refresh -- an expired session means the end
    user must log in again at the RAG platform, not something this adapter can recover from.
    """

    def __init__(self, access_token: str, csrf_token: str) -> None:
        self._access_token = access_token
        self._csrf_token = csrf_token

    async def get_access_token(self) -> str:
        return self._access_token

    async def get_csrf_token(self) -> str:
        return self._csrf_token

    async def refresh(self) -> tuple[str, str]:
        raise RagPlatformAuthError("Supplied session expired or was rejected; please log in again.")
