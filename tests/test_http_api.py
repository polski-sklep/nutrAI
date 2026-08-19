"""The only way into the database that is not a human pressing a button.

Tailscale makes the network private; it does not make the endpoint safe. A
token is required regardless, because "only my devices can reach it" stops
being true the first time a device is lost or an exit node is enabled by
accident. Defence that depends on the network staying the shape you left it is
not defence.
"""

from __future__ import annotations

import importlib

import pytest
from aiohttp.test_utils import TestClient, TestServer

pytest_plugins = ()

TOKEN = "test-token-not-a-real-one"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("NUTRAI_HTTP_TOKEN", TOKEN)
    import nutrai.http_api as mod

    importlib.reload(mod)
    return mod


def run(coro):
    """One loop per test, and the pool dies inside it.

    db.pool() memoises a pool bound to whatever loop created it, so a test that
    reaches the database and then lets its loop close leaves a live pool behind
    for the next file to trip over — "another operation is in progress", raised
    somewhere entirely unrelated."""
    import asyncio

    async def wrapper():
        from nutrai import db

        try:
            return await coro
        finally:
            await db.close()

    return asyncio.run(wrapper())


def test_no_token_configured_means_the_server_does_not_start(monkeypatch):
    monkeypatch.delenv("NUTRAI_HTTP_TOKEN", raising=False)
    import nutrai.http_api as mod

    importlib.reload(mod)
    assert run(mod.start()) is None, "an unauthenticated endpoint was opened"


def test_health_needs_no_token(api):
    async def scenario():
        async with TestClient(TestServer(api.build_app())) as c:
            r = await c.get("/health")
            assert r.status == 200
            assert (await r.json())["ok"] is True

    run(scenario())


def test_activity_requires_the_token(api):
    async def scenario():
        async with TestClient(TestServer(api.build_app())) as c:
            r = await c.post("/activity", json={"telegram_id": 1, "kind": "lifting"})
            assert r.status == 401
            r = await c.post(
                "/activity",
                json={"telegram_id": 1, "kind": "lifting"},
                headers={"X-Nutrai-Token": "wrong"},
            )
            assert r.status == 401

    run(scenario())


def test_bad_input_is_refused_rather_than_stored(api):
    async def scenario():
        h = {"X-Nutrai-Token": TOKEN}
        async with TestClient(TestServer(api.build_app())) as c:
            assert (await c.post("/activity", json={"kind": "lifting"}, headers=h)).status == 400
            r = await c.post(
                "/activity", json={"telegram_id": 1, "kind": "interpretive dance"}, headers=h
            )
            assert r.status == 400
            r = await c.post(
                "/activity",
                json={"telegram_id": 1, "kind": "lifting", "minutes": 99999},
                headers=h,
            )
            assert r.status == 400
            r = await c.post(
                "/activity",
                json={"telegram_id": 1, "kind": "lifting", "local_date": "not-a-date"},
                headers=h,
            )
            assert r.status == 400

    run(scenario())


def test_a_rejection_says_why_in_the_log(api, caplog):
    """A real save was refused and left nothing behind but `400 260`, so the
    cause had to be found by comparing response byte counts against probes.
    The endpoint knows exactly what was wrong; it should say so.

    The value that arrived is echoed too: a client sending the display word
    "high" instead of the enum "hard" is the failure this catches, and quoting
    it turns a forensic exercise into a one-line diagnosis.
    """
    import logging

    async def scenario():
        h = {"X-Nutrai-Token": TOKEN}
        async with TestClient(TestServer(api.build_app())) as c:
            r = await c.post(
                "/activity",
                json={"telegram_id": 1, "kind": "lifting", "intensity": "high"},
                headers=h,
            )
            assert r.status == 400
            body = await r.json()
            assert "'high'" in body["error"], body
            assert "hard" in body["error"], body

    with caplog.at_level(logging.WARNING, logger="nutrai.http"):
        run(scenario())
    assert any("intensity" in rec.message and "high" in rec.message
               for rec in caplog.records), [r.message for r in caplog.records]


@pytest.mark.integration
def test_a_valid_intensity_and_rpe_are_stored(api):
    """Guards the enum the client has to send.

    Marked integration because it reaches the real database — the endpoint has
    no seam short of one — and it removes the rows it made. The first version
    left four sessions under telegram_id 1 in the live activity table, which is
    a test that lies about the day it ran on.
    """
    async def scenario():
        h = {"X-Nutrai-Token": TOKEN}
        async with TestClient(TestServer(api.build_app())) as c:
            for good in ("easy", "moderate", "hard", "max"):
                r = await c.post(
                    "/activity",
                    json={"telegram_id": 1, "kind": "lifting", "minutes": 30,
                          "intensity": good, "rpe": 8},
                    headers=h,
                )
                assert r.status in (200, 201), (good, await r.text())
            r = await c.post(
                "/activity",
                json={"telegram_id": 1, "kind": "lifting", "intensity": "hard", "rpe": 11},
                headers=h,
            )
            assert r.status == 400

        from nutrai import db
        pool = await db.pool()
        await pool.execute(
            """DELETE FROM activity WHERE user_id =
                 (SELECT id FROM app_user WHERE telegram_id = 1)""")

    run(scenario())


@pytest.mark.integration
def test_rpe_is_stored_at_the_precision_it_actually_has(api):
    """`rpe numeric` receiving a Python float stored 9.2 as
    9.199999999999999289457264239899814128875732421875 — eighteen significant
    figures of a one-decimal judgement."""

    async def scenario():
        h = {"X-Nutrai-Token": TOKEN}
        async with TestClient(TestServer(api.build_app())) as c:
            r = await c.post(
                "/activity",
                json={"telegram_id": 1, "kind": "lifting", "minutes": 7,
                      "intensity": "hard", "rpe": 9.2},
                headers=h,
            )
            assert r.status in (200, 201), await r.text()

        from nutrai import db
        pool = await db.pool()
        stored = await pool.fetchval(
            """SELECT rpe FROM activity WHERE user_id =
                 (SELECT id FROM app_user WHERE telegram_id = 1)
               ORDER BY id DESC LIMIT 1""")
        assert str(stored) == "9.2", stored
        await pool.execute(
            """DELETE FROM activity WHERE user_id =
                 (SELECT id FROM app_user WHERE telegram_id = 1)""")

    run(scenario())


@pytest.mark.integration
def test_an_rpe_becomes_an_observation_as_if_rated_by_hand(api):
    """`activity.rpe` is visible in /training and invisible to /insight.

    /insight correlates over `observation`, so an effort figure that only ever
    reaches the activity row is a number the analysis cannot see. Writing it
    here also means the training bot does not have to know to send a /rate as
    well, and the two can never disagree about what the effort was.
    """
    async def scenario():
        from nutrai import db

        h = {"X-Nutrai-Token": TOKEN}
        pool = await db.pool()
        uid = await pool.fetchval(
            "SELECT id FROM app_user WHERE telegram_id = 1")
        before = await pool.fetchval(
            "SELECT count(*) FROM observation WHERE user_id = $1 AND kind = 'rpe'",
            uid) if uid else 0

        async with TestClient(TestServer(api.build_app())) as c:
            r = await c.post(
                "/activity",
                json={"telegram_id": 1, "kind": "lifting", "minutes": 45, "rpe": 8.5},
                headers=h)
            assert r.status == 201, await r.text()
            # The same session posted twice is one effort asserted twice. A
            # second observation would firm up a correlation on its own echo.
            r2 = await c.post(
                "/activity",
                json={"telegram_id": 1, "kind": "lifting", "minutes": 45, "rpe": 8.5},
                headers=h)
            assert r2.status == 200 and (await r2.json())["created"] is False

        uid = await pool.fetchval("SELECT id FROM app_user WHERE telegram_id = 1")
        rows = await pool.fetch(
            """SELECT value, scale, note, local_date FROM observation
                WHERE user_id = $1 AND kind = 'rpe' ORDER BY id DESC""", uid)
        assert len(rows) == before + 1, "a duplicate activity wrote a second rating"
        assert float(rows[0]["value"]) == 8.5
        assert rows[0]["scale"] == "1-10"
        assert "lifting" in (rows[0]["note"] or "")
        # Not asserting hours_fasted here: this user has no confirmed meals, so
        # fast_hours_at correctly returns NULL and the figure would be absent
        # whichever branch ran. The backdated test below is what distinguishes
        # them, because there the date is the evidence.
        import datetime as _dt
        assert rows[0]["local_date"] == _dt.date.today()

        await pool.execute("DELETE FROM observation WHERE user_id = $1 AND kind = 'rpe'", uid)
        await pool.execute("DELETE FROM activity WHERE user_id = $1", uid)

    run(scenario())


@pytest.mark.integration
def test_a_backdated_rpe_lands_on_its_own_day_without_a_made_up_fast(api):
    """The day is known even when the hour is not.

    Dating a Sunday session to Monday puts it against the wrong day's food.
    Noon is the placeholder — inside the day whatever the rollover hour is —
    and the fasting figure is withheld rather than computed from it, because
    the fasting state at an invented hour is not a weak covariate but a
    fabricated one. observations() filters on hours_fasted IS NOT NULL, so the
    rating is recorded and never correlated.
    """
    async def scenario():
        import datetime as _dt

        from nutrai import db

        h = {"X-Nutrai-Token": TOKEN}
        day = _dt.date.today() - _dt.timedelta(days=3)
        async with TestClient(TestServer(api.build_app())) as c:
            r = await c.post(
                "/activity",
                json={"telegram_id": 1, "kind": "running", "minutes": 40,
                      "rpe": 6, "local_date": day.isoformat()},
                headers=h)
            assert r.status == 201, await r.text()

        pool = await db.pool()
        uid = await pool.fetchval("SELECT id FROM app_user WHERE telegram_id = 1")
        row = await pool.fetchrow(
            """SELECT local_date, hours_fasted FROM observation
                WHERE user_id = $1 AND kind = 'rpe' ORDER BY id DESC LIMIT 1""", uid)
        assert row["local_date"] == day
        assert row["hours_fasted"] is None

        await pool.execute("DELETE FROM observation WHERE user_id = $1 AND kind = 'rpe'", uid)
        await pool.execute("DELETE FROM activity WHERE user_id = $1", uid)

    run(scenario())


@pytest.mark.integration
def test_two_similar_sessions_on_one_day_are_two_sessions(api):
    """Dedup on the shape of a workout is a heuristic standing in for identity.

    The fitness side flagged it: their lifting sessions cluster at 96-108
    minutes against four coarse intensity bands, so two real sessions on one
    date look identical and the second is swallowed. It fires exactly when they
    batch-backfill. A retry carries the same session id; two sessions do not.
    """
    async def scenario():
        from nutrai import db

        h = {"X-Nutrai-Token": TOKEN}
        base = {"telegram_id": 1, "kind": "lifting", "minutes": 100,
                "intensity": "hard", "rpe": 9}
        async with TestClient(TestServer(api.build_app())) as c:
            a = await c.post("/activity", json={**base, "external_id": "s-1"}, headers=h)
            b = await c.post("/activity", json={**base, "external_id": "s-2"}, headers=h)
            # Same id twice is a retry, and must not double the covariate.
            again = await c.post("/activity", json={**base, "external_id": "s-1"},
                                 headers=h)
            assert a.status == 201 and b.status == 201, (await a.text(), await b.text())
            assert again.status == 200 and (await again.json())["created"] is False
            assert (await a.json())["id"] != (await b.json())["id"]

            # Without an id the old shape heuristic still applies, so a client
            # that has not been updated keeps its idempotency.
            c1 = await c.post("/activity", json=base, headers=h)
            c2 = await c.post("/activity", json=base, headers=h)
            assert c1.status == 201 and c2.status == 200
            assert (await c2.json())["created"] is False

        pool = await db.pool()
        uid = await pool.fetchval("SELECT id FROM app_user WHERE telegram_id = 1")
        n = await pool.fetchval(
            "SELECT count(*) FROM activity WHERE user_id = $1", uid)
        assert n == 3, f"expected two identified sessions plus one unidentified, got {n}"
        await pool.execute("DELETE FROM observation WHERE user_id = $1 AND kind = 'rpe'", uid)
        await pool.execute("DELETE FROM activity WHERE user_id = $1", uid)

    run(scenario())
