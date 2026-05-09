"""arq helper for opening a tenant-scoped session inside a job.

Pattern
-------
The job receives the principal data as part of its payload (e.g. an
access token + tenant_id, or a serialized principal dict). The job
reconstructs ``SpokePrincipal`` and uses ``session_for_job`` to obtain
an ``AsyncSession``.

Example
-------
::

    from inventia_spoke_sdk.arq import session_for_job
    from inventia_spoke_sdk.principal import SpokePrincipal

    async def run_companies_import(ctx, job_id, tenant_id, access_token):
        principal = SpokePrincipal(
            tenant_id=UUID(tenant_id),
            access_token=access_token,
            kind="user",
            user_id=...,
        )
        async with session_for_job(principal) as session:
            service = ImportService(session, principal)
            await service.process_import(job_id)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from inventia_spoke_sdk.db.session import session_for
from inventia_spoke_sdk.principal import SpokePrincipal


@asynccontextmanager
async def session_for_job(principal: SpokePrincipal) -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` bound to the principal's tenant.

    Thin wrapper over ``inventia_spoke_sdk.db.session_for`` to give arq
    jobs a self-documenting entry point.
    """
    async with session_for(principal) as session:
        yield session


__all__ = ["session_for_job"]
