"""Acesso de leitura ao cadastro do master-data no banco compartilhado.

Na topologia da casa (1 Account = 1 banco), o cadastro do master-data vive no
mesmo banco que o spoke já abre. Este módulo dá leitura direta, tenant-scoped,
sem HTTP e sem réplica:

    from inventia_spoke_sdk.masterdata import MasterDataRepository

    repo = MasterDataRepository()
    async with session_for(principal) as session:
        emit = await repo.get_company(session, tenant_id=tid, company_id=cid)

Models são SOMENTE LEITURA (``ReadBase`` tem MetaData próprio — não inclua no
Alembic do spoke). Escrita do cadastro é exclusiva do master-data. Ver ADR 0004.
"""

from __future__ import annotations

from inventia_spoke_sdk.masterdata.models import Company, Product, ReadBase, UnitOfMeasure
from inventia_spoke_sdk.masterdata.repository import MasterDataRepository

__all__ = ["Company", "MasterDataRepository", "Product", "ReadBase", "UnitOfMeasure"]
