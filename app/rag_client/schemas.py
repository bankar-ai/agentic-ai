"""Schemas mirroring `enterprise-rag-platform`'s auth and retrieval API shapes.

ERP-116 note (discovered live 2026-10-01, deploying against the real platform for the first
time): `POST /auth/login`/`/refresh` no longer return access/refresh tokens in the body -- those
are delivered as httpOnly cookies now, invisible to this client except via its httpx.AsyncClient's
own cookie jar (which captures and replays them automatically, as long as the same AsyncClient
instance is reused across the login call and every subsequent request -- already true of how this
project's auth/retrieval clients are constructed). Only `csrf_token` (needed as the `X-CSRF-Token`
header on every state-changing request, per the double-submit pattern) comes back in the body.
"""

from pydantic import BaseModel


class AuthSession(BaseModel):
    """What `POST /auth/login`/`/refresh` actually return post-ERP-116 -- the access/refresh
    tokens themselves arrive only as httpOnly cookies on the same response, not in this body.
    """

    user_id: str
    csrf_token: str


class RetrievedChunk(BaseModel):
    """A single retrieved chunk, mirroring `enterprise-rag-platform`'s `RetrievedChunk`."""

    chunk_id: str
    document_id: str
    text: str
    section_path: list[str]
    page_start: int
    page_end: int
    source_filename: str
    score: float


class RetrievalResult(BaseModel):
    """Ranked retrieval results, mirroring `enterprise-rag-platform`'s `RetrievalResponse`."""

    results: list[RetrievedChunk]
