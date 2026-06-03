"""v0.6.0 Fase 6 — MultiValidator (dual-validate Hub HS256 + Keycloak RS256)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from inventia_spoke_sdk import HubJWTValidator, InvalidToken, MultiValidator, TenantMismatch

# Simula dois emissores (Hub e Keycloak) via dois secrets/iss/aud distintos.
HUB = HubJWTValidator(secret="hub-secret", issuer="inventia-hub", audience="inventia-spokes")
KC = HubJWTValidator(secret="kc-secret", issuer="kc-realm", audience="https://api.x")


def test_requires_at_least_one():
    with pytest.raises(ValueError):
        MultiValidator([])


def test_accepts_token_from_first_issuer():
    tid = uuid4()
    tok = HUB.issue_for_test({"sub": str(uuid4()), "active_tenant_id": str(tid)})
    mv = MultiValidator([HUB, KC])
    p = mv.validate_any(tok, tenant_id=tid)
    assert p.tenant_id == tid


def test_falls_back_to_second_issuer():
    tid = uuid4()
    # Token emitido pelo KC; o validador HUB deve falhar (InvalidToken) e o
    # MultiValidator cair no KC.
    tok = KC.issue_for_test({"sub": str(uuid4()), "active_tenant_id": str(tid)})
    mv = MultiValidator([HUB, KC])
    p = mv.validate_any(tok, tenant_id=tid)
    assert p.token_tenant_id == tid


def test_rejects_token_from_no_issuer():
    other = HubJWTValidator(secret="stranger", issuer="x", audience="y")
    tok = other.issue_for_test({"sub": str(uuid4())})
    mv = MultiValidator([HUB, KC])
    with pytest.raises(InvalidToken):
        mv.validate_any(tok, tenant_id=uuid4())


def test_tenant_mismatch_propagates_not_retried():
    # Token válido pelo HUB mas tenant pedido diverge → TenantMismatch DEFINITIVO,
    # não deve "passar" tentando o KC.
    tok = HUB.issue_for_test({"sub": str(uuid4()), "active_tenant_id": str(uuid4())})
    mv = MultiValidator([HUB, KC])
    with pytest.raises(TenantMismatch):
        mv.validate_any(tok, tenant_id=uuid4())
