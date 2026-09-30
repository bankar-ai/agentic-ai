"""Schemas mirroring `enterprise-rag-platform`'s auth and retrieval API shapes."""

from pydantic import BaseModel


class TokenPair(BaseModel):
    """An access + refresh token pair, as issued by `enterprise-rag-platform`."""

    access_token: str
    refresh_token: str


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
