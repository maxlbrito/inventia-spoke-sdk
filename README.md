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

### OpenTelemetry distribuído (v0.5.0a2+)

Helpers opcionais para tracing distribuído. Instale com `inventia-spoke-sdk[otel]` para puxar as dependências; sem elas, todos os helpers são no-op silencioso (você pode decorar livremente).

```python
# 1. inicializar no startup (FastAPI lifespan / arq on_startup)
from inventia_spoke_sdk.telemetry import setup_otel

setup_otel(
    service_name="master-data-api",
    environment="production",
    # otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    # sample_rate=0.1,
)
```

```python
# 2. decorar métodos de Service
from inventia_spoke_sdk.telemetry import traced

class CompanyService(BaseService):
    @traced()
    async def upsert(self, payload):
        # span "CompanyService.upsert" com tenant_id/user_id anexos
        ...
```

```python
# 3. propagar trace pela fila arq
from inventia_spoke_sdk.telemetry import enqueue_with_trace, traced_arq_job

# API enfileira:
await enqueue_with_trace(pool, "run_companies_import", str(job_id), tenant_id, token)

# Worker processa: o decorator extrai o traceparent injetado e abre span filho
@traced_arq_job
async def run_companies_import(ctx, job_id, tenant_id, access_token, **kwargs):
    ...
```

Resultado: trace_id único do clique no FE → endpoint API → enqueue → worker → SEFAZ outbound, visível em qualquer backend OTEL (Tempo, Jaeger, Honeycomb).

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
