"""v0.6.0 Fase 5 — RFC 9728 protected-resource metadata + challenge."""

from __future__ import annotations

import pytest

from inventia_spoke_sdk import (
    protected_resource_challenge,
    protected_resource_metadata,
)
from inventia_spoke_sdk.mcp import WELL_KNOWN_PROTECTED_RESOURCE


def test_metadata_shape():
    m = protected_resource_metadata(
        resource="https://reinf.inventiaapp.com",
        authorization_servers=["http://localhost:8080/realms/inventia"],
        scopes_supported=["reinf:read", "reinf:write"],
    )
    assert m["resource"] == "https://reinf.inventiaapp.com"
    assert m["authorization_servers"] == ["http://localhost:8080/realms/inventia"]
    assert m["scopes_supported"] == ["reinf:read", "reinf:write"]
    assert m["bearer_methods_supported"] == ["header"]


def test_challenge_points_to_metadata():
    c = protected_resource_challenge("https://reinf.inventiaapp.com/", scope="reinf:write")
    expected = (
        'resource_metadata="https://reinf.inventiaapp.com'
        '/.well-known/oauth-protected-resource"'
    )
    assert expected in c
    assert 'scope="reinf:write"' in c


def test_mount_serves_well_known():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from inventia_spoke_sdk import mount_protected_resource_metadata

    app = fastapi.FastAPI()
    mount_protected_resource_metadata(
        app,
        resource="https://md.inventiaapp.com",
        authorization_servers=["http://localhost:8080/realms/inventia"],
        scopes_supported=["masterdata:read", "masterdata:write"],
    )
    r = TestClient(app).get(WELL_KNOWN_PROTECTED_RESOURCE)
    assert r.status_code == 200
    body = r.json()
    assert body["resource"] == "https://md.inventiaapp.com"
    assert "masterdata:read" in body["scopes_supported"]
