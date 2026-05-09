"""Tests for the v0.5.0 session resolver + session_for helper."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from inventia_spoke_sdk import SpokePrincipal
from inventia_spoke_sdk.db import (
    configure_session_resolver,
    get_session_resolver,
    reset_session_resolver,
    session_for,
)


class _Base(DeclarativeBase):
    pass


class Widget(_Base):
    __tablename__ = "widgets"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)


@pytest.fixture(autouse=True)
def _reset_resolver():
    reset_session_resolver()
    yield
    reset_session_resolver()


async def _build_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


def _principal() -> SpokePrincipal:
    return SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")


async def test_get_session_resolver_raises_when_not_configured() -> None:
    with pytest.raises(RuntimeError, match="No SessionFactoryResolver configured"):
        get_session_resolver()


async def test_session_for_yields_open_session_and_closes() -> None:
    factory = await _build_factory()

    async def resolver(_: SpokePrincipal):
        return factory

    configure_session_resolver(resolver)

    async with session_for(_principal()) as session:
        assert isinstance(session, AsyncSession)
        result = await session.execute(select(1))
        assert result.scalar_one() == 1

    # Session should be closed; using it now must raise.
    with pytest.raises(Exception):  # noqa: B017 — any session-closed exception
        await session.execute(select(1))


async def test_session_for_writes_persist_within_factory() -> None:
    factory = await _build_factory()

    async def resolver(_: SpokePrincipal):
        return factory

    configure_session_resolver(resolver)

    async with session_for(_principal()) as session:
        session.add(Widget(name="alpha"))
        await session.commit()

    async with session_for(_principal()) as session:
        rows = (await session.execute(select(Widget))).scalars().all()
        assert [w.name for w in rows] == ["alpha"]


async def test_resolver_receives_principal() -> None:
    factory = await _build_factory()
    seen: list[SpokePrincipal] = []

    async def resolver(p: SpokePrincipal):
        seen.append(p)
        return factory

    configure_session_resolver(resolver)
    p = _principal()
    async with session_for(p):
        pass

    assert seen == [p]


async def test_cross_tenant_isolation_via_distinct_factories() -> None:
    """A resolver that picks a distinct factory per tenant must not leak."""
    fa = await _build_factory()
    fb = await _build_factory()

    pa = SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")
    pb = SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")
    by_tenant = {str(pa.tenant_id): fa, str(pb.tenant_id): fb}

    async def resolver(p: SpokePrincipal):
        return by_tenant[str(p.tenant_id)]

    configure_session_resolver(resolver)

    async with session_for(pa) as s:
        s.add(Widget(name="only-in-a"))
        await s.commit()

    async with session_for(pb) as s:
        rows = (await s.execute(select(Widget))).scalars().all()
        assert rows == [], "tenant B must not see tenant A's data"

    async with session_for(pa) as s:
        rows = (await s.execute(select(Widget))).scalars().all()
        assert [w.name for w in rows] == ["only-in-a"]
