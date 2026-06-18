"""Inventia Spoke SDK — public API.

Use:
    from inventia_spoke_sdk import HubJWTValidator, SpokePrincipal, InvalidToken

    # Session + Service layer (v0.5.0+)
    from inventia_spoke_sdk import (
        BaseService,
        configure_session_resolver,
        session_for,
    )

Detalhes em README.md e nos módulos individuais.
"""

from inventia_spoke_sdk.db import (
    SessionFactoryResolver,
    configure_session_resolver,
    get_session_resolver,
    reset_session_resolver,
    session_for,
)
from inventia_spoke_sdk.exceptions import (
    HubUnreachable,
    InvalidToken,
    JWKSError,
    SpokeSDKError,
)
from inventia_spoke_sdk.jwks import JWKSFetcher
from inventia_spoke_sdk.jwt_validator import HubJWTValidator
from inventia_spoke_sdk.outbox import Outbox, OutboxBase, enqueue
from inventia_spoke_sdk.principal import SpokePrincipal
from inventia_spoke_sdk.services import BaseService
from inventia_spoke_sdk.version import __version__

__all__ = [
    "__version__",
    # JWT / principal (v0.1.0+)
    "HubJWTValidator",
    "JWKSFetcher",
    "SpokePrincipal",
    "SpokeSDKError",
    "InvalidToken",
    "JWKSError",
    "HubUnreachable",
    # Session + Service layer (v0.5.0+)
    "BaseService",
    "SessionFactoryResolver",
    "configure_session_resolver",
    "get_session_resolver",
    "reset_session_resolver",
    "session_for",
    # Outbox transacional compartilhado (v0.9.0+)
    "Outbox",
    "OutboxBase",
    "enqueue",
]
