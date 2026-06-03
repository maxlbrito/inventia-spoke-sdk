# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] — 2026-06-02

Camada de enforcement das 5 camadas de isolamento (Fase 3 do
`plano-auth-keycloak`). Fecha a lacuna de segurança em que o `X-Tenant-Id`
não era cross-checado contra o token.

### Added

- **Cross-check de tenant (camada 4)** em `HubJWTValidator`: se o token traz
  claim de tenant (`active_tenant_id`/`tenant_id`) e um `tenant_id` é pedido,
  eles DEVEM bater — senão `TenantMismatch`. Flags `enforce_tenant_match`
  (default `True`) e `require_tenant_claim` (default `False`, para a transição
  HS256→Keycloak).
- **MCP / Resource Server discovery (Fase 5)** — `inventia_spoke_sdk.mcp`:
  `protected_resource_metadata` / `mount_protected_resource_metadata`
  (RFC 9728 `/.well-known/oauth-protected-resource`) e
  `protected_resource_challenge` (header `WWW-Authenticate` apontando para o
  metadata). O RS publica seu `aud` + AS(es) + escopos; o enforcement reusa as
  5 camadas.
- **Claim `scope` (string OIDC/Keycloak)** unido a `scopes` (lista, Hub legacy)
  em `SpokePrincipal.scopes` — o SDK valida tanto tokens HS256 do Hub quanto
  RS256 do Keycloak (Fase 1, AS canônico).
- **`SpokePrincipal.token_tenant_id`** (tenant do token) e **`company_ids`**
  (subconjunto de CNPJs permitidos dentro do tenant; vazio = todos).
  Helpers `company_allowed()` e `has_any_scope()`.
- **`inventia_spoke_sdk.enforcement`** (camadas 2 e 4b + erros padronizados):
  - `assert_scope` / `assert_any_scope` — escopo `recurso:ação`.
  - `assert_company_allowed` — filtro por CNPJ dentro do tenant.
  - `require_scope(scope, principal_dep)` — fábrica de dependency FastAPI.
  - `install_auth_exception_handlers(app)` — mapeia as exceções para
    `401 invalid_token`, `403 insufficient_scope`, `403 tenant_mismatch`,
    `403 company_not_allowed` com header `WWW-Authenticate: Bearer`.
- **Exceções de autorização (403):** `AuthorizationError`, `TenantMismatch`,
  `InsufficientScope`, `CompanyNotAllowed`.
- **`SET LOCAL app.current_tenant` (camada 5/RLS)**: `session_for` reaplica o
  GUC em toda transação via listener `after_begin`, com `is_local=true` (não
  vaza pela pool) e **só em PostgreSQL** (no-op em SQLite). Constante
  `inventia_spoke_sdk.db.TENANT_GUC`.

### Migração (spokes que adotarem v0.6.0)

- Chamar `install_auth_exception_handlers(app)` no startup — caso contrário
  `TenantMismatch`/`InsufficientScope`/`CompanyNotAllowed` viram 500.
- `validate_*` agora pode levantar `TenantMismatch` (403). Tratar via handler
  acima (ou capturar explicitamente).
- Declarar o escopo por endpoint com `require_scope("<recurso>:<ação>", require_principal)`.
- Garantir que o usuário de conexão do banco **não** tem `BYPASSRLS` e que as
  policies usam `current_setting('app.current_tenant', true)`.

## [0.5.0a1] — 2026-05-08 (alpha)

### Added

- **Tenant-aware session resolver** — `inventia_spoke_sdk.db.session_for(principal)` opens an `AsyncSession` bound to the principal's tenant. The spoke registers its own resolver via `configure_session_resolver(...)` at startup; the SDK only enforces the contract.
  - `SessionFactoryResolver` Protocol — async callable `principal → async_sessionmaker`.
  - `configure_session_resolver`, `get_session_resolver`, `reset_session_resolver`.
  - Replaces `_session_for(principal)` previously duplicated in every spoke.
- **`BaseService`** — common parent for spoke services shared by API handlers and arq jobs. Receives `AsyncSession` directly (no UoW wrapper — `AsyncSession` already implements Unit of Work). Exposes `tenant_id` and a `LoggerAdapter` with `tenant_id`/`user_id` attached.
- **`inventia_spoke_sdk.fastapi.session_dep_for(principal_dep)`** — builder for FastAPI dependencies that yield a session for the request's principal.
- **`inventia_spoke_sdk.arq.session_for_job(principal)`** — context manager for arq jobs.
- **Testing utilities (`inventia_spoke_sdk.testing`)**:
  - `create_rollback_session_factory(connection)` for rollback-per-test.
  - `install_test_resolver(factory)` to register a single-factory resolver.
  - `per_principal_resolver(by_tenant)` for cross-tenant isolation tests.

### Changed

- New runtime dependency: `sqlalchemy>=2.0`.
- New optional extras: `[fastapi]` (FastAPI helper) and `[testing]` (pytest + aiosqlite).

### Architectural note

The original v0.5.0 plan included `IUnitOfWork` + `SqlAlchemyUnitOfWork`. After review (RFC-001 §4.1 v2), **dropped**: `AsyncSession` from SQLAlchemy 2.0 already implements Unit of Work. Wrapping it would be cargo cult. The kernel that actually needs to live in the SDK is the **tenant-aware session resolver** plus a **base Service** with logging hooks — that is what this release delivers.

## [0.4.0] — 2026-04-27

### Added

- **Tier/role/policy claims** — `SpokePrincipal` ganha `tier`, `role`, `platform_role`, `policy` (subset do TierPolicy resolvida pelo Hub), `policy_version`, `acr`, `auth_time`, `amr` (RFC 8176). Consumidos do Hub JWT pós-merge das PRs central-hub#116 (TierPolicy) e #118 (claims enriquecidas).
- Helpers em `SpokePrincipal`:
  - `has_role(role)` — match exato de Membership role.
  - `has_platform_role(role)` — match de PlatformRole (platform_owner/admin/support).
  - `policy_get("limits.page_size_max", default=100)` — acesso dotted no policy claim, com fallback se claim ausente.

### Fixed

- **`audience=None` agora funciona corretamente** — `pyjwt` levanta "Invalid audience" se token tem `aud` mas validator passa `audience=None`. Adicionada flag `verify_aud=False` em options quando audience é None. (Hotfix descoberto durante integração SPA → KC.)

### Use cases

```python
from inventia_spoke_sdk import HubJWTValidator

validator = HubJWTValidator(jwks_url="https://auth.inventiaapp.com/realms/inventia/protocol/openid-connect/certs")
principal = validator.validate(token)

# Tier-aware quotas
limit = principal.policy_get("limits.page_size_max", default=100)

# RBAC
if not principal.has_role("admin"):
    raise PermissionDenied()

# Step-up auth: re-pedir credencial se não veio com WebAuthn
if principal.acr != "2":
    raise StepUpRequired()
```

### Compatibility

- `policy_version=2` é o formato emitido pelo Hub atual; spokes que receberem token com `policy_version` desconhecido devem tratar `policy` como opaco e ignorar.
- Campos novos são todos opcionais (`None` quando claim ausente). Tokens emitidos por versões antigas do Hub continuam funcionando.

## [0.3.0] — 2026-04-27

### Added

- **JWKS support (RS256)** — `HubJWTValidator(jwks_url=...)` valida tokens RSA usando chaves publicadas em endpoint JWKS. Necessário para integrar com **Keycloak** (que emite RS256 por padrão) e qualquer OIDC provider.
- **`JWKSFetcher`** classe pública: cache em memória com TTL configurável (default 1h), auto-refresh em `kid` desconhecido, persistência opcional em disco para resiliência (`cache_path` parameter), graceful degradation quando refresh falha (usa cache stale se disponível).
- Constructor agora exige **um dos**: `secret` (HS256, modo legado Hub) **ou** `jwks_url` (RS256, modo Keycloak/OIDC). Mutuamente exclusivos.

### Use cases

```python
# Modo legado (Hub HS256 — pré-Keycloak)
validator = HubJWTValidator(
    secret=settings.HUB_JWT_SECRET,
    issuer="central-hub",
)

# Modo Keycloak (RS256 + JWKS)
validator = HubJWTValidator(
    jwks_url="https://auth.inventia.com.br/realms/inventia/protocol/openid-connect/certs",
    issuer="https://auth.inventia.com.br/realms/inventia",
    required_token_type=None,  # KC não emite 'type' claim
    audience="hub-broker",     # client_id no realm
)

principal = validator.validate(kc_access_token)
```

### Robustez

- `JWKSFetcher` continua usando cache stale se KC ficar indisponível (graceful degradation).
- Cache em disco sobrevive a restart do pod do spoke (resiliência).
- Refresh automático em `kid` desconhecido (suporta rotação de chave do KC sem downtime).

### Tests

- 47 testes (era 29), coverage 95% (era 99% — caiu marginalmente porque JWKS é mais complexo).
- 11 novos testes em `test_jwks.py` (cache, TTL, refresh on unknown kid, disk persistence, graceful degradation, invalid response).
- 7 novos testes em `test_jwt_validator_jwks.py` (RS256 happy path, kid mismatch, signature mismatch, missing kid, constructor guards).

### Migration de v0.2.x → v0.3.0

Spokes que usam HS256 (modo Hub direto): **nada muda**, `secret=...` continua funcionando exatamente igual.

Spokes que vão consumir tokens do Keycloak (Hub broker pattern, M2):
```python
# antes (v0.2.x — não suportado para KC)
# (não há como — KC usa RS256, SDK só fazia HS256)

# agora (v0.3.0)
validator = HubJWTValidator(
    jwks_url="https://kc/realms/inventia/protocol/openid-connect/certs",
    issuer="https://kc/realms/inventia",
    required_token_type=None,
)
```

## [0.2.1] — 2026-04-26

### Changed

- **`HubJWTValidator.issuer` agora é opcional**, default `None` (não valida `iss`). Antes era `"central-hub"`. Razão: o Hub atual ainda não emite a claim `iss`, então o default rígido quebrava integração imediata.
- `issue_for_test()` agora só inclui `iss` na claim se o validator tiver `issuer` configurado.

### Migration de v0.2.0 → v0.2.1

Spokes que **explicitamente** passavam `issuer="central-hub"` continuam funcionando. Spokes que usavam o default agora **não validam `iss`** — o que mantém compatibilidade com o Hub atual.

Quando o Hub começar a emitir `iss=central-hub` (PR futuro), spokes podem voltar a passar `issuer="central-hub"` para defesa em profundidade.

## [0.2.0] — 2026-04-26

### Added

- **M2M client tokens.** `validate_client_token()` aceita tokens com `principal_type="client"` e `sub` como `client_id` (string, não UUID). Exige `account_id` na claim.
- **Auto-detect.** `validate_any()` despacha entre user/client conforme `principal_type`.
- **`tenant_id` no `SpokePrincipal`.** Vem do header `X-Tenant-Id` (não da claim — não há tenant na JWT por convenção do Hub). Passado como argumento opcional ao `validate*`.
- **`access_token` no `SpokePrincipal`.** JWT bruto preservado para forward ao Hub em handshakes (ex.: `GET /spoke/context/{tenant_id}`).
- **`required_token_type`** parâmetro do validator (default `"access"`). Exige claim `type` com valor correspondente — bloqueia uso acidental de refresh tokens.
- `SpokePrincipal` ganha `kind` (`"user"` | `"client"`), `client_id`, `is_user`, `is_client` properties.
- `__post_init__` valida coerência: `kind="user"` exige `user_id`; `kind="client"` exige `client_id`.

### Changed

- `validate()` continua funcionando como **alias** de `validate_user_token()` (compatibilidade com v0.1.0).
- Cobertura de testes: 99% (was 100%).

### Migration de v0.1.0 → v0.2.0

```python
# antes (v0.1.0)
principal = validator.validate(token)

# depois (v0.2.0) — equivalente
principal = validator.validate(token)              # alias
# ou explícito
principal = validator.validate_user_token(token)
# ou auto-detect (recomendado para spokes que aceitam M2M)
principal = validator.validate_any(token, tenant_id=tenant_uuid)
```

Spokes que recebem **apenas tokens de usuário** não precisam mudar nada além do bump de versão. Spokes M2M (com endpoints de cliente credential) devem migrar para `validate_any()`.

## [0.1.0] — 2026-04-26

### Added

- `HubJWTValidator` — decode + validate JWT HS256 emitido pelo Central Hub. Verifica `iss`, `aud` (opcional), `exp`, `sub` UUID, leeway configurável.
- `SpokePrincipal` — dataclass frozen com identidade do caller (`user_id`, `email`, `contract_id`, `account_id`, `scopes`, `is_super_admin`).
- Exception hierarchy: `SpokeSDKError`, `InvalidToken`, `JWKSError`, `HubUnreachable`.
- Helper `HubJWTValidator.issue_for_test()` para spokes forjarem tokens em testes unitários.
- CI: ruff + pytest com cov-fail-under=80 em Python 3.11 e 3.12.

### Notes

- API pública estável; qualquer mudança breaking exige bump major.
- Pareado com Central Hub v1.7+.
- Distribuição privada via git tag (não em PyPI público).
