from app.core.config import Settings
from app.core.tracing import NoOpTracer, get_tracer


def test_get_tracer_returns_noop_without_credentials():
    settings = Settings(
        rag_platform_base_url="http://localhost:8000",
        rag_platform_email="svc@example.com",
        rag_platform_password="secret123",
    )

    tracer = get_tracer(settings)

    assert isinstance(tracer, NoOpTracer)
    tracer.trace_step({"agent": "gatekeeper", "route": "kb"})  # must not raise


def test_get_tracer_returns_langfuse_tracer_with_credentials():
    settings = Settings(
        rag_platform_base_url="http://localhost:8000",
        rag_platform_email="svc@example.com",
        rag_platform_password="secret123",
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
    )

    tracer = get_tracer(settings)

    assert not isinstance(tracer, NoOpTracer)
