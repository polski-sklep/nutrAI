"""A small HTTP surface, for the workout bot to post into.

Deliberately small. This is the only way into the database that is not a human
pressing a button in Telegram, so it gets the narrowest possible shape: one
endpoint that appends activity, one that reports health, a shared secret, and
nothing that can read your food log back out.

On the trust boundary: Tailscale makes the network private, and that is not the
same as making the endpoint safe. A token is still required, because "only my
devices can reach it" becomes false the first time a device is lost, a machine
is shared, or an exit node is enabled by accident. Defence that depends on the
network staying the shape you left it is not defence.

aiohttp rather than a framework: aiogram already depends on it, so this costs no
new package.
"""

from __future__ import annotations

import datetime as dt
import hmac
import logging
import os

from aiohttp import web

from . import db

log = logging.getLogger("nutrai.http")


def _reject(reason: str, status: int = 400) -> web.Response:
    """Refuse, and say why in the log as well as in the response.

    A rejection used to leave nothing behind but an access line, so a client
    posting the display word "high" instead of the enum "hard" showed up as a
    bare `400 260` and had to be identified by comparing response byte counts
    against probes. The endpoint knows exactly what was wrong; the operator
    should not have to work it out forensically.
    """
    log.warning("activity rejected: %s", reason)
    return web.json_response({"error": reason}, status=status)

# Fail closed. With no token the server does not start at all, rather than
# starting open and trusting the network to be private.
TOKEN = os.getenv("NUTRAI_HTTP_TOKEN", "")
BIND = os.getenv("NUTRAI_HTTP_BIND", "127.0.0.1")
PORT = int(os.getenv("NUTRAI_HTTP_PORT", "8081"))

KINDS = {"lifting", "cardio", "cycling", "running", "walk", "swim", "sport", "rest", "other"}
# Intensity is a small closed set on purpose. A 1-10 RPE from one client and a
# "hard" from another are not comparable, and averaging them would invent a
# precision neither has — so both are accepted, separately, and neither is
# derived from the other. Absent means unknown, never moderate.
INTENSITIES = {"easy", "moderate", "hard", "max"}


def _authorised(request: web.Request) -> bool:
    supplied = request.headers.get("X-Nutrai-Token", "")
    # compare_digest rather than ==, so a wrong token cannot be found one
    # character at a time by timing the response.
    return bool(TOKEN) and hmac.compare_digest(supplied, TOKEN)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "nutrai"})


async def post_activity(request: web.Request) -> web.Response:
    """Append one training session.

    Append-only and idempotent per (user, date, kind, minutes): re-posting the
    same session does not double it, because a workout bot that retries on a
    timeout is a workout bot that will eventually retry on a success.
    """
    if not _authorised(request):
        return _reject("unauthorised", 401)

    try:
        body = await request.json()
    except Exception:
        return _reject("body must be JSON", 400)

    telegram_id = body.get("telegram_id")
    if not telegram_id:
        return _reject("telegram_id is required", 400)

    kind = str(body.get("kind", "other")).lower().strip()
    if kind not in KINDS:
        return _reject(f"kind must be one of {sorted(KINDS)} (got {kind!r})", 400)

    try:
        minutes = int(body["minutes"]) if body.get("minutes") is not None else None
        kcal = float(body["kcal_burned"]) if body.get("kcal_burned") is not None else None
    except (TypeError, ValueError):
        return _reject("minutes and kcal_burned must be numbers", 400)

    if minutes is not None and not 0 <= minutes <= 1440:
        return _reject("minutes out of range", 400)
    if kcal is not None and not 0 <= kcal <= 10000:
        return _reject("kcal_burned out of range", 400)

    intensity = body.get("intensity")
    if intensity is not None:
        intensity = str(intensity).lower().strip()
        if intensity not in INTENSITIES:
            # The value that arrived is quoted: a client sending the display
            # word "high" rather than the enum "hard" is exactly what this
            # catches, and echoing it makes the diagnosis one line instead of
            # a byte-count comparison against probe responses.
            return _reject(
                f"intensity must be one of {sorted(INTENSITIES)} "
                f"(got {intensity!r})", 400)
    try:
        rpe = float(body["rpe"]) if body.get("rpe") is not None else None
    except (TypeError, ValueError):
        return _reject("rpe must be a number", 400)
    if rpe is not None and not 1 <= rpe <= 10:
        return _reject("rpe must be between 1 and 10", 400)

    # Every field is validated before the database is touched. Reaching
    # get_or_create_user first meant a request with a malformed date still
    # created an app_user row on its way to being rejected — a write performed
    # by an input the endpoint had already decided was invalid.
    explicit_day: dt.date | None = None
    if body.get("local_date"):
        try:
            explicit_day = dt.date.fromisoformat(str(body["local_date"]))
        except ValueError:
            return _reject("local_date must be YYYY-MM-DD", 400)

    user = await db.get_or_create_user(int(telegram_id))
    day = explicit_day or db.local_date_for(
        dt.datetime.now(dt.timezone.utc), user["tz"], user["day_rollover_hour"]
    )

    activity_id, created = await db.record_activity(
        user["id"], day, kind, minutes=minutes, kcal_burned=kcal,
        intensity=intensity, rpe=rpe,
        note=(str(body["note"])[:500] if body.get("note") else None),
    )
    log.info("activity %s %s %s (%s)", user["id"], day, kind, "new" if created else "duplicate")
    return web.json_response(
        {"ok": True, "id": activity_id, "created": created, "local_date": day.isoformat()},
        status=201 if created else 200,
    )


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/activity", post_activity)
    return app


async def start(loop_runner: bool = True) -> web.AppRunner | None:
    if not TOKEN:
        log.warning(
            "NUTRAI_HTTP_TOKEN is not set — the activity endpoint stays off. "
            "Set it to enable posting workouts."
        )
        return None
    runner = web.AppRunner(build_app())
    await runner.setup()
    site = web.TCPSite(runner, BIND, PORT)
    await site.start()
    log.info("activity endpoint listening on %s:%s", BIND, PORT)
    return runner
