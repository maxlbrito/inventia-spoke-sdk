# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
