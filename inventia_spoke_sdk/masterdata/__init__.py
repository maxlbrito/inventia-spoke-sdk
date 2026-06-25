"""Acesso de leitura ao cadastro do master-data no banco compartilhado.

Na topologia da casa (1 Account = 1 banco), o cadastro do master-data vive no
mesmo banco que o spoke já abre. Este módulo dá leitura direta, tenant-scoped,
sem HTTP e sem réplica:

    from inventia_spoke_sdk.masterdata import MasterDataRepository

    repo = MasterDataRepository()
    async with session_for(principal) as session:
        emit = await repo.get_company(session, tenant_id=tid, company_id=cid)
        dest = await repo.get_participant_by_cnpj(session, tenant_id=tid, cnpj=cnpj)
        un = await repo.get_unit(session, tenant_id=tid, unit_code="UN")
        muni = await repo.get_municipality(session, ibge_code="3550308")

Models são SOMENTE LEITURA (``ReadBase`` tem MetaData próprio — não inclua no
Alembic do spoke). Escrita do cadastro é exclusiva do master-data. Ver ADR 0004.
A guarda de drift (``assert_no_drift``) é chamada pela CI do master-data.
"""

from __future__ import annotations

from inventia_spoke_sdk.masterdata.crypto import (
    CertificateDecryptError,
    CertificateKeyMissing,
)
from inventia_spoke_sdk.masterdata.drift import (
    SchemaDriftError,
    assert_no_drift,
    check_models_against,
)
from inventia_spoke_sdk.masterdata.models import (
    Certificate,
    CertificateKey,
    CnaeCode,
    Company,
    IbgeMunicipality,
    OperationNature,
    Participant,
    Product,
    ReadBase,
    UnitOfMeasure,
)
from inventia_spoke_sdk.masterdata.repository import (
    SYSTEM_TENANT_ID,
    CertificateMaterial,
    MasterDataRepository,
)

__all__ = [
    "SYSTEM_TENANT_ID",
    "Certificate",
    "CertificateDecryptError",
    "CertificateKey",
    "CertificateKeyMissing",
    "CertificateMaterial",
    "CnaeCode",
    "Company",
    "IbgeMunicipality",
    "MasterDataRepository",
    "OperationNature",
    "Participant",
    "Product",
    "ReadBase",
    "SchemaDriftError",
    "UnitOfMeasure",
    "assert_no_drift",
    "check_models_against",
]
