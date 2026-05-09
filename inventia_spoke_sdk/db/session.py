"""Tenant-aware session resolver.

The SDK keeps a process-wide registry of a single
``SessionFactoryResolver``. The spoke configures it at startup
(typically in a FastAPI ``lifespan`` and inside the arq
``WorkerSettings.on_startup`` hook).

Why a resolver and not a fixed engine pool: each spoke owns its own
notion of "where the tenant lives" (per-account DB URL fetched from the
Hub, per-tenant schema, single shared DB with a tenant column, etc).
The SDK only enforces that whatever the spoke does, it produces an
``async_sessionmaker`` for the caller's principal.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inventia_spoke_sdk.principal import SpokePrincipal


class SessionFactoryResolver(Protocol):
    """Spoke-supplied callable: principal → async_sessionmaker.

    Implementations are async to allow Hub round-trips and lazy schema
    provisioning. They MUST return a sessionmaker scoped to the
    tenant of ``principal`` and MUST NOT leak across tenants.
    """

    async def __call__(self, principal: SpokePrincipal) -> async_sessionmaker[AsyncSession]: ...


_resolver: SessionFactoryResolver | None = None


def configure_session_resolver(resolver: SessionFactoryResolver) -> None:
    """Register the spoke's session factory resolver.

    Call once at process startup. Calling again replaces the previous
    resolver — useful in tests via ``reset_session_resolver``.
    """
    global _resolver
    _resolver = resolver


def get_session_resolver() -> SessionFactoryResolver:
    """Return the registered resolver or raise if none is configured."""
    if _resolver is None:
        raise RuntimeError(
            "No SessionFactoryResolver configured. "
            "Call inventia_spoke_sdk.db.configure_session_resolver(...) "
            "during your spoke's startup."
        )
    return _resolver


def reset_session_resolver() -> None:
    """Clear the registered resolver. Tests use this between cases."""
    global _resolver
    _resolver = None


@asynccontextmanager
async def session_for(principal: SpokePrincipal) -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` bound to the principal's tenant.

    Typical use::

        async with session_for(principal) as session:
            service = CompanyService(session, principal=principal)
            await service.upsert(payload)

    The session is closed automatically on exit. Transactions are NOT
    started implicitly — call ``async with session.begin():`` if you
    need an explicit transaction boundary.
    """
    resolver = get_session_resolver()
    factory = await resolver(principal)
    async with factory() as session:
        yield session
