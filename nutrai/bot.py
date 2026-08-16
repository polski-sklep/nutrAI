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
from .core import dsl, estimate, fasting, insight, render
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
                InlineKeyboardButton(text="✅ log it", callback_data=f"ok:{entry_id}"),
                InlineKeyboardButton(text="✏️ fix", callback_data=f"fix:{entry_id}"),
                InlineKeyboardButton(text="🗑 discard", callback_data=f"no:{entry_id}"),
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
    ("/rate", "rate focus, energy, mood, hunger, sleep or rpe"),
    ("/weight", "log a weigh-in, e.g. <code>/weight 78.2</code>"),
    ("/supp", "log today's supplement stack · <code>/supp add</code> to set one up"),
    ("/undo", "unlog the last thing you logged today"),
    ("/week", "the last seven days: excesses, shortfalls, how much to trust it"),
    ("/audit", "check the last week's entries for wrong matches"),
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
            tz=u["tz"],
        ),
        parse_mode="HTML",
    )


@dp.message(Command("week"))
async def week(msg: Message) -> None:
    """The last seven days, on demand. Sent unprompted on Sunday evening."""
    u = await _user(msg)
    day = _today(u)
    await msg.answer(
        render.week_card(await db.week_rows(u["id"], day), await db.week_context(u["id"], day)),
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


RATE_KINDS: dict[str, tuple[str, str]] = {
    "focus": ("🧠", "how sharp you feel right now"),
    "energy": ("⚡", "physical energy, not mood"),
    "mood": ("🙂", "how you feel in yourself"),
    "hunger": ("🍽", "how hungry, 1 full to 10 ravenous"),
    "sleep": ("😴", "last night's sleep quality"),
    "rpe": ("🏋", "how hard the session felt, 1 easy to 10 maximal"),
}


def _rate_kind_keyboard() -> InlineKeyboardMarkup:
    kinds = list(RATE_KINDS.items())
    rows = [
        [InlineKeyboardButton(text=f"{icon} {k}", callback_data=f"ratek:{k}")
         for k, (icon, _) in kinds[i:i + 3]]
        for i in range(0, len(kinds), 3)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _rate_value_keyboard(kind: str) -> InlineKeyboardMarkup:
    """A keypad, because the friction is the point of failure.

    `/rate energy 6` is three words and a number on a phone keyboard, at the
    moment you noticed something worth recording. Ratings you have to stop and
    type are ratings you postpone, and a rating invented later is the noise the
    whole refusal gate exists to keep out of the correlation.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(n), callback_data=f"ratev:{kind}:{n}") for n in range(1, 6)],
        [InlineKeyboardButton(text=str(n), callback_data=f"ratev:{kind}:{n}") for n in range(6, 11)],
    ])


@dp.message(Command("rate"))
async def rate(msg: Message) -> None:
    """`/rate` to choose a kind, then tap or type a number.

    Focus had its own `/f` shortcut, inherited from when ratings were typed and
    `/f 8` was meaningfully shorter than `/rate focus 8`. With a keypad it saved
    one tap on one of six kinds, which is not enough to justify privileging one
    outcome variable over the others in the command list."""
    u = await _user(msg)
    args = (msg.text or "").split()[1:]

    kind, value = None, None
    if args and args[0].lower() in RATE_KINDS:
        kind = args[0].lower()
        if len(args) > 1 and args[1].replace(".", "").isdigit():
            value = float(args[1])
    elif args and args[0].replace(".", "").isdigit():
        kind, value = "focus", float(args[0])

    if kind and value is not None:
        await _record_rating(msg, u, kind, value)
        return
    if kind:
        icon, gloss = RATE_KINDS[kind]
        # A bare number is also the repeat selector, so record which kind is
        # waiting for one. Without this, showing a 1-10 keypad and then typing
        # "4" pulled up dish 4 from the /r menu instead — the keypad invites a
        # number and the grammar had already claimed it.
        await db.put_pending(u["id"], "rate_await", {"kind": kind})
        await msg.answer(
            f"{icon} <b>{kind}</b> — {gloss}\n"
            f"<i>1 lowest, 10 highest. Tap one, or just type the number.</i>",
            parse_mode="HTML",
            reply_markup=_rate_value_keyboard(kind),
        )
        return

    await msg.answer(
        "📊 <b>What are you rating?</b>\n\n"
        "<i>Rate when you notice, not on a schedule. A rating invented at the "
        "end of the day is noise you will later mistake for signal.</i>",
        parse_mode="HTML",
        reply_markup=_rate_kind_keyboard(),
    )


@dp.callback_query(F.data.startswith("ratek:"))
async def cb_rate_kind(cq: CallbackQuery) -> None:
    kind = cq.data.split(":")[1]
    icon, gloss = RATE_KINDS.get(kind, ("📊", ""))
    u = await db.get_or_create_user(cq.from_user.id)
    await db.put_pending(u["id"], "rate_await", {"kind": kind})
    await cq.answer()
    await cq.message.edit_text(
        f"{icon} <b>{kind}</b> — {gloss}\n<i>1 lowest, 10 highest.</i>",
        parse_mode="HTML",
        reply_markup=_rate_value_keyboard(kind),
    )


@dp.callback_query(F.data.startswith("ratev:"))
async def cb_rate_value(cq: CallbackQuery) -> None:
    _, kind, value = cq.data.split(":")
    u = await db.get_or_create_user(cq.from_user.id)
    await db.clear_pending(u["id"], "rate_await")
    await cq.answer("recorded")
    await cq.message.edit_text(
        await _rating_text(u, kind, float(value)), parse_mode="HTML"
    )


async def _record_rating(msg: Message, u: Any, kind: str, value: float) -> None:
    await msg.answer(await _rating_text(u, kind, value), parse_mode="HTML")


async def _rating_text(u: Any, kind: str, value: float) -> str:
    """Log it and say what it bought.

    The old reply was "focus 9 at 4.8h fasted · 19 more before this can be
    analysed", which reads as a rebuke. The gate is real — a correlation on ten
    points is noise — but the useful framing is how far along you are, not how
    far short.
    """
    h = await db.current_fast_hours(u["id"])
    await db.log_observation(
        u["id"], kind, value, tz=u["tz"], rollover_hour=u["day_rollover_hour"]
    )
    obs = await db.observations(u["id"], kind)
    n = len(obs)
    icon, _gloss = RATE_KINDS.get(kind, ("📊", ""))

    lines = [f"{icon} <b>{kind} {value:g}</b> · {h:.1f}h since you last ate"]
    if n >= insight.MIN_PAIRS:
        lines.append(f"📈 {n} ratings — <code>/insight</code> can analyse this.")
    else:
        done = "▓" * n + "░" * (insight.MIN_PAIRS - n)
        lines.append(f"<code>{done}</code> {n}/{insight.MIN_PAIRS} before this can be analysed")
    if n >= 3:
        recent = ", ".join(f"{float(o['value']):g}" for o in obs[-5:])
        lines.append(f"<i>last few: {recent}</i>")
    return "\n".join(lines)


@dp.message(Command("weight", "w"))
async def weight(msg: Message) -> None:
    """`/weight 78.2`.

    The only input path to `body_metric`, and therefore the only thing that
    makes `/insight` capable of answering anything. Mifflin-St Jeor is a ±10%
    population estimate; the slope of your own weight against date is the one
    energy-balance instrument you actually own, and it needs feeding.
    """
    u = await _user(msg)
    parts = (msg.text or "").replace(",", ".").split()[1:]
    try:
        kg = float(parts[0])
    except (IndexError, ValueError):
        await msg.answer(
            "⚖️ <code>/weight 78.2</code> — weigh yourself at the same time of day, "
            "ideally before breakfast.",
            parse_mode="HTML",
        )
        return

    # A fat-fingered 782 for 78.2 would bend the regression for weeks and never
    # look wrong in a list. Refuse the impossible rather than store it.
    if not 20 <= kg <= 400:
        await msg.answer(
            f"⚖️ {kg:g} kg is outside anything I will record. Nothing was saved.",
            parse_mode="HTML",
        )
        return

    _id, prev = await db.log_body_metric(
        u["id"], "weight_kg", kg, tz=u["tz"], rollover_hour=u["day_rollover_hour"]
    )

    lines = [f"⚖️ <b>{kg:g} kg</b> recorded."]
    if prev is not None:
        delta = kg - prev
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "▬"
        lines.append(f"   {arrow} {delta:+.1f} kg since your last weigh-in ({prev:g} kg)")
        if abs(delta) >= 3:
            lines.append(
                "   ⚠️ That is a large jump. Day-to-day swings are mostly water and "
                "gut content — if it was a typo, send the right number and I will "
                "use the later reading."
            )

    span = await db.weight_span_days(u["id"])
    need = insight.MIN_TREND_DAYS - span
    if need > 0:
        lines += [
            "",
            f"📈 {need} more day{'s' if need != 1 else ''} of weigh-ins before "
            "<code>/insight</code> can estimate a rate. Glycogen and water swamp "
            "fat over anything shorter.",
        ]
    else:
        lines += ["", "📈 <code>/insight</code> has enough to work with."]
    await msg.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("supp", "supplements"))
async def supp(msg: Message) -> None:
    """`/supp` logs today's stack · `/supp list` shows it · `/supp add` + photo.

    Logging is a deliberate daily act rather than an assumption. A stack you
    usually take is not a stack you always took, and the difference is a
    micronutrient total nobody confirmed — invariant 5 applies to a capsule
    exactly as it applies to a meal.
    """
    u = await _user(msg)
    arg = (msg.text or "").split(maxsplit=1)
    sub = arg[1].strip().lower() if len(arg) > 1 else ""
    day = _today(u)
    stack = await db.supplement_stack(u["id"])

    if sub.startswith("add"):
        await db.put_pending(u["id"], "supp_label", {"awaiting": True})
        await msg.answer(
            "📸 Send a photo of the supplement's nutrition panel.\n\n"
            "<i>Get the whole panel in frame and in focus. I transcribe what is "
            "printed — I will not fill in what I think the product contains.</i>",
            parse_mode="HTML",
        )
        return

    if not stack:
        await msg.answer(
            "No supplements set up yet. <code>/supp add</code>, then send a photo "
            "of the label.",
            parse_mode="HTML",
        )
        return

    if sub.startswith("list"):
        await msg.answer(render.supplement_stack_card(stack), parse_mode="HTML")
        return

    if sub.startswith(("skip", "clear", "none")):
        n = await db.unlog_supplements(u["id"], day)
        await msg.answer(f"Cleared {n} supplement record(s) for today.")
        return

    # Ask rather than assume, and pre-tick by each supplement's own cadence:
    # daily always, alternate only when yesterday was a rest day, occasional
    # never. Anything already logged today stays ticked.
    today_names = {r["name"] for r in await db.supplements_logged_on(u["id"], day)}
    selected = [s["id"] for s in stack if s["name"] in today_names]
    if not selected:
        selected = await db.supplements_due(u["id"], day)

    action_id = await db.put_pending(u["id"], "supp_pick", {
        "selected": selected, "day": day.isoformat(),
    })
    await msg.answer(
        render.supplement_pick_card(stack, selected),
        parse_mode="HTML",
        reply_markup=_supp_keyboard(action_id, stack, selected),
    )



def _button_label(sup: Any) -> str:
    """Names are the substance now — "Chelated Magnesium", not "HSN
    EssentialSeries Chelated Magnesium" — so this rarely has to do anything.
    Kept as a guard, trimming the front so the substance survives if it ever
    does: truncating the tail is what hid the word "Magnesium" entirely."""
    name = sup["name"]
    return name if len(name) <= 32 else "… " + name[-30:]


def _supp_keyboard(action_id: int, stack: list[Any], selected: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{'✅' if s['id'] in selected else '⬜️'} {_button_label(s)}",
            callback_data=f"supt:{action_id}:{s['id']}",
        )]
        for s in stack
    ]
    rows.append([
        InlineKeyboardButton(text="💊 log these", callback_data=f"suplog:{action_id}"),
        InlineKeyboardButton(text="🗑 none", callback_data=f"supnone:{action_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data.startswith("supt:"))
async def cb_supp_toggle(cq: CallbackQuery) -> None:
    _, action_id, sup_id = cq.data.split(":")
    payload = await db.take_pending(int(action_id))
    if not payload:
        await cq.answer("expired")
        return
    u = await db.get_or_create_user(cq.from_user.id)
    selected = list(payload["selected"])
    sid = int(sup_id)
    selected.remove(sid) if sid in selected else selected.append(sid)

    new_id = await db.put_pending(u["id"], "supp_pick", {**payload, "selected": selected})
    stack = await db.supplement_stack(u["id"])
    await cq.message.edit_text(
        render.supplement_pick_card(stack, selected),
        parse_mode="HTML",
        reply_markup=_supp_keyboard(new_id, stack, selected),
    )
    await cq.answer()


@dp.callback_query(F.data.startswith("suplog:"))
async def cb_supp_log(cq: CallbackQuery) -> None:
    payload = await db.take_pending(int(cq.data.split(":")[1]))
    if not payload:
        await cq.answer("expired")
        return
    u = await db.get_or_create_user(cq.from_user.id)
    day = dt.date.fromisoformat(payload["day"])
    await db.unlog_supplements(u["id"], day)
    n = await db.log_supplements(u["id"], day, payload["selected"])
    await cq.answer("logged")
    taken = await db.supplements_logged_on(u["id"], day)
    if taken:
        lines = [f"💊 <b>Logged for {day:%a %-d %b}</b>"] + [
            f"   • {escape(t['name'])}" for t in taken
        ]
    else:
        lines = [f"💊 Nothing recorded for {day:%a %-d %b}."]
    await cq.message.edit_text("\n".join(lines), parse_mode="HTML")
    await _send_day(cq.message, u, day)


@dp.callback_query(F.data.startswith("supnone:"))
async def cb_supp_none(cq: CallbackQuery) -> None:
    payload = await db.take_pending(int(cq.data.split(":")[1]))
    if not payload:
        await cq.answer("expired")
        return
    u = await db.get_or_create_user(cq.from_user.id)
    day = dt.date.fromisoformat(payload["day"])
    n = await db.unlog_supplements(u["id"], day)
    await cq.answer("cleared")
    await cq.message.edit_text(
        f"💊 Nothing recorded for {day:%a %-d %b}." + (f" Cleared {n}." if n else "")
    )


@dp.message(Command("undo"))
async def undo(msg: Message) -> None:
    """Unlog the last thing logged today.

    Asks first when the target is not recent. "Undo" implies the thing you just
    did, but the last *confirmed* entry of a day can be hours old — typing
    /undo at 20:58 silently removed a meal logged at 14:10. In a system where
    nothing is logged without a confirm, unlogging something from seven hours
    ago without one is the wrong way round.
    """
    u = await _user(msg)
    day = _today(u)
    entry = await db.last_confirmed_entry(u["id"], day)
    if not entry:
        await msg.answer("Nothing logged today to undo.")
        return

    import zoneinfo

    local = entry["logged_at"].astimezone(zoneinfo.ZoneInfo(u["tz"]))
    age_min = (dt.datetime.now(dt.timezone.utc) - entry["logged_at"]).total_seconds() / 60
    label = (
        f"<b>{escape(entry['name'])}</b> — {float(entry['kcal']):,.0f} kcal, "
        f"logged {local:%H:%M}"
    )

    if age_min <= UNDO_ASK_AFTER_MIN:
        await _do_undo(msg, u, entry["id"], label, day)
        return

    await msg.answer(
        f"↩️ The last thing logged today is {label} — "
        f"{int(age_min // 60)}h {int(age_min % 60)}m ago. Undo that?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ undo it", callback_data=f"undook:{entry['id']}"),
                InlineKeyboardButton(text="🔒 keep it", callback_data=f"undono:{entry['id']}"),
            ],
            [InlineKeyboardButton(text="📋 undo something else", callback_data="undopick:")],
        ]),
    )


# Beyond this, /undo asks rather than acts.
UNDO_ASK_AFTER_MIN = 60


async def _do_undo(msg: Message, u: Any, entry_id: int, label: str, day: dt.date) -> None:
    entry = await db.undo_entry(u["id"], entry_id)
    if not entry:
        await msg.answer("That was already undone.")
        return
    await msg.answer(
        f"↩️ <b>Unlogged</b> — {label}\n\n"
        "Marked discarded, not deleted, so it counts towards nothing.",
        parse_mode="HTML",
    )
    await _send_day(msg, u, day)


@dp.callback_query(F.data.startswith("undook:"))
async def cb_undo_ok(cq: CallbackQuery) -> None:
    entry_id = int(cq.data.split(":")[1])
    u = await db.get_or_create_user(cq.from_user.id)
    await cq.answer("undone")
    await cq.message.edit_text((cq.message.text or "") + "\n\n↩️ undone")
    await _do_undo(cq.message, u, entry_id, "that entry", _today(u))


@dp.callback_query(F.data.startswith("undopick:"))
async def cb_undo_pick(cq: CallbackQuery) -> None:
    """List today's confirmed entries so a middle one can be removed.

    The last-logged one is only usually the wrong one. Without this the only
    way to remove an earlier meal is to undo everything after it and log those
    again, which invents more errors than it fixes."""
    u = await db.get_or_create_user(cq.from_user.id)
    day = _today(u)
    entries = await db.confirmed_entries_on(u["id"], day)
    await cq.answer()
    if not entries:
        await cq.message.edit_text("Nothing confirmed today.")
        return

    import zoneinfo

    tz = zoneinfo.ZoneInfo(u["tz"])
    lines = [f"📋 <b>Confirmed on {day:%a %-d %b}</b>", "", "<i>Tap one to unlog it.</i>"]
    rows = []
    for e in entries:
        when = e["logged_at"].astimezone(tz)
        rows.append([InlineKeyboardButton(
            text=f"{when:%H:%M} · {e['name'][:26]} · {float(e['kcal']):,.0f} kcal",
            callback_data=f"undook:{e['id']}",
        )])
    rows.append([InlineKeyboardButton(text="🔒 keep them all", callback_data="undono:0")])
    await cq.message.edit_text(
        "\n".join(lines), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("undono:"))
async def cb_undo_no(cq: CallbackQuery) -> None:
    await cq.answer("kept")
    await cq.message.edit_text((cq.message.text or "") + "\n\n🔒 kept")


@dp.message(Command("audit"))
async def audit_cmd(msg: Message) -> None:
    """Run the daily self-check now, over the last week."""
    u = await _user(msg)
    from .jobs.audit import audit_user

    findings = await audit_user(u["id"], days=7)
    await msg.answer(render.audit_card(findings), parse_mode="HTML")


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

    rows = await db.sleep_predictors(u["id"])
    if rows:
        out.append("")
        out.append("<b>sleep vs the day before</b>")
        sleep = [float(r["sleep"]) for r in rows]
        for label, key in (
            ("energy eaten", "kcal_yesterday"),
            ("alcohol", "alcohol_yesterday"),
            ("training minutes", "training_minutes"),
        ):
            xs = [float(r[key]) for r in rows]
            if len(set(xs)) < 2:
                continue
            f = insight.correlate(f"sleep vs {label}", xs, sleep)
            out.append(f"{escape(f.label)}: {escape(f.verdict)}")
            if f.caveat:
                out.append(f"⚠ {escape(f.caveat)}")
        if len(rows) < insight.MIN_PAIRS:
            out.append(
                f"<i>{len(rows)} nights paired so far. Rate sleep in the morning "
                f"and the day before it is joined automatically.</i>"
            )

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

    # A photo sent after `/supp add` is a label, not a meal.
    if await db.latest_pending(u["id"], "supp_label"):
        await _handle_supplement_label(msg, u)
        return

    # The largest PhotoSize is the last element. Anything smaller loses the
    # scale display, which is the one thing worth reading precisely.
    images = []
    for m in msgs[:4]:
        f = await bot.get_file(m.photo[-1].file_id)
        buf = await bot.download_file(f.file_path)
        b64, w, h = llm.prepare_image(buf.read())
        images.append((b64, w, h, m.photo[-1].file_id))

    note = await msg.answer("🔍 reading the label…")
    try:
        parsed = await llm.parse_photo(images[0][0], caption, user_id=u["id"])
        for extra in images[1:]:
            more = await llm.parse_photo(extra[0], caption, user_id=u["id"], escalate=False)
            parsed.items.extend(more.items)
            parsed.cost_usd += more.cost_usd
    except Exception as exc:
        await _parse_failed(note, exc)
        return

    await _present(msg, u, parsed, source="photo", photo_file_id=images[0][3], edit=note)


async def _parse_failed(note: Message, exc: Exception) -> None:
    """Say so, rather than leaving "reading…" on screen forever.

    An unhandled exception here is invisible: aiogram logs it and returns, the
    placeholder never gets edited, and the only signal is a message that sits
    there indefinitely. That is indistinguishable from a slow model, so you wait
    instead of looking at the logs. The first live photo parse died on a 400 and
    presented as a three-minute hang.
    """
    log.exception("parse failed")
    await note.edit_text(
        f"That did not go through — {escape(type(exc).__name__)}. "
        "Nothing was logged. The detail is in the bot logs; try again in a moment.",
        parse_mode="HTML",
    )


# -------------------------------------------------------------------- text


@dp.message(F.text & ~F.text.startswith("/"))
async def on_text(msg: Message) -> None:
    u = await _user(msg)
    text = (msg.text or "").strip()

    # `/supp add` awaits a label. Anything sent next is that label — including
    # text, which used to fall straight through to the meal parser: a written
    # description of eight supplements became two nonsense meals of 4 kcal and
    # 0 kcal, logged, while the stack stayed empty. A prompt that ignores the
    # answer is worse than no prompt.
    if await db.latest_pending(u["id"], "supp_label"):
        await _handle_supplement_label(msg, u, text=text)
        return

    # A number typed while a rating keypad is on screen is that rating, not a
    # repeat selector. Checked before the grammar, which claims bare numbers.
    awaiting = await db.latest_pending(u["id"], "rate_await")
    if awaiting and text.strip().replace(".", "", 1).isdigit():
        value = float(text.strip())
        if 0 < value <= 10:
            await db.clear_pending(u["id"], "rate_await")
            await _record_rating(msg, u, awaiting["kind"], value)
            return

    # A correction to a card you just pressed ✎ on takes precedence over every
    # other reading of the message. Checked first because "rice 200" is a valid
    # repeat command as well as a valid correction, and while a fix is
    # outstanding the correction is what was meant.
    if await _try_fix(msg, u, text):
        return

    cmd = dsl.parse(text)
    if cmd and await _try_repeat(msg, u, cmd):
        return

    note = await msg.answer("🍽 digesting…")
    try:
        parsed = await llm.parse_text(text, user_id=u["id"])
    except Exception as exc:
        await _parse_failed(note, exc)
        return
    await _present(msg, u, parsed, source="text", photo_file_id=None, edit=note)



def _when_from_ops(ops: list[Any], u: Any, base: dt.datetime | None = None) -> dt.datetime:
    """Fold @date and @time ops into one UTC instant.

    Resolved against the user's own timezone and rollover hour, so "yesterday"
    means the same thing here as it does to local_date_for — otherwise a meal
    logged at 01:00 and marked @yesterday would land two days back.
    """
    import zoneinfo

    tz = zoneinfo.ZoneInfo(u["tz"])
    now = (base or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
    day = db.local_date_for(now, u["tz"], u["day_rollover_hour"])
    hour, minute = now.hour, now.minute

    for op in ops:
        if isinstance(op, dsl.SetDate):
            day = dsl.resolve_date(op, day)
        elif isinstance(op, dsl.SetTime):
            hour, minute = op.hour, op.minute

    local = dt.datetime.combine(day, dt.time(hour, minute), tzinfo=tz)
    # A time before the rollover belongs to the day that has not ended, so the
    # calendar date carrying it is the next one.
    if hour < u["day_rollover_hour"]:
        local += dt.timedelta(days=1)
    return local.astimezone(dt.timezone.utc)



async def _apply_when(entry_id: int, ops: list[Any], u: Any) -> dt.date | None:
    """Move a pending entry to another day or time. Returns the new local date.

    Only pending entries: once confirmed, log_nutrient has been written and the
    entry belongs to a day's arithmetic. Moving it then is a different and
    larger operation than a correction, and /undo plus a re-log is the honest
    way to do it.
    """
    if not any(isinstance(o, (dsl.SetDate, dsl.SetTime)) for o in ops):
        return None
    when = _when_from_ops(ops, u)
    day = db.local_date_for(when, u["tz"], u["day_rollover_hour"])
    p = await db.pool()
    updated = await p.fetchval(
        """UPDATE log_entry SET logged_at = $2, local_date = $3
            WHERE id = $1 AND status = 'pending' RETURNING local_date""",
        entry_id, when, day,
    )
    return updated


async def _try_fix(msg: Message, u: Any, text: str) -> bool:
    """Apply a correction to the pending entry the ✎ button was pressed on.

    Nothing consumed the `fix_entry` action before this, so ✎ printed
    instructions and then ignored whatever you replied — the reply fell through
    to the text parser, cost a Sonnet call, and logged a *second* meal beside
    the one you were trying to correct. Inert would have been better.
    """
    action = await db.latest_pending(u["id"], "fix_entry")
    if not action:
        return False

    entry_id = int(action["entry_id"])
    entry, comps = await db.entry_with_components(entry_id)
    if not entry or entry["status"] != "pending":
        # Confirmed or discarded in the meantime; the correction has nothing to
        # attach to and must not silently become a new meal.
        await db.clear_pending(u["id"], "fix_entry")
        await msg.answer(
            "That card was already dealt with, so there is nothing to correct. "
            "Send the meal again if you need to.",
        )
        return True

    ops, unparsed = dsl.parse_ops(text.split())

    # A date or time on its own is a complete correction. "I ate this
    # yesterday" changes nothing about the components and everything about
    # which day's totals it lands in.
    moved = await _apply_when(entry_id, ops, u)
    if moved and not any(
        isinstance(o, (dsl.Scale, dsl.TotalGrams, dsl.SetComponent,
                       dsl.AddComponent, dsl.DropComponent))
        for o in ops
    ):
        await db.clear_pending(u["id"], "fix_entry")
        entry, comps = await db.entry_with_components(entry_id)
        profs = await db.profiles_for([c["fdc_id"] for c in comps])
        from .core.nutrition import ResolvedComponent as _RC

        resolved = [
            _RC(c["label"], c["fdc_id"], float(c["grams"]), float(c["yield_factor"]),
                float(c["grams_sigma"] or 0), c["grams_source"])
            for c in comps
        ]
        await msg.answer(
            render.confirm_card(
                entry["name"], resolved, total_nutrients(resolved, profs),
                confidence=None,
                warnings=[f"moved to {moved:%a %-d %b}"],
            ),
            parse_mode="HTML",
            reply_markup=kb_confirm(entry_id),
        )
        return True

    if not ops:
        await msg.answer(
            "I could not read that as a correction. Try "
            "<code>rice 200</code>, <code>-oil</code>, <code>+30 butter</code> "
            "or <code>x0.8</code>.",
            parse_mode="HTML",
        )
        return True

    current = [
        dsl.Component(c["label"], c["fdc_id"], float(c["grams"]), c["state"],
                      float(c["yield_factor"]), c["grams_source"])
        for c in comps
    ]
    new_comps, to_add = dsl.apply(current, ops)

    # An added component still has to be resolved to a USDA row. Aliases first,
    # so a food you have logged before costs nothing to add back.
    for add in to_add:
        alias = await db.resolve_alias(u["id"], add.label)
        if alias:
            await db.bump_alias(alias["id"])
            grams = add.grams or float(alias["default_grams"] or 100)
            new_comps.append(
                dsl.Component(add.label, alias["fdc_id"], grams, grams_source="stated")
            )
            continue
        res = await llm.resolve_items(
            u["id"],
            [{"label": add.label, "search_terms": add.label,
              "grams": add.grams or 100, "grams_source": "stated",
              "state": "unknown", "confidence": 0.7}],
        )
        for c in res.components:
            new_comps.append(
                dsl.Component(c.label, c.fdc_id, c.grams, yield_factor=c.yield_factor,
                              grams_source="stated")
            )

    # Sigma is recomputed from the provenance rather than zeroed. Storing 0
    # claims the mass is exact, which shrinks the day's error bar and makes a
    # corrected meal look better measured than an uncorrected one.
    resolved = [
        ResolvedComponent(
            c.label, c.fdc_id, c.grams, c.yield_factor,
            estimate.sigma_for(c.grams, c.grams_source), c.grams_source,
        )
        for c in new_comps if c.fdc_id
    ]
    if not resolved:
        await msg.answer("That would leave the meal empty, so I have not applied it.")
        return True

    await db.replace_components(entry_id, resolved)
    await db.clear_pending(u["id"], "fix_entry")

    profs = await db.profiles_for([c.fdc_id for c in resolved])
    totals = total_nutrients(resolved, profs)
    warnings = [f"could not read: {' '.join(unparsed)}"] if unparsed else []
    await msg.answer(
        render.confirm_card(
            entry["name"], new_comps, totals, confidence=None, warnings=warnings
        ),
        parse_mode="HTML",
        reply_markup=kb_confirm(entry_id),
    )
    return True


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

    when = _when_from_ops(ops, u)
    slot = dish["default_slot"]
    for op in ops:
        if isinstance(op, dsl.SetSlot):
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
    #
    # "Confirmed before" is the load-bearing half, and it was missing.
    # `_present` upserts the dish before the entry exists, so a meal you look at
    # and *discard* still leaves a repeatable dish behind. Discarding a photo
    # and then sending `1` logged 947 kcal with no gate at all — the exact thing
    # invariant 5 forbids. times_logged only increments in confirm_entry, so a
    # dish at zero has never been through a human, and its repeat goes through
    # the gate like any other new claim.
    never_confirmed = int(dish["times_logged"] or 0) == 0
    if not ops and not cmd.needs_model and not never_confirmed:
        totals = await db.confirm_entry(entry_id)
        await msg.answer(
            render.logged_card(
                dish["name"], totals, await db.day_progress(u["id"], _today(u)),
                first_of_day=await db.is_first_entry_of_day(u["id"], _today(u), entry_id),
            ),
            parse_mode="HTML",
        )
        await _check_thresholds(msg, u)
        return True

    profs = await db.profiles_for([c.fdc_id for c in resolved])
    totals = total_nutrients(resolved, profs)
    warnings = (
        ["this dish has never been confirmed — check it once and repeats are instant"]
        if never_confirmed
        else []
    )
    await msg.answer(
        render.confirm_card(
            dish["name"], new_comps, totals, confidence=None, warnings=warnings
        ),
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
        # Keep the parse even though nothing resolved.
        #
        # This used to return here, which threw away the most informative thing
        # the pipeline produces. A photo that reaches this branch has already
        # cost a Sonnet call, often an Opus escalation and a Haiku
        # disambiguation — call it 5p — and the one artefact worth having from
        # it, the model's actual output, went nowhere. You could see that a
        # meal failed but never what search terms it chose, so the resolver
        # could not be improved against the case that beat it.
        #
        # Stored as a discarded entry: `parse` holds the raw tool output and
        # `photo_file_id` still points at the image, so it can be re-run against
        # a better database later. Every rollup filters on status='confirmed',
        # so it counts towards nothing.
        entry_id = await db.create_pending_entry(
            u["id"], parsed.dish_name, [], source=source, slot=parsed.slot,
            confidence=parsed.confidence, model=parsed.model, parse=parsed.raw,
            photo_file_id=photo_file_id, dish_id=None, tz=u["tz"],
            rollover_hour=u["day_rollover_hour"],
        )
        await db.discard_entry(entry_id)

        # Name what failed. "I could not match anything" gives you nothing to
        # act on; the labels tell you which word to rephrase.
        missed = ", ".join(res.unresolved) or parsed.dish_name
        text = (
            f"No match in the food database for: <b>{escape(missed)}</b>\n\n"
            "Nothing was logged. Try naming the ingredients plainly — "
            "<code>2 cheese rolls, 1 pickle, half an avocado, 4 slices salami</code> — "
            "or state the masses and I will trust those over the photo."
        )
        if edit:
            await edit.edit_text(text, parse_mode="HTML")
        else:
            await msg.answer(text, parse_mode="HTML")
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
        # "Check the masses" is the wrong instruction when you supplied every
        # mass yourself. What is left to doubt in that case is whether the right
        # USDA rows were picked.
        all_hard = res.grams_sources and all(
            src in ("scale", "stated", "package") for src in res.grams_sources
        )
        what = "check the foods matched" if all_hard else "check the masses"
        warnings.insert(0, f"low overall confidence ({parsed.confidence:.0%}) — {what}")
    for note in res.prior_notes or []:
        warnings.append(note)

    # Unresolved items are passed separately rather than appended to warnings:
    # the card puts them above the totals, because a total computed from part of
    # a plate must not be readable as the meal's total.
    text = render.confirm_card(
        parsed.dish_name, res.components, totals,
        confidence=parsed.confidence, warnings=warnings, notes=parsed.notes,
        cost_usd=parsed.cost_usd + res.cost_usd, unresolved=res.unresolved,
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


async def _handle_supplement_label(
    msg: Message, u: Any, *, text: str | None = None
) -> None:
    """Transcribe one or more panels, show them, save nothing until confirmed.

    The confirm gate matters more here than on a meal. A meal's numbers are
    checked against a plate in front of you; a supplement's go into every future
    daily total with nothing to contradict them.
    """
    from .core import supplements

    photo_id = None
    b64 = None
    if msg.photo:
        f = await msg.bot.get_file(msg.photo[-1].file_id)
        buf = await msg.bot.download_file(f.file_path)
        b64, _w, _h = llm.prepare_image(buf.read())
        photo_id = msg.photo[-1].file_id

    note = await msg.answer("🔍 reading the label…")
    try:
        data, cost = await llm.read_supplement_label(
            user_id=u["id"], image_b64=b64, text=text
        )
    except Exception as exc:
        await _parse_failed(note, exc)
        return

    units = await db.nutrient_units()
    p = await db.pool()
    names = {r["id"]: r["name"] for r in await p.fetch("SELECT id, name FROM nutrient")}

    parsed: list[dict[str, Any]] = []
    for sup in data.get("supplements", []):
        kept, dropped = supplements.normalise(list(sup.get("nutrients", [])), units)
        parsed.append({
            "name": sup.get("name") or "supplement",
            "brand": sup.get("brand"),
            "serving_desc": sup.get("serving_desc") or "1 serving",
            "servings_per_day": float(sup.get("servings_per_day") or 1),
            "schedule": sup.get("schedule") or "daily",
            "note": sup.get("note") or "",
            "not_tracked": sup.get("not_tracked") or "",
            "nutrients": [[c.nutrient_id, c.amount] for c in kept],
            "_kept": kept,
            "_dropped": dropped,
        })

    if not parsed:
        await db.clear_pending(u["id"], "supp_label")
        await note.edit_text("I could not find a supplement in that.")
        return

    action_id = await db.put_pending(u["id"], "supp_confirm", {
        # Every product, including those with nothing trackable. They are part
        # of the stack, you want to record having taken them, and a nutrient id
        # may exist for one of them later — boron does not have one today.
        "supplements": [
            {k: v for k, v in pp.items() if not k.startswith("_")} for pp in parsed
        ],
        "photo_file_id": photo_id,
    })
    await db.clear_pending(u["id"], "supp_label")

    body = render.supplement_batch_card(parsed, names, units)
    if data.get("unreadable"):
        body += f"\n\n⚠️ {escape(str(data['unreadable']))}"
    body += f"\n\n<i>💸 {cost*100:.2f}¢</i>"
    await note.edit_text(
        body,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ save all", callback_data=f"supok:{action_id}"),
            InlineKeyboardButton(text="🗑 discard", callback_data=f"supno:{action_id}"),
        ]]),
    )


@dp.callback_query(F.data.startswith("supok:"))
async def cb_supp_ok(cq: CallbackQuery) -> None:
    payload = await db.take_pending(int(cq.data.split(":")[1]))
    await cq.answer("saved" if payload else "expired")
    if not payload:
        await cq.message.edit_text("That expired. Send it again.")
        return
    u = await db.get_or_create_user(cq.from_user.id)
    saved = []
    for sup in payload["supplements"]:
        await db.upsert_supplement(
            u["id"], sup["name"],
            [(int(n), float(a)) for n, a in sup["nutrients"]],
            brand=sup.get("brand"),
            serving_desc=sup["serving_desc"],
            servings_per_day=sup["servings_per_day"],
            schedule=sup.get("schedule", "daily"),
            note=sup.get("note") or None,
            photo_file_id=payload.get("photo_file_id"),
        )
        saved.append(sup["name"])
    await cq.message.edit_text(
        (cq.message.text or "") + f"\n\n✅ saved {len(saved)} to your stack",
    )
    await cq.message.answer(
        "Added. <code>/supp</code> asks which you took today, "
        "<code>/supp list</code> shows the stack.",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("supno:"))
async def cb_supp_no(cq: CallbackQuery) -> None:
    await db.take_pending(int(cq.data.split(":")[1]))
    await cq.message.edit_text((cq.message.text or "") + "\n\n❌ discarded")
    await cq.answer("discarded")


# ---------------------------------------------------------------- callbacks


@dp.callback_query(F.data.startswith("ok:"))
async def cb_ok(cq: CallbackQuery) -> None:
    entry_id = int(cq.data.split(":")[1])
    totals = await db.confirm_entry(entry_id)
    await cq.answer("logged")

    entry, _comps = await db.entry_with_components(entry_id)
    u = await db.get_or_create_user(cq.from_user.id)

    # Retire the card. Its text arrives back from Telegram with the markup
    # already stripped, so it is re-sent as plain text; the detail it held has
    # served its purpose and the progress card below replaces it.
    await cq.message.edit_text(
        (cq.message.text or "") + f"\n\n✅ logged — {totals.get(1008, 0):,.0f} kcal"
    )

    day = _today(u)
    await cq.message.answer(
        render.logged_card(
            entry["name"], totals, await db.day_progress(u["id"], day),
            first_of_day=await db.is_first_entry_of_day(u["id"], day, entry["id"]),
        ),
        parse_mode="HTML",
    )
    await _check_thresholds(cq.message, u)


@dp.callback_query(F.data.startswith("no:"))
async def cb_no(cq: CallbackQuery) -> None:
    await db.discard_entry(int(cq.data.split(":")[1]))
    await cq.message.edit_text((cq.message.text or "") + "\n\n❌ discarded")
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
        await msg.answer(text, parse_mode="HTML")


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
    from .http_api import start as start_http
    from .jobs.notify import start_scheduler

    start_scheduler(bot)
    await start_http()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())
