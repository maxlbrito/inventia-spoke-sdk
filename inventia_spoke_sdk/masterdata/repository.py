"""Leitura tenant-scoped do cadastro do master-data no banco COMPARTILHADO.

O repositório recebe a ``AsyncSession`` já aberta pelo ``session_for(principal)``
do SDK — não abre conexão própria, respeitando o invariante per-account. Toda
query é filtrada por ``tenant_id`` (regra dura dos spokes).

Somente leitura: a escrita do cadastro é exclusiva do master-data. Como o dado
está no mesmo banco por account, a indisponibilidade do SERVIÇO HTTP do
master-data não afeta estas leituras — a única dependência é o Postgres, que já
é dependência de todo spoke.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inventia_spoke_sdk.masterdata.models import Company, Product, UnitOfMeasure


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class MasterDataRepository:
    """Acesso de leitura ao cadastro do master-data (banco compartilhado)."""

    async def get_company(
        self, session: AsyncSession, *, tenant_id: str | UUID, company_id: str | UUID
    ) -> Company | None:
        stmt = select(Company).where(
            Company.tenant_id == _as_uuid(tenant_id),
            Company.id == _as_uuid(company_id),
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_company_by_tax_id(
        self, session: AsyncSession, *, tenant_id: str | UUID, tax_id: str
    ) -> Company | None:
        stmt = select(Company).where(
            Company.tenant_id == _as_uuid(tenant_id),
            Company.tax_id == tax_id,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_companies(
        self,
        session: AsyncSession,
        *,
        tenant_id: str | UUID,
        active_only: bool = True,
        limit: int = 500,
    ) -> Sequence[Company]:
        stmt = select(Company).where(Company.tenant_id == _as_uuid(tenant_id))
        if active_only:
            stmt = stmt.where(Company.is_active.is_(True))
        stmt = stmt.order_by(Company.legal_name).limit(limit)
        return (await session.execute(stmt)).scalars().all()

    async def get_product_by_code(
        self, session: AsyncSession, *, tenant_id: str | UUID, code: str
    ) -> Product | None:
        stmt = select(Product).where(
            Product.tenant_id == _as_uuid(tenant_id),
            Product.code == code,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_products_by_codes(
        self, session: AsyncSession, *, tenant_id: str | UUID, codes: Iterable[str]
    ) -> Sequence[Product]:
        wanted = list(codes)
        if not wanted:
            return []
        stmt = select(Product).where(
            Product.tenant_id == _as_uuid(tenant_id),
            Product.code.in_(wanted),
        )
        return (await session.execute(stmt)).scalars().all()

    async def get_unit(
        self, session: AsyncSession, *, tenant_id: str | UUID, unit_code: str
    ) -> UnitOfMeasure | None:
        stmt = select(UnitOfMeasure).where(
            UnitOfMeasure.tenant_id == _as_uuid(tenant_id),
            UnitOfMeasure.unit_code == unit_code,
        )
        return (await session.execute(stmt)).scalar_one_or_none()
