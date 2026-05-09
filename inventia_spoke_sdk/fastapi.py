"""FastAPI dependency helper for opening a tenant-scoped session.

The SDK does not know how a spoke resolves the principal (each spoke
has its own ``require_read``/``require_write`` chain). The spoke wires
its principal dependency into ``session_dep_for`` to produce a ready-to-
use ``Depends`` callable.

Example
-------
::

    # in your spoke's app/api/deps.py
    from inventia_spoke_sdk.fastapi import session_dep_for
    from app.auth import require_read

    db_session = session_dep_for(require_read)

    # in your route
    @router.get("/companies")
    async def list_companies(
        session: AsyncSession = Depends(db_session),
        principal: SpokePrincipal = Depends(require_read),
    ):
        return await CompanyService(session, principal).list_paginated(...)
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from inventia_spoke_sdk.db.session import session_for
from inventia_spoke_sdk.principal import SpokePrincipal


def session_dep_for(
    principal_dep: Callable[..., Awaitable[SpokePrincipal]] | Callable[..., SpokePrincipal],
) -> Callable[..., AsyncIterator[AsyncSession]]:
    """Build a FastAPI dependency that opens a tenant-scoped session.

    ``principal_dep`` is the spoke's own principal dependency
    (``require_read`` / ``require_write`` / etc). The returned callable
    is meant to be used with ``Depends(...)``.
    """
    from fastapi import Depends  # local import: keeps fastapi optional

    async def _dep(
        principal: SpokePrincipal = Depends(principal_dep),  # noqa: B008
    ) -> AsyncIterator[AsyncSession]:
        async with session_for(principal) as session:
            yield session

    # FastAPI inspects __annotations__ — make sure they're explicit
    _dep.__annotations__ = {"principal": SpokePrincipal, "return": AsyncIterator[AsyncSession]}
    return _dep


__all__: list[Any] = ["session_dep_for"]
