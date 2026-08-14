"""OpenTelemetry tracing setup — one tracer shared across the graph nodes."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

_configured = False


def get_tracer():
    global _configured
    if not _configured:
        provider = TracerProvider(resource=Resource.create({"service.name": "orchesql"}))
        # ponytail: console exporter, swap for OTLPSpanExporter (env-configured
        # endpoint) once there's a real collector/backend to point at
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _configured = True
    return trace.get_tracer("orchesql")
