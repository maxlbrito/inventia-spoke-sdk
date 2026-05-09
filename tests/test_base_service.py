"""Tests for BaseService."""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from inventia_spoke_sdk import BaseService, SpokePrincipal


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_base_service_stores_session(session) -> None:
    svc = BaseService(session)
    assert svc.session is session
    assert svc.principal is None
    assert svc.tenant_id is None


async def test_base_service_exposes_tenant_id_from_principal(session) -> None:
    tenant = uuid4()
    p = SpokePrincipal(user_id=uuid4(), tenant_id=tenant, kind="user")
    svc = BaseService(session, principal=p)
    assert svc.tenant_id == str(tenant)


async def test_base_service_logger_attaches_tenant_id(session, caplog) -> None:
    tenant = uuid4()
    p = SpokePrincipal(user_id=uuid4(), tenant_id=tenant, kind="user")
    svc = BaseService(session, principal=p)

    with caplog.at_level(logging.INFO):
        svc.log.info("doing thing")

    assert any(rec.tenant_id == str(tenant) for rec in caplog.records if hasattr(rec, "tenant_id"))


async def test_base_service_subclass_pattern(session) -> None:
    """Smoke test: subclasses can use self.session for queries and transactions."""

    class CounterService(BaseService):
        async def ping(self) -> int:
            from sqlalchemy import select

            return (await self.session.execute(select(1))).scalar_one()

    svc = CounterService(session)
    assert await svc.ping() == 1
