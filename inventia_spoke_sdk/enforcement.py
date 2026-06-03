"""Enforcement helpers — escopo (camada 2), CNPJ (camada 4b) e erros padronizados.

v0.6.0. Centraliza no SDK o que antes cada spoke implementava à mão (e de
forma assimétrica). O spoke continua dono do seu ``require_principal`` (lê
``Authorization`` + ``X-Tenant-Id``/path e chama o ``HubJWTValidator``); este
módulo provê os blocos reutilizáveis em cima do ``SpokePrincipal`` resolvido:

- ``assert_scope`` / ``assert_any_scope`` — camada 2 (``recurso:ação``).
- ``assert_company_allowed`` — camada 4b (CNPJ dentro do tenant).
- ``require_scope`` — fábrica de dependency FastAPI a partir do principal_dep.
- ``install_auth_exception_handlers`` — mapeia as exceções do SDK para os
  status HTTP/OAuth padronizados (401 ``invalid_token``, 403
  ``insufficient_scope``, 403 ``tenant_mismatch``, 403 ``company_not_allowed``).

As funções ``assert_*`` levantam exceções do SDK (puras, sem FastAPI) para
poderem ser usadas também em workers/serviços.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from inventia_spoke_sdk.exceptions import (
    CompanyNotAllowed,
    InsufficientScope,
    InvalidToken,
    TenantMismatch,
)
from inventia_spoke_sdk.principal import SpokePrincipal

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI

PrincipalDep = Callable[..., Awaitable[SpokePrincipal]] | Callable[..., SpokePrincipal]


# ---- pure assertions (usáveis em API, workers e serviços) ------------------


def assert_scope(
    principal: SpokePrincipal,
    scope: str,
    *,
    allow_super_admin: bool = True,
) -> None:
    """Garante que ``principal`` tem ``scope`` (``recurso:ação``).

    Super admin tem bypass por padrão (``allow_super_admin``). Levanta
    ``InsufficientScope`` (HTTP 403) caso contrário.
    """
    if allow_super_admin and principal.is_super_admin:
        return
    if not principal.has_scope(scope):
        raise InsufficientScope(f"missing required scope: {scope}", required=scope)


def assert_any_scope(
    principal: SpokePrincipal,
    scopes: tuple[str, ...] | list[str],
    *,
    allow_super_admin: bool = True,
) -> None:
    """Garante que ``principal`` tem PELO MENOS um dos ``scopes``."""
    if allow_super_admin and principal.is_super_admin:
        return
    if not principal.has_any_scope(tuple(scopes)):
        raise InsufficientScope(
            f"missing required scope (any of): {', '.join(scopes)}",
            required=tuple(scopes),
        )


def assert_company_allowed(
    principal: SpokePrincipal,
    company_id: str | UUID,
    *,
    allow_super_admin: bool = True,
) -> None:
    """Camada 4b: garante que ``company_id`` está na lista permitida da credencial.

    Sem restrição na credencial (``company_ids`` vazio) = acesso a todos os
    CNPJs do tenant. Levanta ``CompanyNotAllowed`` (HTTP 403) caso contrário.
    """
    if allow_super_admin and principal.is_super_admin:
        return
    if not principal.company_allowed(company_id):
        raise CompanyNotAllowed(
            f"company_id {company_id} not allowed for this credential",
            company_id=str(company_id),
        )


# ---- FastAPI dependency factory --------------------------------------------


def require_scope(
    scope: str,
    principal_dep: PrincipalDep,
    *,
    allow_super_admin: bool = True,
) -> Callable[..., Awaitable[SpokePrincipal]]:
    """Constrói uma dependency FastAPI que exige ``scope`` e devolve o principal.

    Uso no spoke::

        from inventia_spoke_sdk.enforcement import require_scope
        from app.auth import require_principal

        reinf_read = require_scope("reinf:read", require_principal)

        @router.get("/...", )
        async def listar(p: SpokePrincipal = Depends(reinf_read)): ...
    """
    from fastapi import Depends  # local import: mantém fastapi opcional

    async def _dep(principal: SpokePrincipal = Depends(principal_dep)) -> SpokePrincipal:  # noqa: B008
        assert_scope(principal, scope, allow_super_admin=allow_super_admin)
        return principal

    _dep.__annotations__ = {"principal": SpokePrincipal, "return": SpokePrincipal}
    return _dep


# ---- exception handlers (mapeamento → HTTP/OAuth) --------------------------

# (exceção, status, código OAuth)
_AUTHZ_MAP: tuple[tuple[type[Exception], int, str], ...] = (
    (InvalidToken, 401, "invalid_token"),
    (InsufficientScope, 403, "insufficient_scope"),
    (TenantMismatch, 403, "tenant_mismatch"),
    (CompanyNotAllowed, 403, "company_not_allowed"),
)


def install_auth_exception_handlers(app: FastAPI) -> None:
    """Registra handlers que convertem exceções do SDK em respostas padronizadas.

    Chame uma vez no startup do spoke (``app = FastAPI(); install_auth_exception_handlers(app)``).
    Respostas seguem o formato de erro OAuth com ``WWW-Authenticate: Bearer``.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    def _make_handler(status_code: int, error_code: str):
        async def _handler(_: Request, exc: Exception) -> JSONResponse:
            body: dict[str, Any] = {"error": error_code, "error_description": str(exc)}
            challenge = f'Bearer error="{error_code}"'
            required = getattr(exc, "required", None)
            if required is not None:
                scope_str = required if isinstance(required, str) else " ".join(required)
                body["scope"] = scope_str
                challenge += f', scope="{scope_str}"'
            return JSONResponse(
                status_code=status_code,
                content=body,
                headers={"WWW-Authenticate": challenge},
            )

        return _handler

    for exc_type, status_code, error_code in _AUTHZ_MAP:
        app.add_exception_handler(exc_type, _make_handler(status_code, error_code))


__all__ = [
    "assert_scope",
    "assert_any_scope",
    "assert_company_allowed",
    "require_scope",
    "install_auth_exception_handlers",
]
