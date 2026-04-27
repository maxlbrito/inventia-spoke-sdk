"""HubJWTValidator — valida JWT emitido pelo Central Hub.

v0.1.0 (M1) suporta apenas HS256 com shared secret (modelo atual do
Hub). Em v0.3+ (M3) adicionamos RS256/JWKS conforme o Hub evolui o
modelo de assinatura.

Uso típico em spoke FastAPI:

    from inventia_spoke_sdk import HubJWTValidator

    validator = HubJWTValidator(
        secret=settings.JWT_SECRET,
        issuer="central-hub",
        audience="master-data",
    )

    principal = validator.validate(token)
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

    - ``secret``: shared secret HS256 (mesmo segredo que o Hub assina).
    - ``issuer``: claim ``iss`` esperado (default: ``"central-hub"``).
    - ``audience``: claim ``aud`` esperado, ou None para não checar.
    - ``leeway_seconds``: tolerância de clock skew (default 30s).
    """

    secret: str
    issuer: str = "central-hub"
    audience: str | None = None
    leeway_seconds: int = 30

    def validate(self, token: str) -> SpokePrincipal:
        if not token:
            raise InvalidToken("empty token")

        options: dict[str, Any] = {"require": ["exp", "sub"]}
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway_seconds,
                options=options,
            )
        except InvalidTokenError as exc:  # JWT lib superclass
            raise InvalidToken(str(exc)) from exc

        # Cross-check: sub must parse to UUID.
        try:
            user_id = UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise InvalidToken(f"invalid sub claim: {exc}") from exc

        contract_id = _maybe_uuid(payload.get("active_contract_id") or payload.get("contract_id"))
        account_id = _maybe_uuid(payload.get("active_account_id") or payload.get("account_id"))

        scopes_raw = payload.get("scopes") or []
        if not isinstance(scopes_raw, (list, tuple)):
            raise InvalidToken("scopes must be a list")
        scopes = tuple(str(s) for s in scopes_raw)

        return SpokePrincipal(
            user_id=user_id,
            email=payload.get("email"),
            contract_id=contract_id,
            account_id=account_id,
            scopes=scopes,
            is_super_admin=bool(payload.get("is_super_admin", False)),
        )

    # Helper used by tests to forge tokens.
    def issue_for_test(self, payload: dict[str, Any], exp_in: int = 60) -> str:
        body = {
            "iss": self.issuer,
            "exp": int(time.time()) + exp_in,
            "iat": int(time.time()),
            **payload,
        }
        if self.audience and "aud" not in body:
            body["aud"] = self.audience
        return jwt.encode(body, self.secret, algorithm="HS256")


def _maybe_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        raise InvalidToken(f"invalid UUID claim: {value!r}") from None
