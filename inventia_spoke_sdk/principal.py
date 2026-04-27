"""SpokePrincipal — identidade resolvida pelo SDK a partir do JWT do Hub.

v0.4.0:
    - Ganha ``tier``, ``role``, ``policy`` (subset do TierPolicy resolvida
      pelo Hub), ``policy_version``, ``platform_role``, ``acr``,
      ``auth_time``, ``amr`` (RFC 8176).
    - Helpers: ``has_role(role)``, ``policy_get("limits.page_size_max")``.

v0.2.0:
    - ``kind`` ("user" | "client"), ``tenant_id``, ``access_token``.

v0.1.0 (legado):
    - Apenas user tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID


@dataclass(frozen=True)
class SpokePrincipal:
    """Identidade do caller no spoke."""

    user_id: UUID | None = None
    email: str | None = None
    contract_id: UUID | None = None
    account_id: UUID | None = None
    tenant_id: UUID | None = None
    scopes: tuple[str, ...] = field(default_factory=tuple)
    is_super_admin: bool = False
    kind: Literal["user", "client"] = "user"
    client_id: str | None = None
    access_token: str | None = None

    # v0.4.0 — claims de tiering/RBAC do Hub
    tier: int | None = None
    role: str | None = None
    platform_role: str | None = None
    policy: dict[str, Any] | None = None
    policy_version: int | None = None
    acr: str | None = None
    auth_time: int | None = None
    amr: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.kind == "user" and self.user_id is None:
            raise ValueError("user kind requires user_id")
        if self.kind == "client" and self.client_id is None:
            raise ValueError("client kind requires client_id")

    @property
    def is_client(self) -> bool:
        return self.kind == "client"

    @property
    def is_user(self) -> bool:
        return self.kind == "user"

    @property
    def has_super_admin(self) -> bool:
        return self.is_super_admin

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def has_role(self, role: str) -> bool:
        """Match exato de Membership role (admin, operator, viewer, etc)."""
        return self.role == role

    def has_platform_role(self, role: str) -> bool:
        """Match de PlatformRole (platform_owner, platform_admin, platform_support)."""
        return self.platform_role == role

    def policy_get(self, path: str, default: Any = None) -> Any:
        """Acesso dotted no policy claim. Ex: ``policy_get("limits.page_size_max")``.

        Retorna ``default`` se qualquer parte do path não existir ou o
        ``policy`` está vazio.
        """
        if not self.policy:
            return default
        cur: Any = self.policy
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur
