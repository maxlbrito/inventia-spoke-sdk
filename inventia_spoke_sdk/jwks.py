"""JWKS fetcher with cache + auto-refresh on unknown kid.

KC 26 emite tokens RS256 (default). O JWKS público está em
``{issuer}/protocol/openid-connect/certs``.

Política de cache:
- TTL configurável (default 1h).
- Refresh automático se o ``kid`` do token não estiver no cache.
- Persistência opcional em disco (resiliência a restart de pod do spoke).

Uso:
    fetcher = JWKSFetcher(jwks_url="https://kc/realms/inventia/protocol/openid-connect/certs")
    key = fetcher.get_key(kid="abc123")
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

from inventia_spoke_sdk.exceptions import JWKSError

logger = logging.getLogger(__name__)


@dataclass
class JWKSFetcher:
    """Fetches and caches a JWKS from a remote URL."""

    jwks_url: str
    ttl_seconds: int = 3600
    timeout_seconds: float = 5.0
    cache_path: Path | None = None
    """Optional disk cache for resilience (pod restart, network outage)."""

    _keys: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _fetched_at: float = field(default=0.0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def __post_init__(self) -> None:
        if self.cache_path:
            self._try_load_disk_cache()

    def get_key(self, kid: str) -> dict[str, Any]:
        """Returns the JWK for a given key id. Refreshes JWKS if needed."""
        with self._lock:
            if kid in self._keys and not self._is_expired():
                return self._keys[kid]
            # Either kid unknown OR cache expired — refresh.
            self._refresh()
            if kid not in self._keys:
                raise JWKSError(f"kid {kid!r} not found in JWKS at {self.jwks_url}")
            return self._keys[kid]

    def all_keys(self) -> dict[str, dict[str, Any]]:
        """Returns all known keys (for tooling/diagnostics)."""
        with self._lock:
            if self._is_expired():
                self._refresh()
            return dict(self._keys)

    # ---- internals --------------------------------------------------------

    def _is_expired(self) -> bool:
        return (time.time() - self._fetched_at) > self.ttl_seconds

    def _refresh(self) -> None:
        try:
            r = httpx.get(self.jwks_url, timeout=self.timeout_seconds)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning("JWKS fetch failed for %s: %s", self.jwks_url, exc)
            if self._keys:
                # We already have a stale cache; keep using it (graceful
                # degradation when KC is briefly unreachable).
                return
            raise JWKSError(f"cannot fetch JWKS at {self.jwks_url}: {exc}") from exc

        keys = data.get("keys", [])
        if not isinstance(keys, list):
            raise JWKSError("JWKS response missing 'keys' array")

        self._keys = {k["kid"]: k for k in keys if "kid" in k}
        self._fetched_at = time.time()
        logger.debug("Refreshed JWKS from %s — %d keys", self.jwks_url, len(self._keys))

        if self.cache_path:
            self._try_save_disk_cache(data)

    def _try_load_disk_cache(self) -> None:
        try:
            if not self.cache_path or not self.cache_path.exists():
                return
            data = json.loads(self.cache_path.read_text())
            keys = data.get("keys", [])
            self._keys = {k["kid"]: k for k in keys if "kid" in k}
            # Don't trust disk timestamp; treat as expired so first get_key
            # triggers a refresh attempt. If refresh fails, stale cache is
            # used (graceful degradation).
            self._fetched_at = 0.0
            logger.debug(
                "Loaded JWKS from disk cache %s — %d keys (will refresh)",
                self.cache_path,
                len(self._keys),
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load JWKS disk cache %s: %s", self.cache_path, exc)

    def _try_save_disk_cache(self, data: dict[str, Any]) -> None:
        try:
            if not self.cache_path:
                return
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(data))
        except OSError as exc:
            logger.warning("Failed to save JWKS disk cache %s: %s", self.cache_path, exc)
