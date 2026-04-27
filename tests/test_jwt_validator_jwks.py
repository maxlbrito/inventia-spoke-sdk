"""HubJWTValidator com JWKS / RS256 — integração com Keycloak."""

from __future__ import annotations

import time
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from inventia_spoke_sdk import HubJWTValidator, InvalidToken


def _generate_rsa_keypair():
    """Gera par RSA + JWK pública para testes."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    # PEM keys
    pem_priv = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # JWK do public key (formato KC)
    public_numbers = public_key.public_numbers()
    import base64

    def b64u(n: int) -> str:
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    jwk = {
        "kid": "test-key-1",
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": b64u(public_numbers.n),
        "e": b64u(public_numbers.e),
    }
    return pem_priv, jwk


def _sign_token(payload: dict, pem_priv: bytes, kid: str) -> str:
    return jwt.encode(payload, pem_priv, algorithm="RS256", headers={"kid": kid})


class _FakeJWKSResponse:
    def __init__(self, jwk: dict) -> None:
        self._jwk = jwk
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"keys": [self._jwk]}


def test_validator_validates_rs256_via_jwks() -> None:
    priv, jwk = _generate_rsa_keypair()
    user_id = uuid4()
    token = _sign_token(
        {
            "iss": "https://kc/realms/inventia",
            "sub": str(user_id),
            "exp": int(time.time()) + 60,
            "iat": int(time.time()),
            "type": "Bearer",
            "email": "user@inventia.com.br",
        },
        priv,
        jwk["kid"],
    )

    v = HubJWTValidator(
        jwks_url="https://kc/realms/inventia/protocol/openid-connect/certs",
        issuer="https://kc/realms/inventia",
        required_token_type="Bearer",
    )

    with patch("httpx.get", return_value=_FakeJWKSResponse(jwk)):
        principal = v.validate(token)

    assert principal.user_id == user_id
    assert principal.email == "user@inventia.com.br"


def test_validator_rejects_token_with_unknown_kid() -> None:
    priv, jwk = _generate_rsa_keypair()
    token = _sign_token(
        {
            "iss": "https://kc/realms/inventia",
            "sub": str(uuid4()),
            "exp": int(time.time()) + 60,
            "type": "Bearer",
        },
        priv,
        "wrong-kid",  # kid no header não bate com o JWK
    )

    v = HubJWTValidator(
        jwks_url="https://kc/realms/inventia/protocol/openid-connect/certs",
        issuer="https://kc/realms/inventia",
        required_token_type="Bearer",
    )

    with patch("httpx.get", return_value=_FakeJWKSResponse(jwk)):
        with pytest.raises(InvalidToken, match="JWKS lookup failed"):
            v.validate(token)


def test_validator_rejects_token_signed_by_other_key() -> None:
    priv1, jwk1 = _generate_rsa_keypair()
    priv2, jwk2 = _generate_rsa_keypair()
    # Token assinado com priv1 mas JWKS publica jwk2
    jwk1_id_with_jwk2_n = {**jwk1, "n": jwk2["n"], "e": jwk2["e"]}

    token = _sign_token(
        {
            "iss": "https://kc/realms/inventia",
            "sub": str(uuid4()),
            "exp": int(time.time()) + 60,
            "type": "Bearer",
        },
        priv1,
        jwk1_id_with_jwk2_n["kid"],
    )

    v = HubJWTValidator(
        jwks_url="https://kc/realms/inventia/protocol/openid-connect/certs",
        issuer="https://kc/realms/inventia",
        required_token_type="Bearer",
    )

    with patch("httpx.get", return_value=_FakeJWKSResponse(jwk1_id_with_jwk2_n)):
        with pytest.raises(InvalidToken):
            v.validate(token)


def test_validator_token_without_kid_rejected() -> None:
    priv, jwk = _generate_rsa_keypair()
    # Token RS256 sem kid no header
    token = jwt.encode(
        {
            "iss": "https://kc/realms/inventia",
            "sub": str(uuid4()),
            "exp": int(time.time()) + 60,
            "type": "Bearer",
        },
        priv,
        algorithm="RS256",
        # No headers={'kid': ...}
    )

    v = HubJWTValidator(
        jwks_url="https://kc/realms/inventia/protocol/openid-connect/certs",
        issuer="https://kc/realms/inventia",
        required_token_type="Bearer",
    )

    with pytest.raises(InvalidToken, match="missing kid"):
        v.validate(token)


def test_validator_constructor_requires_secret_or_jwks_url() -> None:
    with pytest.raises(ValueError, match="must provide secret"):
        HubJWTValidator()


def test_validator_constructor_rejects_both_secret_and_jwks() -> None:
    with pytest.raises(ValueError, match="not both"):
        HubJWTValidator(secret="x", jwks_url="https://kc")


def test_validator_jwks_no_token_type_required() -> None:
    """KC tokens não têm 'type' claim; deve aceitar com required_token_type=None."""
    priv, jwk = _generate_rsa_keypair()
    user_id = uuid4()
    token = _sign_token(
        {
            "iss": "https://kc/realms/inventia",
            "sub": str(user_id),
            "exp": int(time.time()) + 60,
        },
        priv,
        jwk["kid"],
    )

    v = HubJWTValidator(
        jwks_url="https://kc/realms/inventia/protocol/openid-connect/certs",
        issuer="https://kc/realms/inventia",
        required_token_type=None,  # KC não emite 'type'
    )

    with patch("httpx.get", return_value=_FakeJWKSResponse(jwk)):
        principal = v.validate(token)
    assert principal.user_id == user_id
