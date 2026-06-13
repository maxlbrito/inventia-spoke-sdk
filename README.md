# inventia-spoke-sdk

> SDK Python compartilhado pelos **Spokes** da plataforma Inventia (master-data, fiscal, fiscal-sped, agente-fiscal, ...). Encapsula validação de JWT do Central Hub, definição do `SpokePrincipal` e utilitários compartilhados.

## Status

- **Versão:** v0.1.0 (M1 — fundação de identidade)
- **Pareado com:** Central Hub v1.7+
- **Estabilidade:** API pública estável; mudança de major bump em qualquer breaking change.

## Instalação

Distribuição privada (não em PyPI público). Pin via git tag:

```toml
# pyproject.toml do spoke
[project]
dependencies = [
    "inventia-spoke-sdk @ git+https://github.com/maxlbrito/inventia-spoke-sdk.git@v0.1.0",
]
```

## Uso

### Validar JWT do Hub e obter SpokePrincipal

```python
from inventia_spoke_sdk import HubJWTValidator, InvalidToken, SpokePrincipal

validator = HubJWTValidator(
    secret=settings.JWT_SECRET,        # mesmo segredo HS256 que o Hub assina
    issuer="central-hub",
    audience="master-data",            # opcional
)

try:
    principal: SpokePrincipal = validator.validate(token)
except InvalidToken:
    raise HTTPException(401)

# principal.user_id, principal.contract_id, principal.account_id, principal.scopes
```

### FastAPI dependency

```python
from fastapi import Depends, HTTPException, status
from inventia_spoke_sdk import HubJWTValidator, InvalidToken, SpokePrincipal

validator = HubJWTValidator(secret=..., issuer="central-hub", audience="master-data")

async def get_principal(authorization: str = Header(...)) -> SpokePrincipal:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return validator.validate(token)
    except InvalidToken as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
```

### Camada de sessão e Service (v0.5.0+)

`AsyncSession` do SQLAlchemy 2.0 **já é** um Unit of Work — o SDK não embrulha. O que padronizamos é (1) o resolver tenant-aware e (2) a base de Service que API e Worker compartilham.

```python
# 1. registrar resolver no startup do spoke
from inventia_spoke_sdk import configure_session_resolver
from app.db_pool import ensure_schema, get_engine
from app.hub_client import fetch_spoke_context

async def my_resolver(principal):
    ctx = await fetch_spoke_context(principal.access_token, str(principal.tenant_id))
    await ensure_schema(ctx.account_id, ctx.db_url)
    return (await get_engine(ctx.account_id, ctx.db_url)).session_factory

configure_session_resolver(my_resolver)
```

```python
# 2. Service compartilhado por API e Worker
from inventia_spoke_sdk import BaseService

class CompanyService(BaseService):
    async def upsert(self, payload: CompanyDTO) -> Company:
        # validação + persistência
        ...
```

```python
# 3a. Controller fino
from inventia_spoke_sdk.fastapi import session_dep_for
db_session = session_dep_for(require_write)

@router.post("/companies")
async def create(
    payload: CompanyDTO,
    session: AsyncSession = Depends(db_session),
    principal: SpokePrincipal = Depends(require_write),
):
    return await CompanyService(session, principal).upsert(payload)
```

```python
# 3b. Worker chama o mesmo Service
from inventia_spoke_sdk.arq import session_for_job

async def run_companies_import(ctx, job_id, tenant_id, access_token):
    principal = SpokePrincipal(...)
    async with session_for_job(principal) as session:
        await CompanyService(session, principal).process_import(job_id)
```

Para testes, ver `inventia_spoke_sdk.testing` (rollback-per-test e cross-tenant resolver).

### Cadastro do master-data (leitura compartilhada)

Na topologia da casa (1 Account = 1 banco), o cadastro do master-data
(`companies`, `products`, `units_of_measure`, `participants`, `certificates` e
referências IBGE/CNAE) vive no **mesmo banco** que o spoke já abre. O SDK dá
leitura direta, tenant-scoped, **sem HTTP e sem réplica** — então a queda do
serviço HTTP do master-data não derruba a leitura. Ver ADR 0004.

```python
from inventia_spoke_sdk import session_for
from inventia_spoke_sdk.masterdata import MasterDataRepository

repo = MasterDataRepository()
async with session_for(principal) as session:
    emit = await repo.get_company(session, tenant_id=tid, company_id=cid)
    dest = await repo.get_participant_by_cnpj(session, tenant_id=tid, cnpj=cnpj)
    prods = await repo.list_products_by_codes(session, tenant_id=tid, codes=codes)
    un = await repo.get_unit(session, tenant_id=tid, unit_code="UN")
    muni = await repo.get_municipality(session, ibge_code="3550308")  # global
```

Regras: **somente leitura** (escrita do cadastro é exclusiva do master-data);
toda query por-tenant filtra `tenant_id`; **não** inclua `ReadBase.metadata` no
Alembic do spoke (as tabelas pertencem ao master-data). A CI do master-data
chama `masterdata.assert_no_drift(schema)` para travar drift de schema.

## API pública (v0.1.0)

| Símbolo | Descrição |
|---|---|
| `HubJWTValidator` | Decode + validate JWT (HS256) emitido pelo Hub. |
| `SpokePrincipal` | Dataclass frozen com `user_id`, `email`, `contract_id`, `account_id`, `scopes`, `is_super_admin`. |
| `SpokeSDKError` | Base exception. |
| `InvalidToken` | JWT inválido (sub, exp, signature, iss, aud, formato). |
| `JWKSError`, `HubUnreachable` | Reservadas para v0.3+ (RS256/JWKS). |

## Roadmap

| Versão | Conteúdo | Marco |
|---|---|---|
| 0.1.0 | JWT HS256 + SpokePrincipal minimal | M1 |
| 0.2.0 | `SpokePrincipal.tier`/`role`/`policy`; `enforce_page_size`; `report_usage` helper | M3 + M7 |
| 0.3.0 | RS256/JWKS + cache em disco + offline fallback | M5 (Hub HA) |
| 0.4.0 | Audit client + decoradores `@require_role`, `@require_scope` | M3+ |

## Desenvolvimento

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -q
```

## Licença

Proprietary — Inventia. Uso restrito a Spokes Inventia.
