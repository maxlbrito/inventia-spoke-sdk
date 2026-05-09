"""Tests for inventia_spoke_sdk.testing.db rollback-per-test helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from inventia_spoke_sdk import SpokePrincipal, session_for
from inventia_spoke_sdk.db import reset_session_resolver
from inventia_spoke_sdk.testing import (
    create_rollback_session_factory,
    install_test_resolver,
)
from inventia_spoke_sdk.testing.db import per_principal_resolver


class _Base(DeclarativeBase):
    pass


class Thing(_Base):
    __tablename__ = "things"
    id = Column(Integer, primary_key=True)
    label = Column(String(50), nullable=False)


@pytest.fixture(autouse=True)
def _reset_resolver():
    reset_session_resolver()
    yield
    reset_session_resolver()


async def test_create_rollback_session_factory_binds_to_connection() -> None:
    """The factory returned must produce sessions bound to the given
    connection so the caller can manage one outer transaction per test.

    We don't assert SAVEPOINT/rollback semantics here — those are
    SQLAlchemy + driver behavior, and SQLite-in-memory's quirks make
    the assertion noisy. Spokes using Postgres in their test suite get
    the standard `join_transaction_mode="create_savepoint"` discipline
    out of the box.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    p = SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")

    async with engine.connect() as conn:
        await conn.begin()
        factory = create_rollback_session_factory(conn)
        install_test_resolver(factory)

        # Sessions opened via session_for must be bound to `conn`.
        async with session_for(p) as s:
            assert s.bind is conn or s.get_bind() is conn
            s.add(Thing(label="visible-within-outer-txn"))
            await s.flush()
            rows = (await s.execute(select(Thing))).scalars().all()
            assert [t.label for t in rows] == ["visible-within-outer-txn"]

    await engine.dispose()


async def test_per_principal_resolver_routes_by_tenant() -> None:
    """``per_principal_resolver`` returns the right factory per tenant_id."""
    engine_a = create_async_engine("sqlite+aiosqlite:///:memory:")
    engine_b = create_async_engine("sqlite+aiosqlite:///:memory:")
    for e in (engine_a, engine_b):
        async with e.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import async_sessionmaker

    fa = async_sessionmaker(engine_a, expire_on_commit=False)
    fb = async_sessionmaker(engine_b, expire_on_commit=False)

    pa = SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")
    pb = SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")

    from inventia_spoke_sdk.db import configure_session_resolver

    configure_session_resolver(
        per_principal_resolver({str(pa.tenant_id): fa, str(pb.tenant_id): fb})
    )

    async with session_for(pa) as s:
        s.add(Thing(label="A"))
        await s.commit()

    async with session_for(pb) as s:
        rows = (await s.execute(select(Thing))).scalars().all()
        assert rows == []

    async with session_for(pa) as s:
        rows = (await s.execute(select(Thing))).scalars().all()
        assert [t.label for t in rows] == ["A"]

    await engine_a.dispose()
    await engine_b.dispose()


async def test_per_principal_resolver_unknown_tenant() -> None:
    from inventia_spoke_sdk.db import configure_session_resolver

    configure_session_resolver(per_principal_resolver({}))
    p = SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")
    with pytest.raises(KeyError):
        async with session_for(p):
            pass
