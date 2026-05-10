"""Tests for inventia_spoke_sdk.telemetry.

Two paths exercised:

1. Without the OTEL extra (``HAS_OTEL=False``) — every helper must be a
   no-op passthrough. We patch ``HAS_OTEL`` to ``False`` for these
   cases so the test runs even on environments where OTEL is
   installed.
2. With OTEL active — ``@traced`` and ``traced_arq_job`` create the
   right spans, ``enqueue_with_trace`` injects ``traceparent`` into
   kwargs, and the trace_id propagates across the queue boundary.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import uuid4

import pytest

from inventia_spoke_sdk import BaseService, SpokePrincipal

# ---------------------------------------------------------------------------
# OTEL availability guard
# ---------------------------------------------------------------------------


def _otel_installed() -> bool:
    try:
        import opentelemetry  # noqa: F401

        return True
    except ImportError:
        return False


otel_required = pytest.mark.skipif(
    not _otel_installed(), reason="opentelemetry extras not installed"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _module_tracer_provider():
    """Install a fresh TracerProvider once per module.

    OTEL's ``set_tracer_provider`` is no-override by default, so we set
    it exactly once and reuse it for every test in this module. Each
    test gets the in-memory exporter cleared via the function-scoped
    ``in_memory_exporter`` fixture below.
    """
    pytest.importorskip("opentelemetry")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter


@pytest.fixture
def in_memory_exporter(_module_tracer_provider) -> Iterator[object]:
    """Hand the test a clean in-memory exporter."""
    _module_tracer_provider.clear()
    yield _module_tracer_provider
    _module_tracer_provider.clear()


# ---------------------------------------------------------------------------
# No-OTEL path — every helper must be a passthrough
# ---------------------------------------------------------------------------


def test_setup_otel_returns_false_without_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("inventia_spoke_sdk.telemetry.setup.HAS_OTEL", False, raising=False)
    from inventia_spoke_sdk.telemetry import setup_otel

    assert setup_otel(service_name="x") is False


def test_traced_passthrough_without_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("inventia_spoke_sdk.telemetry.decorator.HAS_OTEL", False, raising=False)
    from inventia_spoke_sdk.telemetry.decorator import traced

    class Svc:
        principal = None

        @traced()
        def square(self, x: int) -> int:
            return x * x

    assert Svc().square(4) == 16


def test_traced_arq_job_passthrough_without_otel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "inventia_spoke_sdk.telemetry.arq_propagation.HAS_OTEL", False, raising=False
    )
    from inventia_spoke_sdk.telemetry.arq_propagation import traced_arq_job

    async def job(ctx: dict, x: int) -> int:
        return x + 1

    wrapped = traced_arq_job(job)
    assert wrapped is job


def test_enqueue_with_trace_passthrough_without_otel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "inventia_spoke_sdk.telemetry.arq_propagation.HAS_OTEL", False, raising=False
    )
    from inventia_spoke_sdk.telemetry.arq_propagation import enqueue_with_trace

    captured: dict = {}

    class FakePool:
        async def enqueue_job(self, name: str, *args: object, **kwargs: object) -> str:
            captured["name"] = name
            captured["args"] = args
            captured["kwargs"] = kwargs
            return "job-id"

    asyncio.run(enqueue_with_trace(FakePool(), "task", 1, 2, foo="bar"))
    assert captured["name"] == "task"
    assert captured["args"] == (1, 2)
    assert captured["kwargs"] == {"foo": "bar"}, captured["kwargs"]


# ---------------------------------------------------------------------------
# With-OTEL path
# ---------------------------------------------------------------------------


@otel_required
async def test_traced_creates_span_with_principal_attrs(in_memory_exporter) -> None:
    from inventia_spoke_sdk.telemetry import traced

    class Svc(BaseService):
        @traced()
        async def do_it(self, x: int) -> int:
            return x * 10

    p = SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")
    out = await Svc(session=object(), principal=p).do_it(5)
    assert out == 50

    spans = in_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    # __qualname__ for a class defined inside a test function carries a
    # "<locals>" prefix; the relevant trailing segment is what we care about.
    assert spans[0].name.endswith("Svc.do_it"), spans[0].name
    attrs = dict(spans[0].attributes)
    assert attrs["inventia.tenant_id"] == str(p.tenant_id)
    assert attrs["inventia.user_id"] == str(p.user_id)


@otel_required
async def test_traced_records_exception_and_marks_error(in_memory_exporter) -> None:
    from inventia_spoke_sdk.telemetry import traced

    class Boom(BaseService):
        @traced()
        async def explode(self) -> None:
            raise RuntimeError("kaboom")

    p = SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")
    with pytest.raises(RuntimeError):
        await Boom(session=object(), principal=p).explode()

    spans = in_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
    assert any(ev.name == "exception" for ev in spans[0].events), spans[0].events


@otel_required
async def test_enqueue_with_trace_injects_carrier(in_memory_exporter) -> None:
    """Inside a parent span, enqueue_with_trace must inject traceparent."""
    from opentelemetry import trace

    from inventia_spoke_sdk.telemetry import enqueue_with_trace

    captured: dict = {}

    class FakePool:
        async def enqueue_job(self, name: str, *args: object, **kwargs: object) -> str:
            captured.update(name=name, args=args, kwargs=dict(kwargs))
            return "id"

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("parent"):
        await enqueue_with_trace(FakePool(), "my_job", 1, 2)

    assert captured["name"] == "my_job"
    assert captured["args"] == (1, 2)
    assert "_otel_carrier" in captured["kwargs"]
    carrier = captured["kwargs"]["_otel_carrier"]
    assert "traceparent" in carrier


@otel_required
async def test_traceparent_propagates_through_queue(in_memory_exporter) -> None:
    """End-to-end: parent span → enqueue → traced_arq_job → child span.

    Trace_id of the child must equal the parent's trace_id.
    """
    from opentelemetry import trace

    from inventia_spoke_sdk.telemetry import enqueue_with_trace, traced_arq_job

    captured: dict = {}

    class FakePool:
        async def enqueue_job(self, name: str, *args: object, **kwargs: object) -> str:
            captured.update(args=args, kwargs=dict(kwargs))
            return "id"

    @traced_arq_job
    async def my_job(ctx: dict, x: int, y: int, **kwargs: object) -> int:
        return x + y

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("parent_op"):
        await enqueue_with_trace(FakePool(), "my_job", 2, 3)

    # Drive the worker side using whatever was captured.
    await my_job({"job_id": "abc-123"}, *captured["args"], **captured["kwargs"])

    spans = in_memory_exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert "parent_op" in names
    assert "arq.job my_job" in names

    parent = next(s for s in spans if s.name == "parent_op")
    job = next(s for s in spans if s.name == "arq.job my_job")
    assert parent.context.trace_id == job.context.trace_id


@otel_required
async def test_traced_arq_job_records_exception(in_memory_exporter) -> None:
    from inventia_spoke_sdk.telemetry import traced_arq_job

    @traced_arq_job
    async def boom(ctx: dict, **kwargs: object) -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await boom({"job_id": "x"})

    spans = in_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"


# ---------------------------------------------------------------------------
# Setup / shutdown smoke
# ---------------------------------------------------------------------------


@otel_required
def test_setup_otel_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling setup_otel twice must not raise; second call is a no-op."""
    from inventia_spoke_sdk.telemetry import setup_otel, shutdown_otel

    # Clean any prior state from other tests
    shutdown_otel()
    try:
        first = setup_otel(
            service_name="t1",
            instrument_fastapi=False,
            instrument_httpx=False,
            instrument_sqlalchemy=False,
        )
        second = setup_otel(
            service_name="t1",
            instrument_fastapi=False,
            instrument_httpx=False,
            instrument_sqlalchemy=False,
        )
        assert first is True
        assert second is True
    finally:
        shutdown_otel()
