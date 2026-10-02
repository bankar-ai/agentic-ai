import httpx
import pytest

from app.rag_client.auth import RagPlatformAuth, RagPlatformAuthError, StaticTokenAuth


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

        new_token = await auth.refresh()

        assert new_token == "csrf-2"
        assert await auth.get_csrf_token() == "csrf-2"
        assert client.cookies.get("access_token") == "access-2"


@pytest.mark.asyncio
async def test_login_failure_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid email or password"})

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "wrong", client)

        with pytest.raises(RagPlatformAuthError):
            await auth.get_csrf_token()


@pytest.mark.asyncio
async def test_static_token_auth_returns_the_supplied_csrf_token_and_sets_cookies():
    async with httpx.AsyncClient(base_url="http://rag.test") as client:
        auth = StaticTokenAuth("user-access-token", "user-csrf-token", client, "http://rag.test")

        assert await auth.get_csrf_token() == "user-csrf-token"
        assert client.cookies.get("access_token") == "user-access-token"
        # The platform's CSRF check is a double-submit: X-CSRF-Token header vs. csrf_token
        # cookie, not just a header alone -- both must be set (found live, AGT-017).
        assert client.cookies.get("csrf_token") == "user-csrf-token"


@pytest.mark.asyncio
async def test_static_token_auth_refresh_raises_instead_of_recovering():
    async with httpx.AsyncClient(base_url="http://rag.test") as client:
        auth = StaticTokenAuth("user-access-token", "user-csrf-token", client, "http://rag.test")

        with pytest.raises(RagPlatformAuthError):
            await auth.refresh()
