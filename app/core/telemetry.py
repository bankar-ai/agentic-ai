"""OpenTelemetry trace setup (AGT-018): exports to the same Grafana Cloud stack
`enterprise-rag-platform` already uses, under this project's own `OTEL_SERVICE_NAME`.

Called once from `app.main` at startup. Never load-bearing: any failure during setup is logged
and swallowed rather than preventing the app from starting or serving requests, mirroring
`enterprise-rag-platform/app/core/telemetry.py`'s own stance.

Metrics/logs export (that sibling project's ERP-042/ERP-039) are explicitly out of scope here --
see AGT-018's notes for why traces alone is this ticket's floor.
"""

import logging
import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GrpcOTLPSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HttpOTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

logger = logging.getLogger(__name__)


def _build_span_exporter() -> SpanExporter:
    """Pick the OTLP span exporter matching `OTEL_EXPORTER_OTLP_PROTOCOL`.

    OTel's own standard env var; defaults to `"grpc"` per the OTel spec. Grafana Cloud's OTLP
    gateway requires `"http/protobuf"`. Both exporters read
    `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_EXPORTER_OTLP_HEADERS` from the environment automatically
    when constructed with no args.
    """
    protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    if protocol == "http/protobuf":
        # Explicit timeout: a bare `HttpOTLPSpanExporter()` was observed live on Cloud Run
        # failing every export with "Read timed out. (read timeout=0)" -- some environment in
        # that sandbox resolves the exporter's own default timeout to 0 rather than its
        # documented ~10s fallback. Passing one explicitly sidesteps whatever that default
        # resolution path is doing wrong.
        return HttpOTLPSpanExporter(timeout=10)
    return GrpcOTLPSpanExporter()


def configure_telemetry(app: FastAPI) -> None:
    """Configure the global OTel tracer provider and auto-instrument FastAPI/httpx.

    A no-op in effect (sets up a provider that exports nowhere useful) when
    `OTEL_EXPORTER_OTLP_ENDPOINT` is unset -- local dev without a collector configured just
    doesn't see its spans go anywhere, not an error. Any exception during setup is logged and
    swallowed so the app still starts and serves requests normally either way.
    """
    try:
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(BatchSpanProcessor(_build_span_exporter()))
        trace.set_tracer_provider(tracer_provider)

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
    except Exception:
        logger.exception("Failed to configure telemetry; continuing without instrumentation")
