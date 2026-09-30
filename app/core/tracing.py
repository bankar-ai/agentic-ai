"""Evaluation tracing via Langfuse Cloud (Hobby/free tier) -- gracefully degrades to a no-op
when no credentials are configured, so this project's core flow is never blocked on
`enterprise-rag-platform`'s ERP-112 (its own Langfuse setup) having landed first.
"""

from typing import Protocol

from app.core.config import Settings


class Tracer(Protocol):
    def trace_step(self, step: dict) -> None: ...


class NoOpTracer:
    """Used whenever Langfuse credentials are absent."""

    def trace_step(self, step: dict) -> None:
        return None


class LangfuseTracer:
    """Sends each agent step as a Langfuse observation, sharing the account
    `enterprise-rag-platform`'s ERP-112 sets up, as a separate project within it."""

    def __init__(self, public_key: str, secret_key: str, host: str) -> None:
        from langfuse import Langfuse

        self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    def trace_step(self, step: dict) -> None:
        # `Langfuse.event(...)` from the brief no longer exists in the installed SDK
        # (langfuse 4.16.0 replaced the old event-logging API with an OTEL-based one);
        # `create_event(...)` is its direct successor with the same name/metadata shape.
        self._client.create_event(name=step.get("agent", "unknown"), metadata=step)


def get_tracer(settings: Settings) -> Tracer:
    """Return a `LangfuseTracer` if credentials are configured, else a `NoOpTracer`."""
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        return LangfuseTracer(settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_host)
    return NoOpTracer()
