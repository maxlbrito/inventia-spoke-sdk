"""Leitura tenant-scoped do cadastro do master-data no banco COMPARTILHADO.

O repositório recebe a ``AsyncSession`` já aberta pelo ``session_for(principal)``
do SDK — não abre conexão própria, respeitando o invariante per-account. Toda
query de entidade por-tenant filtra por ``tenant_id`` (regra dura dos spokes).
Tabelas de referência global (IBGE/CNAE) não têm tenant.

Somente leitura: a escrita do cadastro é exclusiva do master-data. Como o dado
está no mesmo banco por account, a indisponibilidade do SERVIÇO HTTP do
master-data não afeta estas leituras — a única dependência é o Postgres.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inventia_spoke_sdk.masterdata.crypto import (
    CertificateKeyMissing,
    decrypt_tokens,
)
from inventia_spoke_sdk.masterdata.models import (
    Certificate,
    CertificateKey,
    CnaeCode,
    Company,
    IbgeMunicipality,
    Participant,
    Product,
    UnitOfMeasure,
)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


@dataclass(frozen=True)
class CertificateMaterial:
    """Material do certificado A1 já decifrado (pronto para assinar).

    Devolvido por ``get_active_certificate_material`` — o consumidor não conhece
    Fernet nem a chave: recebe os bytes do PFX e a senha em claro.
    """

    company_id: UUID
    cnpj: str
    pfx_bytes: bytes
    password: str
    expires_at: datetime
    thumbprint: str | None


class MasterDataRepository:
    """Acesso de leitura ao cadastro do master-data (banco compartilhado)."""

    # --- Company ------------------------------------------------------------

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

    # --- Product ------------------------------------------------------------

    async def get_product(
        self, session: AsyncSession, *, tenant_id: str | UUID, product_id: str | UUID
    ) -> Product | None:
        stmt = select(Product).where(
            Product.tenant_id == _as_uuid(tenant_id),
            Product.id == _as_uuid(product_id),
        )
        return (await session.execute(stmt)).scalar_one_or_none()

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

    async def list_products(
        self,
        session: AsyncSession,
        *,
        tenant_id: str | UUID,
        active_only: bool = True,
        limit: int = 500,
    ) -> Sequence[Product]:
        stmt = select(Product).where(Product.tenant_id == _as_uuid(tenant_id))
        if active_only:
            stmt = stmt.where(Product.is_active.is_(True))
        stmt = stmt.order_by(Product.code).limit(limit)
        return (await session.execute(stmt)).scalars().all()

    # --- UnitOfMeasure ------------------------------------------------------

    async def get_unit(
        self, session: AsyncSession, *, tenant_id: str | UUID, unit_code: str
    ) -> UnitOfMeasure | None:
        stmt = select(UnitOfMeasure).where(
            UnitOfMeasure.tenant_id == _as_uuid(tenant_id),
            UnitOfMeasure.unit_code == unit_code,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_units(
        self, session: AsyncSession, *, tenant_id: str | UUID, active_only: bool = True
    ) -> Sequence[UnitOfMeasure]:
        stmt = select(UnitOfMeasure).where(UnitOfMeasure.tenant_id == _as_uuid(tenant_id))
        if active_only:
            stmt = stmt.where(UnitOfMeasure.is_active.is_(True))
        stmt = stmt.order_by(UnitOfMeasure.unit_code)
        return (await session.execute(stmt)).scalars().all()

    # --- Participant --------------------------------------------------------

    async def get_participant(
        self, session: AsyncSession, *, tenant_id: str | UUID, participant_id: str | UUID
    ) -> Participant | None:
        stmt = select(Participant).where(
            Participant.tenant_id == _as_uuid(tenant_id),
            Participant.id == _as_uuid(participant_id),
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_participant_by_cnpj(
        self, session: AsyncSession, *, tenant_id: str | UUID, cnpj: str
    ) -> Participant | None:
        stmt = select(Participant).where(
            Participant.tenant_id == _as_uuid(tenant_id),
            Participant.cnpj == cnpj,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_participant_by_cpf(
        self, session: AsyncSession, *, tenant_id: str | UUID, cpf: str
    ) -> Participant | None:
        stmt = select(Participant).where(
            Participant.tenant_id == _as_uuid(tenant_id),
            Participant.cpf == cpf,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_participants(
        self,
        session: AsyncSession,
        *,
        tenant_id: str | UUID,
        active_only: bool = True,
        limit: int = 500,
    ) -> Sequence[Participant]:
        stmt = select(Participant).where(Participant.tenant_id == _as_uuid(tenant_id))
        if active_only:
            stmt = stmt.where(Participant.is_active.is_(True))
        stmt = stmt.order_by(Participant.legal_name).limit(limit)
        return (await session.execute(stmt)).scalars().all()

    # --- Certificate (metadados) --------------------------------------------

    async def get_active_certificate(
        self, session: AsyncSession, *, tenant_id: str | UUID, company_id: str | UUID
    ) -> Certificate | None:
        """Certificado ativo MAIS RECENTE da empresa — só metadados (sem pfx/senha).

        Desde o multi-certificado (master-data), uma empresa pode ter mais de um
        certificado ativo; este método devolve o de ``issued_at`` mais recente
        (determinístico, nunca levanta). Para a lista completa use
        ``list_active_certificates``. Material sensível não é exposto por aqui.
        """
        stmt = (
            select(Certificate)
            .where(
                Certificate.tenant_id == _as_uuid(tenant_id),
                Certificate.company_id == _as_uuid(company_id),
                Certificate.is_active.is_(True),
            )
            .order_by(Certificate.issued_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalars().first()

    async def list_active_certificates(
        self, session: AsyncSession, *, tenant_id: str | UUID, company_id: str | UUID
    ) -> Sequence[Certificate]:
        """Todos os certificados ativos da empresa (mais recente primeiro)."""
        stmt = (
            select(Certificate)
            .where(
                Certificate.tenant_id == _as_uuid(tenant_id),
                Certificate.company_id == _as_uuid(company_id),
                Certificate.is_active.is_(True),
            )
            .order_by(Certificate.issued_at.desc())
        )
        return (await session.execute(stmt)).scalars().all()

    async def _tenant_cert_key(self, session: AsyncSession, tenant_id: str | UUID) -> str | None:
        stmt = select(CertificateKey.key).where(CertificateKey.tenant_id == _as_uuid(tenant_id))
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_active_certificate_material(
        self, session: AsyncSession, *, tenant_id: str | UUID, company_id: str | UUID
    ) -> CertificateMaterial | None:
        """Certificado ativo mais recente da empresa, **decifrado** (PFX + senha).

        Encapsula tudo: lê o ciphertext + a chave Fernet per-tenant no MESMO banco
        do account e decifra in-process. Não depende do serviço master-data nem do
        Hub — só do Postgres (assinar continua com o master-data fora, Cenário 1).

        Devolve ``None`` se a empresa não tem certificado ativo. Levanta
        ``CertificateKeyMissing`` se há certificado mas falta a chave do tenant
        (estado inconsistente — checar a migração relocate-first do master-data),
        e ``CertificateDecryptError`` se a chave não decifra o material.
        """
        cert = await self.get_active_certificate(
            session, tenant_id=tenant_id, company_id=company_id
        )
        if cert is None:
            return None
        key = await self._tenant_cert_key(session, tenant_id)
        if not key:
            raise CertificateKeyMissing(str(_as_uuid(tenant_id)))
        pfx_bytes, password_bytes = decrypt_tokens(key, cert.pfx_encrypted, cert.password_encrypted)
        return CertificateMaterial(
            company_id=cert.company_id,
            cnpj=cert.cnpj,
            pfx_bytes=pfx_bytes,
            password=password_bytes.decode(),
            expires_at=cert.expires_at,
            thumbprint=cert.thumbprint,
        )

    # --- Referência global (sem tenant) -------------------------------------

    async def get_municipality(
        self, session: AsyncSession, *, ibge_code: str
    ) -> IbgeMunicipality | None:
        stmt = select(IbgeMunicipality).where(IbgeMunicipality.ibge_code == ibge_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_cnae(self, session: AsyncSession, *, cnae_code: str) -> CnaeCode | None:
        stmt = select(CnaeCode).where(CnaeCode.cnae_code == cnae_code)
        return (await session.execute(stmt)).scalar_one_or_none()
