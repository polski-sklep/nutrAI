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


# Test users, by telegram_id. 123456789 is the integration harness; 1 is the
# HTTP endpoint's, which posts activity as a bare id.
TEST_TELEGRAM_IDS = (123456789, 1, 999000111, 999000222)


@pytest.fixture(scope="session", autouse=True)
def tidy_test_users(request: pytest.FixtureRequest):
    """Leave the database as the run found it.

    The suite writes against a real Postgres — there is no seam short of one
    for the HTTP endpoint or the SQL views — and for months it never cleaned
    up. A `target` table with 11,330 superseded rows for a user that does not
    exist is not a bug in anything, and it makes every honest look at the
    database misleading.
    """
    yield

    import asyncio
    import os

    async def sweep() -> None:
        import asyncpg

        url = os.getenv("DATABASE_URL",
                        "postgresql://nutrai:nutrai@localhost:5432/nutrai")
        try:
            con = await asyncpg.connect(url, timeout=3)
        except Exception:
            return   # no database in this run; the unit tests do not need one
        try:
            ids = await con.fetch(
                "SELECT id FROM app_user WHERE telegram_id = ANY($1::bigint[])",
                list(TEST_TELEGRAM_IDS))
            for row in ids:
                uid = row["id"]
                # Closed targets and volatile per-run rows. The user, its live
                # targets and its notification rules stay, because bootstrapping
                # them again costs a minute of USDA lookups on the next run.
                for sql in (
                    "DELETE FROM target WHERE user_id=$1 AND effective_to IS NOT NULL",
                    "DELETE FROM llm_call WHERE user_id=$1",
                    # Written at resolve time with entry_id NULL, so the
                    # log_entry cascade never reaches the ones that matter.
                    "DELETE FROM resolution_event WHERE user_id=$1",
                    "DELETE FROM rating_prompt WHERE user_id=$1",
                    "DELETE FROM observation WHERE user_id=$1",
                    "DELETE FROM pending_action WHERE user_id=$1",
                    "DELETE FROM notification_log WHERE user_id=$1",
                    "DELETE FROM activity WHERE user_id=$1",
                    "DELETE FROM body_metric WHERE user_id=$1",
                    "DELETE FROM supplement_log WHERE user_id=$1",
                    "DELETE FROM first_contact WHERE user_id=$1",
                    "DELETE FROM morning_note_log WHERE user_id=$1",
                    "DELETE FROM supplement_reminder_log WHERE user_id=$1",
                ):
                    await con.execute(sql, uid)
        finally:
            await con.close()

    asyncio.run(sweep())
