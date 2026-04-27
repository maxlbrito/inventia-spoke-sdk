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
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError

from inventia_spoke_sdk.exceptions import InvalidToken
from inventia_spoke_sdk.principal import SpokePrincipal


@dataclass
class HubJWTValidator:
    """Valida JWT do Hub e retorna ``SpokePrincipal``.

    Args:
        secret: shared secret HS256 (mesmo segredo que o Hub assina).
        issuer: claim ``iss`` esperado (default ``"central-hub"``).
        audience: claim ``aud`` esperado, ou None para não checar.
        required_token_type: se não-None, exige claim ``type`` == valor
            (Hub usa ``"access"`` para tokens de acesso curto).
        leeway_seconds: tolerância de clock skew (default 30s).
        algorithm: algoritmo de assinatura (default ``"HS256"``).
    """

    secret: str
    issuer: str = "central-hub"
    audience: str | None = None
    required_token_type: str | None = "access"
    leeway_seconds: int = 30
    algorithm: str = "HS256"

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
        body = {
            "iss": self.issuer,
            "exp": int(time.time()) + exp_in,
            "iat": int(time.time()),
            **payload,
        }
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
