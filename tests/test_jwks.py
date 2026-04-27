"""JWKSFetcher tests — cache, refresh, disk persistence, graceful degradation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from inventia_spoke_sdk import JWKSError, JWKSFetcher


def _make_jwks_response() -> dict:
    return {
        "keys": [
            {
                "kid": "key-1",
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": "fake-modulus-key-1",
                "e": "AQAB",
            },
            {
                "kid": "key-2",
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": "fake-modulus-key-2",
                "e": "AQAB",
            },
        ]
    }


class _FakeResponse:
    def __init__(self, json_data: dict, status: int = 200) -> None:
        self._json = json_data
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPError(f"status {self.status_code}")

    def json(self) -> dict:
        return self._json


def test_fetcher_returns_key_after_first_call() -> None:
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", ttl_seconds=60)
    with patch("httpx.get", return_value=_FakeResponse(_make_jwks_response())):
        key = f.get_key("key-1")
    assert key["kid"] == "key-1"


def test_fetcher_uses_cache_within_ttl() -> None:
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", ttl_seconds=60)
    call_count = 0

    def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(_make_jwks_response())

    with patch("httpx.get", side_effect=mock_get):
        f.get_key("key-1")
        f.get_key("key-1")
        f.get_key("key-2")
    assert call_count == 1, "should cache JWKS within TTL"


def test_fetcher_refreshes_after_ttl() -> None:
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", ttl_seconds=1)
    call_count = 0

    def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(_make_jwks_response())

    with patch("httpx.get", side_effect=mock_get):
        f.get_key("key-1")
        time.sleep(1.1)
        f.get_key("key-1")
    assert call_count == 2


def test_fetcher_refreshes_on_unknown_kid() -> None:
    """Sem TTL expirado, mas kid desconhecido → forced refresh."""
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", ttl_seconds=3600)
    call_count = 0

    initial_response = {"keys": [{"kid": "old-key", "kty": "RSA", "n": "x", "e": "y"}]}
    full_response = _make_jwks_response()

    def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(initial_response if call_count == 1 else full_response)

    with patch("httpx.get", side_effect=mock_get):
        # First call populates cache with only "old-key"
        f.get_key("old-key")
        # Now ask for "key-1" — cache miss triggers refresh
        f.get_key("key-1")

    assert call_count == 2


def test_fetcher_raises_when_kid_not_found_after_refresh() -> None:
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", ttl_seconds=60)
    with patch("httpx.get", return_value=_FakeResponse(_make_jwks_response())):
        with pytest.raises(JWKSError, match="kid 'unknown' not found"):
            f.get_key("unknown")


def test_fetcher_raises_on_initial_fetch_failure() -> None:
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", ttl_seconds=60)
    with patch("httpx.get", side_effect=httpx.HTTPError("boom")):
        with pytest.raises(JWKSError, match="cannot fetch JWKS"):
            f.get_key("any")


def test_fetcher_uses_stale_cache_when_refresh_fails() -> None:
    """Graceful degradation: refresh falha mas cache tem o kid → usa cache."""
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", ttl_seconds=1)
    call_count = 0

    def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _FakeResponse(_make_jwks_response())
        raise httpx.HTTPError("network error")

    with patch("httpx.get", side_effect=mock_get):
        f.get_key("key-1")
        time.sleep(1.1)
        # Refresh tries; fails; stale cache still has key-1
        key = f.get_key("key-1")
    assert key["kid"] == "key-1"
    assert call_count == 2


def test_fetcher_disk_cache_load(tmp_path: Path) -> None:
    cache = tmp_path / "jwks.json"
    cache.write_text(json.dumps(_make_jwks_response()))

    f = JWKSFetcher(jwks_url="https://kc.example/jwks", cache_path=cache)

    # Disk cache loaded; refresh attempts will be made on first call
    # but if network fails, stale cache is used.
    with patch("httpx.get", side_effect=httpx.HTTPError("offline")):
        key = f.get_key("key-1")
    assert key["kid"] == "key-1"


def test_fetcher_disk_cache_save(tmp_path: Path) -> None:
    cache = tmp_path / "jwks.json"
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", cache_path=cache)

    with patch("httpx.get", return_value=_FakeResponse(_make_jwks_response())):
        f.get_key("key-1")

    assert cache.exists()
    saved = json.loads(cache.read_text())
    assert len(saved["keys"]) == 2


def test_fetcher_invalid_jwks_response_raises() -> None:
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", ttl_seconds=60)
    with patch("httpx.get", return_value=_FakeResponse({"not": "jwks"})):
        with pytest.raises(JWKSError):
            f.get_key("key-1")


def test_fetcher_all_keys() -> None:
    f = JWKSFetcher(jwks_url="https://kc.example/jwks", ttl_seconds=60)
    with patch("httpx.get", return_value=_FakeResponse(_make_jwks_response())):
        keys = f.all_keys()
    assert set(keys.keys()) == {"key-1", "key-2"}
