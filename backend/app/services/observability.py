from contextlib import contextmanager
from typing import Iterator

_tracer = None


def setup_observability(endpoint: str, service_name: str = "tolmach-backend") -> None:
    global _tracer
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
    except Exception:
        _tracer = None


@contextmanager
def trace_span(name: str, attributes: dict | None = None) -> Iterator[None]:
    if _tracer is None:
        yield
        return
    with _tracer.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            span.set_attribute(key, str(value))
        yield
