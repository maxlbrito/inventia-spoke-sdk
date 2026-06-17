"""Read-models do cadastro do master-data — leitura no banco COMPARTILHADO.

Na arquitetura da casa, master-data e os spokes resolvem o MESMO ``db_url`` por
account (1 Account = 1 banco). As tabelas de cadastro já vivem no banco que o
spoke abre — não há réplica, não há cópia, não há HTTP no caminho de leitura.

Estes models são **somente leitura** e usam um ``MetaData`` próprio
(``ReadBase.metadata``), ISOLADO do ``Base`` do spoke. NUNCA inclua este metadata
no ``autogenerate``/``create_all`` do seu Alembic — as tabelas pertencem ao
master-data; tentar migrá-las a partir de um spoke é erro. Escrita é exclusiva
do master-data.

Mapeiam um SUBCONJUNTO das colunas. ``SELECT`` só pelas colunas mapeadas; o
master-data adicionar colunas não quebra a leitura. A guarda de drift
(``masterdata.drift``) protege contra o caso inverso (remover/renomear coluna).

Convenções:
- entidades por-tenant: têm ``tenant_id``, ``is_active`` e ``updated_at``;
- tabelas de referência global (IBGE/CNAE): sem ``tenant_id`` (PK natural).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, MetaData, Numeric, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ReadBase(DeclarativeBase):
    """Base dedicada e isolada para os read-models do cadastro.

    ``MetaData`` próprio: mantém estas tabelas fora do autogenerate do spoke.
    """

    metadata = MetaData()


# --- Entidades por-tenant ---------------------------------------------------


class Company(ReadBase):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    tax_id: Mapped[str] = mapped_column(String(20))
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str | None] = mapped_column(String(200))
    state_registration: Mapped[str | None] = mapped_column(String(30))
    municipal_registration: Mapped[str | None] = mapped_column(String(30))
    tax_regime: Mapped[str | None] = mapped_column(String(30))
    pis_cofins_regime: Mapped[str | None] = mapped_column(String(30))
    # Perfil fiscal (master-data #240 / migration 0018) — base do motor fiscal.
    contribuinte_ipi: Mapped[bool | None] = mapped_column(Boolean)
    pis_cofins_metodo_apropriacao: Mapped[str | None] = mapped_column(String(10))
    regime_especial: Mapped[str | None] = mapped_column(String(40))
    address_zip: Mapped[str | None] = mapped_column(String(10))
    address_street: Mapped[str | None] = mapped_column(String(300))
    address_number: Mapped[str | None] = mapped_column(String(20))
    address_complement: Mapped[str | None] = mapped_column(String(100))
    address_district: Mapped[str | None] = mapped_column(String(100))
    address_city: Mapped[str | None] = mapped_column(String(100))
    address_state: Mapped[str | None] = mapped_column(String(2))
    ibge_city_code: Mapped[str | None] = mapped_column(String(7))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(320))
    is_active: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Product(ReadBase):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(500))
    barcode: Mapped[str | None] = mapped_column(String(14))
    unit_of_measure: Mapped[str] = mapped_column(String(6))
    item_type: Mapped[str] = mapped_column(String(2))
    ncm_code: Mapped[str | None] = mapped_column(String(8))
    cest_code: Mapped[str | None] = mapped_column(String(7))
    icms_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    origin: Mapped[str] = mapped_column(String(1))
    is_active: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UnitOfMeasure(ReadBase):
    __tablename__ = "units_of_measure"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    unit_code: Mapped[str] = mapped_column(String(6))
    description: Mapped[str] = mapped_column(String(100))
    unit_type: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Participant(ReadBase):
    """Fornecedores/clientes/transportadoras (EFD 0150)."""

    __tablename__ = "participants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    tax_id_type: Mapped[str] = mapped_column(String(10))  # cnpj | cpf | foreign
    cnpj: Mapped[str | None] = mapped_column(String(14))
    cpf: Mapped[str | None] = mapped_column(String(11))
    foreign_tax_id: Mapped[str | None] = mapped_column(String(60))
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str | None] = mapped_column(String(200))
    state_registration: Mapped[str | None] = mapped_column(String(30))
    municipal_registration: Mapped[str | None] = mapped_column(String(30))
    address_zip: Mapped[str | None] = mapped_column(String(10))
    address_street: Mapped[str | None] = mapped_column(String(300))
    address_number: Mapped[str | None] = mapped_column(String(20))
    address_district: Mapped[str | None] = mapped_column(String(100))
    address_city: Mapped[str | None] = mapped_column(String(100))
    address_state: Mapped[str | None] = mapped_column(String(2))
    ibge_city_code: Mapped[str | None] = mapped_column(String(7))
    # CNAE da contraparte (master-data #240 / migration 0018) — perfil origem/destino.
    cnae_code: Mapped[str | None] = mapped_column(String(7))
    is_active: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Certificate(ReadBase):
    """Certificado digital A1 — metadados + material cifrado em repouso.

    ``pfx_encrypted``/``password_encrypted`` são cifrados com a chave Fernet
    **per-tenant** (``CertificateKey``, no próprio banco do account). Não use estes
    campos diretamente — passe por
    ``MasterDataRepository.get_active_certificate_material``, que lê a chave e
    decifra in-process, sem depender do serviço master-data nem do Hub (Cenário 1).
    Para só checar presença/validade use ``get_active_certificate`` (metadados).
    """

    __tablename__ = "certificates"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    company_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    cnpj: Mapped[str] = mapped_column(String(20))
    pfx_encrypted: Mapped[str] = mapped_column(String)
    password_encrypted: Mapped[str] = mapped_column(String)
    thumbprint: Mapped[str | None] = mapped_column(String(64))
    issuer_name: Mapped[str | None] = mapped_column(String(300))
    subject_name: Mapped[str | None] = mapped_column(String(300))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CertificateKey(ReadBase):
    """Chave Fernet **per-tenant** que cifra os certificados A1 (read-model).

    Mora no próprio banco do account (master-data `certificate_crypto_keys`, sob
    RLS). Lida junto com o ciphertext, na mesma sessão, para decifrar in-process.
    Material sensível: nunca exponha o ``key`` fora do SDK.
    """

    __tablename__ = "certificate_crypto_keys"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String)


# --- Referência global (sem tenant_id) --------------------------------------


class IbgeMunicipality(ReadBase):
    __tablename__ = "ibge_municipalities"

    ibge_code: Mapped[str] = mapped_column(String(7), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    state_code: Mapped[str] = mapped_column(String(2), index=True)
    state_name: Mapped[str] = mapped_column(String(50))


class CnaeCode(ReadBase):
    __tablename__ = "cnae_codes"

    cnae_code: Mapped[str] = mapped_column(String(7), primary_key=True)
    description: Mapped[str] = mapped_column(String(300))
    section: Mapped[str] = mapped_column(String(1))
    division: Mapped[str] = mapped_column(String(2))
    group_code: Mapped[str] = mapped_column(String(3))
    class_code: Mapped[str] = mapped_column(String(5))
