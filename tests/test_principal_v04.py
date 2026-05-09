"""SpokePrincipal v0.4.0 — tier/role/policy/acr/amr."""

from __future__ import annotations

from uuid import uuid4

from inventia_spoke_sdk import SpokePrincipal


def test_principal_v04_defaults_none():
    p = SpokePrincipal(user_id=uuid4())
    assert p.tier is None
    assert p.role is None
    assert p.platform_role is None
    assert p.policy is None
    assert p.policy_version is None
    assert p.acr is None
    assert p.auth_time is None
    assert p.amr == ()


def test_principal_v04_populated():
    p = SpokePrincipal(
        user_id=uuid4(),
        tier=2,
        role="admin",
        platform_role="platform_support",
        policy={
            "limits": {"page_size_max": 100, "overage_behavior": "warn"},
            "mfa": {"required": True},
        },
        policy_version=2,
        acr="1",
        auth_time=1735000000,
        amr=("pwd", "totp"),
    )
    assert p.tier == 2
    assert p.role == "admin"
    assert p.platform_role == "platform_support"
    assert p.policy_version == 2
    assert p.acr == "1"
    assert p.auth_time == 1735000000
    assert p.amr == ("pwd", "totp")


def test_has_role():
    p = SpokePrincipal(user_id=uuid4(), role="viewer")
    assert p.has_role("viewer")
    assert not p.has_role("admin")


def test_has_platform_role():
    p = SpokePrincipal(user_id=uuid4(), platform_role="platform_admin")
    assert p.has_platform_role("platform_admin")
    assert not p.has_platform_role("platform_owner")
    assert not SpokePrincipal(user_id=uuid4()).has_platform_role("platform_admin")


def test_policy_get_dotted_path():
    p = SpokePrincipal(
        user_id=uuid4(),
        policy={"limits": {"page_size_max": 50, "export_async_threshold": 5000}},
    )
    assert p.policy_get("limits.page_size_max") == 50
    assert p.policy_get("limits.export_async_threshold") == 5000


def test_policy_get_returns_default_when_missing():
    p = SpokePrincipal(user_id=uuid4(), policy={"limits": {"page_size_max": 50}})
    assert p.policy_get("limits.unknown", default="fallback") == "fallback"
    assert p.policy_get("nonexistent.path", default=42) == 42


def test_policy_get_when_policy_is_none():
    """policy ausente (token de versão antiga do Hub) → sempre default."""
    p = SpokePrincipal(user_id=uuid4())
    assert p.policy_get("limits.page_size_max", default=100) == 100


def test_policy_get_through_non_dict_value():
    """policy_get para de descer quando encontra valor escalar; retorna default."""
    p = SpokePrincipal(user_id=uuid4(), policy={"mfa": {"required": True}})
    assert p.policy_get("mfa.required.something", default="x") == "x"
