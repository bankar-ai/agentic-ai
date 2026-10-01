import httpx
import pytest

from app.rag_client.auth import RagPlatformAuth, RagPlatformAuthError, StaticTokenAuth


@pytest.fixture
def transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={
                "access_token": "access-1", "refresh_token": "refresh-1", "token_type": "bearer",
            })
        if request.url.path == "/auth/refresh":
            return httpx.Response(200, json={
                "access_token": "access-2", "refresh_token": "refresh-2", "token_type": "bearer",
            })
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_get_access_token_logs_in_once(transport):
    async with httpx.AsyncClient(base_url="http://rag.test", transport=transport) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)

        token1 = await auth.get_access_token()
        token2 = await auth.get_access_token()

        assert token1 == "access-1"
        assert token2 == "access-1"  # cached, no second login


@pytest.mark.asyncio
async def test_refresh_rotates_tokens(transport):
    async with httpx.AsyncClient(base_url="http://rag.test", transport=transport) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "secret123", client)
        await auth.get_access_token()

        new_token = await auth.refresh()

        assert new_token == "access-2"
        assert await auth.get_access_token() == "access-2"


@pytest.mark.asyncio
async def test_login_failure_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid email or password"})

    async with httpx.AsyncClient(base_url="http://rag.test", transport=httpx.MockTransport(handler)) as client:
        auth = RagPlatformAuth("http://rag.test", "svc@example.com", "wrong", client)

        with pytest.raises(RagPlatformAuthError):
            await auth.get_access_token()


@pytest.mark.asyncio
async def test_static_token_auth_returns_the_supplied_token():
    auth = StaticTokenAuth("user-supplied-token")

    assert await auth.get_access_token() == "user-supplied-token"
    assert await auth.get_access_token() == "user-supplied-token"  # stable, no login involved


@pytest.mark.asyncio
async def test_static_token_auth_refresh_raises_instead_of_recovering():
    auth = StaticTokenAuth("user-supplied-token")

    with pytest.raises(RagPlatformAuthError):
        await auth.refresh()
