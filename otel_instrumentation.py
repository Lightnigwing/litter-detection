"""
OpenTelemetry Instrumentation for Litter Detection Training.

Initializes and configures OpenTelemetry SDK for metrics & traces collection
and exports to OTLP (gRPC) endpoint for Grafana/Prometheus/Tempo visualization.

Based on HSE lecture pattern: opentelemetry-distro + auto-instrumentation.
"""

import logging
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

# Global instances
_meter = None
_tracer = None


def setup_otel(
    service_name: str = "litter-detection-training",
    otlp_endpoint: str = "http://localhost:4317",
    service_version: str = "1.0",
):
    """
    Initialize OpenTelemetry SDK for both metrics and traces.
    
    Args:
        service_name: Name of the service for telemetry export
        otlp_endpoint: OTLP gRPC endpoint (default: localhost for docker-compose)
        service_version: Service version for resource metadata
    """
    global _meter, _tracer
    
    # Create resource with service metadata
    resource = Resource.create({
        "service.name": service_name,
        "service.version": service_version,
        "service.namespace": "litter-detection",
    })
    
    # ── Metrics ─────────────────────────────────────────────────────
    metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
    metric_reader = PeriodicExportingMetricReader(exporter=metric_exporter)
    metric_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(metric_provider)
    
    # ── Traces ──────────────────────────────────────────────────────
    trace_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    
    # Get meter and tracer
    _meter = metrics.get_meter(__name__)
    _tracer = trace.get_tracer(__name__)
    
    logger.info(f"✅ OpenTelemetry initialized: {service_name} @ {otlp_endpoint}")
    return _meter, _tracer


def get_meter():
    """Get the global meter instance."""
    if _meter is None:
        raise RuntimeError("OTel not initialized. Call setup_otel() first.")
    return _meter


def get_tracer():
    """Get the global tracer instance."""
    if _tracer is None:
        raise RuntimeError("OTel not initialized. Call setup_otel() first.")
    return _tracer
