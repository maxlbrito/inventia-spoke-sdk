"""Compatibility layer — OTEL is optional.

If ``opentelemetry`` is not importable, ``HAS_OTEL`` is ``False`` and
helpers downgrade to no-ops. This keeps the SDK installable without
the OTEL extra and lets spokes opt in.
"""

from __future__ import annotations

try:  # pragma: no cover — exercised by environment, not by unit tests
    from opentelemetry import context as otel_context
    from opentelemetry import trace as otel_trace
    from opentelemetry.propagate import extract as otel_extract
    from opentelemetry.propagate import inject as otel_inject
    from opentelemetry.trace import Status, StatusCode

    HAS_OTEL = True
except ImportError:  # pragma: no cover — same
    otel_context = None  # type: ignore[assignment]
    otel_trace = None  # type: ignore[assignment]
    otel_extract = None  # type: ignore[assignment]
    otel_inject = None  # type: ignore[assignment]
    Status = None  # type: ignore[assignment,misc]
    StatusCode = None  # type: ignore[assignment,misc]
    HAS_OTEL = False


__all__ = [
    "HAS_OTEL",
    "Status",
    "StatusCode",
    "otel_context",
    "otel_extract",
    "otel_inject",
    "otel_trace",
]
