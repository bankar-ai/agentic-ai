import base64
import json

import httpx
import pytest

from app.rag_client.auth import RagPlatformAuth, RagPlatformAuthError, StaticTokenAuth


def _fake_jwt(sub: str) -> str:
    def b64(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS256'})}.{b64({'sub': sub})}.sig"


class _FakeSessionStore:
    """Stands in for `SessionStore` -- an in-memory dict, no real database."""

    def __init__(self, tokens: dict[str, str] | None = None):
        self._tokens = dict(tokens or {})
        self.deleted: list[str] = []

    async def get_refresh_token(self, user_id: str) -> str | None:
        return self._tokens.get(user_id)

    async def save_refresh_token(self, user_id: str, refresh_token: str) -> None:
        self._tokens[user_id] = refresh_token

    async def delete(self, user_id: str) -> None:
        self.deleted.append(user_id)
        self._tokens.pop(user_id, None)


@pytest.fixture
def transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            response = httpx.Response(200, json={"user_id": "u1", "csrf_token": "csrf-1"})
            response.headers["set-cookie"] = "access_token=access-1; Path=/; HttpOnly"
            return response
        if request.url.path == "/auth/refresh":
            assert request.headers.get("x-csrf-token") == "csrf-1"
            response = httpx.Response(200, json={"user_id": "u1", "csrf_token": "csrf-2"})
            response.headers["set-cookie"] = "access_token=access-2; Path=/; HttpOnly"
            return response
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_get_csrf_token_logs_in_once(transport):
    async with httpx.AsyncClient(base_url="http://rag.test", transport=transport) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)

        token1 = await auth.get_csrf_token()
        token2 = await auth.get_csrf_token()

        assert token1 == "csrf-1"
        assert token2 == "csrf-1"  # cached, no second login
        assert client.cookies.get("access_token") == "access-1"  # captured via the cookie jar


@pytest.mark.asyncio
async def test_refresh_rotates_csrf_token_and_sends_current_one_as_header(transport):
    async with httpx.AsyncClient(base_url="http://rag.test", transport=transport) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        await auth.get_csrf_token()

        new_access_token, new_csrf_token = await auth.refresh()

        assert new_csrf_token == "csrf-2"
        assert new_access_token == "access-2"
        assert await auth.get_csrf_token() == "csrf-2"
        assert await auth.get_access_token() == "access-2"


@pytest.mark.asyncio
async def test_login_failure_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid email or password"})

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "wrong", client)

        with pytest.raises(RagPlatformAuthError):
            await auth.get_csrf_token()


@pytest.mark.asyncio
async def test_static_token_auth_returns_the_supplied_access_and_csrf_tokens():
    auth = StaticTokenAuth("user-access-token", "user-csrf-token")

    assert await auth.get_access_token() == "user-access-token"
    assert await auth.get_csrf_token() == "user-csrf-token"


@pytest.mark.asyncio
async def test_static_token_auth_refresh_raises_instead_of_recovering():
    auth = StaticTokenAuth("user-access-token", "user-csrf-token")

    with pytest.raises(RagPlatformAuthError):
        await auth.refresh()


# AGT-051: silent refresh, when a session_store/http_client were wired in.


@pytest.mark.asyncio
async def test_static_token_auth_refresh_raises_when_no_stored_refresh_token():
    """session_store/http_client wired in, but nothing stored for this user yet -- same
    "log in again" behavior as before AGT-051, not a crash."""
    access_token = _fake_jwt("user-1")
    store = _FakeSessionStore()  # empty
    async with httpx.AsyncClient(base_url="http://rag.test") as client:
        auth = StaticTokenAuth(access_token, "old-csrf", store, client)
        with pytest.raises(RagPlatformAuthError):
            await auth.refresh()


@pytest.mark.asyncio
async def test_static_token_auth_silently_refreshes_with_a_stored_refresh_token():
    access_token = _fake_jwt("user-1")
    store = _FakeSessionStore({"user-1": "stored-refresh-token"})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/refresh"
        assert "refresh_token=stored-refresh-token" in request.headers["cookie"]
        assert request.headers["x-csrf-token"] == "old-csrf"
        response = httpx.Response(200, json={"user_id": "user-1", "csrf_token": "new-csrf"})
        response.headers["set-cookie"] = "access_token=new-access; Path=/; HttpOnly"
        return response

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = StaticTokenAuth(access_token, "old-csrf", store, client)
        new_access_token, new_csrf_token = await auth.refresh()

    assert new_access_token == "new-access"
    assert new_csrf_token == "new-csrf"
    assert await auth.get_access_token() == "new-access"


@pytest.mark.asyncio
async def test_static_token_auth_saves_a_rotated_refresh_token():
    access_token = _fake_jwt("user-1")
    store = _FakeSessionStore({"user-1": "old-refresh-token"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"user_id": "user-1", "csrf_token": "new-csrf"},
            headers=[
                ("set-cookie", "access_token=new-access; Path=/; HttpOnly"),
                ("set-cookie", "refresh_token=rotated-refresh-token; Path=/; HttpOnly"),
            ],
        )

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = StaticTokenAuth(access_token, "old-csrf", store, client)
        await auth.refresh()

    assert await store.get_refresh_token("user-1") == "rotated-refresh-token"


@pytest.mark.asyncio
async def test_static_token_auth_deletes_a_dead_stored_refresh_token_and_raises():
    """The platform rejecting the stored refresh token (expired/revoked server-side) must clean
    it up, not keep retrying a credential that will never work again."""
    access_token = _fake_jwt("user-1")
    store = _FakeSessionStore({"user-1": "dead-refresh-token"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid or expired refresh token"})

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = StaticTokenAuth(access_token, "old-csrf", store, client)
        with pytest.raises(RagPlatformAuthError):
            await auth.refresh()

    assert store.deleted == ["user-1"]
    assert await store.get_refresh_token("user-1") is None
