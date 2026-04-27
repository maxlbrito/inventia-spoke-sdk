"""HubJWTValidator v0.4.0 — populates tier/role/policy from claims."""

from __future__ import annotations

import time
from uuid import uuid4

import jwt as pyjwt

from inventia_spoke_sdk import HubJWTValidator


SECRET = "test-secret"


def _user_token(claims: dict) -> str:
    payload = {
        "sub": claims.pop("sub", str(uuid4())),
        "type": "access",
        "exp": int(time.time()) + 60,
        "iat": int(time.time()),
        **claims,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def test_validate_populates_v04_user_claims():
    v = HubJWTValidator(secret=SECRET)
    token = _user_token(
        {
            "active_contract_id": str(uuid4()),
            "active_account_id": str(uuid4()),
            "tier": 2,
            "role": "admin",
            "scopes": ["master-data"],
            "platform_role": "platform_support",
            "policy": {"limits": {"page_size_max": 100}, "mfa": {"required": True}},
            "policy_version": 2,
            "acr": "1",
            "auth_time": 1735000000,
            "amr": ["pwd", "totp"],
        }
    )
    p = v.validate(token)
    assert p.kind == "user"
    assert p.tier == 2
    assert p.role == "admin"
    assert p.platform_role == "platform_support"
    assert p.policy["limits"]["page_size_max"] == 100
    assert p.policy_version == 2
    assert p.acr == "1"
    assert p.auth_time == 1735000000
    assert p.amr == ("pwd", "totp")


def test_validate_legacy_token_without_v04_claims():
    """Token sem novos claims (Hub antigo) → todos os campos ficam None/()."""
    v = HubJWTValidator(secret=SECRET)
    token = _user_token({"scopes": ["master-data"]})
    p = v.validate(token)
    assert p.tier is None
    assert p.role is None
    assert p.policy is None
    assert p.policy_version is None
    assert p.amr == ()


def test_validate_rejects_bad_int_tier():
    """tier não-numérico no claim levanta InvalidToken."""
    from inventia_spoke_sdk import InvalidToken

    v = HubJWTValidator(secret=SECRET)
    token = _user_token({"tier": "not-a-number"})
    try:
        v.validate(token)
    except InvalidToken:
        return
    raise AssertionError("expected InvalidToken for non-int tier")


def test_validate_rejects_bad_dict_policy():
    from inventia_spoke_sdk import InvalidToken

    v = HubJWTValidator(secret=SECRET)
    token = _user_token({"policy": "not-a-dict"})
    try:
        v.validate(token)
    except InvalidToken:
        return
    raise AssertionError("expected InvalidToken for non-dict policy")


def test_audience_none_does_not_raise_when_token_has_aud():
    """Hotfix v0.4.0 — audience=None com token contendo aud não deve falhar."""
    v = HubJWTValidator(secret=SECRET)  # audience=None
    payload = {
        "sub": str(uuid4()),
        "type": "access",
        "aud": "some-audience",
        "exp": int(time.time()) + 60,
        "iat": int(time.time()),
    }
    token = pyjwt.encode(payload, SECRET, algorithm="HS256")
    p = v.validate(token)
    assert p.user_id is not None  # sucesso = sem InvalidToken
