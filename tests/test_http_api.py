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
