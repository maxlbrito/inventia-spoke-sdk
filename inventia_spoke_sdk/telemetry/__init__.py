"""OpenTelemetry helpers for spokes.

This package is optional: install with ``inventia-spoke-sdk[otel]`` to
pull the OpenTelemetry runtime dependencies. The submodules below
silently no-op when OTEL is not installed, so importing
``inventia_spoke_sdk.telemetry`` from a spoke that opted out remains
safe.

The public surface is:

- ``setup_otel(...)`` — idempotent process-wide initialisation.
- ``shutdown_otel()`` — flush the exporter (test/benchmark helper).
- ``traced`` decorator — wraps a ``BaseService`` method in a span.
- ``enqueue_with_trace(pool, name, *args, **kwargs)`` — arq enqueue
  helper that injects ``traceparent`` into the job kwargs.
- ``traced_arq_job`` — wraps an arq function so it picks up the
  injected ``traceparent`` and runs inside a span.

Naming follows the W3C Trace Context spec
(https://www.w3.org/TR/trace-context/).
"""

from inventia_spoke_sdk.telemetry.arq_propagation import (
    enqueue_with_trace,
    traced_arq_job,
)
from inventia_spoke_sdk.telemetry.decorator import traced
from inventia_spoke_sdk.telemetry.setup import setup_otel, shutdown_otel

__all__ = [
    "enqueue_with_trace",
    "setup_otel",
    "shutdown_otel",
    "traced",
    "traced_arq_job",
]
