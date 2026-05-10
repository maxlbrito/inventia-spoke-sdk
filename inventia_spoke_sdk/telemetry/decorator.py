"""``@traced`` — wrap a ``BaseService`` method in an OTEL span.

The decorator attaches ``tenant_id``, ``user_id`` and ``client_id`` to
the span when those are available on ``self.principal``. When OTEL is
not installed (no ``[otel]`` extra), ``@traced`` becomes a no-op
passthrough — spokes can decorate freely and pay only when telemetry
is enabled.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from inventia_spoke_sdk.telemetry._compat import HAS_OTEL, Status, StatusCode, otel_trace

F = TypeVar("F", bound=Callable[..., Any])
A = TypeVar("A", bound=Callable[..., Awaitable[Any]])


def traced(span_name: str | None = None) -> Callable[[F], F]:
    """Wrap a sync or async method on a ``BaseService`` subclass.

    ``span_name`` defaults to ``"<ClassName>.<method_name>"``.

    Usage::

        class CompanyService(BaseService):
            @traced()
            async def upsert(self, payload):
                ...
    """

    def decorator(func: F) -> F:
        if not HAS_OTEL:
            return func  # zero-cost passthrough

        is_coro = inspect.iscoroutinefunction(func)
        resolved_name = span_name or _default_span_name(func)
        tracer = otel_trace.get_tracer("inventia_spoke_sdk.telemetry")

        if is_coro:

            @functools.wraps(func)
            async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                with tracer.start_as_current_span(resolved_name) as span:
                    _attach_principal_attrs(span, self)
                    try:
                        return await func(self, *args, **kwargs)
                    except Exception as exc:
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        span.record_exception(exc)
                        raise

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(resolved_name) as span:
                _attach_principal_attrs(span, self)
                try:
                    return func(self, *args, **kwargs)
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _default_span_name(func: Callable[..., Any]) -> str:
    qualname = getattr(func, "__qualname__", func.__name__)
    return qualname  # e.g. "CompanyService.upsert"


def _attach_principal_attrs(span: Any, instance: Any) -> None:
    principal = getattr(instance, "principal", None)
    if principal is None:
        return
    tenant_id = getattr(principal, "tenant_id", None)
    user_id = getattr(principal, "user_id", None)
    client_id = getattr(principal, "client_id", None)
    if tenant_id is not None:
        span.set_attribute("inventia.tenant_id", str(tenant_id))
    if user_id is not None:
        span.set_attribute("inventia.user_id", str(user_id))
    if client_id is not None:
        span.set_attribute("inventia.client_id", str(client_id))
