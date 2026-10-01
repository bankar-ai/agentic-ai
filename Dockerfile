# Cloud Run deployment (AGT-005). See docs/architecture.md's "Deployment" section for why this
# needs to be a separate service from enterprise-rag-platform's own VM: that VM has no room (only
# ~958MB RAM) for anything beyond what it already runs, and this project needs no database/cache
# of its own, so Cloud Run's scale-to-zero free tier is a clean fit -- same pattern already
# proven for that repo's own docling service.
FROM python:3.12-slim

WORKDIR /app

# Install uv itself (pinned, matches the official recommended install pattern for container
# builds: copy the static binary out of uv's own distroless image rather than pip-installing it).
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

# Use the synced venv directly at runtime -- `uv run` re-resolves/syncs on every invocation
# (pulling in dev-only packages despite the build-time --no-dev sync, confirmed live when this
# was first tried), which defeats the point of a frozen production image.
ENV PATH="/app/.venv/bin:$PATH"

ENV PORT=8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
