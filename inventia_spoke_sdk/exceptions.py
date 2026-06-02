"""SDK exception hierarchy.

Spokes catch ``SpokeSDKError`` para tratar todos de uma vez, ou
sub-classes específicas para lógica diferenciada (ex.: invalidar cache
JWKS em ``JWKSError``).
"""

from __future__ import annotations


class SpokeSDKError(Exception):
    """Base for all SDK errors."""


class InvalidToken(SpokeSDKError):
    """JWT inválido (assinatura, expiração, issuer, audience, formato). → HTTP 401."""


class JWKSError(SpokeSDKError):
    """Erro buscando ou interpretando JWKS do Hub."""


class HubUnreachable(SpokeSDKError):
    """Hub não respondeu dentro do timeout."""


# ---- Authorization errors (HTTP 403) --------------------------------------
# Token é válido, mas a identidade não pode fazer a operação/alcançar o recurso.
# Mapeadas para 403 por ``install_auth_exception_handlers`` (ver enforcement.py).


class AuthorizationError(SpokeSDKError):
    """Base das falhas de autorização (token válido, acesso negado). → HTTP 403."""


class TenantMismatch(AuthorizationError):
    """Tenant pedido (path/header) ≠ tenant do token, ou claim de tenant ausente.

    Esta é a defesa contra o bug do §1.6: um token do tenant A NÃO pode operar
    sobre o tenant B só porque o header/path diz B.
    """


class InsufficientScope(AuthorizationError):
    """Falta o escopo ``recurso:ação`` exigido pelo endpoint.

    ``required`` carrega o escopo (ou escopos) que o endpoint pediu, para
    compor o header ``WWW-Authenticate: Bearer error="insufficient_scope"``.
    """

    def __init__(self, message: str, *, required: str | tuple[str, ...] | None = None) -> None:
        super().__init__(message)
        self.required = required


class CompanyNotAllowed(AuthorizationError):
    """CNPJ (``company_id``) pedido está fora da lista permitida da credencial.

    Camada 4b: filtro por empresa DENTRO do tenant. Não é fronteira de RLS.
    """

    def __init__(self, message: str, *, company_id: str | None = None) -> None:
        super().__init__(message)
        self.company_id = company_id
