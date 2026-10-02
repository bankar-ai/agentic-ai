"""`POST /auth/login`: proxies a login against `enterprise-rag-platform` and hands back the
resulting session as plain JSON (AGT-016).

Exists because a standalone browser SPA (`AGT-017`) cannot do this itself: `enterprise-rag-
platform`'s own `/auth/login` delivers tokens as httpOnly cookies (`ERP-116`), readable only by
server-side code, never by browser JS. This endpoint does that server-side cookie-jar read on the
caller's behalf and returns the two values a later `POST /query` needs as headers.
"""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.rag_client.auth import RagPlatformAuthError, login_and_extract_session

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    csrf_token: str


@router.post("/auth/login")
async def login(request: LoginRequest) -> LoginResponse:
    """Log in against `enterprise-rag-platform` and return `{access_token, csrf_token}`.

    Never logs or persists the submitted password beyond this one call. The returned pair is
    exactly what `POST /query` expects as `Authorization: Bearer <access_token>` +
    `X-RAG-CSRF-Token: <csrf_token>`.
    """
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.rag_platform_base_url, timeout=30.0) as http_client:
        try:
            access_token, csrf_token = await login_and_extract_session(
                settings.rag_platform_base_url, request.email, request.password, http_client
            )
        except RagPlatformAuthError:
            raise HTTPException(status_code=401, detail="Invalid email or password.") from None
    return LoginResponse(access_token=access_token, csrf_token=csrf_token)
