"""Inventia Spoke SDK — public API.

Use:
    from inventia_spoke_sdk import HubJWTValidator, SpokePrincipal, InvalidToken

Detalhes em README.md e nos módulos individuais.
"""

from inventia_spoke_sdk.exceptions import (
    HubUnreachable,
    InvalidToken,
    JWKSError,
    SpokeSDKError,
)
from inventia_spoke_sdk.jwt_validator import HubJWTValidator
from inventia_spoke_sdk.principal import SpokePrincipal
from inventia_spoke_sdk.version import __version__

__all__ = [
    "__version__",
    "HubJWTValidator",
    "SpokePrincipal",
    "SpokeSDKError",
    "InvalidToken",
    "JWKSError",
    "HubUnreachable",
]
