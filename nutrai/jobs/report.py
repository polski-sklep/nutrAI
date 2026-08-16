"""The weekly review, and the only scheduled job that calls a model.

Deliberately not in `jobs/notify.py`. Invariant 4 says summaries and
notifications are template-and-SQL only, and that stays true: the Sunday week
card in notify.py is still pure SQL and still arrives whatever happens here.
This is a second, separate artefact that says so about itself.

The model earns its cost here in a way it does not anywhere else in this
system, because the task is judgement under uncertainty rather than
extraction. It sees an evidence pack of medians, target comparisons, coverage
and measurement quality — never a raw log line — and it runs once a week.
"""

from __future__ import annotations

import logging

from apscheduler.triggers.cron import CronTrigger

from .. import db
from ..core import plan, render

log = logging.getLogger("nutrai.report")

# Below this many logged days in the last 28, there is nothing to review and
# an expensive model will confabulate a pattern out of four dinners.
MIN_DAYS_LOGGED = 10


async def weekly_report(bot) -> None:
    p = await db.pool()
    for u in await p.fetch("SELECT id, telegram_id, tz, day_rollover_hour FROM app_user"):
        import datetime as dt

        now = dt.datetime.now(dt.timezone.utc)
        day = db.local_date_for(now, u["tz"], u["day_rollover_hour"])
        logged = await p.fetchval(
            """SELECT count(DISTINCT local_date) FROM log_entry
                WHERE user_id=$1 AND status='confirmed' AND local_date > $2::date - 28""",
            u["id"], day,
        )
        if logged < MIN_DAYS_LOGGED:
            log.info("skipping report for %s: %s logged days", u["id"], logged)
            continue
        try:
            data, cost = await plan.propose(u["id"], day)
        except Exception as exc:
            log.warning("weekly report failed for %s: %s", u["telegram_id"], exc)
            continue
        try:
            await bot.send_message(
                u["telegram_id"], render.plan_card(data, cost), parse_mode="HTML")
        except Exception as exc:
            log.warning("weekly report send failed for %s: %s", u["telegram_id"], exc)


def schedule(sched, bot) -> None:
    # 18:00 Europe/Warsaw. The deterministic week card follows at 20:00, so the
    # judgement arrives first and the numbers behind it are still one tap away.
    sched.add_job(weekly_report, CronTrigger(day_of_week="sun", hour=16, minute=0),
                  args=[bot], id="weekly_report")
