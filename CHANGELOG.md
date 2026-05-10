# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0a2] — 2026-05-09 (alpha)

### Added — OpenTelemetry helpers (RFC-001 §4.2, issue #4)

- **`inventia_spoke_sdk.telemetry.setup_otel(...)`** — idempotent process-wide initialisation. Reads sane defaults from `OTEL_*` env vars; explicit kwargs win. Auto-instruments FastAPI, httpx and SQLAlchemy when their instrumentation packages are available. `shutdown_otel()` flushes and resets state (test/graceful-stop helper).
- **`inventia_spoke_sdk.telemetry.traced`** — decorator for `BaseService` methods. Opens a span named `<ClassName>.<method>`, attaches `inventia.tenant_id` / `inventia.user_id` / `inventia.client_id` from `self.principal`, records exceptions and marks span error on raise. Works with sync and async methods.
- **`inventia_spoke_sdk.telemetry.enqueue_with_trace(pool, fn_name, *args, **kwargs)`** — drop-in replacement for `pool.enqueue_job` that injects the W3C `traceparent` (and `tracestate`) into a reserved `_otel_carrier` kwarg.
- **`inventia_spoke_sdk.telemetry.traced_arq_job`** — decorator for arq job functions that pops `_otel_carrier`, restores the OTEL context, and runs the body inside an `arq.job <name>` span. Together with `enqueue_with_trace`, the parent's `trace_id` propagates across the Redis queue boundary unchanged.

### Changed

- New optional extra: `[otel]` — `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, plus FastAPI/httpx/SQLAlchemy instrumentations. Telemetry helpers no-op silently when this extra is not installed, so spokes can decorate services and replace `pool.enqueue_job` calls without paying anything until they opt in.

### Tests

- 10 new tests in `tests/test_telemetry.py` covering both code paths:
  - Without OTEL extra (HAS_OTEL=False) → every helper is a passthrough.
  - With OTEL active → `@traced` creates the right span + attrs, exceptions are recorded, `enqueue_with_trace` injects `traceparent`, end-to-end propagation preserves `trace_id` across queue.
- Full suite: 83 passed (was 73), CI green on 3.11 + 3.12.

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
