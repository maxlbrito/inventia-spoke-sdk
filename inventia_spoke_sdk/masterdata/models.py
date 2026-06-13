"""Read-models do cadastro do master-data — leitura no banco COMPARTILHADO.

Na arquitetura da casa, master-data e os spokes resolvem o MESMO ``db_url`` por
account (1 Account = 1 banco). As tabelas de cadastro (``companies``,
``products``, ``units_of_measure``) já vivem no banco que o spoke abre — não há
réplica, não há cópia, não há HTTP no caminho de leitura.

Estes models são **somente leitura** e usam um ``MetaData`` próprio
(``ReadBase.metadata``), ISOLADO do ``Base`` do spoke. NUNCA inclua este metadata
no ``autogenerate``/``create_all`` do seu Alembic — as tabelas pertencem ao
master-data; tentar migrá-las a partir de um spoke é erro. Escrita é exclusiva
do master-data.

Mapeiam um SUBCONJUNTO das colunas (as que os consumidores precisam). ``SELECT``
só pelas colunas mapeadas; adicionar colunas no master-data não quebra a leitura.
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
    address_zip: Mapped[str | None] = mapped_column(String(10))
    address_street: Mapped[str | None] = mapped_column(String(300))
    address_number: Mapped[str | None] = mapped_column(String(20))
    address_complement: Mapped[str | None] = mapped_column(String(100))
    address_district: Mapped[str | None] = mapped_column(String(100))
    address_city: Mapped[str | None] = mapped_column(String(100))
    address_state: Mapped[str | None] = mapped_column(String(2))
    ibge_city_code: Mapped[str | None] = mapped_column(String(7))
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
