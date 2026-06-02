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
from inventia_spoke_sdk.enforcement import (
    assert_any_scope,
    assert_company_allowed,
    assert_scope,
    install_auth_exception_handlers,
    require_scope,
)
from inventia_spoke_sdk.exceptions import (
    AuthorizationError,
    CompanyNotAllowed,
    HubUnreachable,
    InsufficientScope,
    InvalidToken,
    JWKSError,
    SpokeSDKError,
    TenantMismatch,
)
from inventia_spoke_sdk.jwks import JWKSFetcher
from inventia_spoke_sdk.jwt_validator import HubJWTValidator
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
    # Authorization (v0.6.0)
    "AuthorizationError",
    "TenantMismatch",
    "InsufficientScope",
    "CompanyNotAllowed",
    # Enforcement helpers (v0.6.0)
    "assert_scope",
    "assert_any_scope",
    "assert_company_allowed",
    "require_scope",
    "install_auth_exception_handlers",
    # Session + Service layer (v0.5.0+)
    "BaseService",
    "SessionFactoryResolver",
    "configure_session_resolver",
    "get_session_resolver",
    "reset_session_resolver",
    "session_for",
]
