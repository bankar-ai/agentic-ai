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
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GrpcOTLPSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HttpOTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.textmap import (
    CarrierT,
    Getter,
    Setter,
    TextMapPropagator,
    default_getter,
    default_setter,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

logger = logging.getLogger(__name__)


class _NoExtractPropagator(TextMapPropagator):
    """A real no-op propagator: ignores any inbound trace-context header entirely and injects
    nothing. `CompositePropagator([])` looks like the obvious way to express "ignore everything",
    but is actually broken for this -- with zero propagators to run, its `extract()` returns
    whatever `context` it was passed (`None` from FastAPI's ASGI middleware), not a valid
    `Context`, which crashes every later `context.get(...)` call. This class returns a real,
    valid `Context` instead.
    """

    def extract(self, carrier: CarrierT, context: Context | None = None, getter: Getter[CarrierT] = default_getter) -> Context:
        return context if context is not None else Context()

    def inject(self, carrier: CarrierT, context: Context | None = None, setter: Setter[CarrierT] = default_setter) -> None:
        return None

    @property
    def fields(self) -> set[str]:
        return set()


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
        # Found live on Cloud Run (2026-10-04): Google's Cloud Run frontend (GFE) injects its
        # own `traceparent` header into every proxied request. OTel's default propagator
        # extracts that and makes every server span a *child* of a parent that lives only in
        # Google's internal Cloud Trace system -- never exported to us -- so Tempo waits
        # forever for a root span that will never arrive ("<root span not yet received>",
        # blank service/no data on the dashboard). An empty propagator ignores any inbound
        # trace context entirely, so every request starts its own real root span instead.
        set_global_textmap(_NoExtractPropagator())

        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(BatchSpanProcessor(_build_span_exporter()))
        trace.set_tracer_provider(tracer_provider)

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
    except Exception:
        logger.exception("Failed to configure telemetry; continuing without instrumentation")
