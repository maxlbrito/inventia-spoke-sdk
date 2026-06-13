"""MasterDataRepository — leitura tenant-scoped sobre o banco compartilhado.

SQLite in-memory: cria as tabelas a partir do ``ReadBase.metadata`` (mesmo
mapeamento usado em produção contra o banco do account) e exercita o repositório
real. Foco: leitura correta + isolamento por tenant + degradação por ausência.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from inventia_spoke_sdk.masterdata import (
    Company,
    MasterDataRepository,
    Product,
    ReadBase,
    UnitOfMeasure,
)

TENANT_A = uuid4()
TENANT_B = uuid4()
COMPANY_A = uuid4()
PRODUCT_A = uuid4()
UNIT_A = uuid4()


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ReadBase.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        now = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
        s.add(
            Company(
                id=COMPANY_A,
                tenant_id=TENANT_A,
                tax_id="11222333000181",
                legal_name="ACME LTDA",
                state_registration="123456",
                tax_regime="real",
                address_city="São Paulo",
                address_state="SP",
                is_active=True,
                updated_at=now,
            )
        )
        # Mesma tax_id em OUTRO tenant — não pode vazar.
        s.add(
            Company(
                id=uuid4(),
                tenant_id=TENANT_B,
                tax_id="11222333000181",
                legal_name="OUTRO TENANT SA",
                is_active=True,
                updated_at=now,
            )
        )
        s.add(
            Company(
                id=uuid4(),
                tenant_id=TENANT_A,
                tax_id="99888777000166",
                legal_name="Inativa ME",
                is_active=False,
                updated_at=now,
            )
        )
        s.add(
            Product(
                id=PRODUCT_A,
                tenant_id=TENANT_A,
                code="P-001",
                description="Parafuso",
                unit_of_measure="UN",
                item_type="00",
                ncm_code="73181500",
                icms_rate=Decimal("18.00"),
                origin="0",
                is_active=True,
                updated_at=now,
            )
        )
        s.add(
            Product(
                id=uuid4(),
                tenant_id=TENANT_A,
                code="P-002",
                description="Porca",
                unit_of_measure="UN",
                item_type="00",
                origin="0",
                is_active=True,
                updated_at=now,
            )
        )
        s.add(
            UnitOfMeasure(
                id=UNIT_A,
                tenant_id=TENANT_A,
                unit_code="UN",
                description="Unidade",
                unit_type="quantity",
                is_active=True,
                updated_at=now,
            )
        )
        await s.commit()
        yield s
    await engine.dispose()


@pytest.fixture
def repo() -> MasterDataRepository:
    return MasterDataRepository()


async def test_get_company_by_id(session, repo) -> None:
    c = await repo.get_company(session, tenant_id=TENANT_A, company_id=COMPANY_A)
    assert c is not None
    assert c.legal_name == "ACME LTDA"
    assert c.state_registration == "123456"


async def test_get_company_accepts_str_ids(session, repo) -> None:
    c = await repo.get_company(session, tenant_id=str(TENANT_A), company_id=str(COMPANY_A))
    assert c is not None and c.tax_id == "11222333000181"


async def test_get_company_missing_returns_none(session, repo) -> None:
    assert await repo.get_company(session, tenant_id=TENANT_A, company_id=uuid4()) is None


async def test_company_tenant_isolation(session, repo) -> None:
    # COMPANY_A pertence ao TENANT_A — buscar no TENANT_B não retorna nada.
    assert await repo.get_company(session, tenant_id=TENANT_B, company_id=COMPANY_A) is None


async def test_get_company_by_tax_id_is_tenant_scoped(session, repo) -> None:
    a = await repo.get_company_by_tax_id(session, tenant_id=TENANT_A, tax_id="11222333000181")
    b = await repo.get_company_by_tax_id(session, tenant_id=TENANT_B, tax_id="11222333000181")
    assert a is not None and a.legal_name == "ACME LTDA"
    assert b is not None and b.legal_name == "OUTRO TENANT SA"


async def test_list_companies_active_only(session, repo) -> None:
    active = await repo.list_companies(session, tenant_id=TENANT_A)
    names = {c.legal_name for c in active}
    assert "ACME LTDA" in names
    assert "Inativa ME" not in names


async def test_list_companies_including_inactive(session, repo) -> None:
    allc = await repo.list_companies(session, tenant_id=TENANT_A, active_only=False)
    assert any(c.legal_name == "Inativa ME" for c in allc)


async def test_get_product_by_code(session, repo) -> None:
    p = await repo.get_product_by_code(session, tenant_id=TENANT_A, code="P-001")
    assert p is not None
    assert p.description == "Parafuso"
    assert p.icms_rate == Decimal("18.00")


async def test_list_products_by_codes(session, repo) -> None:
    prods = await repo.list_products_by_codes(session, tenant_id=TENANT_A, codes=["P-001", "P-002"])
    assert {p.code for p in prods} == {"P-001", "P-002"}


async def test_list_products_by_codes_empty(session, repo) -> None:
    assert await repo.list_products_by_codes(session, tenant_id=TENANT_A, codes=[]) == []


async def test_get_unit(session, repo) -> None:
    u = await repo.get_unit(session, tenant_id=TENANT_A, unit_code="UN")
    assert u is not None and u.description == "Unidade"


async def test_get_unit_missing(session, repo) -> None:
    assert await repo.get_unit(session, tenant_id=TENANT_A, unit_code="KG") is None
