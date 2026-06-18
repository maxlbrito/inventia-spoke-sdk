"""Outbox transacional COMPARTILHADO — model + helper de enfileiramento.

A tabela ``outbox`` é única no banco compartilhado (1 Account = 1 banco) e seu
**DDL pertence ao master-data** (migration 0020). Este módulo dá aos Spokes
**produtores** (``doc-flow-nfe``, ``doc-flow-nfse``, ...) a definição ORM e o
helper ``enqueue`` para gravar o envelope canônico **dentro da própria
transação** que muda o estado de negócio — é isso que garante a atomicidade
documento↔mensagem.

Como em ``masterdata.models``, usamos um ``DeclarativeBase`` com ``MetaData``
PRÓPRIO e isolado (``OutboxBase.metadata``): a tabela é de outro dono, então ela
NUNCA pode entrar no ``autogenerate``/``create_all`` do Alembic do produtor.

Escrita é direta na tabela (NÃO via serviço do master-data). Leitura/drenagem é
do relay/publisher, que por ser cross-tenant roda sob role ``BYPASSRLS``
dedicado (ver migration 0020 do master-data). A deduplicação real é no inbox do
consumidor por ``envelope_id``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Identity,
    Integer,
    MetaData,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class OutboxBase(DeclarativeBase):
    """Base dedicada e isolada para o outbox (MetaData próprio).

    Mantém a tabela fora do autogenerate do spoke produtor — o DDL é do
    master-data.
    """

    metadata = MetaData()


class Outbox(OutboxBase):
    __tablename__ = "outbox"

    # identidade / ordenação
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # created_at compõe a PK por ser a coluna de particionamento (exigência do PG)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now()
    )
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    envelope_id: Mapped[UUID] = mapped_column(Uuid)

    # roteamento
    message_type: Mapped[str] = mapped_column(Text)  # 'document' | 'event'
    event_type: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(Text)  # app produtor
    envelope_version: Mapped[str] = mapped_column(Text)
    access_key: Mapped[str | None] = mapped_column(String(100))
    document_date: Mapped[date | None] = mapped_column(Date)  # data do XML OU do evento, sem hora

    # isolamento (3 níveis)
    account: Mapped[str] = mapped_column(Text)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    company_id: Mapped[UUID | None] = mapped_column(Uuid)

    # conteúdo
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONB)

    # ciclo de vida / relay
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="8")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("message_type IN ('document','event')", name="outbox_message_type_chk"),
        CheckConstraint("status IN ('pending','published','dead')", name="outbox_status_chk"),
    )


def enqueue(
    session: AsyncSession,
    *,
    envelope_id: UUID,
    message_type: str,
    source: str,
    envelope_version: str,
    account: str,
    tenant_id: UUID,
    envelope: dict[str, Any],
    event_type: str | None = None,
    access_key: str | None = None,
    document_date: date | None = None,
    company_id: UUID | None = None,
    max_attempts: int = 8,
) -> Outbox:
    """Enfileira um envelope no outbox DENTRO da transação corrente do produtor.

    NÃO faz commit: quem chama dá o ``commit`` junto da mudança de estado de
    negócio, na mesma transação — é o que garante a atomicidade. ``session.add``
    é síncrono mesmo em ``AsyncSession``.

    Para ``message_type='event'``, informe ``event_type`` e use a data do evento
    em ``document_date``; para ``'document'``, use a data de emissão/entrada-saída.
    """
    row = Outbox(
        envelope_id=envelope_id,
        message_type=message_type,
        event_type=event_type,
        source=source,
        envelope_version=envelope_version,
        access_key=access_key,
        document_date=document_date,
        account=account,
        tenant_id=tenant_id,
        company_id=company_id,
        envelope=envelope,
        max_attempts=max_attempts,
    )
    session.add(row)
    return row
