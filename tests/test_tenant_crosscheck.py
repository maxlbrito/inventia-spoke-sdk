"""v0.6.0 — cross-check de tenant (camada 4) + parsing de company_ids.

Cobre a correção do §1.6: token de um tenant não pode operar sobre outro só
porque o header/path pede outro.
"""

from __future__ import annotations

import time
from uuid import uuid4

import jwt as pyjwt
import pytest

from inventia_spoke_sdk import HubJWTValidator, TenantMismatch

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


def test_tenant_match_ok() -> None:
    v = HubJWTValidator(secret=SECRET)
    tenant = uuid4()
    token = _user_token({"active_tenant_id": str(tenant)})
    p = v.validate_any(token, tenant_id=tenant)
    assert p.tenant_id == tenant
    assert p.token_tenant_id == tenant


def test_tenant_mismatch_raises() -> None:
    v = HubJWTValidator(secret=SECRET)
    token = _user_token({"active_tenant_id": str(uuid4())})
    with pytest.raises(TenantMismatch):
        v.validate_any(token, tenant_id=uuid4())


def test_tenant_claim_via_plain_tenant_id_key() -> None:
    v = HubJWTValidator(secret=SECRET)
    tenant = uuid4()
    token = _user_token({"tenant_id": str(tenant)})
    p = v.validate_any(token, tenant_id=tenant)
    assert p.token_tenant_id == tenant


def test_missing_tenant_claim_allowed_by_default() -> None:
    """Transição HS256→KC: token sem claim de tenant não bloqueia (default)."""
    v = HubJWTValidator(secret=SECRET)
    tenant = uuid4()
    token = _user_token({})  # sem active_tenant_id
    p = v.validate_any(token, tenant_id=tenant)
    assert p.tenant_id == tenant
    assert p.token_tenant_id is None


def test_missing_tenant_claim_rejected_when_required() -> None:
    v = HubJWTValidator(secret=SECRET, require_tenant_claim=True)
    with pytest.raises(TenantMismatch):
        v.validate_any(_user_token({}), tenant_id=uuid4())


def test_enforce_disabled_skips_crosscheck() -> None:
    v = HubJWTValidator(secret=SECRET, enforce_tenant_match=False)
    token = _user_token({"active_tenant_id": str(uuid4())})
    p = v.validate_any(token, tenant_id=uuid4())  # diverge, mas não checa
    assert p.tenant_id is not None


def test_company_ids_parsed() -> None:
    v = HubJWTValidator(secret=SECRET)
    tenant = uuid4()
    c1, c2 = str(uuid4()), str(uuid4())
    token = _user_token({"active_tenant_id": str(tenant), "company_ids": [c1, c2]})
    p = v.validate_any(token, tenant_id=tenant)
    assert p.company_ids == (c1, c2)
    assert p.company_allowed(c1) is True
    assert p.company_allowed(uuid4()) is False


def test_no_company_ids_means_all_allowed() -> None:
    v = HubJWTValidator(secret=SECRET)
    p = v.validate_any(_user_token({}), tenant_id=uuid4())
    assert p.company_ids == ()
    assert p.company_allowed(uuid4()) is True


def test_client_token_crosscheck() -> None:
    v = HubJWTValidator(secret=SECRET)
    tenant = uuid4()
    token = _user_token(
        {
            "sub": "client-abc",
            "principal_type": "client",
            "account_id": str(uuid4()),
            "active_tenant_id": str(uuid4()),  # diverge
        }
    )
    with pytest.raises(TenantMismatch):
        v.validate_any(token, tenant_id=tenant)
