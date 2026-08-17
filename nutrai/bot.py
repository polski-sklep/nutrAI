from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import zoneinfo
from collections import defaultdict
from collections.abc import Sequence
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

from . import db, off
from .config import CARB, CONFIDENCE_FLOOR, ENERGY_KCAL, FAT, PROTEIN, settings
from .core import dsl, estimate, fasting, insight, plan, render, suggest
from .core import profile as profile_mod
from .core.nutrition import ResolvedComponent, total_nutrients
from .jobs import report as report_job
from .llm import parse as llm

log = logging.getLogger("nutrai")


# Every prompt that waits for a typed reply, in one registry.
#
# Opening a prompt and consuming its reply used to be two edits in two places,
# and forgetting the second was silent: the bot printed instructions and then
# fed your answer to the meal parser. That happened with the ✏️ fix button, the
# rating keypad, /weight, /supp add, /profile and /why — six times, each found
# by a person rather than by a test.
#
# Registering a consumer is now the only way to get a kind into AWAITING_KINDS,
# because this dict *is* the list. A prompt with no consumer cannot be opened,
# and `_ask` sends the message and registers the wait in one call so the two
# cannot drift apart.
PROMPT_CONSUMERS: dict[str, Any] = {}


def consumes(kind: str):
    def register(fn):
        PROMPT_CONSUMERS[kind] = fn
        return fn
    return register


async def _ask(msg: Message, u: Any, kind: str, text: str, **kw) -> None:
    """Send a prompt and open the wait for its answer. Never one without the other."""
    if kind not in PROMPT_CONSUMERS:
        raise KeyError(f"no consumer registered for prompt {kind!r}")
    await msg.answer(text, parse_mode="HTML", **kw)
    await db.put_pending(u["id"], kind, {})


dp = Dispatcher()

# Telegram delivers each photo of an album as its own update. Without this
# buffer, a four-photo meal becomes four meals.
_album: dict[str, list[Message]] = defaultdict(list)
_album_tasks: dict[str, asyncio.Task] = {}
ALBUM_WAIT = 1.2


def _define_button(weak: Sequence[tuple[str, float]]) -> list[InlineKeyboardButton]:
    """Offered at the moment the gap is visible, which is the only moment you
    know the database is missing something."""
    if not weak:
        return []
    label = weak[0][0]
    return [InlineKeyboardButton(
        text=f"🥫 define {render._short_note(label)[:20]} yourself",
        callback_data=f"deffood:{label[:40]}")]


@dp.callback_query(F.data.startswith("deffood:"))
async def cb_define_food(cq: CallbackQuery) -> None:
    """Straight into /food with the name already filled in.

    Offered at the moment the gap is visible, which is the only moment you
    know the database is missing something.
    """
    u = await db.get_or_create_user(cq.from_user.id)
    name = cq.data.split(":", 1)[1].strip()
    await db.put_pending(u["id"], "food_await", {"name": name})
    await cq.answer()
    await cq.message.answer(
        f"🥫 Making a food called <b>{render._esc(name)}</b>.\n\n"
        "<b>What goes into it?</b> Reply with ingredients and amounts:\n"
        "<code>1000 ml water, 30 g salt, 100 ml white vinegar</code>\n\n"
        "<i>Resolved against USDA and added up — nothing estimated. Once saved "
        "it outranks the generic row every time you log that name.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✋ never mind", callback_data="foodcancel:"),
        ]]),
    )


def kb_confirm(entry_id: int,
               weak: Sequence[tuple[str, float]] = ()) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="✅ log it", callback_data=f"ok:{entry_id}"),
        InlineKeyboardButton(text="🕐 time", callback_data=f"when:{entry_id}"),
        InlineKeyboardButton(text="✏️ fix", callback_data=f"fix:{entry_id}"),
        InlineKeyboardButton(text="🗑 discard", callback_data=f"no:{entry_id}"),
    ]]
    if weak:
        # The offer belongs here, beside the discard, because this is the
        # moment you can see that the database has nothing like your food —
        # and the moment you would otherwise give up and log something wrong.
        label = weak[0][0]
        rows.append([InlineKeyboardButton(
            text=f"🥫 define {render._short_note(label)[:18]} yourself",
            callback_data=f"deffood:{label[:40]}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _user(msg: Message) -> Any:
    if settings.allowed_ids and msg.from_user.id not in settings.allowed_ids:
        raise PermissionError("not allowed")
    u = await db.get_or_create_user(msg.from_user.id, msg.from_user.full_name)
    # Typing another command means you moved on. Without this, tapping
    # `/supp add` and then changing your mind leaves the label prompt open, and
    # the next meal you send is parsed as a supplement panel — expensively, and
    # wrongly. `on_text` never reaches here, so a reply to a prompt is safe;
    # only a command clears one.
    # When you first speak each day, which is what the morning note's timing
    # is learned from. Cheap, and it makes the estimate a measurement rather
    # than a guess about a guess.
    await db.note_first_contact(u["id"], _today(u))
    if (msg.text or "").startswith("/"):
        await db.clear_awaits(u["id"], tuple(PROMPT_CONSUMERS))
    return u


def _local_now(u: Any) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone(zoneinfo.ZoneInfo(u["tz"]))


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
# Ordered by how often each is likely to be wanted, not alphabetically and not
# by when it was built. The menu is a list you scan under a keyboard, so the
# six you use every day sit above the fold and the setup screens you touched
# once are at the bottom.
#
# Descriptions are the menu, and Telegram truncates a long one mid-word on a
# phone — "Sessions posted by the workout bot, and the week's…" told you less
# than four words would have. Sentence case, under about forty characters, no
# worked examples: the card that opens explains itself far better than a menu
# row can, and a row that has to be read twice is worse than a short one.
COMMANDS: list[tuple[str, str]] = [
    # Logging and checking, which is nearly everything.
    ("/repeat", "Log something you have had before"),
    ("/today", "Where you stand today"),
    ("/next", "What would close today's gaps"),
    ("/yesterday", "Where you stood yesterday"),
    ("/why", "Where a nutrient came from today"),
    ("/undo", "Unlog your last entry"),
    # The other things you record daily.
    ("/supp", "Log today's supplements"),
    ("/weight", "Log a weigh-in"),
    ("/rate", "Rate sleep, focus, mood or effort"),
    ("/training", "Sessions, and this week's total"),
    ("/fast", "Your current fast"),
    ("/window", "Your eating window"),
    # Looking back, weekly or thereabouts.
    ("/week", "The last seven days"),
    ("/report", "The weekly review"),
    ("/insight", "What your own data supports"),
    # Setting things up, rarely after the first week.
    ("/food", "Foods you define yourself"),
    ("/stack", "Add, stop or restore a supplement"),
    ("/schedule", "When each supplement is taken"),
    ("/profile", "Your details, and targets from them"),
    ("/target", "Set a nutrient target yourself"),
    # Checking on the system rather than on yourself.
    ("/audit", "Check entries for wrong matches"),
    ("/spend", "What this has cost so far"),
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
    hour = _local_now(u).hour
    dishes = await db.top_dishes(u["id"], 8, tz=u["tz"], hour=hour)
    components = await db.top_components(u["id"], 6, tz=u["tz"], hour=hour)
    if not dishes:
        await msg.answer("Nothing to repeat yet. Log something first.")
        return
    await db.put_pending(u["id"], "repeat_menu", {
        "ids": [d["id"] for d in dishes],
        "components": [
            {"fdc_id": c["fdc_id"], "label": c["label"],
             "grams": float(c["stated_grams"] or c["median_grams"] or 0),
             "stated": c["stated_grams"] is not None}
            for c in components
        ],
    })
    await msg.answer(render.repeat_menu(dishes, components=components),
                     parse_mode="HTML")


@dp.message(Command("today"))
async def today(msg: Message) -> None:
    u = await _user(msg)
    # Everything by default. "Worth a look" still leads and the rest follows
    # under "On track", so the full card is longer without being flatter.
    await _send_day(msg, u, _today(u), show_all="brief" not in (msg.text or ""))


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
    "rpe": ("🏋", "how hard training felt — 1 is easy, 10 is all you had"),
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


@dp.callback_query(F.data.startswith("wnew:"))
async def cb_weight_new(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await db.put_pending(u["id"], "weight_await", {})
    await cq.answer()
    await cq.message.answer(
        "⚖️ <b>What do you weigh?</b>\n"
        "<i>Send the number. Same time of day, ideally before breakfast.</i>",
        parse_mode="HTML",
    )


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


def _num(v: str, lo: float, hi: float) -> float | None:
    """A number, tolerating the unit the user naturally typed after it."""
    cleaned = re.sub(r"[^\d.\-]", "", v.replace(",", "."))
    n = float(cleaned)
    return n if lo <= n <= hi else None


def _activity(v: str) -> float | None:
    """A level name, a 1-5 position, or a raw multiplier.

    The card prints "Moderate" and the validator used to accept only numbers,
    so the one word the screen showed you was the one word it refused.

    An integer 1-5 is read as a position in the list and anything with a
    decimal point as a raw factor. They overlap only at 1 and 2, and nobody
    means a 1.0 multiplier when they type "1" under a numbered list of five.
    """
    txt = v.strip().lower()
    for i, (factor, name, _gloss) in enumerate(profile_mod.ACTIVITY_LEVELS, start=1):
        if txt == name.lower() or txt == str(i):
            return factor
    return _num(v, 1.0, 2.5)


def _date(v: str) -> dt.date:
    """ISO, or the day-first forms a European keyboard produces.

    Day-first rather than month-first: the deployment is Europe/Warsaw and
    locale_units is metric. It is still a guess for 09/05/1991, which is why
    the reply echoes the date back as "9 May 1991" — a transcription is
    checkable at the moment it is made, and this one is.
    """
    v = v.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            d = dt.datetime.strptime(v, fmt).date()
        except ValueError:
            continue
        if dt.date(1900, 1, 1) <= d <= dt.date.today():
            return d
        raise ValueError(v)
    raise ValueError(v)


# Accept what a person types, not what a parser would prefer. Every one of
# these was a real refusal: "M" for male, "21/09/1991" for a birth date,
# "176cm" for a height.
PROFILE_VALIDATORS: dict[str, Any] = {
    "sex": lambda v: {"m": "male", "male": "male", "man": "male",
                      "f": "female", "female": "female", "woman": "female"}.get(v.strip().lower()),
    "goal": lambda v: {"lose": "lose", "lose weight": "lose", "cut": "lose",
                       "fat loss": "lose", "cutting": "lose",
                       "maintain": "maintain", "maintenance": "maintain",
                       "gain": "gain", "bulk": "gain", "bulking": "gain",
                       "muscle gain": "gain", "gain weight": "gain",
                       # Body recomposition: both at once. Not a synonym for
                       # either — it earns a higher protein floor and a
                       # shallower deficit than a straight cut.
                       "recomp": "recomp", "recomposition": "recomp",
                       "muscle gain and fat loss": "recomp",
                       "fat loss and muscle gain": "recomp",
                       "build muscle and lose fat": "recomp",
                       "lose fat and build muscle": "recomp",
                       }.get(v.strip().lower()),
    "birth_date": _date,
    "height_cm": lambda v: _num(v, 100, 250),
    "activity_factor": lambda v: _activity(v),
    "goal_weight_kg": lambda v: _num(v, 20, 400),
    "deficit_kcal": lambda v: _num(v, -1500, 1500),
    "tz": lambda v: v.strip() if zoneinfo.ZoneInfo(v.strip()) else None,
    "wake_hour": lambda v: int(_num(v, 0, 23)) if _num(v, 0, 23) is not None else None,
    "display_name": lambda v: v.strip()[:80] or None,
}

# "2. M" is a profile edit. "2 eggs" is breakfast. The punctuation after the
# number is the whole discriminator, and it has to be required: without it,
# answering a numbered list and describing a meal are the same string, and
# guessing wrong either loses a meal or writes nonsense into the profile.
PROFILE_LINE = re.compile(r"^\s*(\d{1,2})\s*[.):]\s*(\S.*?)\s*$")


def _profile_edits(text: str) -> list[tuple[int, str]] | None:
    """Every line numbered, or none. A partial match is not a profile message."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    out = []
    for ln in lines:
        m = PROFILE_LINE.match(ln)
        if not m:
            return None
        out.append((int(m.group(1)), m.group(2)))
    return out


async def _apply_profile_edits(msg: Message, u: Any, edits: list[tuple[int, str]]) -> None:
    """Apply what is valid, refuse what is not, and say which was which."""
    notes: list[str] = []
    changed = False
    for index, raw in edits:
        if not 1 <= index <= len(render.PROFILE_ROWS):
            notes.append(f"❌ line {index} — the list runs 1–{len(render.PROFILE_ROWS)}")
            continue
        field, label, hint = render.PROFILE_ROWS[index - 1]
        try:
            value = PROFILE_VALIDATORS[field](raw)
        except Exception:
            value = None
        if value is None:
            # Refused rather than coerced. A height of 0 or a timezone of
            # "Warsaw" stores happily and then poisons every derived number.
            notes.append(
                f"❌ <b>{render._esc(label)}</b> takes {render._esc(hint)} — "
                f"got {render._esc(raw)}"
            )
            continue
        await db.set_profile_field(u["id"], field, value)
        changed = True
        # Echo the interpretation, not the input: "21/09/1991" and
        # "21 Sep 1991" are the same claim, and only one of them is checkable.
        shown = f"{value:%-d %b %Y}" if isinstance(value, dt.date) else str(value)
        notes.append(f"✅ {render._esc(label)} → {render._esc(shown)}")

    data = await db.profile(u["id"])
    await msg.answer(
        "\n".join(notes) + "\n\n" + render.profile_card(data, _today(u)),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 recalculate targets", callback_data="precalc:"),
        ]]),
    )
    if changed:
        # Keep the prompt open: filling in a profile is a handful of lines, and
        # closing it after the first would send the second to the food parser.
        await db.put_pending(u["id"], "profile_await", {})


# Not aliased to /targets: that name is reserved for core/plan.py, which is
# written and deliberately unwired until stage 5. Squatting on it would make
# the eventual wiring a rename with muscle memory already attached.
TARGET_LINE = re.compile(
    r"^\s*(?P<name>[A-Za-z][A-Za-z0-9 ,\-]*?)\s+"
    r"(?:(?P<bound>max|min|ceiling|floor|at most|at least|under|over|weight)\s+)?"
    r"(?P<value>\d+(?:\.\d+)?|clear|none|off|reset)\s*"
    r"(?P<unit>kcal|kj|mg|ug|µg|mcg|g|iu)?\s*$",
    re.IGNORECASE,
)


async def _set_one_target(msg: Message, u: Any, term: str, bound: str | None,
                          value_tok: str) -> bool:
    """Resolve a nutrient and set or clear one target. False if unresolvable."""
    # Search the word the card printed, not only the word USDA stores.
    matches = await db.find_nutrients(render.usda_name_for(term) or term)
    if not matches:
        return False
    today = _today(u)
    standing = {r["nutrient_id"]: r for r in await db.standing_targets(u["id"])}

    # Match what the card actually shows. It prints "Alcohol"; the column is
    # "Alcohol, ethyl"; and asking the user to choose between that and "Total
    # sugar alcohols" after they typed the word on screen is the card refusing
    # its own vocabulary.
    exact = [m for m in matches
             if term.lower() in (m["name"].lower(), render._short(m["name"]).lower())]
    if len(exact) == 1:
        matches = exact
    elif len(matches) > 1:
        # Otherwise prefer something you already have a target for: those are
        # the rows the list you just read was made of.
        owned = [m for m in matches if m["id"] in standing]
        if len(owned) == 1:
            matches = owned

    if len(matches) > 1:
        shown = "\n".join(f"• {render._esc(render._short(m['name']))}" for m in matches)
        await msg.answer(f"{render._esc(term)} matches several — say which:\n{shown}",
                         parse_mode="HTML")
        return True
    n = matches[0]
    current = standing.get(n["id"])

    if value_tok.lower() in ("clear", "reset", "none", "off"):
        row = await db.profile(u["id"])
        try:
            targets, _w = profile_mod.derive_targets(
                sex=row["user"]["sex"], weight_kg=row["weight_kg"],
                height_cm=float(row["user"]["height_cm"]) if row["user"]["height_cm"] else None,
                age=profile_mod.age_years(row["user"]["birth_date"], today),
                activity=float(row["user"]["activity_factor"]) if row["user"]["activity_factor"] else None,
                deficit=float(row["user"]["deficit_kcal"] or 0), goal=row["user"]["goal"],
            )
            restored = targets.get(n["id"])
        except (profile_mod.IncompleteProfile, TypeError):
            restored = None
        if restored:
            await db.apply_targets(u["id"], {n["id"]: restored}, today, "profile recalculation")
            lo, hi = restored
            what = f"back to the derived {lo:g} {n['unit']} minimum" if lo is not None \
                else f"back to the derived {hi:g} {n['unit']} ceiling"
        else:
            what = "not cleared — the profile is too incomplete to derive a default"
        await msg.answer(f"🎯 <b>{render._esc(render._short(n['name']))}</b> {render._esc(what)}.",
                         parse_mode="HTML")
        return True

    if bound == "weight":
        w = float(value_tok)
        if not 0 < w <= 10:
            await msg.answer("A weight runs from 0 to 10.", parse_mode="HTML")
            return True
        await db.set_target_weight(u["id"], n["id"], w, today)
        await msg.answer(
            f"⚖️ <b>{render._esc(render._short(n['name']))}</b> now counts "
            f"<b>×{w:g}</b> toward the day's score.\n\n"
            "<i>Only the score changes — the target itself is untouched, and "
            "past days keep the weighting they were scored with.</i>",
            parse_mode="HTML")
        return True

    value = float(value_tok)
    if bound:
        is_max = bound.lower() in ("max", "ceiling", "at most", "under")
    elif current is not None:
        # Follow the target that is already there. Replying "Alcohol 0" to a
        # list showing "Alcohol max 16 G" plainly means a ceiling of nothing,
        # and reading it as a floor would invert it.
        is_max = current["min_amount"] is None
    else:
        is_max = False

    await db.set_manual_target(
        u["id"], n["id"], today,
        minimum=None if is_max else value,
        maximum=value if is_max else None,
    )
    word = "ceiling" if is_max else "minimum"
    extra = ""
    if is_max and value == 0:
        extra = "\n<i>Zero is a real ceiling: anything at all will now flag.</i>"
    await msg.answer(
        f"🎯 <b>{render._esc(render._short(n['name']))}</b> daily {word} set to "
        f"<b>{value:g} {render._esc(n['unit'].lower())}</b>.{extra}\n\n"
        "<i>Yesterday is still judged against what it was set to then — "
        "targets are versioned, not rewritten.</i>",
        parse_mode="HTML",
    )
    return True


async def _try_target_lines(msg: Message, u: Any, text: str) -> bool:
    """"Alcohol 0g", one per line. False if it does not name a nutrient."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    parsed = [TARGET_LINE.match(ln) for ln in lines]
    if not lines or not all(parsed):
        return False
    # Resolve every name before changing anything: a message that is really a
    # meal must fall through whole, not half-applied.
    for m in parsed:
        term = m.group("name").strip()
        if not await db.find_nutrients(render.usda_name_for(term) or term):
            return False
    for m in parsed:
        await _set_one_target(msg, u, m.group("name").strip(),
                              m.group("bound"), m.group("value"))
    return True


@dp.message(Command("training", "train"))
async def training(msg: Message) -> None:
    """What the workout bot has actually posted.

    Until now the only way to see whether a session had landed was to query
    Postgres by hand — which meant three failed forwards in a row looked
    exactly like three successful ones from inside Telegram.
    """
    u = await _user(msg)
    day = _today(u)
    week_start = day - dt.timedelta(days=day.weekday())
    rows = await db.activity_range(u["id"], week_start, day)
    today_rows = [r for r in rows if r["local_date"] == day]
    await msg.answer(
        render.training_card(today_rows, rows, day, week_start),
        parse_mode="HTML",
        reply_markup=_training_keyboard(today_rows),
    )


def _training_keyboard(today_rows: Sequence[Any]) -> InlineKeyboardMarkup | None:
    """One ❌ per session logged today.

    Only today's: a session from Tuesday is history, and a delete button next
    to it invites removing something you can no longer check.
    """
    if not today_rows:
        return None
    if len(today_rows) == 1:
        buttons = [[InlineKeyboardButton(text="❌ remove this session",
                                         callback_data=f"actdel:{today_rows[0]['id']}")]]
    else:
        buttons = [[
            InlineKeyboardButton(text=f"❌ {i}", callback_data=f"actdel:{r['id']}")
            for i, r in enumerate(today_rows, start=1)
        ]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _describe_activity(r: Any) -> str:
    bits = [r["kind"]]
    if r["minutes"]:
        bits.append(render._hm(float(r["minutes"])))
    if r["intensity"]:
        bits.append(str(r["intensity"]))
    if r["rpe"] is not None:
        bits.append(f"effort {float(r['rpe']):g}/10")
    return " · ".join(bits)


@dp.callback_query(F.data.startswith("actdel:"))
async def cb_activity_delete(cq: CallbackQuery) -> None:
    """Ask first. A delete cannot be taken back, and the session came from
    another system that will not re-send it unprompted."""
    u = await db.get_or_create_user(cq.from_user.id)
    activity_id = int(cq.data.split(":", 1)[1])
    row = await db.activity_by_id(u["id"], activity_id)
    await cq.answer()
    if not row:
        await cq.message.answer("That session is already gone.")
        return
    await cq.message.answer(
        f"Remove this session?\n\n<b>{render._esc(_describe_activity(row))}</b>"
        + (f"\n<i>{render._esc(row['note'])}</i>" if row["note"] else ""),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ remove it", callback_data=f"actdel!:{activity_id}"),
            InlineKeyboardButton(text="keep it", callback_data="actkeep:"),
        ]]),
    )


@dp.callback_query(F.data.startswith("actdel!:"))
async def cb_activity_delete_confirm(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    activity_id = int(cq.data.split(":", 1)[1])
    row = await db.activity_by_id(u["id"], activity_id)
    if not row:
        await cq.answer("Already gone")
        return
    what = _describe_activity(row)
    await db.delete_activity(u["id"], activity_id)
    await cq.answer("Removed")
    await cq.message.edit_text(
        f"🗑 Removed <b>{render._esc(what)}</b>.\n\n"
        "<i>The workout bot can post it again — nothing here stops it.</i>",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("actkeep:"))
async def cb_activity_keep(cq: CallbackQuery) -> None:
    await cq.answer("Kept")
    await cq.message.edit_text("Kept. Nothing was removed.")


@dp.message(Command("target"))
async def target_cmd(msg: Message) -> None:
    """`/target` lists · `/target fibre 40` sets a floor · `max 2000` a ceiling.

    Everything except protein and energy used to be a population RDA you could
    not touch without editing the database. A target you disagree with and
    cannot change is worse than no target: it turns every day card into a
    verdict handed down by nobody.
    """
    u = await _user(msg)
    args = (msg.text or "").split()[1:]

    if not args:
        await msg.answer(render.target_list_card(await db.standing_targets(u["id"])),
                         parse_mode="HTML")
        # Having just read a list, the natural next message is "Alcohol 0g",
        # not "/target alcohol max 0". Third time a card has taught one format
        # and refused the obvious one; the gate is the same gate.
        await db.put_pending(u["id"], "target_await", {})
        return

    joined = " ".join(args)
    if await _try_target_lines(msg, u, joined):
        return
    m = TARGET_LINE.match(joined)
    if m and await _set_one_target(msg, u, m.group("name").strip(),
                                   m.group("bound"), m.group("value")):
        return
    await msg.answer(
        f"I could not find a nutrient in {render._esc(joined)}. "
        "Try <code>/target</code> to see the names as they are stored.",
        parse_mode="HTML",
    )


@dp.message(Command("profile", "me"))
async def profile_cmd(msg: Message) -> None:
    """`/profile` reads · `/profile 4 183`, or several numbered lines, set.

    These five numbers used to exist only as arguments to a bootstrap script:
    read once, turned into targets, and discarded. That made every target
    unexplainable — you could see 2,418 kcal and nothing could tell you what it
    was derived from — and uncorrectable without hand-editing the database.
    """
    u = await _user(msg)
    text = (msg.text or "")
    rest = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""

    # `/profile 4 183` and a multi-line block are the same operation.
    edits = _profile_edits(rest) or (
        [(int(rest.split()[0]), rest.split(maxsplit=1)[1])]
        if rest.split() and rest.split()[0].isdigit() and len(rest.split()) > 1
        else None
    )
    if edits:
        await _apply_profile_edits(msg, u, edits)
        return

    data = await db.profile(u["id"])
    await msg.answer(
        render.profile_card(data, _today(u)),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 recalculate targets", callback_data="precalc:"),
        ]]),
    )
    await db.put_pending(u["id"], "profile_await", {})


async def _recalculate_targets(msg: Message, u: Any) -> None:
    """Recompute every derived target from the current profile and weight.

    Never automatic. Invariant 3 says targets are versioned rather than
    updated, and the reason is that a weigh-in must not silently rewrite what
    yesterday was being judged against — you would open /yesterday and find a
    different verdict than the one you were given.
    """
    data = await db.profile(u["id"])
    row = data["user"]
    today = _today(u)

    try:
        targets, working = profile_mod.derive_targets(
            sex=row["sex"],
            weight_kg=data["weight_kg"],
            height_cm=float(row["height_cm"]) if row["height_cm"] else None,
            age=profile_mod.age_years(row["birth_date"], today),
            activity=float(row["activity_factor"]) if row["activity_factor"] else None,
            deficit=float(row["deficit_kcal"] or 0),
            goal=row["goal"],
            measured_tdee=float(row["measured_tdee_kcal"]) if row["measured_tdee_kcal"] else None,
        )
    except (profile_mod.IncompleteProfile, TypeError) as exc:
        missing = str(exc) if isinstance(exc, profile_mod.IncompleteProfile) else "some fields"
        await msg.answer(
            f"❌ Cannot compute targets: {render._esc(missing)} still missing. "
            "Set them with <code>/profile</code> first — a target derived from a "
            "guessed height looks exactly like a real one, which is worse than none.",
            parse_mode="HTML",
        )
        return

    applied = await db.apply_targets(u["id"], targets, today, "profile recalculation")
    await db.mark_targets_derived(u["id"], data["weight_kg"], today)

    # The card knows what is wrong and knows the number that fixes it. Making
    # you retype it is the same friction as every other prompt here that taught
    # a syntax instead of doing the thing.
    offset = profile_mod.suggested_offset(row["goal"])
    fix = None
    if profile_mod.goal_conflict(row["goal"], row["deficit_kcal"]) and offset:
        word = "deficit" if offset > 0 else "surplus"
        fix = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=f"⚡ use a {abs(offset):g} kcal {word}",
            callback_data=f"setdef:{offset:g}")]])
    await msg.answer(
        render.profile_recalc_card(working, applied, data["weight_kg"],
                                   goal=row["goal"], deficit=row["deficit_kcal"]),
        parse_mode="HTML",
        reply_markup=fix,
    )


@dp.callback_query(F.data.startswith("precalc:"))
async def cb_profile_recalc(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await cq.answer("Recalculated")
    await _recalculate_targets(cq.message, u)


@dp.callback_query(F.data.startswith("setdef:"))
async def cb_set_deficit(cq: CallbackQuery) -> None:
    """Set the offset and redo the recalculation in one tap."""
    u = await db.get_or_create_user(cq.from_user.id)
    offset = float(cq.data.split(":", 1)[1])
    await db.set_profile_field(u["id"], "deficit_kcal", offset)
    await cq.answer(f"Set to {abs(offset):g}")
    await _recalculate_targets(cq.message, u)


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
        # Reading is the safe default. The menu sends a bare /weight the
        # instant it is tapped, and half the time the question is "what was I
        # last?" rather than "record this" — so answer that, and make recording
        # a deliberate second step rather than something a stray tap starts.
        await msg.answer(
            render.weight_card(await db.last_weight(u["id"]), u["tz"]),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⚖️ log a new one", callback_data="wnew:"),
            ]]),
        )
        return

    await _record_weight(msg, u, kg)


async def _record_weight(msg: Message, u: Any, kg: float) -> None:
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


def _supp_manage_keyboard(stack: Sequence[Any],
                          retired: Sequence[Any] = ()) -> InlineKeyboardMarkup | None:
    """A ❌ per supplement, numbered to match the card, plus ↩️ to restore."""
    rows: list[list[InlineKeyboardButton]] = []
    for chunk in (list(enumerate(stack, start=1))[i:i + 5] for i in range(0, len(stack), 5)):
        rows.append([
            InlineKeyboardButton(text=f"❌ {i}", callback_data=f"suppoff:{s['id']}")
            for i, s in chunk
        ])
    for r in retired[:5]:
        rows.append([InlineKeyboardButton(
            text=f"↩️ restore {render._short_note(r['name'])}",
            callback_data=f"suppon:{r['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


@dp.callback_query(F.data.startswith("suppoff:"))
async def cb_supp_stop(cq: CallbackQuery) -> None:
    """Ask first. Stopping is reversible, but the confirmation is where the
    distinction between stopping and deleting gets said out loud."""
    u = await db.get_or_create_user(cq.from_user.id)
    sid = int(cq.data.split(":", 1)[1])
    row = await db.supplement_by_id(u["id"], sid)
    await cq.answer()
    if not row:
        await cq.message.answer("That one is not in your stack.")
        return
    await cq.message.answer(
        f"Stop taking <b>{render._esc(row['name'])}</b>?\n\n"
        "<i>It comes off the daily list from now on. Every day you already "
        "logged it keeps counting — the past does not change because you "
        "stopped.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ stop it", callback_data=f"suppoff!:{sid}"),
            InlineKeyboardButton(text="keep taking it", callback_data="suppkeep:"),
        ]]),
    )


@dp.callback_query(F.data.startswith("suppoff!:"))
async def cb_supp_stop_confirm(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    sid = int(cq.data.split(":", 1)[1])
    name = await db.set_supplement_active(u["id"], sid, False)
    await cq.answer("Stopped")
    await cq.message.edit_text(
        f"💊 Stopped <b>{render._esc(name or 'it')}</b>. "
        "<code>/supp list</code> to restore it.",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("suppon:"))
async def cb_supp_restore(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    sid = int(cq.data.split(":", 1)[1])
    name = await db.set_supplement_active(u["id"], sid, True)
    await cq.answer("Restored")
    await cq.message.edit_text(
        f"💊 <b>{render._esc(name or 'it')}</b> is back in the daily stack.",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("suppkeep:"))
async def cb_supp_keep(cq: CallbackQuery) -> None:
    await cq.answer("Kept")
    await cq.message.edit_text("Kept. Nothing changed.")


SLOT_ASSIGN = re.compile(r"^\s*(\d{1,2})\s*[.):]\s*(fasted|breakfast|evening|bed|none|-)\s*$",
                         re.IGNORECASE)
SLOT_TIME = re.compile(
    r"^\s*(fasted|breakfast|evening|bed)\s+(?:(\d{1,2})[:.](\d{2})|(off|none))\s*$",
    re.IGNORECASE)


async def _try_slot_lines(msg: Message, u: Any, text: str) -> bool:
    """"3. evening" and "evening 21:00", one per line. False if neither."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    parsed = [(SLOT_ASSIGN.match(ln), SLOT_TIME.match(ln)) for ln in lines]
    if not all(a or t for a, t in parsed):
        return False

    stack = await db.supplement_stack(u["id"])
    notes: list[str] = []
    for assign, at_time in parsed:
        if assign:
            idx = int(assign.group(1))
            word = assign.group(2).lower()
            if not 1 <= idx <= len(stack):
                notes.append(f"❌ line {idx} — the list runs 1–{len(stack)}")
                continue
            slot = None if word in ("none", "-") else word
            name = await db.set_supplement_slot(u["id"], stack[idx - 1]["id"], slot)
            notes.append(
                f"✅ {render._esc(name)} → "
                + (render.slot_name(slot) if slot else "no moment")
            )
        else:
            slot = at_time.group(1).lower()
            if at_time.group(4):
                await db.set_slot_time(u["id"], slot, None)
                notes.append(f"🔕 {render.slot_name(slot)} — reminder off")
                continue
            hh, mm = int(at_time.group(2)), int(at_time.group(3))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                notes.append(f"❌ {hh}:{mm:02d} is not a time")
                continue
            await db.set_slot_time(u["id"], slot, dt.time(hh, mm))
            notes.append(f"⏰ {render.slot_name(slot)} at {hh:02d}:{mm:02d}")

    stack = await db.supplement_stack(u["id"])
    await msg.answer(
        "\n".join(notes) + "\n\n"
        + render.slot_settings_card(stack, await db.slot_times(u["id"])),
        parse_mode="HTML",
    )
    await db.put_pending(u["id"], "slot_await", {})
    return True


@dp.callback_query(F.data.startswith("slotlog:"))
async def cb_slot_log(cq: CallbackQuery) -> None:
    """Log exactly the supplements in one slot, from its reminder."""
    u = await db.get_or_create_user(cq.from_user.id)
    slot = cq.data.split(":", 1)[1]
    day = db.local_date_for(dt.datetime.now(dt.timezone.utc), u["tz"], u["day_rollover_hour"])
    rows = await db.supplements_in_slot(u["id"], slot, day)
    ids = [r["id"] for r in rows if not r["logged"]]
    if not ids:
        await cq.answer("Already logged")
        return
    n = await db.log_supplements(u["id"], day, ids)
    await cq.answer(f"Logged {n}")
    await cq.message.edit_text(
        f"✅ Logged {n} for <b>{render.slot_name(slot)}</b>.",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("slotskip:"))
async def cb_slot_skip(cq: CallbackQuery) -> None:
    slot = cq.data.split(":", 1)[1]
    await cq.answer()
    await cq.message.edit_text(
        f"Nothing logged for {render.slot_name(slot)}. "
        "<code>/supp</code> when you take them.",
        parse_mode="HTML",
    )


@dp.message(Command("next", "suggest"))
async def suggest_next(msg: Message) -> None:
    """What would close today's outstanding gaps, from dishes you already eat.

    Zero tokens and no model. See core/suggest.py for why that is the design
    rather than a limitation.
    """
    u = await _user(msg)
    day = _today(u)
    progress = await db.day_progress(u["id"], day)
    snapshots = await db.dish_snapshots(u["id"])
    ranked = suggest.rank(snapshots, progress)

    energy = next((r for r in progress if r["nutrient_id"] == 1008), None)
    kcal_left = None
    if energy and energy["max_amount"]:
        kcal_left = float(energy["max_amount"]) - float(energy["amount"])

    rows = [[InlineKeyboardButton(text=f"\U0001F37D {render._short_note(s.name)[:28]}",
                                  callback_data=f"rpt:{s.slug}")]
            for s in ranked]
    await msg.answer(
        render.suggest_card(ranked, progress, kcal_left),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
    )


@dp.callback_query(F.data.startswith("rpt:"))
async def cb_repeat_dish(cq: CallbackQuery) -> None:
    """Tap a suggestion to log it, through the ordinary repeat path.

    Not a second logging route: it builds the same RepeatCommand a typed
    repeat produces and hands it to the same function, so the confirm gate,
    the provenance and the zero-token accounting are identical.
    """
    u = await db.get_or_create_user(cq.from_user.id)
    slug = cq.data.split(":", 1)[1]
    await cq.answer()
    cmd = dsl.RepeatCommand(selector=slug, selector_kind="slug", ops=[])
    if not await _try_repeat(cq.message, u, cmd):
        await cq.message.answer(
            "That dish is not available to repeat any more. "
            "<code>/repeat</code> shows what is.",
            parse_mode="HTML",
        )


async def _tdee_offer(u: Any, flr: Any) -> tuple[str, Any] | None:
    """The card and keyboard for adopting a measured TDEE, or None."""
    if not flr or not flr.implied_tdee_kcal:
        return None
    data = await db.profile(u["id"])
    row = data["user"]
    if row["measured_tdee_kcal"] and abs(
            float(row["measured_tdee_kcal"]) - flr.implied_tdee_kcal) < 25:
        return None    # already using essentially this number

    ree = None
    if all(row[f] is not None for f in ("sex", "height_cm", "birth_date")) and data["weight_kg"]:
        ree = profile_mod.mifflin_st_jeor(
            row["sex"], data["weight_kg"], float(row["height_cm"]),
            profile_mod.age_years(row["birth_date"], _today(u)),
        )
    implied = profile_mod.implied_activity_factor(flr.implied_tdee_kcal, ree) if ree else None
    card = render.measured_tdee_offer(
        flr, data["energy_target"], row["activity_factor"], implied)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=f"\U0001F4D0 set targets from {flr.implied_tdee_kcal:,.0f} kcal",
        callback_data=f"usetdee:{flr.implied_tdee_kcal:.0f}:{flr.days}")]])
    return card, kb


@dp.callback_query(F.data.startswith("usetdee:"))
async def cb_use_measured_tdee(cq: CallbackQuery) -> None:
    """Adopt the measurement, and record the activity factor it implies.

    The factor is written back too, so a later recalculation after a weight
    change does not quietly fall back to the multiplier you once picked off a
    list. A measurement that is used once and then forgotten is a measurement
    that was not really adopted.
    """
    u = await db.get_or_create_user(cq.from_user.id)
    _, tdee_s, days_s = cq.data.split(":")
    tdee, days = float(tdee_s), int(days_s)
    today = _today(u)

    data = await db.profile(u["id"])
    row = data["user"]
    if all(row[f] is not None for f in ("sex", "height_cm", "birth_date")) and data["weight_kg"]:
        ree = profile_mod.mifflin_st_jeor(
            row["sex"], data["weight_kg"], float(row["height_cm"]),
            profile_mod.age_years(row["birth_date"], today),
        )
        implied = profile_mod.implied_activity_factor(tdee, ree)
        if implied:
            await db.set_profile_field(u["id"], "activity_factor", implied)

    await db.record_measured_tdee(u["id"], tdee, days, today)
    await cq.answer("Using your measurement")
    await _recalculate_targets(cq.message, u)


@dp.message(Command("why", "breakdown"))
async def why_cmd(msg: Message) -> None:
    """`/why cholesterol` — which meal, and which thing on it.

    A day card can say 250% of a ceiling and leave you no way to find out
    where it came from short of reading every entry. That makes a breach
    something that happens to you rather than something you did.
    """
    u = await _user(msg)
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        # Asks and then listens. Printing instructions and dropping the reply
        # into the meal parser is the bug this registry exists to prevent.
        await _ask(msg, u, "why_await",
                   "Which nutrient? Reply with a name — <code>cholesterol</code>, "
                   "<code>fat</code>, <code>sugar</code> — or "
                   "<code>/why fibre</code> in one go.")
        return
    await _explain_nutrient(msg, u, parts[1].strip())


async def _explain_nutrient(msg: Message, u: Any, term: str) -> bool:
    """Returns False when the word is not a nutrient, so a meal still parses."""
    matches = await db.find_nutrients(render.usda_name_for(term) or term)
    if not matches:
        return False
    exact = [m for m in matches
             if term.lower() in (m["name"].lower(), render._short(m["name"]).lower())]
    n = exact[0] if exact else matches[0]

    day = _today(u)
    progress = {r["nutrient_id"]: r for r in await db.day_progress(u["id"], day)}
    row = progress.get(n["id"])
    target = None
    is_ceiling = False
    if row:
        if row["max_amount"] is not None:
            target, is_ceiling = float(row["max_amount"]), True
        elif row["min_amount"] is not None:
            target = float(row["min_amount"])

    await msg.answer(
        render.why_card(
            n["name"], n["unit"], day,
            await db.nutrient_attribution(u["id"], day, n["id"]),
            await db.supplement_contribution(u["id"], day, n["id"]),
            target, is_ceiling, tz=u["tz"],
        ),
        parse_mode="HTML",
    )
    await db.clear_pending(u["id"], "why_await")
    return True


@dp.message(Command("food", "foods"))
async def food_cmd(msg: Message) -> None:
    """`/food` lists your own foods · `/food new pickle juice` makes one.

    USDA has no row for pickle brine, so "100 ml of pickle juice" matched
    "Relish, pickle" at 130 kcal and 35 g of carbs. Some things you eat are
    simply not in a national food database, and without somewhere to put them
    the resolver has to pick the least-bad wrong answer every single time.
    """
    u = await _user(msg)
    rest = (msg.text or "").split(maxsplit=2)

    if len(rest) >= 3 and rest[1].lower() in ("new", "add"):
        name = rest[2].strip()
        await db.put_pending(u["id"], "food_await", {"name": name})
        await msg.answer(
            f"🥫 <b>{render._esc(name)}</b> — what goes into it?\n\n"
            "Reply with the ingredients and amounts, as you would a meal:\n"
            "<code>1000 ml water, 30 g salt, 100 ml white vinegar</code>\n\n"
            "<i>I will resolve each one against USDA, add them up, and store "
            "the result per 100 g. Nothing is estimated — if an ingredient "
            "has no row, I will say so rather than guess around it.</i>",
            parse_mode="HTML",
        )
        return

    if len(rest) >= 2 and rest[1].lower() in ("new", "add"):
        await msg.answer(
            "Name it first — <code>/food new pickle juice</code>.", parse_mode="HTML")
        return

    # Lists *and* listens. Printing "/food new pickle juice" and then sending
    # the reply to the meal parser is the eighth instance of a card teaching a
    # syntax instead of doing the thing.
    await _ask(
        msg, u, "food_name_await",
        render.user_food_list_card(await db.user_foods(u["id"])),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✋ never mind", callback_data="foodcancel:"),
        ]]),
    )


@consumes("food_name_await")
async def _consume_food_name(msg: Message, u: Any, text: str, payload: dict) -> bool:
    """The reply to "what would you like to call it?".

    A food name and a meal description are the same kind of string — "pickle
    juice" is both — so this cannot be told apart by inspection. It asks
    instead, and one tap sends it to the meal parser if that is what you meant.
    """
    name = text.strip()
    if not name or len(name) > 60:
        return False
    await db.clear_pending(u["id"], "food_name_await")
    await db.put_pending(u["id"], "food_await", {"name": name})
    await msg.answer(
        f"🥫 Making a food called <b>{render._esc(name)}</b>.\n\n"
        "<b>What goes into it?</b> Reply with ingredients and amounts:\n"
        "<code>1000 ml water, 30 g salt, 100 ml white vinegar</code>\n\n"
        "<i>Or <b>photograph the nutrition panel</b>, or send its "
        "<b>barcode</b>. Ingredients are resolved against USDA and added "
        "up — nothing estimated; an ingredient with no row is left out and "
        "named, not guessed around.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔎 search OpenFoodFacts",
                                  callback_data="offsearch:")],
            [InlineKeyboardButton(text="🍽 no — log it as a meal",
                                  callback_data="foodmeal:")],
        ]),
    )
    return True


@dp.callback_query(F.data.startswith("foodcancel:"))
async def cb_food_cancel(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await db.clear_awaits(u["id"], ("food_name_await", "food_await"))
    await cq.answer("Closed")
    await cq.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data.startswith("foodmeal:"))
async def cb_food_as_meal(cq: CallbackQuery) -> None:
    """You meant to log it, not define it. One tap, no retyping."""
    u = await db.get_or_create_user(cq.from_user.id)
    pending = await db.latest_pending(u["id"], "food_await")
    name = (pending or {}).get("name", "")
    await db.clear_awaits(u["id"], ("food_name_await", "food_await"))
    await cq.answer()
    if not name:
        await cq.message.answer("Nothing to log. Send the meal again.")
        return
    await cq.message.edit_reply_markup(reply_markup=None)
    note = await cq.message.answer("🍽 digesting…")
    try:
        parsed = await llm.parse_text(name, user_id=u["id"])
    except Exception as exc:
        await _parse_failed(note, exc)
        return
    await _present(cq.message, u, parsed, source="text",
                   photo_file_id=None, edit=note)


@consumes("food_await")
async def _consume_food_recipe(msg: Message, u: Any, text: str, payload: dict) -> bool:
    """Turn a list of ingredients into one food row, by arithmetic only."""
    name = payload.get("name") or "unnamed"

    bc = BARCODE.match(text)
    if bc:
        note = await msg.answer("🔎 looking up the barcode…")
        p = await off.by_barcode(bc.group(1))
        if not p:
            await note.edit_text(
                "That barcode is not on OpenFoodFacts. Send the ingredients "
                "instead and I will build the panel from USDA rows.")
            return True
        await note.delete()
        await _offer_off_product(msg, u, p, name)
        return True

    note = await msg.answer("🥫 working it out…")
    try:
        parsed = await llm.parse_text(text, user_id=u["id"])
    except Exception as exc:
        await _parse_failed(note, exc)
        return True
    res = await llm.resolve_items(u["id"], parsed.items)
    if not res.components:
        await note.edit_text(
            "None of those matched a food row, so there is nothing to build "
            "from. Try naming the ingredients more plainly.")
        return True

    profiles = await db.profiles_for({c.fdc_id for c in res.components})
    totals = total_nutrients(res.components, profiles)
    yield_g = sum(c.grams for c in res.components)
    if yield_g <= 0:
        await note.edit_text("That came to no mass at all, so I cannot store it.")
        return True

    per_100g = {nid: amount / yield_g * 100 for nid, amount in totals.items()}

    # A food with macros and no energy is a wrong row, not a zero-calorie
    # food. "butter" resolved to a Foundation entry carrying 81.5 g of fat and
    # no energy figure at all, and the panel was stored saying zero — which
    # then subtracts nothing from an energy ceiling for ever.
    if not per_100g.get(ENERGY_KCAL) and any(
        per_100g.get(n, 0) > 0 for n in (PROTEIN, CARB, FAT)
    ):
        await note.edit_text(
            "❌ The rows those ingredients matched carry no energy figure, so "
            "this would be stored as a food with fat and no calories.\n\n"
            "<i>Name the ingredient differently — 'butter' rather than a "
            "brand, say — or photograph the panel instead.</i>",
            parse_mode="HTML",
        )
        return True
    fdc_id = await db.create_user_food(
        u["id"], name, per_100g,
        note=f"made from: {', '.join(f'{c.grams:g} g {c.label}' for c in res.components)}",
    )
    # The name becomes an alias too, so the next time you type it the resolver
    # takes the free path rather than searching for it again.
    await db.upsert_alias(u["id"], name, fdc_id, None)
    await db.clear_pending(u["id"], "food_await")

    parts = [f"{c.grams:g} g {c.label}" for c in res.components]
    if res.unresolved:
        parts.append("(not found, and therefore not counted: "
                     + ", ".join(res.unresolved) + ")")
    await note.edit_text(
        render.user_food_made_card(name, per_100g, parts, yield_g),
        parse_mode="HTML",
    )
    return True


@dp.message(Command("report", "review"))
async def report_cmd(msg: Message) -> None:
    """The weekly review, on demand. It also arrives on Sunday at 18:00.

    The only path here that calls a large model to reason rather than to
    extract, and the only card that is an argument rather than arithmetic.
    """
    u = await _user(msg)
    day = _today(u)
    p = await db.pool()
    logged = await p.fetchval(
        """SELECT count(DISTINCT local_date) FROM log_entry
            WHERE user_id=$1 AND status='confirmed' AND local_date > $2::date - 28""",
        u["id"], day,
    )
    if logged < report_job.MIN_DAYS_LOGGED:
        await msg.answer(
            f"📓 {logged} of the last 28 days have anything logged. Below "
            f"{report_job.MIN_DAYS_LOGGED} there is no pattern to review, and an "
            "expensive model asked anyway will find one — it would describe a "
            "diet you do not eat.",
            parse_mode="HTML")
        return

    note = await msg.answer("🧠 reading the last four weeks…")
    try:
        data, cost = await plan.propose(u["id"], day)
    except Exception as exc:
        await _parse_failed(note, exc)
        return
    await note.edit_text(render.plan_card(data, cost), parse_mode="HTML")
    if data.get("recommendations"):
        await db.put_pending(u["id"], "plan_apply", {})


@consumes("plan_apply")
async def _consume_plan_apply(msg: Message, u: Any, text: str, payload: dict) -> bool:
    """"apply 1 3" / "apply all". Anything else is a meal and passes through."""
    words = text.strip().lower().split()
    if not words or words[0] != "apply":
        return False
    action = await db.latest_pending(u["id"], "plan_proposal")
    if not action:
        await msg.answer("That proposal has expired. <code>/report</code> for a new one.",
                         parse_mode="HTML")
        return True
    recs = action.get("recommendations") or []
    if len(words) > 1 and words[1] == "all":
        numbers = {int(r["n"]) for r in recs}
    else:
        numbers = {int(w) for w in words[1:] if w.isdigit()}
    if not numbers:
        await msg.answer("Which ones? <code>apply 1 3</code> or <code>apply all</code>.",
                         parse_mode="HTML")
        return True

    applied = await plan.apply_recommendations(u["id"], action, numbers, _today(u))
    await db.clear_pending(u["id"], "plan_apply")
    if not applied:
        await msg.answer("Nothing matched those numbers, so nothing changed.")
        return True
    await msg.answer(
        "✅ Applied:\n" + "\n".join(f"   • {render._esc(a)}" for a in applied)
        + "\n\n<i>Targets are versioned, so past days keep the ones they were "
          "judged against.</i>",
        parse_mode="HTML",
    )
    return True


@dp.callback_query(F.data.startswith("when:"))
async def cb_set_time(cq: CallbackQuery) -> None:
    """Move an entry to when you actually ate it.

    Logging happens when you get round to it, not when you eat — and the
    fasting window, the caffeine-after-noon covariate and every sleep
    correlation are computed from the timestamp, so a meal filed an hour late
    is a small error in four places at once.
    """
    u = await db.get_or_create_user(cq.from_user.id)
    entry_id = int(cq.data.split(":", 1)[1])
    await db.put_pending(u["id"], "time_await", {"entry_id": entry_id})
    await cq.answer()
    await cq.message.answer(
        "🕐 <b>When did you have it?</b>\n\n"
        "<code>08:30</code> · <code>yesterday 19:00</code> · "
        "<code>-2h</code> for two hours ago",
        parse_mode="HTML",
    )


TIME_REPLY = re.compile(
    r"^\s*(?:(?P<rel>-\d{1,2})\s*h"
    r"|(?:(?P<yday>yesterday|yday)\s+)?(?P<h>\d{1,2})[:.](?P<m>\d{2}))\s*$",
    re.IGNORECASE,
)


@consumes("time_await")
async def _consume_time(msg: Message, u: Any, text: str, payload: dict) -> bool:
    m = TIME_REPLY.match(text)
    if not m:
        return False    # not a time, so it is a meal and passes through
    now = _local_now(u)
    if m.group("rel"):
        when = now + dt.timedelta(hours=int(m.group("rel")))
    else:
        when = now.replace(hour=int(m.group("h")), minute=int(m.group("m")),
                           second=0, microsecond=0)
        if m.group("yday"):
            when -= dt.timedelta(days=1)
        elif when > now:
            # 23:40 typed at 00:10 means last night, not tonight. Never
            # forward: you cannot have eaten something you have not eaten.
            when -= dt.timedelta(days=1)

    entry_id = int(payload["entry_id"])
    day = await db.set_entry_time(
        entry_id, when.astimezone(dt.timezone.utc), u["tz"], u["day_rollover_hour"])
    await db.clear_pending(u["id"], "time_await")
    same_day = day == _today(u)
    await msg.answer(
        f"🕐 Moved to <b>{when:%H:%M}</b>"
        + ("" if same_day else f" on <b>{day:%a %-d %b}</b>")
        + ".\n\n<i>Confirm it above when you are ready.</i>",
        parse_mode="HTML",
    )
    return True


BARCODE = re.compile(r"^\s*(\d{8,14})\s*$")


async def _offer_off_product(msg: Message, u: Any, p: dict, name: str) -> None:
    """Show a looked-up panel and wait for a decision. Never saves first."""
    await db.put_pending(u["id"], "off_product", {"product": {
        "name": p["name"], "brand": p["brand"], "barcode": p["barcode"],
        "panel": {str(k): v for k, v in p["panel"].items()},
    }, "name": name})
    await msg.answer(
        render.off_product_card(p, name),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ save it", callback_data="offok:"),
            InlineKeyboardButton(text="✏️ rename", callback_data="offname:"),
            InlineKeyboardButton(text="🗑 no", callback_data="offno:"),
        ]]),
    )


@dp.callback_query(F.data.startswith("offsearch:"))
async def cb_off_search(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    pending = await db.latest_pending(u["id"], "food_await")
    name = (pending or {}).get("name", "")
    await cq.answer()
    if not name:
        await cq.message.answer("Start with <code>/food</code> and a name.",
                                parse_mode="HTML")
        return
    note = await cq.message.answer("🔎 searching OpenFoodFacts…")
    results = await off.search(name)
    if not results:
        await note.edit_text(render.off_choices_card([], name), parse_mode="HTML")
        return
    await db.put_pending(u["id"], "off_choices", {
        "results": [{"name": r["name"], "brand": r["brand"],
                     "barcode": r["barcode"]} for r in results],
        "name": name,
    })
    await note.edit_text(
        render.off_choices_card(results, name),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=str(i + 1), callback_data=f"offpick:{i}")
            for i in range(len(results))
        ]]),
    )


@dp.callback_query(F.data.startswith("offpick:"))
async def cb_off_pick(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    idx = int(cq.data.split(":", 1)[1])
    choices = await db.latest_pending(u["id"], "off_choices")
    await cq.answer()
    if not choices or idx >= len(choices["results"]):
        await cq.message.answer("That list has expired. <code>/food</code> to start again.",
                                parse_mode="HTML")
        return
    picked = choices["results"][idx]
    p = await off.by_barcode(picked["barcode"])
    if not p:
        await cq.message.answer("OpenFoodFacts did not return that product.")
        return
    await _offer_off_product(cq.message, u, p, choices["name"])


@dp.callback_query(F.data.startswith("offok:"))
async def cb_off_save(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    pending = await db.latest_pending(u["id"], "off_product")
    await cq.answer()
    if not pending:
        await cq.message.answer("That product has expired. <code>/food</code> again.",
                                parse_mode="HTML")
        return
    prod = pending["product"]
    name = pending.get("name") or prod["name"]
    panel = {int(k): float(v) for k, v in prod["panel"].items()}
    fdc_id = await db.create_user_food(
        u["id"], name, panel,
        note=f"OpenFoodFacts {prod['barcode']} · {prod['brand']}".strip(" ·"),
    )
    await db.upsert_alias(u["id"], name, fdc_id, None)
    await db.clear_awaits(u["id"], ("food_await", "off_product", "off_choices"))
    await cq.message.answer(
        f"🥫 <b>{render._esc(render._title(name))}</b> saved from OpenFoodFacts "
        f"({len(panel)} nutrients).\n\n"
        "<i>It outranks USDA's generic row when you log that name. Correct it "
        "any time by defining it again — same name, same row.</i>",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("offname:"))
async def cb_off_rename(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await db.put_pending(u["id"], "off_rename", {})
    await cq.answer()
    await cq.message.answer(
        "What should it be called? <i>The name you will actually type when "
        "logging it — short beats accurate.</i>", parse_mode="HTML")


@consumes("off_rename")
async def _consume_off_rename(msg: Message, u: Any, text: str, payload: dict) -> bool:
    name = text.strip()
    if not name or len(name) > 60:
        return False
    pending = await db.latest_pending(u["id"], "off_product")
    if not pending:
        return False
    await db.put_pending(u["id"], "off_product", {**pending, "name": name})
    await db.clear_pending(u["id"], "off_rename")
    await msg.answer(
        f"Renamed to <b>{render._esc(render._title(name))}</b>. "
        "Tap <b>save it</b> above.", parse_mode="HTML")
    return True


@dp.callback_query(F.data.startswith("offno:"))
async def cb_off_discard(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await db.clear_awaits(u["id"], ("off_product", "off_choices"))
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.message.answer("Nothing saved. Send the ingredients instead, or "
                            "another barcode.")


async def _handle_food_label(msg: Message, u: Any, name: str) -> None:
    """Transcribe a packaged food's panel and offer to store it.

    Same amendment as the supplement panel: a model may transcribe a printed
    figure, never estimate one. What makes that safe is that it is checkable
    at the moment it is made — so the card shows each line as printed beside
    the figure taken from it.
    """
    f = await msg.bot.get_file(msg.photo[-1].file_id)
    buf = await msg.bot.download_file(f.file_path)
    b64, _w, _h = llm.prepare_image(buf.read())

    note = await msg.answer("🏷 reading the panel…")
    try:
        data, cost = await llm.read_food_label(
            user_id=u["id"], image_b64=b64, name_hint=name)
    except Exception as exc:
        await _parse_failed(note, exc)
        return

    panel, warnings = llm.per_100g(data)
    label_name = name or data.get("product_name") or "unnamed"
    if not panel:
        await note.edit_text(
            render.food_label_card(label_name, {}, data, warnings), parse_mode="HTML")
        return

    await db.put_pending(u["id"], "food_panel", {
        "name": label_name,
        "panel": {str(k): v for k, v in panel.items()},
        "cost": cost,
    })
    await note.edit_text(
        render.food_label_card(label_name, panel, data, warnings)
        + f"\n<i>💸 {cost*100:.1f}¢</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ save it", callback_data="panelok:"),
            InlineKeyboardButton(text="🗑 no", callback_data="panelno:"),
        ]]),
    )


@dp.callback_query(F.data.startswith("panelok:"))
async def cb_food_panel_save(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    pending = await db.latest_pending(u["id"], "food_panel")
    await cq.answer()
    if not pending:
        await cq.message.answer("That panel has expired. <code>/food</code> again.",
                                parse_mode="HTML")
        return
    name = pending["name"]
    panel = {int(k): float(v) for k, v in pending["panel"].items()}
    fdc_id = await db.create_user_food(
        u["id"], name, panel, note="transcribed from the printed panel")
    await db.upsert_alias(u["id"], name, fdc_id, None)
    await db.clear_awaits(u["id"], ("food_await", "food_panel"))
    await cq.message.answer(
        f"🥫 <b>{render._esc(render._title(name))}</b> saved — "
        f"{len(panel)} nutrients from the packet.\n\n"
        "<i>It outranks USDA's generic row whenever you log that name. "
        "Photograph the panel again to correct it.</i>",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("panelno:"))
async def cb_food_panel_discard(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await db.clear_pending(u["id"], "food_panel")
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.message.answer("Nothing saved. Send a clearer photo, a barcode, "
                            "or the ingredients.")


@dp.message(Command("stack"))
async def supp_stack_cmd(msg: Message) -> None:
    """`/supp list` under its own name.

    Telegram's menu can only hold single tokens, so a subcommand is invisible
    there — and a feature reachable only by typing a word you have to already
    know about is one most people never find.
    """
    u = await _user(msg)
    stack = await db.supplement_stack(u["id"])
    retired = [r for r in await db.supplement_stack(u["id"], active_only=False)
               if not r["active"]]
    if not stack and not retired:
        await msg.answer(
            "No supplements yet. <code>/supp</code>, then “➕ add”.", parse_mode="HTML")
        return
    await msg.answer(
        render.supplement_stack_card(stack, retired),
        parse_mode="HTML",
        reply_markup=_supp_manage_keyboard(stack, retired),
    )


@dp.message(Command("schedule"))
async def supp_schedule_cmd(msg: Message) -> None:
    """`/supp times` under its own name."""
    u = await _user(msg)
    stack = await db.supplement_stack(u["id"])
    if not stack:
        await msg.answer(
            "No supplements to schedule yet. <code>/supp</code>, then “➕ add”.",
            parse_mode="HTML")
        return
    await msg.answer(
        render.slot_settings_card(stack, await db.slot_times(u["id"])),
        parse_mode="HTML",
    )
    await db.put_pending(u["id"], "slot_await", {})


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
    # The daily picker hides what has not started. /stack and /schedule show
    # everything, because a supplement decided on but not begun is exactly
    # what those two screens exist to display.
    stack = await db.supplement_stack(u["id"], on_day=day)

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

    if sub.startswith(("time", "when")):
        await msg.answer(
            render.slot_settings_card(stack, await db.slot_times(u["id"])),
            parse_mode="HTML",
        )
        await db.put_pending(u["id"], "slot_await", {})
        return

    if sub.startswith("list"):
        retired = [r for r in await db.supplement_stack(u["id"], active_only=False)
                   if not r["active"]]
        await msg.answer(
            render.supplement_stack_card(stack, retired),
            parse_mode="HTML",
            reply_markup=_supp_manage_keyboard(stack, retired),
        )
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
    reason = "logged"
    if not selected:
        selected = await db.supplements_due(u["id"], day)
        reason = "schedule"

    action_id = await db.put_pending(u["id"], "supp_pick", {
        "selected": selected, "day": day.isoformat(), "reason": reason,
    })
    await msg.answer(
        render.supplement_pick_card(stack, selected, reason),
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
    # Managing the stack has to live on the card you actually open. Removal
    # and scheduling existed behind `/supp list` and `/supp times`, which is
    # the same as not existing if the picker never mentions them.
    rows.append([
        InlineKeyboardButton(text="➕ add", callback_data="supadd:"),
        InlineKeyboardButton(text="🗑 stop one", callback_data="supmanage:"),
        InlineKeyboardButton(text="⏰ times", callback_data="suptimes:"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data.startswith("supmanage:"))
async def cb_supp_manage(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    stack = await db.supplement_stack(u["id"])
    retired = [r for r in await db.supplement_stack(u["id"], active_only=False)
               if not r["active"]]
    await cq.answer()
    await cq.message.answer(
        render.supplement_stack_card(stack, retired),
        parse_mode="HTML",
        reply_markup=_supp_manage_keyboard(stack, retired),
    )


@dp.callback_query(F.data.startswith("suptimes:"))
async def cb_supp_times(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await cq.answer()
    await cq.message.answer(
        render.slot_settings_card(await db.supplement_stack(u["id"]),
                                  await db.slot_times(u["id"])),
        parse_mode="HTML",
    )
    await db.put_pending(u["id"], "slot_await", {})


@dp.callback_query(F.data.startswith("supadd:"))
async def cb_supp_add(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await db.put_pending(u["id"], "supp_label", {"awaiting": True})
    await cq.answer()
    await cq.message.answer(
        "📸 Send a photo of the label, or paste the product details as text.\n\n"
        "<i>I transcribe what is stated — I will not fill in what I think the "
        "product contains.</i>",
        parse_mode="HTML",
    )


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
        render.supplement_pick_card(stack, selected, payload.get("reason", "schedule")),
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
    tdee_offer: tuple[str, Any] | None = None

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
        # The measurement existed here all along and nothing ever used it: the
        # energy target stayed an equation's guess times a chosen multiplier
        # while the real number sat two lines above it, read and ignored.
        tdee_offer = await _tdee_offer(u, flr)

    for kind, label in (("focus", "focus vs hours fasted"),
                        ("rpe", "training effort vs hours fasted")):
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
        # Local, not UTC. This is the confounder check that decides whether a
        # correlation is really about the clock, so getting the clock wrong
        # defeats its whole purpose — and an offset that wraps past midnight
        # reorders the ranks rather than merely shifting them.
        import zoneinfo

        zone = zoneinfo.ZoneInfo(u["tz"])
        clock = [
            (lambda t: t.hour + t.minute / 60)(o["observed_at"].astimezone(zone))
            for o in obs
        ]
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
            ("caffeine after noon", "caffeine_pm_yesterday"),
            ("caffeine, total", "caffeine_yesterday"),
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

    # Sent as its own message, not appended: it is an offer to change your
    # targets, and burying a button under three screens of correlations is how
    # it goes unnoticed for another month.
    if tdee_offer:
        card, keyboard = tdee_offer
        await msg.answer(card, parse_mode="HTML", reply_markup=keyboard)


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

    # A photo sent while naming a food is that food's nutrition panel.
    food = await db.latest_pending(u["id"], "food_await", within_minutes=30)
    if food:
        await _handle_food_label(msg, u, food.get("name") or "")
        return

    # A photo sent *just* after "add a supplement" is a label. One sent hours
    # later is dinner: the prompt was still open because only a command clears
    # it, so a stale tap from the afternoon captured a plate of stir fry and
    # announced "reading the label…" over it.
    if await db.latest_pending(u["id"], "supp_label", within_minutes=15):
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

    # Every prompt that waits for a typed reply is handled in one place.
    if await _consume_awaited_reply(msg, u, text):
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



# Prompts answered by an ordinary message rather than a button.
#
# This gate exists because the same bug was fixed four times in four handlers:
# `/supp add` ignoring a written label, ✏️ ignoring a correction, the rating
# keypad ignoring its own number, `/weight` ignoring the number it had just
# asked for. Each time the answer fell through to the meal parser, which
# dutifully spent a Sonnet call establishing that "78.4" is not a food. A prompt
# that ignores its own answer is worse than no prompt, so a fifth prompt now
# inherits the behaviour instead of repeating the bug.
@consumes("supp_label")
async def _consume_supp_label(msg: Message, u: Any, text: str, payload: dict) -> bool:
    await _handle_supplement_label(msg, u, text=text)
    return True


@consumes("fix_entry")
async def _consume_fix(msg: Message, u: Any, text: str, payload: dict) -> bool:
    return await _try_fix(msg, u, text)


@consumes("profile_await")
async def _consume_profile(msg: Message, u: Any, text: str, payload: dict) -> bool:
    edits = _profile_edits(text)
    if not edits:
        return False   # not numbered lines, so it is a meal: let it through
    await _apply_profile_edits(msg, u, edits)
    return True


@consumes("slot_await")
async def _consume_slots(msg: Message, u: Any, text: str, payload: dict) -> bool:
    return await _try_slot_lines(msg, u, text)


@consumes("target_await")
async def _consume_targets(msg: Message, u: Any, text: str, payload: dict) -> bool:
    # Falls through to the meal parser when the line does not name a nutrient,
    # so "chicken 200g" is still dinner.
    return await _try_target_lines(msg, u, text)


@consumes("why_await")
async def _consume_why(msg: Message, u: Any, text: str, payload: dict) -> bool:
    return await _explain_nutrient(msg, u, text.strip())


@consumes("weight_await")
async def _consume_weight(msg: Message, u: Any, text: str, payload: dict) -> bool:
    try:
        value = float(text.strip().replace(",", "."))
    except ValueError:
        return False
    await db.clear_pending(u["id"], "weight_await")
    await _record_weight(msg, u, value)
    return True


@consumes("rate_await")
async def _consume_rating(msg: Message, u: Any, text: str, payload: dict) -> bool:
    try:
        value = float(text.strip().replace(",", "."))
    except ValueError:
        return False
    if not 0 < value <= 10:
        return False
    await db.clear_pending(u["id"], "rate_await")
    await _record_rating(msg, u, payload["kind"], value)
    return True


async def _consume_awaited_reply(msg: Message, u: Any, text: str) -> bool:
    """Route a message to whichever prompt is waiting for it. True if consumed.

    Newest prompt wins: if you press ✏️ and then tap /weight, the weight prompt
    is the one being answered — the earlier one was superseded by your own next
    action rather than abandoned.

    A consumer returning False means "this was not an answer to me", and the
    message goes on to the meal parser. That is how "chicken 200g" is still
    dinner while a target prompt is open.
    """
    pending = await db.latest_await(u["id"], tuple(PROMPT_CONSUMERS))
    if not pending:
        return False
    consumer = PROMPT_CONSUMERS.get(pending["kind"])
    if not consumer:
        return False
    return await consumer(msg, u, text, pending["payload"] or {})


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


async def _log_one_component(msg: Message, u: Any, comp: dict,
                             cmd: dsl.RepeatCommand) -> bool:
    """Log a single food at the amount you usually have of it.

    The mass is `stated` only when it came from portion_history, which reads
    weighed and stated masses alone — invariant 7. Otherwise it is a `prior`,
    and sigma is computed from that, so a median of estimates never presents
    itself as something you measured.
    """
    grams = float(comp.get("grams") or 0)
    for op in cmd.ops:
        if isinstance(op, dsl.Scale):
            grams *= float(op.factor)
        elif isinstance(op, dsl.TotalGrams):
            grams = float(op.grams)
    if grams <= 0:
        return False

    source = "stated" if comp.get("stated") else "prior"
    label = comp["label"]
    resolved = [ResolvedComponent(
        label, int(comp["fdc_id"]), grams, 1.0,
        estimate.sigma_for(grams, source), source)]
    entry_id = await db.create_pending_entry(
        u["id"], render._title(label), resolved,
        source="repeat", slot=dsl.slot_for_hour(_local_now(u).hour),
        confidence=None, model=None, parse={"one_component": True},
        photo_file_id=None, dish_id=None, when=_when_from_ops(cmd.ops, u),
        tz=u["tz"], rollover_hour=u["day_rollover_hour"],
        grams_sources=[source],
    )
    profiles = await db.profiles_for([int(comp["fdc_id"])])
    totals = total_nutrients(resolved, profiles)
    await msg.answer(
        render.confirm_card(render._title(label), resolved, totals,
                            confidence=None, warnings=[]),
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
        comps = menu.get("components", [])
        if len(ids) <= idx < len(ids) + len(comps):
            # A number past the dish list is one of the single foods below it.
            return await _log_one_component(msg, u, comps[idx - len(ids)], cmd)
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
        # The dish now carries provenance, so a repeat inherits it rather than
        # downgrading a stated portion to a guess every time it is reused.
        dsl.Component(r["label"], r["fdc_id"], float(r["grams"]), r["state"],
                      float(r["yield_factor"]), r["grams_source"])
        for r in rows
    ]

    ops = list(cmd.ops)
    model_used = None
    mod_warnings: list[str] = []
    if cmd.needs_model:
        # One cheap call, and it sees only the label list and the phrase.
        data = await llm.modifier_ops(
            [c.label for c in comps], " ".join(cmd.unparsed), user_id=u["id"]
        )
        model_used = "modifier"
        before = len(ops)
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

        # A change you asked for and did not get must never pass in silence.
        # "1 decaffe espresso" was read, paid for, understood by nobody, and
        # logged as ordinary espresso — 64 mg of caffeine — with the card
        # showing the unmodified dish and no indication anything had been
        # dropped. The gate is only a gate if it shows what it is gating.
        if len(ops) == before:
            mod_warnings.append(
                f"could not apply “{' '.join(cmd.unparsed)}” — this is the dish "
                f"unchanged. Describe it as a new meal if it was different."
            )

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
                new_comps.append(dsl.Component(c.label, c.fdc_id, c.grams,
                                               yield_factor=c.yield_factor,
                                               grams_source="stated"))

    when = _when_from_ops(ops, u)
    slot = dish["default_slot"]
    for op in ops:
        if isinstance(op, dsl.SetSlot):
            slot = op.slot

    # Sigma from the provenance, as on the fix path: a repeated stated mass is
    # as tight as the statement was, and a repeated guess is still a guess.
    resolved = [
        ResolvedComponent(c.label, c.fdc_id, c.grams, c.yield_factor,
                          estimate.sigma_for(c.grams, c.grams_source), c.grams_source)
        for c in new_comps if c.fdc_id
    ]
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
    warnings = list(mod_warnings)
    if never_confirmed:
        warnings.append(
            "this dish has never been confirmed — check it once and repeats are instant"
        )
    dropped = [c.label for c in new_comps if not c.fdc_id]
    if dropped:
        warnings.append(
            "could not find a food database row for: " + ", ".join(dropped)
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


async def _matched_names(components: Sequence[Any]) -> dict[int, str]:
    """USDA descriptions for what a parse resolved to, for the confirm card."""
    ids = [c.fdc_id for c in components if getattr(c, "fdc_id", None)]
    if not ids:
        return {}
    p = await db.pool()
    rows = await p.fetch(
        "SELECT fdc_id, description FROM food WHERE fdc_id = ANY($1::int[])", ids)
    return {r["fdc_id"]: r["description"] for r in rows}


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
            u["id"], parsed.dish_name, [],
            source=source, slot=dsl.slot_for_hour(_local_now(u).hour, parsed.slot),
            confidence=parsed.confidence, model=parsed.model,
        parse={**(parsed.raw or {}), "_weak": [w[0] for w in res.weak_matches]},
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
    # The clock decides the meal, not the model — see dsl.slot_for_hour.
    slot = dsl.slot_for_hour(_local_now(u).hour, parsed.slot)
    dish_name = render._title(parsed.dish_name)
    dish_id = await db.upsert_dish(u["id"], slug, dish_name, slot, res.components)

    entry_id = await db.create_pending_entry(
        u["id"], dish_name, res.components, source=source, slot=slot,
        confidence=parsed.confidence, model=parsed.model,
        parse={**(parsed.raw or {}), "_weak": [w[0] for w in res.weak_matches]},
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
        matched=await _matched_names(res.components),
        weak=res.weak_matches,
    )
    kb = kb_confirm(entry_id, res.weak_matches)
    if edit:
        await edit.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


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
    entry_id = int(cq.data.split(":")[1])
    # What the card offered before you discarded it, so the offer survives the
    # act that most strongly signals the food is missing: discarding a weak
    # match means the closest row in the database was not close enough.
    # Read from the entry, not from the message. Telegram echoes the keyboard
    # back on a callback but the offer is too important to depend on that, and
    # it is a fact about the parse rather than about the message.
    weak = await db.weak_labels(entry_id)
    await db.discard_entry(entry_id)
    keep = [InlineKeyboardButton(
        text=f"🥫 define {render._short_note(weak[0])[:18]} yourself",
        callback_data=f"deffood:{weak[0][:40]}")] if weak else []
    await cq.message.edit_text(
        (cq.message.text or "") + "\n\n❌ discarded",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[keep]) if keep else None,
    )
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


async def sync_command_menu(bot: Bot) -> None:
    """Push COMMANDS to Telegram's own menu on every start.

    The menu is server-side state that only setMyCommands changes, so removing
    a command from the code leaves it in the client indefinitely — /f survived
    three deploys after being deleted, and its description was two revisions
    behind. A menu maintained by hand is a menu that is wrong.

    Descriptions are stripped of the markup COMMANDS carries for the /start
    text; Telegram takes plain text only.
    """
    import re

    from aiogram.types import BotCommand

    try:
        await bot.set_my_commands([
            BotCommand(
                command=name.lstrip("/"),
                description=re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", desc)).strip()[:256],
            )
            for name, desc in COMMANDS
        ])
        log.info("command menu synced: %d commands", len(COMMANDS))
    except Exception as exc:  # a stale menu must not stop the bot starting
        log.warning("could not sync the command menu: %s", exc)


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(settings.telegram_token)
    bot.session.middleware(resend_unformatted)
    await sync_command_menu(bot)
    from .http_api import start as start_http
    from .jobs.notify import start_scheduler

    start_scheduler(bot)
    await start_http()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())


# Every registered prompt, resolved after the whole module has been imported.
# Assigning it beside the registry captured an empty dict, because the
# @consumes decorators below had not run yet.
AWAITING_KINDS = tuple(PROMPT_CONSUMERS)
