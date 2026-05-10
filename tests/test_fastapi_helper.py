"""Tests for inventia_spoke_sdk.fastapi.session_dep_for."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from inventia_spoke_sdk import SpokePrincipal
from inventia_spoke_sdk.db import (
    configure_session_resolver,
    reset_session_resolver,
)
from inventia_spoke_sdk.fastapi import session_dep_for


@pytest.fixture(autouse=True)
def _reset_resolver():
    reset_session_resolver()
    yield
    reset_session_resolver()


async def test_session_dep_for_yields_session_via_principal_dep() -> None:
    """The dep produced by session_dep_for opens a session and closes it."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def resolver(_: SpokePrincipal):
        return factory

    configure_session_resolver(resolver)

    principal = SpokePrincipal(user_id=uuid4(), tenant_id=uuid4(), kind="user")

    # Simulate FastAPI's principal dep
    async def fake_principal_dep() -> SpokePrincipal:
        return principal

    dep = session_dep_for(fake_principal_dep)

    # The returned dep is an async generator. Drive it manually like FastAPI does.
    gen = dep(principal=principal)
    session = await gen.__anext__()
    try:
        assert isinstance(session, AsyncSession)
        result = await session.execute(select(1))
        assert result.scalar_one() == 1
    finally:
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    await engine.dispose()
