"""SpokePrincipal — identidade resolvida pelo SDK a partir do JWT do Hub.

Versão 0.1.0 (M1) carrega apenas os campos legados — `tier`, `role`,
`policy` chegam em 0.2.0 (M3). Mantemos o dataclass minimal para evitar
churn em spokes existentes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class SpokePrincipal:
    """Identidade do caller no spoke (user ou cliente M2M)."""

    user_id: UUID
    email: str | None = None
    contract_id: UUID | None = None
    account_id: UUID | None = None
    scopes: tuple[str, ...] = field(default_factory=tuple)
    is_super_admin: bool = False

    @property
    def has_super_admin(self) -> bool:
        return self.is_super_admin

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
