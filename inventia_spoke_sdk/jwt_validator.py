"""HubJWTValidator — valida JWT emitido pelo Central Hub.

v0.2.0 suporta tokens **user** e **client** (M2M). Auto-detect via
claim ``principal_type`` ou método explícito.

v0.1.0 → v0.2.0:
    - novo método ``validate_user_token``, ``validate_client_token``,
      ``validate_any``.
    - parâmetro ``required_token_type`` (default "access").
    - ``validate`` continua funcionando como alias para
      ``validate_user_token`` (compatibilidade).

Uso:

    validator = HubJWTValidator(
        secret=settings.HUB_JWT_SECRET,
        issuer="central-hub",
        audience="master-data",         # opcional
        required_token_type="access",   # exige claim type=access
    )

    # auto-detect via principal_type:
    principal = validator.validate_any(token, tenant_id=tenant)

    # ou explícito:
    principal = validator.validate_user_token(token, tenant_id=tenant)
    principal = validator.validate_client_token(token, tenant_id=tenant)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import jwt
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidTokenError

from inventia_spoke_sdk.exceptions import InvalidToken
from inventia_spoke_sdk.jwks import JWKSFetcher
from inventia_spoke_sdk.principal import SpokePrincipal


@dataclass
class HubJWTValidator:
    """Valida JWT (Hub HS256 OU Keycloak RS256) e retorna ``SpokePrincipal``.

    Modos suportados:

    - **HS256 (legacy / Hub direct)**: passar ``secret``. Algoritmo HS256.
    - **RS256 + JWKS (Keycloak / OIDC)**: passar ``jwks_url``. Algoritmo
      RS256 (ou outros publicados no JWKS — KC usa RS256). Cache JWKS
      com TTL configurável + auto-refresh em ``kid`` desconhecido.

    Args:
        secret: shared secret HS256. Mutuamente exclusivo com jwks_url.
        jwks_url: URL do JWKS (RS256). Mutuamente exclusivo com secret.
        issuer: claim ``iss`` esperado, ou None para não checar.
        audience: claim ``aud`` esperado, ou None para não checar.
        required_token_type: se não-None, exige claim ``type`` == valor
            (Hub legacy usa ``"access"``; KC tokens NÃO têm essa claim).
        leeway_seconds: tolerância de clock skew (default 30s).
        algorithm: algoritmo (default HS256). Em modo JWKS é determinado
            pelo header ``alg`` do token (validado contra os algoritmos
            suportados no JWKS).
        jwks_ttl_seconds: TTL do cache JWKS (default 3600).
        jwks_cache_path: caminho de disco opcional para cache JWKS.
    """

    secret: str | None = None
    jwks_url: str | None = None
    issuer: str | None = None
    audience: str | None = None
    required_token_type: str | None = "access"
    leeway_seconds: int = 30
    algorithm: str = "HS256"
    jwks_ttl_seconds: int = 3600
    jwks_cache_path: Any = None  # Path | None — Any to avoid Pydantic-style type strictness

    _jwks: JWKSFetcher | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.secret is None and self.jwks_url is None:
            raise ValueError("must provide secret (HS256) or jwks_url (RS256)")
        if self.secret is not None and self.jwks_url is not None:
            raise ValueError("provide either secret or jwks_url, not both")
        if self.jwks_url:
            self._jwks = JWKSFetcher(
                jwks_url=self.jwks_url,
                ttl_seconds=self.jwks_ttl_seconds,
                cache_path=self.jwks_cache_path,
            )

    # ---- public API -------------------------------------------------------

    def validate(self, token: str, *, tenant_id: UUID | None = None) -> SpokePrincipal:
        """Backwards-compat alias for ``validate_user_token``."""
        return self.validate_user_token(token, tenant_id=tenant_id)

    def validate_user_token(self, token: str, *, tenant_id: UUID | None = None) -> SpokePrincipal:
        """Valida token de usuário (sub deve ser UUID)."""
        payload = self._decode(token)
        if payload.get("principal_type") == "client":
            raise InvalidToken("expected user token, got client token")
        return self._principal_from_user_payload(payload, token, tenant_id)

    def validate_client_token(self, token: str, *, tenant_id: UUID | None = None) -> SpokePrincipal:
        """Valida token M2M (principal_type=client; sub é client_id)."""
        payload = self._decode(token)
        if payload.get("principal_type") != "client":
            raise InvalidToken("expected client token, got user token")
        return self._principal_from_client_payload(payload, token, tenant_id)

    def validate_any(self, token: str, *, tenant_id: UUID | None = None) -> SpokePrincipal:
        """Valida qualquer tipo (auto-detect via ``principal_type``)."""
        payload = self._decode(token)
        if payload.get("principal_type") == "client":
            return self._principal_from_client_payload(payload, token, tenant_id)
        return self._principal_from_user_payload(payload, token, tenant_id)

    # ---- helpers ----------------------------------------------------------

    def issue_for_test(self, payload: dict[str, Any], exp_in: int = 60) -> str:
        """Forge a token for spoke tests. Defaults type="access" if absent."""
        body: dict[str, Any] = {
            "exp": int(time.time()) + exp_in,
            "iat": int(time.time()),
            **payload,
        }
        if self.issuer and "iss" not in body:
            body["iss"] = self.issuer
        if self.audience and "aud" not in body:
            body["aud"] = self.audience
        if self.required_token_type and "type" not in body:
            body["type"] = self.required_token_type
        return jwt.encode(body, self.secret, algorithm=self.algorithm)

    # ---- internals --------------------------------------------------------

    def _decode(self, token: str) -> dict[str, Any]:
        if not token:
            raise InvalidToken("empty token")
        options: dict[str, Any] = {"require": ["exp", "sub"]}

        # JWKS path (RS256, KC tokens).
        if self._jwks is not None:
            try:
                header = jwt.get_unverified_header(token)
            except InvalidTokenError as exc:
                raise InvalidToken(f"malformed token header: {exc}") from exc
            kid = header.get("kid")
            if not kid:
                raise InvalidToken("token missing kid (required for JWKS)")
            try:
                jwk = self._jwks.get_key(kid)
            except Exception as exc:
                raise InvalidToken(f"JWKS lookup failed: {exc}") from exc
            try:
                key = RSAAlgorithm.from_jwk(jwk)
            except Exception as exc:
                raise InvalidToken(f"invalid JWK for kid={kid}: {exc}") from exc
            try:
                payload = jwt.decode(
                    token,
                    key,
                    algorithms=[header.get("alg", "RS256")],
                    issuer=self.issuer,
                    audience=self.audience,
                    leeway=self.leeway_seconds,
                    options=options,
                )
            except InvalidTokenError as exc:
                raise InvalidToken(str(exc)) from exc
            if self.required_token_type is not None:
                actual = payload.get("type")
                if actual != self.required_token_type:
                    raise InvalidToken(
                        f"wrong token type: expected {self.required_token_type!r}, got {actual!r}"
                    )
            return payload

        # HS256 path (legacy Hub).
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway_seconds,
                options=options,
            )
        except InvalidTokenError as exc:
            raise InvalidToken(str(exc)) from exc

        if self.required_token_type is not None:
            actual = payload.get("type")
            if actual != self.required_token_type:
                raise InvalidToken(
                    f"wrong token type: expected {self.required_token_type!r}, got {actual!r}"
                )
        return payload

    def _principal_from_user_payload(
        self,
        payload: dict[str, Any],
        token: str,
        tenant_id: UUID | None,
    ) -> SpokePrincipal:
        try:
            user_id = UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise InvalidToken(f"invalid sub claim: {exc}") from exc

        return SpokePrincipal(
            kind="user",
            user_id=user_id,
            email=payload.get("email"),
            contract_id=_maybe_uuid(
                payload.get("active_contract_id") or payload.get("contract_id")
            ),
            account_id=_maybe_uuid(payload.get("active_account_id") or payload.get("account_id")),
            tenant_id=tenant_id,
            scopes=_parse_scopes(payload.get("scopes")),
            is_super_admin=bool(payload.get("is_super_admin", False)),
            access_token=token,
        )

    def _principal_from_client_payload(
        self,
        payload: dict[str, Any],
        token: str,
        tenant_id: UUID | None,
    ) -> SpokePrincipal:
        client_id = payload.get("sub")
        if not client_id or not isinstance(client_id, str):
            raise InvalidToken("client token missing sub (client_id)")

        try:
            account_id = UUID(payload["account_id"])
        except (KeyError, ValueError) as exc:
            raise InvalidToken(f"client token missing account_id claim: {exc}") from exc

        return SpokePrincipal(
            kind="client",
            client_id=client_id,
            account_id=account_id,
            contract_id=_maybe_uuid(
                payload.get("active_contract_id") or payload.get("contract_id")
            ),
            tenant_id=tenant_id,
            scopes=_parse_scopes(payload.get("scopes")),
            access_token=token,
        )


def _maybe_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        raise InvalidToken(f"invalid UUID claim: {value!r}") from None


def _parse_scopes(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise InvalidToken("scopes must be a list")
    return tuple(str(s) for s in raw)
