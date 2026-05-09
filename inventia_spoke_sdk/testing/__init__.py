"""Testing utilities for spokes that consume this SDK.

The fixtures here implement the rollback-per-test pattern: each test
runs inside a SAVEPOINT that is rolled back on teardown, so cases stay
isolated against a real ``AsyncSession`` (no in-memory UoW wrapper).

Importing this module pulls in pytest — install the SDK with the
``[testing]`` extra to get pytest available.
"""

from inventia_spoke_sdk.testing.db import (
    create_rollback_session_factory,
    install_test_resolver,
)

__all__ = [
    "create_rollback_session_factory",
    "install_test_resolver",
]
