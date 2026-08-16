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
