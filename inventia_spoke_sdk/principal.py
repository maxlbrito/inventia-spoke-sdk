"""SpokePrincipal — identidade resolvida pelo SDK a partir do JWT do Hub.

v0.2.0:
    - Suporta `kind` ("user" | "client") para diferenciar usuários humanos
      de tokens M2M.
    - Adiciona `tenant_id` (vem do header X-Tenant-Id, não da claim) e
      `access_token` (preservado para forward ao Hub em handshakes).

v0.1.0 (legado):
    - Apenas user tokens, sem tenant/access_token.

Tier, role, policy ficam para v0.3.0+ (M3 do plano consolidado).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class SpokePrincipal:
    """Identidade do caller no spoke.

    Campos principais:
    - ``user_id``: UUID do user (None se ``kind == "client"``).
    - ``client_id``: identificador M2M (None se ``kind == "user"``).
    - ``account_id``: account ativo do caller (claim ``account_id`` ou
      ``active_account_id``).
    - ``contract_id``: contrato ativo (claim correspondente).
    - ``tenant_id``: tenant ativo (vem do header X-Tenant-Id, **não** da
      claim — preenchido pelo spoke no momento da resolução).
    - ``access_token``: JWT bruto preservado para forward ao Hub em
      handshakes (ex.: ``GET /spoke/context/{tenant_id}``).
    """

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
