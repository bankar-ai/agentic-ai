"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.router import router as query_router
from app.core.cors import get_cors_settings
from app.rag_client.shared_client import close_shared_rag_platform_client


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """AGT-009: the shared `enterprise-rag-platform` http client is created lazily on first use
    and must be closed explicitly on shutdown -- nothing else owns its lifecycle.
    """
    yield
    await close_shared_rag_platform_client()


app = FastAPI(title="Agentic RAG Orchestration", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_settings().allowed_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(query_router)
app.include_router(auth_router)
