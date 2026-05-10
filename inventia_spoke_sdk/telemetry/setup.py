"""Process-wide OTEL initialisation.

The spoke calls ``setup_otel(...)`` once at startup. We pick safe
defaults from the OTEL_* environment variables; explicit kwargs win.

Auto-instrumentation we enable here:

- FastAPI — every HTTP route gets a span automatically.
- httpx (sync + async) — every outbound Hub call is a child span.
- SQLAlchemy — every query is a span (helpful for slow-query digs).
- arq — propagation is wired separately via the helpers in
  ``arq_propagation`` because arq has no ready-made instrumentation.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from inventia_spoke_sdk.telemetry._compat import HAS_OTEL

log = logging.getLogger("inventia_spoke_sdk.telemetry.setup")

_state: dict[str, Any] = {"initialised": False, "tracer_provider": None}


def setup_otel(
    *,
    service_name: str | None = None,
    service_version: str | None = None,
    environment: str | None = None,
    otlp_endpoint: str | None = None,
    sample_rate: float | None = None,
    instrument_fastapi: bool = True,
    instrument_httpx: bool = True,
    instrument_sqlalchemy: bool = True,
) -> bool:
    """Initialise OTEL for the current process. Idempotent.

    Returns ``True`` if OTEL is wired up, ``False`` if the OTEL extra
    is not installed (in which case all telemetry helpers no-op).

    Defaults read from the environment when args are ``None``:

    - ``service_name`` ← ``OTEL_SERVICE_NAME``
    - ``otlp_endpoint`` ← ``OTEL_EXPORTER_OTLP_ENDPOINT``
    - ``sample_rate``  ← ``OTEL_TRACES_SAMPLER_ARG`` (parent-based ratio).
    """
    if not HAS_OTEL:
        log.info(
            "OTEL extras not installed — telemetry helpers will no-op. "
            "Install with `pip install inventia-spoke-sdk[otel]` to enable."
        )
        return False

    if _state["initialised"]:
        return True

    # Imports here are safe: HAS_OTEL guarantees the packages exist.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import (
        ParentBased,
        TraceIdRatioBased,
    )

    resolved_service = service_name or os.getenv("OTEL_SERVICE_NAME") or "inventia-spoke"
    resolved_env = environment or os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT") or "dev"
    resolved_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if sample_rate is None:
        env_rate = os.getenv("OTEL_TRACES_SAMPLER_ARG")
        sample_rate = float(env_rate) if env_rate else 1.0

    resource_attrs: dict[str, str] = {
        "service.name": resolved_service,
        "deployment.environment": resolved_env,
    }
    if service_version:
        resource_attrs["service.version"] = service_version

    provider = TracerProvider(
        resource=Resource.create(resource_attrs),
        sampler=ParentBased(root=TraceIdRatioBased(sample_rate)),
    )
    if resolved_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=resolved_endpoint))
        )
    trace.set_tracer_provider(provider)
    _state["tracer_provider"] = provider
    _state["initialised"] = True

    _maybe_instrument_fastapi(instrument_fastapi)
    _maybe_instrument_httpx(instrument_httpx)
    _maybe_instrument_sqlalchemy(instrument_sqlalchemy)

    log.info(
        "OTEL initialised: service=%s env=%s endpoint=%s sample=%.3f",
        resolved_service,
        resolved_env,
        resolved_endpoint or "<no exporter>",
        sample_rate,
    )
    return True


def shutdown_otel() -> None:
    """Flush spans and reset state. Useful for tests and graceful shutdown."""
    provider = _state.get("tracer_provider")
    if provider is None:
        return
    try:
        provider.shutdown()
    finally:
        _state["initialised"] = False
        _state["tracer_provider"] = None


# ----- Per-instrumentation guarded imports --------------------------------


def _maybe_instrument_fastapi(enabled: bool) -> None:
    if not enabled:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument()
    except ImportError:
        log.debug("FastAPI instrumentation not installed; skipping")
    except Exception as exc:  # noqa: BLE001
        log.warning("FastAPI instrumentation failed: %s", exc)


def _maybe_instrument_httpx(enabled: bool) -> None:
    if not enabled:
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except ImportError:
        log.debug("httpx instrumentation not installed; skipping")
    except Exception as exc:  # noqa: BLE001
        log.warning("httpx instrumentation failed: %s", exc)


def _maybe_instrument_sqlalchemy(enabled: bool) -> None:
    if not enabled:
        return
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
    except ImportError:
        log.debug("SQLAlchemy instrumentation not installed; skipping")
    except Exception as exc:  # noqa: BLE001
        log.warning("SQLAlchemy instrumentation failed: %s", exc)
