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

from app.core.query_cache import decode_user_id
from app.core.session_store import SessionStore
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
    account. Has no password of its own, so a *silent* refresh is only possible when a refresh
    token for this user was captured at login and handed in here via `session_store`/`http_client`
    (AGT-051) -- without those, an expired session still means the end user must log in again,
    same as before AGT-051.
    """

    def __init__(
        self,
        access_token: str,
        csrf_token: str,
        session_store: SessionStore | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._access_token = access_token
        self._csrf_token = csrf_token
        self._session_store = session_store
        self._http = http_client

    async def get_access_token(self) -> str:
        return self._access_token

    async def get_csrf_token(self) -> str:
        return self._csrf_token

    async def refresh(self) -> tuple[str, str]:
        """AGT-051: if this instance was built with a `session_store`/`http_client` (i.e. the
        caller forwarded them, which every real request path does -- see `app/api/router.py`),
        attempt a real silent refresh using whatever refresh token was captured at login. Falls
        back to the original "please log in again" error in every case that isn't a clean
        success: no store/client wired in, no stored token for this user, decode failure, or the
        platform itself rejecting the stored token (e.g. it was revoked) -- a stale/invalid
        refresh token is deleted so the next attempt doesn't keep retrying a dead credential.
        """
        if self._session_store is not None and self._http is not None:
            new_tokens = await self._try_silent_refresh()
            if new_tokens is not None:
                return new_tokens
        raise RagPlatformAuthError("Supplied session expired or was rejected; please log in again.")

    async def _try_silent_refresh(self) -> tuple[str, str] | None:
        assert self._session_store is not None and self._http is not None
        user_id = decode_user_id(self._access_token)
        if user_id is None:
            return None
        refresh_token = await self._session_store.get_refresh_token(user_id)
        if refresh_token is None:
            return None
        response = await self._http.post(
            "/auth/refresh",
            headers={
                "X-CSRF-Token": self._csrf_token,
                "Cookie": f"refresh_token={refresh_token}; csrf_token={self._csrf_token}",
            },
        )
        if response.status_code != 200:
            # The stored refresh token itself is dead (expired/revoked server-side) -- clean it
            # up so the next request fails fast into the normal "log in again" path instead of
            # retrying a credential that will never work again.
            await self._session_store.delete(user_id)
            return None
        new_access_token = response.cookies.get("access_token")
        new_refresh_token = response.cookies.get("refresh_token")
        if not new_access_token:
            return None
        new_csrf_token = AuthSession(**response.json()).csrf_token
        if new_refresh_token:
            # ERP-116-style refresh rotation: the old refresh token may already be invalidated by
            # this call, so the stored value must be updated to the new one or the *next* refresh
            # attempt would fail even though this one just succeeded.
            await self._session_store.save_refresh_token(user_id, new_refresh_token)
        self._access_token = new_access_token
        self._csrf_token = new_csrf_token
        return self._access_token, self._csrf_token
