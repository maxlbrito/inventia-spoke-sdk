"""SpokePrincipal — tests for v0.1.0 minimal surface."""

from __future__ import annotations

from uuid import uuid4

from inventia_spoke_sdk import SpokePrincipal


def test_principal_defaults() -> None:
    user_id = uuid4()
    p = SpokePrincipal(user_id=user_id)
    assert p.user_id == user_id
    assert p.email is None
    assert p.contract_id is None
    assert p.account_id is None
    assert p.scopes == ()
    assert p.is_super_admin is False
    assert p.has_super_admin is False


def test_principal_with_scopes() -> None:
    p = SpokePrincipal(user_id=uuid4(), scopes=("master-data", "fiscal"))
    assert p.has_scope("master-data")
    assert not p.has_scope("agente-fiscal")


def test_principal_is_frozen() -> None:
    p = SpokePrincipal(user_id=uuid4())
    try:
        p.email = "x@y.com"  # type: ignore[misc]
    except (AttributeError, Exception):
        return
    raise AssertionError("SpokePrincipal should be frozen")
