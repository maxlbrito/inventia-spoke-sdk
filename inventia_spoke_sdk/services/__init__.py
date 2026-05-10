"""Service-layer base class shared by API handlers and arq workers.

The point of ``BaseService`` is to give controllers and jobs a single
place to put business rules, instead of duplicating validation and
queries between ``app/api/`` and ``app/workers/``.

It deliberately does not abstract transactions — ``AsyncSession`` from
SQLAlchemy 2.0 is itself a Unit of Work.
"""

from inventia_spoke_sdk.services.base import BaseService

__all__ = ["BaseService"]
