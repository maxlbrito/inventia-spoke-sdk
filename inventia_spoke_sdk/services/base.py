"""``BaseService`` — common parent for spoke services."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from inventia_spoke_sdk.principal import SpokePrincipal


class BaseService:
    """Base class for services shared by API handlers and arq jobs.

    Construction::

        service = CompanyService(session, principal=principal)

    Subclasses implement business methods. ``AsyncSession`` is the unit
    of work — when atomicity matters, wrap the work in
    ``async with self.session.begin():``.

    Attributes
    ----------
    session
        The SQLAlchemy ``AsyncSession`` already bound to the tenant.
    principal
        Optional. When provided, callers get ``tenant_id`` and audit
        info without re-injecting the principal everywhere.
    log
        ``logging.Logger`` named after the concrete subclass, with
        ``tenant_id`` attached to every record via ``LoggerAdapter``.
    """

    def __init__(
        self,
        session: AsyncSession,
        principal: SpokePrincipal | None = None,
    ) -> None:
        self.session = session
        self.principal = principal
        self.log = self._build_logger()

    @property
    def tenant_id(self) -> str | None:
        """Convenience accessor; ``None`` when no principal is bound."""
        if self.principal is None or self.principal.tenant_id is None:
            return None
        return str(self.principal.tenant_id)

    def _build_logger(self) -> logging.LoggerAdapter[logging.Logger]:
        base = logging.getLogger(self.__class__.__module__ + "." + self.__class__.__name__)
        extra: dict[str, Any] = {"tenant_id": self.tenant_id}
        if self.principal is not None:
            if self.principal.user_id is not None:
                extra["user_id"] = str(self.principal.user_id)
            if self.principal.client_id is not None:
                extra["client_id"] = self.principal.client_id
        return logging.LoggerAdapter(base, extra)
