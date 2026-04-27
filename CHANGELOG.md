# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
