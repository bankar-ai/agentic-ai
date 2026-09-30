"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.router import router as query_router

app = FastAPI(title="Agentic RAG Orchestration")
app.include_router(query_router)
