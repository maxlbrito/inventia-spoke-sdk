"""MasterDataRepository — leitura tenant-scoped sobre o banco compartilhado.

SQLite in-memory: cria as tabelas a partir do ``ReadBase.metadata`` (mesmo
mapeamento usado em produção contra o banco do account) e exercita o repositório
real. Foco: leitura correta de cada entidade + isolamento por tenant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from inventia_spoke_sdk.masterdata import (
    Certificate,
    CnaeCode,
    Company,
    IbgeMunicipality,
    MasterDataRepository,
    Participant,
    Product,
    ReadBase,
    UnitOfMeasure,
)

TENANT_A = uuid4()
TENANT_B = uuid4()
COMPANY_A = uuid4()
PRODUCT_A = uuid4()
UNIT_A = uuid4()
PART_A = uuid4()
NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
LATER = datetime(2030, 1, 1, 0, 0, 0, tzinfo=UTC)


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ReadBase.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
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
                updated_at=NOW,
            )
        )
        s.add(  # mesma tax_id em OUTRO tenant — não pode vazar
            Company(
                id=uuid4(),
                tenant_id=TENANT_B,
                tax_id="11222333000181",
                legal_name="OUTRO TENANT SA",
                is_active=True,
                updated_at=NOW,
            )
        )
        s.add(
            Company(
                id=uuid4(),
                tenant_id=TENANT_A,
                tax_id="99888777000166",
                legal_name="Inativa ME",
                is_active=False,
                updated_at=NOW,
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
                updated_at=NOW,
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
                updated_at=NOW,
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
                updated_at=NOW,
            )
        )
        s.add(
            Participant(
                id=PART_A,
                tenant_id=TENANT_A,
                tax_id_type="cnpj",
                cnpj="44555666000177",
                legal_name="Fornecedor X SA",
                address_state="RJ",
                is_active=True,
                updated_at=NOW,
            )
        )
        s.add(
            Participant(
                id=uuid4(),
                tenant_id=TENANT_A,
                tax_id_type="cpf",
                cpf="12345678909",
                legal_name="João Cliente",
                is_active=True,
                updated_at=NOW,
            )
        )
        s.add(
            Certificate(
                id=uuid4(),
                tenant_id=TENANT_A,
                company_id=COMPANY_A,
                cnpj="11222333000181",
                thumbprint="AB12",
                issued_at=NOW,
                expires_at=LATER,
                is_active=True,
                updated_at=NOW,
            )
        )
        s.add(
            IbgeMunicipality(
                ibge_code="3550308", name="São Paulo", state_code="SP", state_name="São Paulo"
            )
        )
        s.add(
            CnaeCode(
                cnae_code="4711301",
                description="Comércio varejista",
                section="G",
                division="47",
                group_code="471",
                class_code="47113",
            )
        )
        await s.commit()
        yield s
    await engine.dispose()


@pytest.fixture
def repo() -> MasterDataRepository:
    return MasterDataRepository()


# --- Company ---------------------------------------------------------------


async def test_get_company_by_id(session, repo) -> None:
    c = await repo.get_company(session, tenant_id=TENANT_A, company_id=COMPANY_A)
    assert c is not None and c.legal_name == "ACME LTDA" and c.state_registration == "123456"


async def test_get_company_accepts_str_ids(session, repo) -> None:
    c = await repo.get_company(session, tenant_id=str(TENANT_A), company_id=str(COMPANY_A))
    assert c is not None and c.tax_id == "11222333000181"


async def test_get_company_missing_returns_none(session, repo) -> None:
    assert await repo.get_company(session, tenant_id=TENANT_A, company_id=uuid4()) is None


async def test_company_tenant_isolation(session, repo) -> None:
    assert await repo.get_company(session, tenant_id=TENANT_B, company_id=COMPANY_A) is None


async def test_get_company_by_tax_id_is_tenant_scoped(session, repo) -> None:
    a = await repo.get_company_by_tax_id(session, tenant_id=TENANT_A, tax_id="11222333000181")
    b = await repo.get_company_by_tax_id(session, tenant_id=TENANT_B, tax_id="11222333000181")
    assert a is not None and a.legal_name == "ACME LTDA"
    assert b is not None and b.legal_name == "OUTRO TENANT SA"


async def test_list_companies_active_only(session, repo) -> None:
    names = {c.legal_name for c in await repo.list_companies(session, tenant_id=TENANT_A)}
    assert "ACME LTDA" in names and "Inativa ME" not in names


async def test_list_companies_including_inactive(session, repo) -> None:
    allc = await repo.list_companies(session, tenant_id=TENANT_A, active_only=False)
    assert any(c.legal_name == "Inativa ME" for c in allc)


# --- Product ---------------------------------------------------------------


async def test_get_product_by_id(session, repo) -> None:
    p = await repo.get_product(session, tenant_id=TENANT_A, product_id=PRODUCT_A)
    assert p is not None and p.code == "P-001"


async def test_get_product_by_code(session, repo) -> None:
    p = await repo.get_product_by_code(session, tenant_id=TENANT_A, code="P-001")
    assert p is not None and p.description == "Parafuso" and p.icms_rate == Decimal("18.00")


async def test_list_products_by_codes(session, repo) -> None:
    prods = await repo.list_products_by_codes(session, tenant_id=TENANT_A, codes=["P-001", "P-002"])
    assert {p.code for p in prods} == {"P-001", "P-002"}


async def test_list_products_by_codes_empty(session, repo) -> None:
    assert await repo.list_products_by_codes(session, tenant_id=TENANT_A, codes=[]) == []


async def test_list_products(session, repo) -> None:
    codes = {p.code for p in await repo.list_products(session, tenant_id=TENANT_A)}
    assert codes == {"P-001", "P-002"}


# --- Unit ------------------------------------------------------------------


async def test_get_unit(session, repo) -> None:
    u = await repo.get_unit(session, tenant_id=TENANT_A, unit_code="UN")
    assert u is not None and u.description == "Unidade"


async def test_get_unit_missing(session, repo) -> None:
    assert await repo.get_unit(session, tenant_id=TENANT_A, unit_code="KG") is None


async def test_list_units(session, repo) -> None:
    units = await repo.list_units(session, tenant_id=TENANT_A)
    assert {u.unit_code for u in units} == {"UN"}


# --- Participant -----------------------------------------------------------


async def test_get_participant_by_id(session, repo) -> None:
    p = await repo.get_participant(session, tenant_id=TENANT_A, participant_id=PART_A)
    assert p is not None and p.legal_name == "Fornecedor X SA"


async def test_get_participant_by_cnpj(session, repo) -> None:
    p = await repo.get_participant_by_cnpj(session, tenant_id=TENANT_A, cnpj="44555666000177")
    assert p is not None and p.tax_id_type == "cnpj"


async def test_get_participant_by_cpf(session, repo) -> None:
    p = await repo.get_participant_by_cpf(session, tenant_id=TENANT_A, cpf="12345678909")
    assert p is not None and p.legal_name == "João Cliente"


async def test_participant_tenant_isolation(session, repo) -> None:
    assert (
        await repo.get_participant_by_cnpj(session, tenant_id=TENANT_B, cnpj="44555666000177")
        is None
    )


async def test_list_participants(session, repo) -> None:
    parts = await repo.list_participants(session, tenant_id=TENANT_A)
    assert {p.legal_name for p in parts} == {"Fornecedor X SA", "João Cliente"}


# --- Certificate (metadados) -----------------------------------------------


async def test_get_active_certificate(session, repo) -> None:
    cert = await repo.get_active_certificate(session, tenant_id=TENANT_A, company_id=COMPANY_A)
    # expires_at: SQLite devolve naive; comparamos pelo ano (em produção é tz-aware)
    assert cert is not None and cert.thumbprint == "AB12" and cert.expires_at.year == 2030
    # material sensível NÃO é exposto pelo read-model
    assert not hasattr(cert, "pfx_encrypted")
    assert not hasattr(cert, "password_encrypted")


async def test_get_active_certificate_missing(session, repo) -> None:
    assert (
        await repo.get_active_certificate(session, tenant_id=TENANT_A, company_id=uuid4()) is None
    )


# --- Referência global -----------------------------------------------------


async def test_get_municipality(session, repo) -> None:
    m = await repo.get_municipality(session, ibge_code="3550308")
    assert m is not None and m.name == "São Paulo" and m.state_code == "SP"


async def test_get_municipality_missing(session, repo) -> None:
    assert await repo.get_municipality(session, ibge_code="0000000") is None


async def test_get_cnae(session, repo) -> None:
    c = await repo.get_cnae(session, cnae_code="4711301")
    assert c is not None and c.section == "G"
