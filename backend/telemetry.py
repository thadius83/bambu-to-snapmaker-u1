"""OpenTelemetry setup — traces, metrics, and log correlation.

Initialised once at startup via setup(). Instruments are created inside
setup() after the real MeterProvider is registered, then assigned to
module-level names so callers can import them unconditionally. Before
setup() runs (or when OTel is disabled) they remain no-op instruments
from the default SDK no-op provider.
"""
from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_log = logging.getLogger(__name__)


def _otel_enabled() -> bool:
    enabled = os.environ.get("OTEL_ENABLED", "").strip().lower()
    if enabled in ("false", "0", "no"):
        return False
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    return bool(endpoint)


def setup() -> None:
    if not _otel_enabled():
        return
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()

    service = os.environ.get("OTEL_SERVICE_NAME", "u13mf-converter")
    resource = Resource.create({"service.name": service})

    # Traces
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(tp)

    # Metrics — export every 15 s
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
        export_interval_millis=15_000,
    )
    mp = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(mp)

    # Instruments must be created AFTER set_meter_provider so they bind to the
    # real exporting meter, not the default no-op provider.
    _init_instruments()

    # Correlate Python log records with the active trace/span IDs
    LoggingInstrumentor().instrument(set_logging_format=True)

    _log.info("OpenTelemetry active  service=%s  endpoint=%s", service, endpoint)


# ---------------------------------------------------------------------------
# Instruments — initialised as no-ops; reassigned by _init_instruments() in
# setup() once the real MeterProvider is registered.

_meter = metrics.get_meter("u13mf")

conversions_counter = _meter.create_counter(
    "u13mf.conversions",
    description="Total conversion requests completed",
)
conversion_duration = _meter.create_histogram(
    "u13mf.conversion_duration_ms",
    description="End-to-end conversion pipeline duration in milliseconds",
)
file_size_histogram = _meter.create_histogram(
    "u13mf.file_size_kb",
    description="Input .3mf file size in kilobytes",
)
keys_dropped_histogram = _meter.create_histogram(
    "u13mf.keys_dropped",
    description="Bambu-only keys removed per conversion",
)
rules_matched_histogram = _meter.create_histogram(
    "u13mf.rules_matched",
    description="Filament rules matched per conversion",
)
slots_histogram = _meter.create_histogram(
    "u13mf.slots",
    description="Filament slot count in source file",
)
swap_pauses_histogram = _meter.create_histogram(
    "u13mf.swap_pauses",
    description="Filament swap pause markers inserted per conversion",
)
upload_errors_counter = _meter.create_counter(
    "u13mf.upload_errors",
    description="Rejected uploads (bad file type, unrecognised format, oversized)",
)
http_errors_counter = _meter.create_counter(
    "u13mf.http_errors",
    description="HTTP 4xx/5xx responses by status code and path",
)


def _init_instruments() -> None:
    """Reassign module-level instruments to real exporters after MeterProvider is set."""
    global conversions_counter, conversion_duration, file_size_histogram
    global keys_dropped_histogram, rules_matched_histogram, slots_histogram
    global swap_pauses_histogram, upload_errors_counter, http_errors_counter

    m = metrics.get_meter("u13mf")
    conversions_counter = m.create_counter(
        "u13mf.conversions",
        description="Total conversion requests completed",
    )
    conversion_duration = m.create_histogram(
        "u13mf.conversion_duration_ms",
        description="End-to-end conversion pipeline duration in milliseconds",
    )
    file_size_histogram = m.create_histogram(
        "u13mf.file_size_kb",
        description="Input .3mf file size in kilobytes",
    )
    keys_dropped_histogram = m.create_histogram(
        "u13mf.keys_dropped",
        description="Bambu-only keys removed per conversion",
    )
    rules_matched_histogram = m.create_histogram(
        "u13mf.rules_matched",
        description="Filament rules matched per conversion",
    )
    slots_histogram = m.create_histogram(
        "u13mf.slots",
        description="Filament slot count in source file",
    )
    swap_pauses_histogram = m.create_histogram(
        "u13mf.swap_pauses",
        description="Filament swap pause markers inserted per conversion",
    )
    upload_errors_counter = m.create_counter(
        "u13mf.upload_errors",
        description="Rejected uploads (bad file type, unrecognised format, oversized)",
    )
    http_errors_counter = m.create_counter(
        "u13mf.http_errors",
        description="HTTP 4xx/5xx responses by status code and path",
    )


def record_conversion(
    *,
    profile: str,
    status: str,
    duration_ms: float,
    file_size_kb: float,
    keys_dropped: int,
    rules_matched: int,
    is_painted: bool = False,
    has_vlh: bool = False,
    n_slots: int = 0,
    swap_pauses_requested: bool = False,
    swap_pauses_inserted: int = 0,
    swap_pauses_skipped: bool = False,
    source_printer: str = "unknown",
    already_converted: bool = False,
    error_reason: str = "",
) -> None:
    attrs: dict = {
        "profile": profile,
        "status": status,
        "painted": str(is_painted).lower(),
        "vlh": str(has_vlh).lower(),
        "source_printer": source_printer,
        "already_converted": str(already_converted).lower(),
    }
    if error_reason:
        attrs["error_reason"] = error_reason
    conversions_counter.add(1, attrs)
    conversion_duration.record(duration_ms, attrs)
    file_size_histogram.record(file_size_kb, {"status": status, "painted": str(is_painted).lower()})
    keys_dropped_histogram.record(keys_dropped, {"status": status})
    rules_matched_histogram.record(rules_matched, {"status": status})
    if n_slots > 0:
        slots_histogram.record(n_slots, {"status": status})
    if swap_pauses_requested:
        swap_pauses_histogram.record(
            swap_pauses_inserted,
            {"status": status, "skipped_painted": str(swap_pauses_skipped).lower()},
        )
