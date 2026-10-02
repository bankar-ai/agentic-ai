"""Authentication against `enterprise-rag-platform`: login, cache, and refresh CSRF tokens.

ERP-116 (discovered live 2026-10-01): that platform delivers access/refresh tokens as httpOnly
cookies now, not in the login/refresh response body or accepted via an `Authorization` header --
see `app/rag_client/schemas.py`'s module docstring for the full contract. This client relies on
its caller passing the *same* `httpx.AsyncClient` instance to both this class and
`RagPlatformRetrievalClient`: that client's own cookie jar captures the `Set-Cookie`s from login
and replays them automatically on every later request, so this file only ever has to track the
one thing that does NOT travel via cookie -- the CSRF token, required as an `X-CSRF-Token` header
on every state-changing (POST/PUT/PATCH/DELETE) request.
"""

from typing import Protocol

import httpx

from app.rag_client.schemas import AuthSession


class RagPlatformAuthError(RuntimeError):
    """Raised when login or token refresh against `enterprise-rag-platform` fails."""


class RagPlatformAuthProvider(Protocol):
    """What `RagPlatformRetrievalClient` needs from an auth source -- satisfied by both
    `RagPlatformAuth` (the fixed service account) and `StaticTokenAuth` (a per-user session,
    AGT-013), so the retrieval client doesn't need to know which one it was given.
    """

    async def get_csrf_token(self) -> str: ...
    async def refresh(self) -> str: ...


class RagPlatformAuth:
    """Holds and refreshes one user's session (cookies + CSRF token) for `enterprise-rag-platform`.

    The access/refresh token *cookies* are never touched directly here -- they live in the shared
    `http_client`'s own cookie jar, set by the platform's `Set-Cookie` response headers and
    replayed by httpx automatically on every later request through that same client instance.
    """

    def __init__(self, base_url: str, email: str, password: str, http_client: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._email = email
        self._password = password
        self._http = http_client
        self._csrf_token: str | None = None

    async def get_csrf_token(self) -> str:
        """Return a cached CSRF token, logging in on first use."""
        if self._csrf_token is None:
            self._csrf_token = await self._login()
        return self._csrf_token

    async def refresh(self) -> str:
        """Rotate the refresh-token cookie (sent automatically by the shared http client) and
        return the new CSRF token. The refresh call is itself CSRF-protected, so it needs the
        *current* token as a header even though it's about to issue a new one.
        """
        if self._csrf_token is None:
            self._csrf_token = await self._login()
            return self._csrf_token
        response = await self._http.post("/auth/refresh", headers={"X-CSRF-Token": self._csrf_token})
        if response.status_code != 200:
            raise RagPlatformAuthError(f"Token refresh failed: {response.status_code} {response.text}")
        self._csrf_token = AuthSession(**response.json()).csrf_token
        return self._csrf_token

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

    Shared by every caller that needs a usable session handed back as plain values rather than
    left sitting in `http_client`'s cookie jar (AGT-016): the Gradio UI's own login flow and the
    `POST /auth/login` proxy endpoint both call this instead of duplicating the
    `RagPlatformAuth` + cookie-jar-read dance. Raises `RagPlatformAuthError` on bad credentials,
    or if login otherwise succeeds without actually issuing the `access_token` cookie.
    """
    auth = RagPlatformAuth(base_url, email, password, http_client)
    csrf_token = await auth.get_csrf_token()
    access_token = http_client.cookies.get("access_token")
    if not access_token:
        raise RagPlatformAuthError("Login succeeded but no session cookie was issued.")
    return access_token, csrf_token


class StaticTokenAuth:
    """Wraps an already-established end-user session (AGT-013's multi-tenant path): the access
    token to inject into the shared http client's cookie jar, plus the matching CSRF token.

    Used when a caller supplies their own `enterprise-rag-platform` session (e.g. via this
    project's `Authorization`/`X-RAG-CSRF-Token` headers) instead of the fixed service account
    `RagPlatformAuth` logs in as. Has no password, so it cannot actually refresh -- an expired
    session means the end user must log in again at the RAG platform, not something this adapter
    can recover from on its own.
    """

    def __init__(self, access_token: str, csrf_token: str, http_client: httpx.AsyncClient, base_url: str) -> None:
        # httpx cookie jars are scoped by domain; setting this directly (rather than waiting for
        # a Set-Cookie response) is what lets a supplied session work without this adapter ever
        # calling /auth/login itself.
        http_client.cookies.set("access_token", access_token, domain=httpx.URL(base_url).host)
        self._csrf_token = csrf_token

    async def get_csrf_token(self) -> str:
        return self._csrf_token

    async def refresh(self) -> str:
        raise RagPlatformAuthError("Supplied session expired or was rejected; please log in again.")
