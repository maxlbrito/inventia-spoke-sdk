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
