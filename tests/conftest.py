"""Shared fixtures. Nothing here is imported by the unit tests, which stay
DB-free — `pytest -q` must keep working on a laptop with no Postgres running.
"""

from __future__ import annotations

import asyncio
import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: needs a live Postgres with USDA loaded (see tests/test_integration.py)",
    )


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    return asyncio.get_event_loop_policy()


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql://nutrai:nutrai@localhost:5432/nutrai")
