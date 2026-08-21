from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .. import db
from ..core import render

log = logging.getLogger("nutrai.notify")

# "Under" rules do not fire before this local hour.
#
# A floor is not assessable at breakfast. At 09:17 you are at 4% of a daily
# protein floor because you have had two coffees, and saying so is the same
# category error as counting an unbreached ceiling as an achievement: it
# describes the hour, not the eating. Late enough that a shortfall is real,
# early enough that there is still a meal left to fix it with.
UNDER_RULES_FROM_HOUR = 16

# Nothing is sent between these local hours.
#
# The day does not end at midnight here — day_rollover_hour is 04:00, so a
# ceiling crossed at dinner stays crossed and the sweep kept re-announcing it
# at 23:30, 01:30 and 03:30. Every one of those was true and none was useful:
# a notification you can act on is one that arrives while you can still decide
# what to eat.
QUIET_FROM_HOUR = 22
QUIET_UNTIL_HOUR = 7


async def evaluate_user(user_id: int, day: dt.date, *, now: dt.datetime | None = None) -> list[str]:
    """Evaluate every enabled threshold rule for one user against one day.

    Pure SQL and string formatting. No model, no cost, no latency, and no way
    for the text to disagree with the number it is reporting.
    """
    import zoneinfo

    p = await db.pool()
    user = await p.fetchrow("SELECT tz FROM app_user WHERE id = $1", user_id)
    local_hour = (now or dt.datetime.now(dt.timezone.utc)).astimezone(
        zoneinfo.ZoneInfo(user["tz"] if user else "UTC")
    ).hour

    if local_hour >= QUIET_FROM_HOUR or local_hour < QUIET_UNTIL_HOUR:
        return []

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
        if rule["direction"] == "under" and local_hour < UNDER_RULES_FROM_HOUR:
            continue
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


async def supplement_reminders(bot) -> None:
    """Nudge each supplement moment once, at its own local time.

    Template and SQL only, like every other notification here — invariant 4.

    Fires only when something in that slot is still unlogged, and records the
    send so a ten-minute sweep cannot repeat it. A reminder that arrives when
    there is nothing to do is how a useful notification becomes one you mute.
    """
    import zoneinfo

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    p = await db.pool()
    now = dt.datetime.now(dt.timezone.utc)
    for u in await p.fetch("SELECT id, telegram_id, tz, day_rollover_hour FROM app_user"):
        times = await db.slot_times(u["id"])
        if not times:
            continue
        local = now.astimezone(zoneinfo.ZoneInfo(u["tz"]))
        day = db.local_date_for(now, u["tz"], u["day_rollover_hour"])
        for slot, when in times.items():
            # Past its time today, and not so far past that the nudge is noise.
            due_at = local.replace(hour=when.hour, minute=when.minute,
                                   second=0, microsecond=0)
            if not (dt.timedelta(0) <= local - due_at <= dt.timedelta(hours=3)):
                continue
            if await db.reminder_already_sent(u["id"], slot, day):
                continue
            rows = await db.supplements_in_slot(u["id"], slot, day)
            # Anything deferred earlier today comes with it. Without this the
            # only way a "not yet" could be honoured was for the user to
            # remember unprompted, which is what the reminder exists to avoid.
            carried = await db.deferred_supplements(u["id"], day, slot)
            if not (rows and not all(r["logged"] for r in rows)) and not carried:
                continue
            # Claim the slot before sending: a send that fails should not be
            # retried into a second notification a few minutes later.
            if not await db.mark_reminder_sent(u["id"], slot, day):
                continue
            try:
                await bot.send_message(
                    u["telegram_id"],
                    render.supplement_reminder_card(slot, rows, carried),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ all taken",
                                                 callback_data=f"slotlog:{slot}"),
                            InlineKeyboardButton(text="not yet",
                                                 callback_data=f"slotskip:{slot}"),
                        ],
                        [InlineKeyboardButton(text="☑️ tick the ones I took",
                                              callback_data="suppick:")],
                    ]),
                )
            except Exception as exc:
                log.warning("supplement reminder failed for %s: %s", u["telegram_id"], exc)


async def morning_notes(bot) -> None:
    """Good morning, half an hour before you are usually up.

    Template and SQL only, like everything else in this module. The one line
    of judgement it contains — which excess to mention — is a fixed ordering
    over yesterday's own numbers, not a model's opinion of them.
    """
    import zoneinfo

    p = await db.pool()
    now = dt.datetime.now(dt.timezone.utc)
    for u in await p.fetch(
        """SELECT id, telegram_id, tz, day_rollover_hour, display_name,
                  wake_hour, morning_note FROM app_user"""
    ):
        if not u["morning_note"]:
            continue
        wake = u["wake_hour"]
        if wake is None:
            wake = await db.wake_hour_estimate(u["id"], u["tz"])
        if wake is None:
            continue   # not told, and not enough history to have learned

        local = now.astimezone(zoneinfo.ZoneInfo(u["tz"]))
        send_at = (local.replace(hour=int(wake), minute=0, second=0, microsecond=0)
                   - dt.timedelta(minutes=30))
        # A greeting three hours late is not a greeting.
        if not (dt.timedelta(0) <= local - send_at <= dt.timedelta(hours=2)):
            continue

        day = db.local_date_for(now, u["tz"], u["day_rollover_hour"])
        if not await db.morning_note_sent(u["id"], day):
            continue

        yday = day - dt.timedelta(days=1)
        try:
            await bot.send_message(
                u["telegram_id"],
                render.morning_note(
                    u["display_name"],
                    await db.day_progress(u["id"], yday),
                    await db.day_coverage(u["id"], yday),
                ),
                parse_mode="HTML",
            )
        except Exception as exc:
            log.warning("morning note failed for %s: %s", u["telegram_id"], exc)


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


async def weekly_summary(bot) -> None:
    """Sunday evening. Silent for a week with nothing in it."""
    p = await db.pool()
    now = dt.datetime.now(dt.timezone.utc)
    for u in await p.fetch("SELECT id, telegram_id, tz, day_rollover_hour FROM app_user"):
        day = db.local_date_for(now, u["tz"], u["day_rollover_hour"])
        rows = await db.week_rows(u["id"], day)
        if not rows:
            continue
        try:
            await bot.send_message(
                u["telegram_id"],
                render.week_card(rows, await db.week_context(u["id"], day)),
                parse_mode="HTML",
            )
        except Exception as exc:
            log.warning("weekly failed for %s: %s", u["telegram_id"], exc)


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
    # Every ten minutes so a reminder lands near its time rather than up to
    # twenty minutes after it. The once-per-slot-per-day record is what makes
    # a frequent sweep safe.
    sched.add_job(supplement_reminders, "interval", minutes=10, args=[bot],
                  id="supp_reminders")
    # Same cadence: the note has to land near a time that differs per person
    # and moves as the wake estimate does, so a cron hour cannot express it.
    sched.add_job(morning_notes, "interval", minutes=10, args=[bot],
                  id="morning_notes")
    # 21:00 Europe/Warsaw. Move this to a per-user job once there is more than
    # one user; a single cron is honest for a single-user deployment.
    sched.add_job(daily_summary, CronTrigger(hour=19, minute=0), args=[bot], id="daily")
    # After the summary, so a bad match is flagged while the day is still in
    # mind and the entry is still easy to recognise.
    from .audit import audit_and_report

    sched.add_job(audit_and_report, CronTrigger(hour=19, minute=5), args=[bot], id="audit")
    # Sunday 20:00 Europe/Warsaw, after the day's summary and the audit, when
    # the week is as complete as it is going to get.
    sched.add_job(
        weekly_summary, CronTrigger(day_of_week="sun", hour=18, minute=0),
        args=[bot], id="weekly",
    )
    # The one scheduled job that calls a model, kept in its own module so this
    # one stays template-and-SQL only — invariant 4.
    from .report import schedule as schedule_report

    schedule_report(sched, bot)
    sched.start()
    return sched
