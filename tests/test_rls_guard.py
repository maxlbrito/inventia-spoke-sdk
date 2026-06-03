"""v0.6.0 Fase 6 — assert_rls_enforceable (guard de role SUPERUSER/BYPASSRLS)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from inventia_spoke_sdk.db import assert_rls_enforceable


async def test_noop_on_non_postgres():
    """Em SQLite (testes) não há pg_roles — retorna True sem consultar nem falhar."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        assert await assert_rls_enforceable(session) is True
        # strict também não levanta em dialeto não-postgres
        assert await assert_rls_enforceable(session, strict=True) is True
    await engine.dispose()
