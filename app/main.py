"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.router import router as query_router

app = FastAPI(title="Agentic RAG Orchestration")
app.include_router(query_router)
app.include_router(auth_router)
