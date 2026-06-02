"""v0.6.0 — enforcement de escopo (camada 2), CNPJ (camada 4b) e handlers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from inventia_spoke_sdk import (
    CompanyNotAllowed,
    InsufficientScope,
    SpokePrincipal,
    assert_any_scope,
    assert_company_allowed,
    assert_scope,
)


def _principal(**kw) -> SpokePrincipal:
    base = {"user_id": uuid4(), "tenant_id": uuid4(), "kind": "user"}
    base.update(kw)
    return SpokePrincipal(**base)


# ---- assert_scope ----------------------------------------------------------


def test_assert_scope_ok() -> None:
    assert_scope(_principal(scopes=("reinf:read", "reinf:write")), "reinf:write")


def test_assert_scope_missing_raises() -> None:
    with pytest.raises(InsufficientScope) as ei:
        assert_scope(_principal(scopes=("reinf:read",)), "reinf:write")
    assert ei.value.required == "reinf:write"


def test_assert_scope_super_admin_bypass() -> None:
    assert_scope(_principal(scopes=(), is_super_admin=True), "anything:write")


def test_assert_scope_super_admin_bypass_disabled() -> None:
    with pytest.raises(InsufficientScope):
        assert_scope(
            _principal(scopes=(), is_super_admin=True),
            "x:write",
            allow_super_admin=False,
        )


def test_assert_any_scope() -> None:
    assert_any_scope(_principal(scopes=("nfe:read",)), ["nfe:read", "nfe:write"])
    with pytest.raises(InsufficientScope):
        assert_any_scope(_principal(scopes=("cte:read",)), ["nfe:read", "nfe:write"])


# ---- assert_company_allowed (camada 4b) ------------------------------------


def test_company_allowed_no_restriction() -> None:
    assert_company_allowed(_principal(company_ids=()), uuid4())  # vazio = todos


def test_company_allowed_in_list() -> None:
    cid = str(uuid4())
    assert_company_allowed(_principal(company_ids=(cid,)), cid)


def test_company_not_allowed_raises() -> None:
    with pytest.raises(CompanyNotAllowed):
        assert_company_allowed(_principal(company_ids=(str(uuid4()),)), uuid4())


def test_company_super_admin_bypass() -> None:
    assert_company_allowed(
        _principal(company_ids=(str(uuid4()),), is_super_admin=True), uuid4()
    )


# ---- FastAPI integration: require_scope + handlers -------------------------


def test_require_scope_and_handlers_via_fastapi() -> None:
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from inventia_spoke_sdk import install_auth_exception_handlers, require_scope

    granted = _principal(scopes=("reinf:read",))

    async def principal_dep() -> SpokePrincipal:
        return granted

    app = fastapi.FastAPI()
    install_auth_exception_handlers(app)

    reinf_read = require_scope("reinf:read", principal_dep)
    reinf_write = require_scope("reinf:write", principal_dep)

    @app.get("/ok")
    async def _ok(p: SpokePrincipal = fastapi.Depends(reinf_read)):  # noqa: B008
        return {"tenant": str(p.tenant_id)}

    @app.get("/denied")
    async def _denied(p: SpokePrincipal = fastapi.Depends(reinf_write)):  # noqa: B008
        return {"never": True}

    client = TestClient(app)

    r_ok = client.get("/ok")
    assert r_ok.status_code == 200

    r_denied = client.get("/denied")
    assert r_denied.status_code == 403
    assert r_denied.json()["error"] == "insufficient_scope"
    assert r_denied.json()["scope"] == "reinf:write"
    assert 'error="insufficient_scope"' in r_denied.headers["WWW-Authenticate"]
