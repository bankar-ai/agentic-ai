"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.router import router as query_router
from app.core.cors import get_cors_settings

app = FastAPI(title="Agentic RAG Orchestration")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_settings().allowed_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(query_router)
app.include_router(auth_router)
