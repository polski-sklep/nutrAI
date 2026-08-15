from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections import defaultdict
from html import escape
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from . import db
from .config import CONFIDENCE_FLOOR, settings
from .core import dsl, fasting, insight, render
from .core.nutrition import ResolvedComponent, total_nutrients
from .llm import parse as llm

log = logging.getLogger("nutrai")
dp = Dispatcher()

# Telegram delivers each photo of an album as its own update. Without this
# buffer, a four-photo meal becomes four meals.
_album: dict[str, list[Message]] = defaultdict(list)
_album_tasks: dict[str, asyncio.Task] = {}
ALBUM_WAIT = 1.2


def kb_confirm(entry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✓ log it", callback_data=f"ok:{entry_id}"),
                InlineKeyboardButton(text="✎ fix", callback_data=f"fix:{entry_id}"),
                InlineKeyboardButton(text="✕ discard", callback_data=f"no:{entry_id}"),
            ]
        ]
    )


async def _user(msg: Message) -> Any:
    if settings.allowed_ids and msg.from_user.id not in settings.allowed_ids:
        raise PermissionError("not allowed")
    return await db.get_or_create_user(msg.from_user.id, msg.from_user.full_name)


def _today(u: Any) -> dt.date:
    return db.local_date_for(dt.datetime.now(dt.timezone.utc), u["tz"], u["day_rollover_hour"])


# ---------------------------------------------------------------- commands


# The single source of truth for what this bot can do. `/start` renders it, the
# unknown-command handler renders it, and a test asserts every entry has a
# handler registered. That test exists because `/start` advertised `/improve`,
# `/targets` and `/week` for a while when none of the three had a handler, and
# typing them did nothing at all — aiogram matched nothing and dropped the
# message. Advertising a command you have not written is a bug you only find by
# reading, so it is now findable by running the tests instead.
COMMANDS: list[tuple[str, str]] = [
    ("/r", "repeat something you have eaten before"),
    ("/today", "where you stand · <code>/today all</code> for every nutrient"),
    ("/yesterday", "the same, for yesterday"),
    ("/fast", "current fast, duration and phase"),
    ("/window", "your eating window, midpoint and stability"),
    ("/f", "rate your focus now, e.g. <code>/f 8</code>"),
    ("/rate", "energy, mood, hunger, sleep or rpe — <code>/rate energy 6</code>"),
    ("/insight", "fat-loss rate and what the data actually supports"),
    ("/spend", "what this has cost in API calls"),
]


def command_list() -> str:
    return "\n".join(f"<code>{c}</code> {desc}" for c, desc in COMMANDS)


@dp.message(CommandStart())
async def start(msg: Message) -> None:
    await _user(msg)
    await msg.answer(
        "Send a photo of what you ate, or describe it in text.\n\n"
        + command_list()
        + "\n\nWeigh things when you can. A scale reading in the frame beats every "
        "visual estimate a model will ever make.",
        parse_mode="HTML",
    )


@dp.message(Command("r", "repeat"))
async def repeat_menu(msg: Message) -> None:
    u = await _user(msg)
    dishes = await db.top_dishes(u["id"], 8)
    if not dishes:
        await msg.answer("Nothing to repeat yet. Log something first.")
        return
    await db.put_pending(u["id"], "repeat_menu", {"ids": [d["id"] for d in dishes]})
    await msg.answer(render.repeat_menu(dishes), parse_mode="HTML")


@dp.message(Command("today"))
async def today(msg: Message) -> None:
    u = await _user(msg)
    await _send_day(msg, u, _today(u), show_all="all" in (msg.text or ""))


@dp.message(Command("yesterday"))
async def yesterday(msg: Message) -> None:
    u = await _user(msg)
    await _send_day(msg, u, _today(u) - dt.timedelta(days=1))


async def _send_day(msg: Message, u: Any, day: dt.date, show_all: bool = False) -> None:
    prog = await db.day_progress(u["id"], day, core_only=not show_all)
    entries = await db.day_entries(u["id"], day)
    conf = await db.day_mass_confidence(u["id"], day)
    sigma = await db.day_energy_sigma(u["id"], day)
    coverage = await db.day_coverage(u["id"], day)
    await msg.answer(
        render.day_card(
            day, prog, entries, show_all=show_all,
            pct_measured=float(conf["pct_measured"]) if conf and conf["pct_measured"] is not None else None,
            energy_sigma=sigma,
            coverage=coverage,
        ),
        parse_mode="HTML",
    )


@dp.message(Command("spend"))
async def spend(msg: Message) -> None:
    u = await _user(msg)
    rows = await db.spend_report(u["id"], 30)
    if not rows:
        await msg.answer("No model calls in the last 30 days.")
        return
    total = sum(float(r["usd"]) for r in rows)
    # Two decimals renders the entire point of this command as "$0.00". The
    # design target is ~$0.42 a month, so the interesting digits are the ones
    # $%.2f throws away.
    headline = f"${total:.2f}" if total >= 1 else f"{total*100:.2f}¢"
    lines = [f"<b>30 days: {headline}</b>", ""]
    # One <pre> for the whole table: the columns only line up inside a
    # single preformatted block.
    table = []
    for r in rows:
        table.append(
            f"{escape(r['purpose']):<20} {r['calls']:>4} calls  ${float(r['usd']):.3f}  "
            f"({r['tin']:,} in / {r['cached']:,} cached / {r['tout']:,} out)"
        )
    zero = await db.pool()
    n_free = await zero.fetchval(
        """SELECT count(*) FROM log_entry
            WHERE user_id = $1 AND model IS NULL AND status = 'confirmed'
              AND created_at >= now() - interval '30 days'""",
        u["id"],
    )
    lines.append("<pre>" + "\n".join(table) + "</pre>")
    lines.append(f"{n_free} entries logged without any model call.")
    await msg.answer("\n".join(lines), parse_mode="HTML")


# ------------------------------------------------------------------ fasting


@dp.message(Command("fast"))
async def fast_now(msg: Message) -> None:
    u = await _user(msg)
    h = await db.current_fast_hours(u["id"])
    if h <= 0:
        await msg.answer("Nothing logged yet, so there is no fast to measure.")
        return
    phase, gloss = fasting.phase_label(h)
    lines = [
        f"<b>{int(h)}h {int((h % 1) * 60):02d}m</b> since your last logged intake",
        f"phase: {escape(phase)} — {escape(gloss)}",
        "",
        "<i>A population-average timeline, not a measurement of you. Nothing here"
        " observes your respiratory quotient or your ketones, and a fasting"
        " phase is not a fat-loss rate — see /insight for that.</i>",
    ]
    await msg.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("window"))
async def window(msg: Message) -> None:
    u = await _user(msg)
    rows = await db.eating_windows(u["id"], 14)
    if len(rows) < 3:
        await msg.answer("Fewer than three days with two or more logged meals. Nothing to say yet.")
        return
    times = await db.meal_times(u["id"], 14)
    windows = [
        fasting.EatingWindow(
            r["local_date"], r["first_at"], r["last_at"], float(r["window_hours"]),
            r["midpoint_at"].time(), r["n_meals"],
        )
        for r in rows
    ]
    s = fasting.summarise(fasting.fasts_from(times), windows)
    # The figures are a column-aligned table, so they live in one <pre>.
    lines = [
        "<b>eating window, last 14 days</b>",
        "<pre>"
        + "\n".join(
            [
                f"median window        {s['median_window_h']} h",
                f"median overnight fast {s['median_overnight_fast_h']} h",
                f"longest fast         {s['longest_fast_h']} h",
                f"mean midpoint        {s['mean_midpoint']}  ({s['tre_class']})",
                f"midpoint variability ±{s['midpoint_sd_h']} h",
            ]
        )
        + "</pre>",
    ]
    if float(s["midpoint_sd_h"]) > 1.5:
        lines.append(
            "<i>Your window position moves more than an hour and a half day to day."
            " Window length is what people talk about; position is what the"
            " trials separate, and an unstable position is the harder problem.</i>"
        )
    elif s["tre_class"] == "late":
        lines.append(
            "<i>Late-positioned window. In the trial evidence early windows"
            " outrank late ones for fat mass at matched energy, though the"
            " margin is small and energy deficit is doing most of the work.</i>"
        )
    await msg.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("rate", "f"))
async def rate(msg: Message) -> None:
    """`/rate focus 8`, or `/f 8` for focus. Five seconds, and it is the only
    reason any question about timing can ever be answered."""
    u = await _user(msg)
    parts = (msg.text or "").split()[1:]
    kinds = {"focus", "energy", "mood", "hunger", "sleep", "rpe"}
    if len(parts) == 1 and parts[0].replace(".", "").isdigit():
        kind, value = "focus", float(parts[0])
    elif len(parts) >= 2 and parts[0].lower() in kinds:
        kind, value = parts[0].lower(), float(parts[1])
    else:
        await msg.answer(
            "<code>/rate focus 8</code> · <code>/rate energy 6</code> · "
            "<code>/rate rpe 9</code> · <code>/f 8</code> is focus\n"
            "Rate when you notice, not on a schedule. Ratings you invent at the"
            " end of the day are noise you will later mistake for signal.",
            parse_mode="HTML",
        )
        return
    h = await db.current_fast_hours(u["id"])
    await db.log_observation(
        u["id"], kind, value, tz=u["tz"], rollover_hour=u["day_rollover_hour"]
    )
    n = len(await db.observations(u["id"], kind))
    need = max(0, insight.MIN_PAIRS - n)
    tail = f" · {need} more before this can be analysed" if need else " · analysable"
    await msg.answer(f"{kind} {value:g} at {h:.1f}h fasted{tail}")


@dp.message(Command("insight"))
async def insight_cmd(msg: Message) -> None:
    u = await _user(msg)
    out: list[str] = []

    weights = await db.weight_series(u["id"], 42)
    energy = await db.daily_energy(u["id"], 42)
    flr = insight.fat_loss_rate(weights, energy)
    out.append("<b>fat loss</b>")
    if not flr:
        out.append(
            f"Need {insight.MIN_TREND_DAYS}+ days of weigh-ins spanning at least two weeks."
            f" You have {len(weights)}."
        )
    else:
        out.append(
            f"{flr.kg_per_week:+.2f} kg/week over {flr.days} days\n"
            f"implied energy balance {-flr.implied_deficit_kcal:+,.0f} kcal/day\n"
            f"median intake {flr.median_intake_kcal:,.0f} · implied TDEE {flr.implied_tdee_kcal:,.0f}"
        )
        if flr.note:
            out.append(f"<i>{escape(flr.note)}</i>")
        out.append(
            "<i>This is the only trustworthy answer to 'am I burning fat', and note"
            " that it contains no reference to when you ate.</i>"
        )

    for kind, label in (("focus", "focus vs hours fasted"), ("rpe", "session RPE vs hours fasted")):
        obs = await db.observations(u["id"], kind)
        out.append("")
        out.append(f"<b>{escape(label)}</b>")
        if not obs:
            out.append(
                f"No <code>{escape(kind)}</code> ratings logged. "
                f"<code>/rate {escape(kind)} 7</code>"
            )
            continue
        xs = [float(o["hours_fasted"]) for o in obs]
        ys = [float(o["value"]) for o in obs]
        clock = [o["observed_at"].hour + o["observed_at"].minute / 60 for o in obs]
        f = insight.correlate(label, xs, ys, clock_hours=clock)
        out.append(escape(f.verdict))
        if f.caveat:
            out.append(f"⚠ {escape(f.caveat)}")

    await msg.answer("\n".join(out), parse_mode="HTML")


# ------------------------------------------------------------------ photos


@dp.message(F.photo)
async def on_photo(msg: Message) -> None:
    gid = msg.media_group_id
    if not gid:
        await _handle_photos([msg])
        return
    _album[gid].append(msg)
    if gid in _album_tasks:
        _album_tasks[gid].cancel()
    _album_tasks[gid] = asyncio.create_task(_flush_album(gid))


async def _flush_album(gid: str) -> None:
    try:
        await asyncio.sleep(ALBUM_WAIT)
    except asyncio.CancelledError:
        return
    msgs = _album.pop(gid, [])
    _album_tasks.pop(gid, None)
    if msgs:
        await _handle_photos(msgs)


async def _handle_photos(msgs: list[Message]) -> None:
    msg = msgs[0]
    u = await _user(msg)
    bot: Bot = msg.bot
    caption = next((m.caption for m in msgs if m.caption), None)

    # The largest PhotoSize is the last element. Anything smaller loses the
    # scale display, which is the one thing worth reading precisely.
    images = []
    for m in msgs[:4]:
        f = await bot.get_file(m.photo[-1].file_id)
        buf = await bot.download_file(f.file_path)
        b64, w, h = llm.prepare_image(buf.read())
        images.append((b64, w, h, m.photo[-1].file_id))

    note = await msg.answer("reading…")
    parsed = await llm.parse_photo(images[0][0], caption, user_id=u["id"])
    for extra in images[1:]:
        more = await llm.parse_photo(extra[0], caption, user_id=u["id"], escalate=False)
        parsed.items.extend(more.items)
        parsed.cost_usd += more.cost_usd

    await _present(msg, u, parsed, source="photo", photo_file_id=images[0][3], edit=note)


# -------------------------------------------------------------------- text


@dp.message(F.text & ~F.text.startswith("/"))
async def on_text(msg: Message) -> None:
    u = await _user(msg)
    text = (msg.text or "").strip()

    cmd = dsl.parse(text)
    if cmd and await _try_repeat(msg, u, cmd):
        return

    note = await msg.answer("parsing…")
    parsed = await llm.parse_text(text, user_id=u["id"])
    await _present(msg, u, parsed, source="text", photo_file_id=None, edit=note)


async def _try_repeat(msg: Message, u: Any, cmd: dsl.RepeatCommand) -> bool:
    """The zero-token path. Returns False if this was not a repeat after all."""
    dish = None
    if cmd.selector_kind == "index":
        menu = await db.latest_pending(u["id"], "repeat_menu")
        if not menu:
            return False
        idx = int(cmd.selector) - 1
        ids = menu.get("ids", [])
        if not (0 <= idx < len(ids)):
            return False
        p = await db.pool()
        dish = await p.fetchrow("SELECT * FROM dish WHERE id = $1", ids[idx])
    else:
        tpl = await db.template_by_slug(u["id"], cmd.selector)
        if tpl:
            await _log_template(msg, u, tpl, cmd)
            return True
        dish = await db.dish_by_slug(u["id"], cmd.selector)

    if not dish:
        return False

    rows = await db.dish_components(dish["id"])
    comps = [
        dsl.Component(r["label"], r["fdc_id"], float(r["grams"]), r["state"], float(r["yield_factor"]))
        for r in rows
    ]

    ops = list(cmd.ops)
    model_used = None
    if cmd.needs_model:
        # One cheap call, and it sees only the label list and the phrase.
        data = await llm.modifier_ops(
            [c.label for c in comps], " ".join(cmd.unparsed), user_id=u["id"]
        )
        model_used = "modifier"
        for o in data.get("operations", []):
            op, label = o.get("op"), (o.get("label") or "").lower()
            if op == "drop":
                ops.append(dsl.DropComponent(label))
            elif op == "set" and o.get("grams"):
                ops.append(dsl.SetComponent(label, float(o["grams"])))
            elif op == "add":
                ops.append(dsl.AddComponent(label, float(o["grams"]) if o.get("grams") else None))
            elif op == "scale_all" and o.get("factor"):
                ops.append(dsl.Scale(float(o["factor"])))

    new_comps, unresolved = dsl.apply(comps, ops)

    for add in unresolved:
        alias = await db.resolve_alias(u["id"], add.label)
        if alias:
            grams = add.grams or float(alias["default_grams"] or 100)
            new_comps.append(dsl.Component(add.label, alias["fdc_id"], grams, grams_source="stated"))
        else:
            res = await llm.resolve_items(
                u["id"],
                [{"label": add.label, "search_terms": add.label,
                  "grams": add.grams or 100, "grams_source": "stated", "state": "unknown",
                  "confidence": 0.7}],
            )
            for c in res.components:
                new_comps.append(dsl.Component(c.label, c.fdc_id, c.grams, yield_factor=c.yield_factor))

    when = dt.datetime.now(dt.timezone.utc)
    slot = dish["default_slot"]
    for op in ops:
        if isinstance(op, dsl.SetTime):
            import zoneinfo

            tz = zoneinfo.ZoneInfo(u["tz"])
            local = dt.datetime.now(tz).replace(hour=op.hour, minute=op.minute, second=0, microsecond=0)
            when = local.astimezone(dt.timezone.utc)
        elif isinstance(op, dsl.SetSlot):
            slot = op.slot

    resolved = [ResolvedComponent(c.label, c.fdc_id, c.grams, c.yield_factor) for c in new_comps if c.fdc_id]
    entry_id = await db.create_pending_entry(
        u["id"], dish["name"], resolved, source="repeat", slot=slot, confidence=None,
        model=model_used, parse={"ops": [str(o) for o in ops]}, photo_file_id=None,
        dish_id=dish["id"], when=when, tz=u["tz"], rollover_hour=u["day_rollover_hour"],
        grams_sources=[c.grams_source for c in new_comps if c.fdc_id],
    )

    # An unmodified repeat of a dish you have confirmed before is not a claim
    # about the world that needs re-checking. It logs immediately.
    if not ops and not cmd.needs_model:
        totals = await db.confirm_entry(entry_id)
        await msg.answer(
            f"✓ {dish['name']} — {totals.get(1008,0):,.0f} kcal, "
            f"{totals.get(1003,0):.0f} g protein",
        )
        await _check_thresholds(msg, u)
        return True

    profs = await db.profiles_for([c.fdc_id for c in resolved])
    totals = total_nutrients(resolved, profs)
    await msg.answer(
        render.confirm_card(dish["name"], new_comps, totals, confidence=None, warnings=[]),
        parse_mode="HTML",
        reply_markup=kb_confirm(entry_id),
    )
    return True


async def _log_template(msg: Message, u: Any, tpl: tuple[Any, list[Any]], cmd: dsl.RepeatCommand) -> None:
    t, items = tpl
    logged = []
    for item in items:
        sub = dsl.RepeatCommand(selector=str(item["slug"]), selector_kind="slug", ops=list(cmd.ops))
        ok = await _try_repeat(msg, u, sub)
        if ok:
            logged.append(item["name"])
    await msg.answer(f"✓ {t['name']}: {', '.join(logged)}")


# ---------------------------------------------------------------- presenting


async def _present(
    msg: Message, u: Any, parsed: llm.ParsedMeal, *, source: str,
    photo_file_id: str | None, edit: Message | None = None,
) -> None:
    res = await llm.resolve_items(u["id"], parsed.items)
    if not res.components:
        await (edit or msg).edit_text(
            "I could not match anything in that to the food database. "
            "Name the ingredients plainly and I will try again."
        )
        return

    verdict = await llm.validate(res.components, parsed)
    profs = await db.profiles_for([c.fdc_id for c in res.components])
    totals = total_nutrients(res.components, profs)

    slug = _slugify(parsed.dish_name)
    dish_id = await db.upsert_dish(u["id"], slug, parsed.dish_name, parsed.slot, res.components)

    entry_id = await db.create_pending_entry(
        u["id"], parsed.dish_name, res.components, source=source, slot=parsed.slot,
        confidence=parsed.confidence, model=parsed.model, parse=parsed.raw,
        photo_file_id=photo_file_id, dish_id=dish_id, tz=u["tz"],
        rollover_hour=u["day_rollover_hour"], grams_sources=res.grams_sources,
    )

    warnings = list(verdict.warnings)
    if parsed.confidence < CONFIDENCE_FLOOR:
        warnings.insert(0, f"low overall confidence ({parsed.confidence:.0%}) — check the masses")
    if res.unresolved:
        warnings.append("not matched: " + ", ".join(res.unresolved))
    for note in res.prior_notes or []:
        warnings.append(note)

    text = render.confirm_card(
        parsed.dish_name, res.components, totals,
        confidence=parsed.confidence, warnings=warnings, notes=parsed.notes,
        cost_usd=parsed.cost_usd + res.cost_usd,
    )
    if edit:
        await edit.edit_text(text, parse_mode="HTML", reply_markup=kb_confirm(entry_id))
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb_confirm(entry_id))


def _slugify(name: str) -> str:
    import re

    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:32] or "dish"


# ------------------------------------------------------- unknown commands
# Registered after every other message handler, so it catches only what nothing
# else claimed. aiogram walks handlers in registration order and stops at the
# first match; without a terminal case an unrecognised `/command` matches
# nothing and is discarded in silence, which from the other side of the screen
# is indistinguishable from the bot being down.


@dp.message(F.text.startswith("/"))
async def unknown_command(msg: Message) -> None:
    await _user(msg)
    typed = (msg.text or "").split()[0]
    await msg.answer(
        f"{escape(typed)} is not a command here.\n\n" + command_list(),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------- callbacks


@dp.callback_query(F.data.startswith("ok:"))
async def cb_ok(cq: CallbackQuery) -> None:
    entry_id = int(cq.data.split(":")[1])
    totals = await db.confirm_entry(entry_id)
    await cq.message.edit_text(
        (cq.message.text or "") + f"\n\n✓ logged — {totals.get(1008,0):,.0f} kcal"
    )
    await cq.answer("logged")
    u = await db.get_or_create_user(cq.from_user.id)
    await _check_thresholds(cq.message, u)


@dp.callback_query(F.data.startswith("no:"))
async def cb_no(cq: CallbackQuery) -> None:
    await db.discard_entry(int(cq.data.split(":")[1]))
    await cq.message.edit_text((cq.message.text or "") + "\n\n✕ discarded")
    await cq.answer("discarded")


@dp.callback_query(F.data.startswith("fix:"))
async def cb_fix(cq: CallbackQuery) -> None:
    entry_id = int(cq.data.split(":")[1])
    e, comps = await db.entry_with_components(entry_id)
    lines = [
        (
            "Reply with the correction, e.g. <code>rice 200</code> or "
            "<code>-oil</code> or <code>x0.8</code>."
        ),
        "",
    ]
    for c in comps:
        lines.append(f"<code>{escape(c['label'])}</code> {float(c['grams']):.0f} g")
    await db.put_pending(e["user_id"], "fix_entry", {"entry_id": entry_id})
    await cq.message.answer("\n".join(lines), parse_mode="HTML")
    await cq.answer()


# ------------------------------------------------------------ notifications


async def _check_thresholds(msg: Message, u: Any) -> None:
    """Fires immediately after a write, in addition to the scheduled sweep.

    'You have consumed 80% of your carbs' is only useful before the next meal,
    not at the next 15-minute tick."""
    from .jobs.notify import evaluate_user

    for text in await evaluate_user(u["id"], _today(u)):
        await msg.answer(text)


async def resend_unformatted(make_request, bot: Bot, method):
    """Retry once without parse_mode when Telegram rejects the markup.

    Outbound messages are HTML, escaped with `html.escape`, which should make
    this unreachable — that is the point of having moved off Markdown. It stays
    because the cost of being wrong is asymmetric: an unbalanced tag gets the
    whole message rejected with HTTP 400, and the user experiences that as the
    bot silently ignoring them. For a confirmation card that is the worst
    available outcome, because the entry is already sitting in `pending`.

    Delivering the same text unformatted is strictly better than delivering
    nothing. The warning is there so an escaping bug shows up in the logs as a
    repeated line rather than as an app that "sometimes doesn't reply".
    """
    from aiogram.exceptions import TelegramBadRequest

    try:
        return await make_request(bot, method)
    except TelegramBadRequest as exc:
        if "parse entities" not in str(exc).lower() or getattr(method, "parse_mode", None) is None:
            raise
        log.warning("markup rejected by Telegram, resending as plain text: %s", exc)
        return await make_request(bot, method.model_copy(update={"parse_mode": None}))


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(settings.telegram_token)
    bot.session.middleware(resend_unformatted)
    from .jobs.notify import start_scheduler

    start_scheduler(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())
