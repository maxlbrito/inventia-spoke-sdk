"""Rollback-per-test helpers.

Two pieces:

1. ``create_rollback_session_factory(connection)`` — wraps an open
   ``AsyncConnection`` so every ``Session()`` call attaches to the same
   connection inside a SAVEPOINT. The outer transaction can be rolled
   back at teardown to undo everything done by the test.

2. ``install_test_resolver(factory)`` — registers a
   ``SessionFactoryResolver`` for tests that always returns the same
   factory regardless of principal. Multi-tenant isolation is still
   asserted by the spoke's own tests; here we only need a single bound
   factory for the rollback wrapper.

Spokes typically build a session-scoped fixture::

    @pytest_asyncio.fixture
    async def db_factory(engine):
        async with engine.connect() as conn:
            await conn.begin()
            factory = create_rollback_session_factory(conn)
            install_test_resolver(lambda principal: factory)
            try:
                yield factory
            finally:
                reset_session_resolver()
                await conn.rollback()
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
)

from inventia_spoke_sdk.db.session import (
    SessionFactoryResolver,
    configure_session_resolver,
)
from inventia_spoke_sdk.principal import SpokePrincipal


def create_rollback_session_factory(
    connection: AsyncConnection,
) -> async_sessionmaker[AsyncSession]:
    """Return an ``async_sessionmaker`` bound to ``connection``.

    All sessions created from the returned factory share the same
    connection. The caller is responsible for rolling back the outer
    transaction at the end of the test to undo the SAVEPOINTs.
    """
    return async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


def install_test_resolver(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Register a resolver that ignores the principal and returns ``factory``.

    Suitable for unit tests of services where multi-tenant isolation is
    not the subject under test. For cross-tenant tests, register a
    resolver that selects per-principal factories.
    """

    async def _resolver(principal: SpokePrincipal) -> async_sessionmaker[AsyncSession]:
        return factory

    configure_session_resolver(_resolver)


@asynccontextmanager
async def isolated_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Open a session, yield it, rollback on exit.

    Convenience for tests that want one session and don't go through
    ``session_for(principal)``.
    """
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


def per_principal_resolver(
    by_tenant: dict[str | None, async_sessionmaker[AsyncSession]],
) -> SessionFactoryResolver:
    """Build a resolver that picks a factory by ``principal.tenant_id``.

    Use this in cross-tenant tests to verify a service never reads or
    writes outside the principal's tenant. Each tenant gets its own
    connection (and therefore its own data), and a service called with
    principal A must not touch principal B's data.
    """

    async def _resolver(principal: SpokePrincipal) -> async_sessionmaker[AsyncSession]:
        key = str(principal.tenant_id) if principal.tenant_id is not None else None
        if key not in by_tenant:
            raise KeyError(f"No factory registered for tenant_id={key!r}")
        return by_tenant[key]

    return _resolver


__all__ = [
    "create_rollback_session_factory",
    "install_test_resolver",
    "isolated_session",
    "per_principal_resolver",
]
