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

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inventia_spoke_sdk.principal import SpokePrincipal

logger = logging.getLogger("inventia_spoke_sdk.db")

# Nome canônico da variável de sessão (GUC) usada pelas policies de RLS.
# Decisão da arquitetura (ver plano): ``app.current_tenant``.
TENANT_GUC = "app.current_tenant"


def _bind_tenant_guc(session: AsyncSession, tenant_id: str) -> None:
    """Garante ``SET LOCAL app.current_tenant = <tenant_id>`` em TODA transação.

    Implementado via listener ``after_begin`` no ``sync_session``: a cada
    transação aberta (lazy, no 1º statement), reaplica o GUC com
    ``is_local=true`` — então vale só dentro daquela transação e nunca vaza
    pela connection pool. Só roda em PostgreSQL; em outros dialetos (ex.:
    SQLite nos testes) é no-op, pois ``set_config`` não existe.

    Camada 5 (RLS) só protege se este GUC estiver setado: sem ele, as policies
    ``USING (tenant_id = current_setting('app.current_tenant', true))`` casam
    com NULL e retornam 0 linhas (deny-by-default).
    """

    @event.listens_for(session.sync_session, "after_begin")
    def _set_tenant(_sess: object, _transaction: object, connection: Any) -> None:  # noqa: ANN401
        if connection.dialect.name != "postgresql":
            return
        connection.execute(
            text(f"SELECT set_config('{TENANT_GUC}', :tid, true)"), {"tid": tenant_id}
        )


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


async def assert_rls_enforceable(session: AsyncSession, *, strict: bool = False) -> bool:
    """Verifica se o role de conexão NÃO ignora RLS (risco R-2b do plano).

    SUPERUSER ou BYPASSRLS fazem a RLS (camada 5) ser silenciosamente ignorada —
    o isolamento por tenant deixa de valer. Use no startup do spoke / num
    health check. Retorna ``True`` se a RLS é aplicável (role sem bypass).

    - PostgreSQL: consulta ``pg_roles`` do ``current_user``.
    - Outros dialetos (ex.: SQLite em testes): retorna ``True`` (no-op).
    - ``strict=True``: levanta ``RuntimeError`` se o role puder burlar RLS
      (fail-closed, recomendado em prod). Default: só loga ``warning``.
    """
    bind = session.get_bind()
    if getattr(bind.dialect, "name", "") != "postgresql":
        return True
    row = (
        await session.execute(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
    ).scalar()
    can_bypass = bool(row)
    if can_bypass:
        msg = (
            "RLS NÃO será aplicada: o role de conexão é SUPERUSER/BYPASSRLS. "
            "Use um role dedicado sem esses atributos em produção (risco R-2b)."
        )
        if strict:
            raise RuntimeError(msg)
        logger.warning(msg)
    return not can_bypass


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
        if principal.tenant_id is not None:
            _bind_tenant_guc(session, str(principal.tenant_id))
        yield session
