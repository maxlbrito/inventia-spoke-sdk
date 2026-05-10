"""Trace context propagation through arq's Redis queue.

arq has no built-in OpenTelemetry integration. Two thin helpers solve
the gap:

- ``enqueue_with_trace(pool, function_name, *args, **kwargs)`` — wraps
  ``pool.enqueue_job``. Injects the current W3C ``traceparent`` (and
  ``tracestate`` if present) into a special ``_otel_carrier`` kwarg.
- ``traced_arq_job`` decorator — wraps the worker function. Pops
  ``_otel_carrier`` from kwargs, restores OTEL context, and runs the
  original body inside a span named after the function.

Both no-op when the OTEL extra is not installed.

Wire example::

    # API side
    from inventia_spoke_sdk.telemetry import enqueue_with_trace
    await enqueue_with_trace(
        pool,
        "run_companies_import",
        str(job_id),
        str(tenant_id),
        access_token,
    )

    # Worker side
    from inventia_spoke_sdk.telemetry import traced_arq_job

    @traced_arq_job
    async def run_companies_import(ctx, job_id, tenant_id, access_token):
        ...
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from inventia_spoke_sdk.telemetry._compat import (
    HAS_OTEL,
    Status,
    StatusCode,
    otel_context,
    otel_extract,
    otel_inject,
    otel_trace,
)

log = logging.getLogger("inventia_spoke_sdk.telemetry.arq")

# Reserved kwarg name for the W3C carrier dict. Workers must accept
# ``**kwargs`` or have ``_otel_carrier=None`` declared explicitly.
_CARRIER_KWARG = "_otel_carrier"


async def enqueue_with_trace(
    pool: Any,
    function_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Drop-in replacement for ``pool.enqueue_job(function_name, *args, **kwargs)``.

    When OTEL is enabled, injects the current ``traceparent`` /
    ``tracestate`` into ``_otel_carrier`` so the worker can resume the
    trace. Otherwise behaves identically to ``pool.enqueue_job``.
    """
    if HAS_OTEL:
        carrier: dict[str, str] = {}
        otel_inject(carrier)
        if carrier:
            kwargs[_CARRIER_KWARG] = carrier
    return await pool.enqueue_job(function_name, *args, **kwargs)


def traced_arq_job(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Wrap an arq job function so it picks up the injected trace context.

    The decorated function still receives ``ctx`` plus the original
    args/kwargs. The ``_otel_carrier`` kwarg is consumed before the
    body runs, so existing job signatures don't have to change as long
    as they accept ``**kwargs`` or declare ``_otel_carrier=None``.
    """
    if not HAS_OTEL:
        return func

    tracer = otel_trace.get_tracer("inventia_spoke_sdk.telemetry.arq")
    span_name = f"arq.job {getattr(func, '__name__', 'job')}"

    @functools.wraps(func)
    async def wrapper(ctx: dict, *args: Any, **kwargs: Any) -> Any:
        carrier = kwargs.pop(_CARRIER_KWARG, None)
        parent_ctx = otel_extract(carrier) if carrier else None
        token = otel_context.attach(parent_ctx) if parent_ctx is not None else None
        try:
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("arq.job_id", str(ctx.get("job_id") or ctx.get("job_try") or ""))
                span.set_attribute("arq.function", getattr(func, "__name__", ""))
                try:
                    return await func(ctx, *args, **kwargs)
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise
        finally:
            if token is not None:
                otel_context.detach(token)

    return wrapper


__all__ = ["enqueue_with_trace", "traced_arq_job"]
