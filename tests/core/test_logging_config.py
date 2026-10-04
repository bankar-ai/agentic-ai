import logging

from opentelemetry.sdk.trace import TracerProvider

from app.core.logging_config import (
    _NO_TRACE_PLACEHOLDER,
    TraceIdFilter,
    _build_log_exporter,
    configure_logging,
)


def test_trace_id_filter_sets_placeholder_when_no_active_span():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", None, None)

    passed = TraceIdFilter().filter(record)

    assert passed is True
    assert record.trace_id == _NO_TRACE_PLACEHOLDER


def test_trace_id_filter_sets_real_trace_id_when_span_active():
    # A real TracerProvider, local to this test -- the global one may be an unconfigured NoOp
    # (e.g. if nothing in this test run ever called configure_telemetry), which would make every
    # span context invalid and silently fall back to the placeholder this test is checking isn't
    # used.
    tracer = TracerProvider().get_tracer(__name__)
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", None, None)

    with tracer.start_as_current_span("test-span"):
        TraceIdFilter().filter(record)

    assert record.trace_id != _NO_TRACE_PLACEHOLDER
    assert len(record.trace_id) == 32


def test_build_log_exporter_defaults_to_grpc(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_PROTOCOL", raising=False)

    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
        OTLPLogExporter as GrpcExporter,
    )

    assert isinstance(_build_log_exporter(), GrpcExporter)


def test_build_log_exporter_uses_http_protobuf_when_configured(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")

    from opentelemetry.exporter.otlp.proto.http._log_exporter import (
        OTLPLogExporter as HttpExporter,
    )

    assert isinstance(_build_log_exporter(), HttpExporter)


def test_configure_logging_never_raises_even_if_otlp_setup_fails(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("OTLP log export blew up")

    monkeypatch.setattr("app.core.logging_config._build_log_exporter", _boom)

    configure_logging()  # must not raise
