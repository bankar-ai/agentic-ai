from fastapi import FastAPI

from app.core.telemetry import _build_span_exporter, configure_telemetry


def test_build_span_exporter_defaults_to_grpc(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_PROTOCOL", raising=False)

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as GrpcExporter,
    )

    assert isinstance(_build_span_exporter(), GrpcExporter)


def test_build_span_exporter_uses_http_protobuf_when_configured(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as HttpExporter,
    )

    assert isinstance(_build_span_exporter(), HttpExporter)


def test_configure_telemetry_never_raises_even_if_instrumentation_fails(monkeypatch):
    """Observability must never be able to take the app down (same stance as
    enterprise-rag-platform's own configure_telemetry)."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("instrumentation blew up")

    monkeypatch.setattr("app.core.telemetry._build_span_exporter", _boom)

    configure_telemetry(FastAPI())  # must not raise
