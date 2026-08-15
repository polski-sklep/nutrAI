from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .. import db
from ..core import render

log = logging.getLogger("nutrai.notify")


async def evaluate_user(user_id: int, day: dt.date) -> list[str]:
    """Evaluate every enabled threshold rule for one user against one day.

    Pure SQL and string formatting. No model, no cost, no latency, and no way
    for the text to disagree with the number it is reporting.
    """
    p = await db.pool()
    rules = await p.fetch(
        """SELECT r.*, n.name AS nutrient_name, n.unit
             FROM notification_rule r JOIN nutrient n ON n.id = r.nutrient_id
            WHERE r.user_id = $1 AND r.enabled AND r.kind = 'threshold'""",
        user_id,
    )
    if not rules:
        return []

    prog = {r["nutrient_id"]: r for r in await p.fetch("SELECT * FROM day_progress($1,$2)", user_id, day)}
    out: list[str] = []

    # Which rules actually crossed, and by how much.
    crossed: list[tuple[Any, float, float]] = []
    for rule in rules:
        row = prog.get(rule["nutrient_id"])
        if not row:
            continue
        amount = float(row["amount"])
        direction = rule["direction"]
        target = row["max_amount"] if direction == "over" else row["min_amount"]
        if not target:
            continue
        pct = amount / float(target) * 100
        hit = (
            pct >= float(rule["threshold_pct"])
            if direction == "over"
            else pct <= float(rule["threshold_pct"])
        )
        if hit:
            crossed.append((rule, amount, pct))

    # Of the ones that crossed, only the tightest per nutrient and direction.
    #
    # bootstrap seeds energy at 80% and 100%. At 113% both cross, both render
    # from the same amount against the same target, and the text does not say
    # which threshold fired — so the identical sentence arrives twice, seconds
    # apart. The 80% warning has nothing left to tell you once you are past
    # 100%. Deduped *after* the crossing test, not before: at 85% the 100% rule
    # has not fired and the 80% one is the whole message.
    best: dict[tuple[int, str], tuple[Any, float, float]] = {}
    for rule, amount, pct in crossed:
        key = (rule["nutrient_id"], rule["direction"])
        prev = best.get(key)
        if prev is None:
            best[key] = (rule, amount, pct)
            continue
        tighter = float(rule["threshold_pct"]) > float(prev[0]["threshold_pct"])
        if tighter if rule["direction"] == "over" else not tighter:
            best[key] = (rule, amount, pct)

    for rule, amount, pct in best.values():
        direction = rule["direction"]
        row = prog[rule["nutrient_id"]]
        target = float(row["max_amount"] if direction == "over" else row["min_amount"])

        recent = await p.fetchval(
            """SELECT max(sent_at) FROM notification_log
                WHERE rule_id = $1 AND local_date = $2""",
            rule["id"], day,
        )
        if recent and (dt.datetime.now(dt.timezone.utc) - recent).total_seconds() < rule["cooldown_minutes"] * 60:
            continue

        text = rule["template"] or render.threshold_message(
            rule["nutrient_name"], amount, target, rule["unit"], direction,
            nutrient_id=rule["nutrient_id"],
        )
        await p.execute(
            "INSERT INTO notification_log (rule_id, user_id, local_date, payload) VALUES ($1,$2,$3,$4)",
            rule["id"], user_id, day, f'{{"pct": {pct:.1f}}}',
        )
        out.append(text)

    return out


async def sweep(bot) -> None:
    """Periodic pass. Catches 'under' rules, which a write can never trigger:
    the reason you missed your protein floor is that you stopped eating."""
    p = await db.pool()
    users = await p.fetch("SELECT id, telegram_id, tz, day_rollover_hour FROM app_user")
    now = dt.datetime.now(dt.timezone.utc)
    for u in users:
        day = db.local_date_for(now, u["tz"], u["day_rollover_hour"])
        for text in await evaluate_user(u["id"], day):
            try:
                await bot.send_message(u["telegram_id"], text, parse_mode="HTML")
            except Exception as exc:  # a blocked bot must not kill the sweep
                log.warning("notify failed for %s: %s", u["telegram_id"], exc)


async def daily_summary(bot) -> None:
    p = await db.pool()
    users = await p.fetch("SELECT id, telegram_id, tz, day_rollover_hour FROM app_user")
    now = dt.datetime.now(dt.timezone.utc)
    for u in users:
        day = db.local_date_for(now, u["tz"], u["day_rollover_hour"])
        prog = await db.day_progress(u["id"], day)
        entries = await db.day_entries(u["id"], day)
        coverage = await db.day_coverage(u["id"], day)
        try:
            await bot.send_message(
                u["telegram_id"],
                render.day_card(day, prog, entries, coverage=coverage, tz=u["tz"]),
                parse_mode="HTML",
            )
        except Exception as exc:
            log.warning("summary failed for %s: %s", u["telegram_id"], exc)


def start_scheduler(bot) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(sweep, "interval", minutes=20, args=[bot], id="sweep")
    # 21:00 Europe/Warsaw. Move this to a per-user job once there is more than
    # one user; a single cron is honest for a single-user deployment.
    sched.add_job(daily_summary, CronTrigger(hour=19, minute=0), args=[bot], id="daily")
    # After the summary, so a bad match is flagged while the day is still in
    # mind and the entry is still easy to recognise.
    from .audit import audit_and_report

    sched.add_job(audit_and_report, CronTrigger(hour=19, minute=5), args=[bot], id="audit")
    sched.start()
    return sched
