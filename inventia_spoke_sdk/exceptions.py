"""SDK exception hierarchy.

Spokes catch ``SpokeSDKError`` para tratar todos de uma vez, ou
sub-classes específicas para lógica diferenciada (ex.: invalidar cache
JWKS em ``JWKSError``).
"""


class SpokeSDKError(Exception):
    """Base for all SDK errors."""


class InvalidToken(SpokeSDKError):
    """JWT inválido (assinatura, expiração, issuer, audience, formato)."""


class JWKSError(SpokeSDKError):
    """Erro buscando ou interpretando JWKS do Hub."""


class HubUnreachable(SpokeSDKError):
    """Hub não respondeu dentro do timeout."""
