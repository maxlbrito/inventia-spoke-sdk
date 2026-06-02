"""Database session helpers — tenant-aware factory and SDK base service.

The SDK does not know how a spoke resolves tenant → DB (Hub call,
schema provisioning, engine pool). The spoke registers a
``SessionFactoryResolver`` at startup; the SDK exposes a uniform
``session_for(principal)`` that delegates to it.

``AsyncSession`` from SQLAlchemy 2.0 is itself a Unit of Work — there is
no UoW wrapper here on purpose. Use ``async with session.begin():`` for
explicit transaction boundaries.
"""

from inventia_spoke_sdk.db.session import (
    TENANT_GUC,
    SessionFactoryResolver,
    configure_session_resolver,
    get_session_resolver,
    reset_session_resolver,
    session_for,
)

__all__ = [
    "TENANT_GUC",
    "SessionFactoryResolver",
    "configure_session_resolver",
    "get_session_resolver",
    "reset_session_resolver",
    "session_for",
]
