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
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from . import db, off
from .config import CARB, CONFIDENCE_FLOOR, ENERGY_KCAL, FAT, PROTEIN, settings
from .core import dsl, estimate, fasting, insight, plan, render, suggest
from .core import profile as profile_mod
from .core.nutrition import (
    ResolvedComponent,
    energy_cross_check,
    total_nutrients,
)
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
    payload = kw.pop("payload", None) or {}
    await msg.answer(text, parse_mode="HTML", **kw)
    await db.put_pending(u["id"], kind, payload)


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
        "<i>Baked? End with what it made — then a slice needs no weighing:</i>\n"
        "<code>… makes 850 g, 16 slices</code>\n\n"
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
    ("/again", "Repeat a whole morning, afternoon or evening"),
    ("/supp", "Tick off today's supplements"),
    ("/today", "Where you stand today"),
    ("/next", "What would close today's gaps"),
    ("/last", "What you logged most recently"),
    ("/yesterday", "Log food from an earlier day"),
    ("/undo", "Unlog your last entry"),
    ("/why", "Where a nutrient came from today"),
    ("/history", "Everything you have logged"),
    ("/export", "Your whole diary as a spreadsheet"),
    ("/incomplete", "Mark a day you did not log properly"),
    # The other things you record daily.
    ("/weight", "Log a weigh-in"),
    ("/rate", "Rate sleep, focus, mood or effort"),
    ("/training", "Sessions, and this week's total"),
    ("/fast", "Your current fast"),
    ("/window", "Your eating window"),
    # Looking back, weekly or thereabouts.
    ("/week", "Seven days of numbers, day by day"),
    ("/report", "Four weeks read by a model, with an argument"),
    ("/insight", "What your own data supports"),
    # Setting things up, rarely after the first week.
    ("/food", "Foods you define yourself"),
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


# Where the day divides. Not meal slots: a coffee at 09:00 is a "drink" and
# belongs to the morning, and a snack at 16:00 is a "snack" and does not.
BLOCKS: dict[str, tuple[int, int, str]] = {
    "morning":   (0, 12, "🌅"),
    "afternoon": (12, 18, "🌤"),
    "evening":   (18, 24, "🌙"),
}


@dp.message(Command("again", "block"))
async def again(msg: Message) -> None:
    """Repeat a whole block of a day — `/again morning`.

    A morning is a set of meals rather than a dish, and repeating it through
    /repeat is five taps with a chance of forgetting the fourth. The dishes are
    already stored; what was missing was a way to name several of them at once.

    Nothing is logged here. Each meal comes back as its own confirmation card,
    because five meals landing silently is exactly the case invariant 5 exists
    for — an unmodified repeat of one confirmed dish is a small assertion, and
    a whole morning is not.
    """
    u = await _user(msg)
    rest = (msg.text or "").split(maxsplit=1)
    which = rest[1].strip().lower() if len(rest) > 1 else ""

    if which not in BLOCKS:
        hour = _local_now(u).hour
        guess = next((n for n, (lo, hi, _i) in BLOCKS.items() if lo <= hour < hi),
                     "morning")
        await msg.answer(
            "🔁 <b>Repeat a block of a day</b>\n\n"
            "Which part?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"{icon} {name}" + (" (now)" if name == guess else ""),
                    callback_data=f"blk:{name}")
                for name, (_lo, _hi, icon) in BLOCKS.items()
            ]]))
        return
    await _offer_block(msg, u, which)


@dp.callback_query(F.data.startswith("blk:"))
async def cb_block(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=None)
    await _offer_block(cq.message, u, cq.data.split(":", 1)[1], user=u)


async def _offer_block(msg: Message, u: Any, which: str, user: Any = None) -> None:
    lo, hi, icon = BLOCKS[which]
    today = _today(u)
    # The most recent day that had one, not necessarily yesterday: a morning
    # skipped is not a morning of nothing, and offering an empty block because
    # the calendar says "yesterday" is a worse answer than reaching back a day.
    src = await db.recent_block_day(u["id"], today - dt.timedelta(days=1), hi, u["tz"])
    if not src:
        await msg.answer(f"Nothing logged in a {which} yet.")
        return
    rows = [r for r in await db.block_entries(u["id"], src, hi, u["tz"])
            if r["local_time"].hour >= lo]
    rows = [r for r in rows if r["dish_id"]]
    if not rows:
        await msg.answer(
            f"That {which} had nothing repeatable — its entries were one-offs "
            "rather than saved dishes.")
        return

    # Slugs rather than ids, so logging each one goes through _try_repeat and
    # inherits everything it already does right: component provenance, the
    # portion prior, the confirm gate. A second logging path would be a second
    # place for those to be got wrong.
    # Slug and label per meal, in order, so a selection can be expressed as
    # indices and survive the round trip through the pending payload.
    pool = await db.pool()
    by_id = {r2["id"]: r2["slug"] for r2 in await pool.fetch(
        "SELECT id, slug FROM dish WHERE id = ANY($1::bigint[])",
        [int(r["dish_id"]) for r in rows])}
    meals = [
        {"slug": by_id[int(r["dish_id"])],
         "label": render._title(r["name"] or "?"),
         "icon": render.dish_icon(r["name"] or "", r["slot"]),
         "at": f"{r['local_time']:%H:%M}"}
        for r in rows if int(r["dish_id"]) in by_id
    ]
    if not meals:
        await msg.answer("None of those dishes still exist.")
        return

    action_id = await db.put_pending(u["id"], "block_repeat", {
        "meals": meals, "selected": list(range(len(meals))),
        "title": f"{icon} {which.title()} of {src:%a %-d %b}",
    })
    await msg.answer(
        _block_card(meals, list(range(len(meals))),
                    f"{icon} {which.title()} of {src:%a %-d %b}"),
        parse_mode="HTML",
        reply_markup=_block_keyboard(action_id, meals, list(range(len(meals))),
                                     picking=False))


def _block_card(meals: list[dict], selected: list[int], title: str) -> str:
    lines = [f"<b>{title}</b>", ""]
    for i, m in enumerate(meals):
        mark = "" if len(selected) == len(meals) else ("✅ " if i in selected else "⬜️ ")
        lines.append(f"   {mark}{m['at']} {m['icon']} {render._esc(m['label'])}")
    n = len(selected)
    lines.append(
        f"\n<i>{n} meal{'s' if n != 1 else ''}. Each comes back as its own card "
        "to confirm — nothing is logged by pressing this.</i>")
    return "\n".join(lines)


def _block_keyboard(action_id: int, meals: list[dict], selected: list[int],
                    *, picking: bool) -> InlineKeyboardMarkup:
    """Two states on one card: the summary, and the same list with checkboxes.

    A separate "choose" card would mean two places rendering one list, and the
    thing being chosen from is exactly what the summary already shows.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if picking:
        rows += [
            [InlineKeyboardButton(
                text=f"{'✅' if i in selected else '⬜️'} {m['at']} {m['label'][:28]}",
                callback_data=f"blkt:{action_id}:{i}")]
            for i, m in enumerate(meals)
        ]
    rows.append([
        InlineKeyboardButton(
            text=(f"🔁 log {len(selected)}" if picking
                  else f"🔁 log all {len(meals)}"),
            callback_data=f"blkgo:{action_id}"),
        InlineKeyboardButton(text="✋ never mind", callback_data="blkno:"),
    ])
    if not picking:
        rows.append([InlineKeyboardButton(
            text="☑️ choose which", callback_data=f"blkpick:{action_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data.startswith("blkpick:"))
async def cb_block_pick(cq: CallbackQuery) -> None:
    """Open the checkboxes on the card already on screen."""
    payload = await db.take_pending(int(cq.data.split(":")[1]))
    await cq.answer()
    if not payload:
        await cq.message.answer("That block has expired — send /again.")
        return
    u = await db.get_or_create_user(cq.from_user.id)
    meals, selected = payload["meals"], payload["selected"]
    new_id = await db.put_pending(u["id"], "block_repeat", payload)
    await cq.message.edit_text(
        _block_card(meals, selected, payload["title"]), parse_mode="HTML",
        reply_markup=_block_keyboard(new_id, meals, selected, picking=True))


@dp.callback_query(F.data.startswith("blkt:"))
async def cb_block_toggle(cq: CallbackQuery) -> None:
    _k, aid, idx = cq.data.split(":")
    payload = await db.take_pending(int(aid))
    if not payload:
        await cq.answer("expired")
        return
    await cq.answer()
    u = await db.get_or_create_user(cq.from_user.id)
    i = int(idx)
    selected = list(payload["selected"])
    selected.remove(i) if i in selected else selected.append(i)
    selected.sort()
    new_id = await db.put_pending(u["id"], "block_repeat",
                                  {**payload, "selected": selected})
    await cq.message.edit_text(
        _block_card(payload["meals"], selected, payload["title"]),
        parse_mode="HTML",
        reply_markup=_block_keyboard(new_id, payload["meals"], selected,
                                     picking=True))


@dp.callback_query(F.data.startswith("blkno:"))
async def cb_block_cancel(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await db.clear_awaits(u["id"], ("block_repeat",))
    await cq.answer("Closed")
    await cq.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data.startswith("blkgo:"))
async def cb_block_go(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    aid = cq.data.split(":")[1] if ":" in cq.data else ""
    pending = await db.take_pending(int(aid)) if aid else None
    await db.clear_awaits(u["id"], ("block_repeat",))
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=None)
    meals = (pending or {}).get("meals") or []
    selected = (pending or {}).get("selected") or []
    slugs = [meals[i]["slug"] for i in selected if 0 <= i < len(meals)]
    if not slugs:
        await cq.message.answer(
            "Nothing selected." if pending else
            "That block has expired — send /again.")
        return
    done = 0
    for slug in slugs:
        if await _try_repeat(cq.message, u, dsl.RepeatCommand(
                selector=str(slug), selector_kind="slug")):
            done += 1
    if not done:
        await cq.message.answer("None of those dishes still exist.")


@dp.message(Command("today"))
async def today(msg: Message) -> None:
    u = await _user(msg)
    # Everything by default. "Worth a look" still leads and the rest follows
    # under "On track", so the full card is longer without being flatter.
    await _send_day(msg, u, _today(u), show_all="brief" not in (msg.text or ""))


# How many days back a bare word means. Anything older is a date.
_BACK_WORDS = {"yesterday": 1, "yday": 1, "sat": None}


@dp.message(Command("yesterday", "back", "backdate"))
async def yesterday(msg: Message) -> None:
    """Log something you ate on an earlier day.

    This used to show yesterday's card, which /history 2026-08-17 now does
    better and for any day. What it could not do was put food *into* an
    earlier day, and food gets remembered late — so the day you actually ate
    it was either corrupted by omission or corrupted by landing on today.

    `/yesterday 2 empanadas 19:00` works in one message; the argument form is
    accepted because it is the fastest path, not advertised on the card,
    because a card that teaches a syntax instead of doing the thing is the
    failure this file has hit eight times.
    """
    u = await _user(msg)
    rest = (msg.text or "").split(maxsplit=1)
    day = _today(u) - dt.timedelta(days=1)
    if len(rest) > 1 and rest[1].strip():
        await _backdate(msg, u, rest[1].strip(), day)
        return
    await _ask(
        msg, u, "backdate_food",
        f"📅 <b>{day:%A %-d %b}</b> — what did you eat?\n\n"
        "Describe it as you would any meal. I will ask what time it was "
        "before anything is logged.\n\n"
        "<i>Or say it in one line — <code>2 empanadas 19:00</code>.</i>",
        payload={"iso": day.isoformat()},
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✋ never mind", callback_data="backcancel:"),
        ]]),
    )


# A trailing time on a food line: "2 empanadas 19:00", "toast at 8.30".
_TRAILING_TIME = re.compile(r"(?:\s+at)?\s+(\d{1,2})[:.](\d{2})\s*$")


@consumes("backdate_food")
async def _consume_backdate(msg: Message, u: Any, text: str, payload: dict) -> bool:
    day = dt.date.fromisoformat(payload.get("iso") or "") if payload.get("iso") else None
    if not day:
        return False
    await db.clear_pending(u["id"], "backdate_food")
    await _backdate(msg, u, text, day)
    return True


async def _backdate(msg: Message, u: Any, text: str, day: dt.date) -> None:
    """Parse a meal, file it on `day`, and settle the time before confirming."""
    zone = zoneinfo.ZoneInfo(u["tz"])
    stated = _TRAILING_TIME.search(text)
    if stated:
        hh, mm = int(stated.group(1)), int(stated.group(2))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            stated = None
    when = None
    if stated:
        text = text[: stated.start()].strip()
        when = dt.datetime.combine(day, dt.time(int(stated.group(1)), int(stated.group(2))),
                                   tzinfo=zone).astimezone(dt.timezone.utc)
    else:
        # Noon, deliberately: it is inside the day whatever the rollover hour
        # is, so the entry cannot land on a neighbouring date while its real
        # time is still unknown.
        when = dt.datetime.combine(day, dt.time(12, 0), tzinfo=zone).astimezone(dt.timezone.utc)

    if not text:
        await msg.answer("That was only a time — tell me what you ate too.")
        return

    note = await msg.answer("🍽 digesting…")
    try:
        parsed = await llm.parse_text(text, user_id=u["id"])
        entry_id = await _present(msg, u, parsed, source="text", photo_file_id=None,
                                  edit=note, text=text, when=when)
    except Exception as exc:
        await _parse_failed(note, exc)
        return

    if stated or entry_id is None:
        return
    # Asked, not assumed. The slot and the fasting window both depend on it,
    # and noon is a placeholder rather than an answer.
    await _ask(
        msg, u, "time_await",
        f"🕐 What time on <b>{day:%a %-d %b}</b>? — <code>19:00</code>\n"
        "<i>Confirm above to accept the placeholder of 12:00.</i>",
        payload={"entry_id": entry_id},
    )


@dp.callback_query(F.data.startswith("backcancel:"))
async def cb_backdate_cancel(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    await db.clear_awaits(u["id"], ("backdate_food",))
    await cq.answer("Closed")
    await cq.message.edit_reply_markup(reply_markup=None)


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


@dp.message(Command("history", "log", "diary"))
async def history(msg: Message) -> None:
    """Everything logged, newest first. `/history 30`, or `/history 2026-08-14`.

    /today and /week both answer "how am I doing". This answers "what did I
    actually eat", which is a different question and had no command at all —
    the only way to read the diary was to open Adminer.
    """
    u = await _user(msg)
    arg = (msg.text or "").split(maxsplit=1)
    arg = arg[1].strip() if len(arg) > 1 else ""

    # A date shows that one day in full, using the same card /today uses.
    # Anything else is a window in days.
    if arg:
        try:
            return await _send_day(msg, u, dt.date.fromisoformat(arg), show_all=True)
        except ValueError:
            pass
    try:
        days = max(1, min(365, int(arg))) if arg else 14
    except ValueError:
        await msg.answer(
            "<code>/history</code> the last fortnight · "
            "<code>/history 60</code> a longer window · "
            "<code>/history 2026-08-14</code> one day in full",
            parse_mode="HTML")
        return

    today = _today(u)
    rows = await db.history_entries(u["id"], today - dt.timedelta(days=days - 1), today)
    span = await db.history_span(u["id"])
    await msg.answer(render.history_card(rows, span, days, tz=u["tz"]),
                     parse_mode="HTML")


def _csv(rows: Sequence[Any]) -> bytes:
    """Records to CSV bytes, with the numbers readable.

    asyncpg returns `numeric` as Decimal, and str(Decimal) prints the full
    stored precision — a meal's energy comes out as
    11.879999999999999005240169935859739780426025390625, which is correct and
    unusable. Rounded to six places: past that it is float noise from the
    per-100 g arithmetic, not a figure anyone measured.

    Timestamps are written as ISO strings so a spreadsheet does not reinterpret
    them, and the date column stays separate from the timestamp for the same
    reason — `local_date` is the day the food belongs to, which is not always
    the UTC date in `logged_at`.
    """
    import csv, io, decimal

    if not rows:
        return b""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(rows[0].keys())
    for r in rows:
        w.writerow([
            format(v.quantize(decimal.Decimal("0.000001")).normalize(), "f")
            if isinstance(v, decimal.Decimal)
            else v.isoformat() if isinstance(v, (dt.datetime, dt.date))
            else "" if v is None else v
            for v in r.values()
        ])
    return buf.getvalue().encode()


@dp.message(Command("export"))
async def export(msg: Message) -> None:
    """The whole diary as two CSVs, in the chat.

    Adminer can export a table, but a table is not the diary: the meals are in
    one, the ingredients in another and the numbers in a third, and what you
    actually want is them joined. This sends that join, so the export needs no
    SQL and no second tool.
    """
    u = await _user(msg)
    meals = _csv(await db.export_rows(u["id"]))
    days = _csv(await db.export_day_rows(u["id"]))
    if not meals:
        await msg.answer("Nothing logged yet.")
        return
    stamp = _today(u).isoformat()
    await msg.answer_document(
        BufferedInputFile(meals, filename=f"nutrai-meals-{stamp}.csv"),
        caption="Every confirmed meal, one row per ingredient — with the USDA "
                "row it matched and whether the mass was weighed or guessed.")
    await msg.answer_document(
        BufferedInputFile(days, filename=f"nutrai-days-{stamp}.csv"),
        caption="Daily totals per nutrient, food and supplement kept apart, "
                "with the target that applied on the day.")


@dp.message(Command("incomplete", "partial"))
async def incomplete(msg: Message) -> None:
    """Mark a day as not properly logged, so nothing draws conclusions from it.

    Every trend, correlation and measured-TDEE figure reads the diary as if it
    were complete. A day out where three meals went unlogged is not a 900 kcal
    day — it is a day with no usable number in it, and left unmarked it drags
    the weight-trend deficit, weakens a real /insight correlation, and raises
    the energy target off the back of a day nobody recorded.

    The alternative was to guess at what was missed, which is the estimate this
    design refuses everywhere else.
    """
    u = await _user(msg)
    rest = (msg.text or "").split(maxsplit=1)
    arg = rest[1].strip().lower() if len(rest) > 1 else ""

    if arg in ("list", "which"):
        rows = await db.incomplete_days(u["id"])
        if not rows:
            await msg.answer("No days marked incomplete.")
            return
        lines = ["📉 <b>Marked incomplete</b>", ""]
        lines += [f"   • {r['local_date']:%a %-d %b}"
                  + (f" — {render._esc(r['note'])}" if r["note"] else "")
                  for r in rows]
        lines.append("\n<i>Excluded from trends, /insight and measured TDEE. "
                     "<code>/incomplete 2026-08-17 ok</code> puts one back.</i>")
        await msg.answer("\n".join(lines), parse_mode="HTML")
        return

    day = _today(u) - dt.timedelta(days=1)
    complete = False
    note = None
    for tok in arg.split():
        if tok in ("today",):
            day = _today(u)
        elif tok in ("ok", "fine", "complete", "undo"):
            complete = True
        else:
            try:
                day = min(dt.date.fromisoformat(tok), _today(u))
            except ValueError:
                note = (note + " " + tok) if note else tok

    await db.mark_day(u["id"], day, complete, note)
    if complete:
        await msg.answer(
            f"✅ <b>{day:%a %-d %b}</b> counts again — back in trends, "
            "/insight and measured TDEE.", parse_mode="HTML")
        return
    await msg.answer(
        f"📉 <b>{day:%a %-d %b}</b> marked incomplete"
        + (f" — {render._esc(note)}" if note else "") + ".\n\n"
        "<i>Its entries stay in the diary and still show in /today and "
        "/history. What changes is that nothing draws a conclusion from it: "
        "no weight trend, no /insight pair, no measured TDEE.</i>\n\n"
        "<code>/incomplete list</code> · <code>/incomplete "
        f"{day:%Y-%m-%d} ok</code> to undo.", parse_mode="HTML")


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
        f"⏳ <b>{int(h)}h {int((h % 1) * 60):02d}m</b> fasted",
        f"phase: {escape(phase)} — {escape(gloss)}",
    ]

    # What ended the last one, and which rule ended it. "12.8 hours" says
    # where you are; it does not say that a ginger tea did it, which is the
    # part you can do something about tomorrow.
    broke = await db.fast_broken_by(u["id"])
    if broke:
        import zoneinfo

        when = broke["logged_at"].astimezone(zoneinfo.ZoneInfo(u["tz"]))
        why = {
            "energy": f"{float(broke['kcal']):,.0f} kcal",
            "carbohydrate": f"{float(broke['carb_g']):.1f} g carbs",
            "protein": f"{float(broke['protein_g']):.1f} g protein",
        }[broke["broken_by"]]
        lines += [
            "",
            f"🍽 Broken at <b>{when:%H:%M}</b> by "
            f"<b>{render._esc(render._title(broke['name']))}</b> — {why}.",
        ]

    lines += [
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
    obs_id, text = await _rating_text(u, kind, float(value))
    await cq.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="📝 why?", callback_data=f"ratenote:{obs_id}")]]),
    )


async def _record_rating(msg: Message, u: Any, kind: str, value: float,
                         note: str | None = None) -> None:
    obs_id, text = await _rating_text(u, kind, value, note)
    # A note is worth more than the number it annotates and is the part a
    # correlation cannot recover: a 4 from a late coffee, a 4 from a noisy
    # street and a 4 from illness are three observations the permutation test
    # sees as one. So it is offered every time rather than waited for.
    kb = None
    if not note:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="📝 why?", callback_data=f"ratenote:{obs_id}")]])
    await msg.answer(text, parse_mode="HTML", reply_markup=kb)


async def _rating_text(u: Any, kind: str, value: float,
                       note: str | None = None) -> tuple[int, str]:
    """Log it and say what it bought.

    The old reply was "focus 9 at 4.8h fasted · 19 more before this can be
    analysed", which reads as a rebuke. The gate is real — a correlation on ten
    points is noise — but the useful framing is how far along you are, not how
    far short.
    """
    h = await db.current_fast_hours(u["id"])
    obs_id = await db.log_observation(
        u["id"], kind, value, tz=u["tz"], rollover_hour=u["day_rollover_hour"],
        note=note,
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
    if note:
        lines.append(f"<i>“{_esc_note(note)}”</i>")
    if n >= 3:
        recent = ", ".join(f"{float(o['value']):g}" for o in obs[-5:])
        lines.append(f"<i>last few: {recent}</i>")
    return obs_id, "\n".join(lines)


def _esc_note(text: str) -> str:
    from html import escape as _e

    return _e(text[:200], quote=False)


@dp.callback_query(F.data.startswith("ratenote:"))
async def cb_rating_note(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    obs_id = int(cq.data.split(":", 1)[1])
    await db.put_pending(u["id"], "rating_note", {"obs_id": obs_id})
    await cq.answer()
    await cq.message.answer(
        "📝 <b>What was going on?</b>\n\n"
        "<i>A sentence is plenty — 'woke at 3 and could not get back down', "
        "'trained fasted', 'streaming cold'. It is the part a correlation "
        "cannot recover from the number.</i>",
        parse_mode="HTML",
    )


@consumes("rating_note")
async def _consume_rating_note(msg: Message, u: Any, text: str, payload: dict) -> bool:
    note = text.strip()
    if not note or len(note) > 500:
        return False
    ok = await db.set_observation_note(u["id"], int(payload["obs_id"]), note)
    await db.clear_pending(u["id"], "rating_note")
    if not ok:
        await msg.answer("That rating is no longer there.")
        return True
    await msg.answer("📝 Noted. It travels with that rating from here on.",
                     parse_mode="HTML")
    return True


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
    "fast_break_kcal": lambda v: _num(v, 0, 500),
    "fast_break_carb_g": lambda v: _num(v, 0, 100),
    "fast_break_protein_g": lambda v: _num(v, 0, 100),
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
        # Buttons for what is actually out of line today, because that is what
        # you are opening /why to ask about nine times in ten. Typing still
        # works for the tenth.
        day = _today(u)
        prog = await db.day_progress(u["id"], day)
        worst = sorted(
            ((float(r["amount"]) / float(r["max_amount"]), r) for r in prog
             if r["max_amount"] and float(r["max_amount"]) > 0
             and float(r["amount"]) / float(r["max_amount"]) > 1),
            key=lambda x: -x[0],
        )[:3]
        rows = [[InlineKeyboardButton(
            text=f"{render._short(r['nutrient_name'])} {share:.0%}",
            callback_data=f"whyn:{r['nutrient_id']}")] for share, r in worst]
        await _ask(msg, u, "why_await",
                   ("Which nutrient?" if rows else
                    "Which nutrient? Nothing is over a ceiling today.")
                   + " Reply with a name — <code>cholesterol</code>, "
                     "<code>fat</code>. Several at once is fine: "
                     "<code>fat and sodium</code>.",
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
        return

    for term in _nutrient_terms(parts[1]) or [parts[1].strip()]:
        if not await _explain_nutrient(msg, u, term):
            await msg.answer(
                f"No nutrient matches {render._esc(term)}. <code>/target</code> "
                "lists the names as they are stored.", parse_mode="HTML")


@dp.callback_query(F.data.startswith("whyn:"))
async def cb_why_nutrient(cq: CallbackQuery) -> None:
    u = await db.get_or_create_user(cq.from_user.id)
    nid = int(cq.data.split(":", 1)[1])
    p = await db.pool()
    name = await p.fetchval("SELECT name FROM nutrient WHERE id = $1", nid)
    await cq.answer()
    await db.clear_pending(u["id"], "why_await")
    await _explain_nutrient(cq.message, u, name or str(nid))


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
        "<i>Baked? End with what it made — then a slice needs no weighing:</i>\n"
        "<code>… makes 850 g, 16 slices</code>\n\n"
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
        "<i>Baked? End with what it made — then a slice needs no weighing:</i>\n"
        "<code>… makes 850 g, 16 slices</code>\n\n"
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
    await _present(cq.message, u, parsed, source="text", text=name,
                   photo_file_id=None, edit=note)


# "makes 850 g, 16 slices" — the two facts a recipe needs and an ingredient
# list cannot carry.
#
# Baking drives off water. A blondie tray is ~1,100 g of butter, sugar, flour
# and eggs going in and ~850 g coming out, so a panel computed against the raw
# sum is understated by a quarter — every slice logged from it under-counts by
# the same amount, silently and for ever. The fix is not a shrinkage constant
# (it varies with the bake) but the number you already have: what the tin
# weighed when it came out.
#
# The piece count is the other half. Having weighed the tray once, every slice
# after that is arithmetic, and there is no reason to estimate it by eye.
_MAKES = re.compile(
    r"\bmakes?\b(?:[^.\n]|\.(?=\d))*", re.I)
_MAKES_MASS = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|g|grams?)\b", re.I)
_MAKES_PIECES = re.compile(
    r"(\d+)\s*(slices?|pieces?|servings?|portions?|squares?|bars?|"
    r"muffins?|cookies?|cupcakes?|rolls?|buns?)\b", re.I)


def _read_makes(text: str) -> tuple[str, float | None, int | None, str]:
    """Split a "makes ..." clause off an ingredient list.

    Returned as (ingredients without the clause, finished grams, pieces, unit).
    The clause has to come out: left in, "makes 16 slices" reaches the meal
    parser as an ingredient and sixteen slices of something get added to the
    recipe.
    """
    m = _MAKES.search(text)
    if not m:
        return text, None, None, "serving"
    clause = m.group(0)
    grams = pieces = None
    unit = "serving"
    if g := _MAKES_MASS.search(clause):
        grams = float(g.group(1).replace(",", "."))
        if g.group(2).lower() == "kg":
            grams *= 1000
    if pc := _MAKES_PIECES.search(clause):
        pieces = int(pc.group(1))
        unit = pc.group(2).lower().rstrip("s")
    if grams is None and pieces is None:
        return text, None, None, unit
    return (text[:m.start()] + text[m.end():]).strip(" ,\n"), grams, pieces, unit


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

    text, made_g, pieces, portion_unit = _read_makes(text)

    note = await msg.answer("🥫 working it out…")
    try:
        parsed = await llm.parse_text(text, user_id=u["id"])
    except Exception as exc:
        await _parse_failed(note, exc)
        return True
    res = await llm.resolve_items(u["id"], parsed.items, parsed.dish_name)
    if not res.components:
        await note.edit_text(
            "None of those matched a food row, so there is nothing to build "
            "from. Try naming the ingredients more plainly.")
        return True

    profiles = await db.profiles_for({c.fdc_id for c in res.components})
    totals = total_nutrients(res.components, profiles)
    raw_g = sum(c.grams for c in res.components)
    if raw_g <= 0:
        await note.edit_text("That came to no mass at all, so I cannot store it.")
        return True

    # Divide by what came out of the oven where that is known, and by what went
    # in where it is not. Cooking loss is real and one-directional, so the raw
    # sum always understates a baked panel; the card says which divisor was
    # used rather than leaving that to be inferred from the calorie figure.
    yield_g = made_g if made_g and made_g > 0 else raw_g
    per_100g = {nid: amount / yield_g * 100 for nid, amount in totals.items()}

    # 100 g of anything cannot contain more than 100 g of macronutrients.
    #
    # A stated finished weight is the one number here that nothing else checks,
    # and understating it inflates every figure in exact proportion — the panel
    # stays internally consistent all the way to absurdity. 1,587 g of blondie
    # ingredients declared as an 850 g tray produced 105.6 g of carbohydrate,
    # 46.8 g of fat and 8.1 g of protein per 100 g: 160 g of food inside 100 g
    # of food, saved without complaint, and wrong by a factor of 1.7 on every
    # slice logged from it thereafter.
    #
    # This is arithmetic rather than a plausibility heuristic, so it can refuse
    # outright. The floor it reports is a real lower bound: the batch cannot
    # weigh less than the mass of the macronutrients known to be in it.
    macro_g = sum(per_100g.get(n, 0) for n in (PROTEIN, CARB, FAT))
    if macro_g > 100:
        floor = yield_g * macro_g / 100
        await note.edit_text(
            f"❌ That comes to <b>{macro_g:.0f} g of protein, carbs and fat in "
            f"every 100 g</b>, which is more food than the food weighs.\n\n"
            f"The ingredients total {raw_g:,.0f} g and you said the batch makes "
            f"{yield_g:,.0f} g. Cooking loses water, but it cannot lose this "
            f"much — the batch cannot weigh less than <b>{floor:,.0f} g</b>, and "
            f"a tray bake usually keeps around 90% of what went in.\n\n"
            f"<i>Weigh the tin, or drop the weight and send just "
            f"<code>makes 16 slices</code>. Nothing was saved.</i>",
            parse_mode="HTML",
        )
        return True

    # A food with macros and no energy is a wrong row, not a zero-calorie
    # food. "butter" resolved to a Foundation entry carrying 81.5 g of fat and
    # no energy figure at all, and the panel was stored saying zero — which
    # then subtracts nothing from an energy ceiling for ever.
    #
    # The all-or-nothing test only caught it when *every* ingredient was
    # energy-less. One out of eight is the commoner and worse case: the blondie
    # stored 336 kcal per 100 g against macros implying 528, because 340 g of
    # butter contributed 277 g of fat and zero calories while the other seven
    # rows carried theirs. Nothing about the saved panel looks wrong — it is
    # simply, quietly, a third low, and every slice logged from it inherits
    # that. Atwater is the check, and it is the same one every confirm card
    # already runs against a meal.
    check = energy_cross_check(per_100g)
    if not per_100g.get(ENERGY_KCAL) or not check.ok:
        await note.edit_text(
            "❌ This panel does not add up.\n\n"
            f"Its macros imply <b>{check.kcal_atwater:,.0f} kcal per 100 g</b> "
            f"and the rows those ingredients matched give "
            f"<b>{check.kcal_db:,.0f}</b>. Some USDA rows carry fat and protein "
            "but no energy figure — <i>Butter, stick, unsalted</i> is one — and "
            "an ingredient that matched one of those contributes its mass to "
            "the total and nothing to the calories.\n\n"
            "<i>Name that ingredient differently and send the list again: "
            "'butter' rather than 'unsalted butter', say, or a brand you can "
            "photograph the panel of. Nothing was saved.</i>",
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
    if pieces and pieces > 0:
        await db.declare_portion(fdc_id, yield_g / pieces, portion_unit,
                                 yield_grams=made_g)
    await db.clear_pending(u["id"], "food_await")

    parts = [f"{c.grams:g} g {c.label}" for c in res.components]
    if res.unresolved:
        parts.append("(not found, and therefore not counted: "
                     + ", ".join(res.unresolved) + ")")
    await note.edit_text(
        render.user_food_made_card(name, per_100g, parts, yield_g,
                                   raw_g=raw_g, pieces=pieces,
                                   portion_unit=portion_unit),
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
    # The buttons come with it. "Confirm it above" means scrolling past the
    # prompt and the reply to reach a card you have already read, and the
    # whole point of correcting the time here was to avoid leaving this
    # message.
    await msg.answer(
        f"🕐 Moved to <b>{when:%H:%M}</b>"
        + ("" if same_day else f" on <b>{day:%a %-d %b}</b>") + ".",
        parse_mode="HTML",
        reply_markup=kb_confirm(entry_id),
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

    if sub.startswith("taken"):
        await msg.answer(
            render.supplement_taken_card(
                await db.supplements_logged_on(u["id"], day), u["tz"]),
            parse_mode="HTML")
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
    # Nothing is pre-ticked any more. A tick used to mean "this is on your
    # daily list" and now means "I took this", which is the only version that
    # can carry a time with it — and the only one where an untaken capsule
    # cannot end up in a day's totals because you did not think to untick it.
    await _send_supp_picker(msg, u, stack, day)


async def _send_supp_picker(msg: Message, u: Any, stack: list[Any],
                            day: dt.date) -> None:
    """The checklist, from /supp or from a reminder's third button.

    Shared rather than reimplemented, because the callback has no user on its
    message — `cq.message.from_user` is the bot — so the caller passes the user
    it already resolved instead of the handler digging one out.
    """
    today_names = {r["name"] for r in await db.supplements_logged_on(u["id"], day)}
    selected = [s["id"] for s in stack if s["name"] in today_names]
    reason = "logged"

    action_id = await db.put_pending(u["id"], "supp_pick", {
        "selected": selected, "day": day.isoformat(), "reason": reason,
    })
    await msg.answer(
        render.supplement_pick_card(stack, selected, reason),
        parse_mode="HTML",
        reply_markup=_supp_keyboard(action_id, stack, selected),
    )



@dp.callback_query(F.data.startswith("suppick:"))
async def cb_supp_pick_from_reminder(cq: CallbackQuery) -> None:
    """The reminder's third button: the same checklist /supp opens.

    "Taken" logs the whole slot and "not yet" logs none of it, which are the
    two ends of a range that is mostly used in the middle — three of the five,
    the collagen forgotten. Without this the honest answer costs a trip to the
    menu, and the quick answer is the inaccurate one.
    """
    u = await db.get_or_create_user(cq.from_user.id)
    await cq.answer()
    stack = await db.supplement_stack(u["id"])
    if not stack:
        await cq.message.answer("No supplements set up yet.")
        return
    await _send_supp_picker(cq.message, u, stack, _today(u))


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


@dp.message(Command("last"))
async def last_entry(msg: Message) -> None:
    """What went in most recently. The question asked after every gap.

    "Did that log?" was previously answered by /today, which means reading a
    whole day's card to check one line at the bottom of it.
    """
    u = await _user(msg)
    rows = await db.history_entries(
        u["id"], _today(u) - dt.timedelta(days=6), _today(u))
    if not rows:
        await msg.answer("Nothing logged in the last week.")
        return
    e = rows[0]
    zone = zoneinfo.ZoneInfo(u["tz"])
    when = e["logged_at"].astimezone(zone)
    ago = (_local_now(u) - when)
    mins = int(ago.total_seconds() // 60)
    since = (f"{mins} min ago" if mins < 60 else
             f"{mins // 60} h {mins % 60:02d} ago" if mins < 1440 else
             f"{mins // 1440} days ago")
    _row, comps = await db.entry_with_components(int(e["id"]))
    lines = [
        f"🕐 <b>Last logged</b> — {render._esc(render._title(e['name'] or '?'))}",
        f"<i>{when:%a %-d %b, %H:%M} · {since}</i>",
        "",
    ]
    for c in comps:
        lines.append(f"   • {render._esc(c['label'])} — {float(c['grams']):,.0f} g")
    lines += ["", f"📊 {float(e['kcal'] or 0):,.0f} kcal · "
                  f"{float(e['protein'] or 0):.0f} g protein"]
    await msg.answer("\n".join(lines), parse_mode="HTML",
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                         InlineKeyboardButton(text="↩️ undo it",
                                              callback_data=f"undook:{e['id']}"),
                     ]]))


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

    note = await msg.answer("🍽 looking at the photo…")
    try:
        parsed = await llm.parse_photo(images[0][0], caption, user_id=u["id"])
        for extra in images[1:]:
            more = await llm.parse_photo(extra[0], caption, user_id=u["id"], escalate=False)
            parsed.items.extend(more.items)
            parsed.cost_usd += more.cost_usd
    except Exception as exc:
        await _parse_failed(note, exc)
        return

    try:
        await _present(msg, u, parsed, source="photo",
                       photo_file_id=images[0][3], edit=note)
    except Exception as exc:
        await _parse_failed(note, exc)


async def _parse_failed(note: Message, exc: Exception) -> None:
    """Say so, rather than leaving "reading…" on screen forever.

    An unhandled exception here is invisible: aiogram logs it and returns, the
    placeholder never gets edited, and the only signal is a message that sits
    there indefinitely. That is indistinguishable from a slow model, so you wait
    instead of looking at the logs. The first live photo parse died on a 400 and
    presented as a three-minute hang.
    """
    log.exception("parse failed")
    await note.edit_text(_failure_reason(exc), parse_mode="HTML")


# What the class name does not tell you, and what to do instead.
#
# Every failure read "BadRequestError … try again in a moment", which named the
# HTTP class rather than the cause and then gave advice that was wrong in the
# one case it mattered: an exhausted credit balance is a 400, and retrying it
# never works. So the message has to distinguish a wait from a fix, and say
# which of the two it is.
#
# Matched on the message text rather than the status code because the code is
# shared — 400 covers both "you are out of credit" and "that image is
# malformed" — and only the body separates them. Substrings, not exact
# matches: the wording changes, the noun does not.
_FAILURES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("credit balance", "billing", "insufficient_quota", "quota", "usage limit",
      "spending limit", "payment"),
     "Your Anthropic API account has hit a limit — credit, quota or spend cap. "
     "Nothing can be parsed until it is topped up or the cap is raised, at "
     "console.anthropic.com. Retrying will not help."),
    (("invalid x-api-key", "authentication_error", "invalid api key"),
     "The Anthropic API key is being rejected. It needs replacing in "
     "<code>.env</code>; retrying will not help."),
    (("rate_limit", "429"),
     "Rate-limited by the API. This one does clear on its own — try again in a "
     "minute."),
    (("overloaded", "529", "503"),
     "The API is overloaded. Try again in a minute."),
    (("timeout", "timed out", "connection"),
     "Could not reach the API. Check the connection and try again."),
)


def _failure_reason(exc: Exception) -> str:
    """A sentence naming the cause, and whether waiting is the right response."""
    blob = f"{type(exc).__name__} {exc}".lower()
    for needles, sentence in _FAILURES:
        if any(n in blob for n in needles):
            # /repeat, /today and the whole DSL are local. Worth saying,
            # because "the bot is down" and "the parser is down" are different
            # situations and only one of them stops you logging lunch.
            return (f"⚠️ {sentence}\n\nNothing was logged. "
                    "<code>/repeat</code> still works — it never calls a model.")
    # Naming the exception class tells you the HTTP shape and nothing about
    # the cause. Where the failure plainly came from the model API, say so —
    # that alone distinguishes "my account" from "my bot is broken", which are
    # the two things worth telling apart before reading a log.
    if "anthropic" in blob or "api" in blob or "400" in blob:
        return ("⚠️ The Anthropic API refused that request "
                f"(<code>{escape(type(exc).__name__)}</code>) — most often an "
                "account limit. Check console.anthropic.com; the exact message "
                "is in the bot logs.\n\nNothing was logged. "
                "<code>/repeat</code> still works — it never calls a model.")
    return (f"That did not go through — {escape(type(exc).__name__)}. "
            "Nothing was logged. The detail is in the bot logs; try again in a moment.")


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
        await _present(msg, u, parsed, source="text", photo_file_id=None,
                       edit=note, text=text)
    except Exception as exc:
        await _parse_failed(note, exc)



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


# "fat and sodium" is one reply about two nutrients, and it used to reach the
# meal parser — which paid for a model call to report "No match in the food
# database for: Unknown meal". Split on the words people join lists with.
NUTRIENT_SEPARATORS = re.compile(r"\s*(?:,|&|\+|\band\b|\bplus\b)\s*", re.IGNORECASE)


def _nutrient_terms(text: str) -> list[str]:
    return [t for t in NUTRIENT_SEPARATORS.split(text.strip()) if t]


@consumes("why_await")
async def _consume_why(msg: Message, u: Any, text: str, payload: dict) -> bool:
    """Answers for every nutrient named, or none.

    All-or-nothing on purpose: a reply where one word is a nutrient and the
    rest is dinner is dinner, and answering the half that resolved would log
    nothing while looking like it had done something.
    """
    terms = _nutrient_terms(text)
    if not terms or len(terms) > 4:
        return False
    resolved = []
    for term in terms:
        matches = await db.find_nutrients(render.usda_name_for(term) or term)
        if not matches:
            return False
        resolved.append(term)
    for term in resolved:
        await _explain_nutrient(msg, u, term)
    return True


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
    before_g = sum(c.grams for c in current)
    new_comps, to_add = dsl.apply(current, ops)
    after_g = sum(c.grams for c in new_comps)

    # A correction that changes the plate several times over is almost always
    # a misread instruction rather than a meal that shrank. "40g chicken
    # breast" once meant "set the whole plate to 40 g" and turned a 633 kcal
    # dinner into 91 — every component scaled by a fifteenth, and the card
    # showed the new masses without ever saying they had all moved.
    mass_warning = None
    if before_g > 0 and after_g > 0 and not (before_g / 3 <= after_g <= before_g * 3):
        mass_warning = (
            f"this changes the whole plate from {before_g:,.0f} g to "
            f"{after_g:,.0f} g — check it is what you meant"
        )

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
    if mass_warning:
        warnings.insert(0, mass_warning)
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
    text: str | None = None, when: dt.datetime | None = None,
) -> int | None:
    res = await llm.resolve_items(u["id"], parsed.items, parsed.dish_name, text=text)
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
            "or define it yourself if the database simply has no row for it."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[_define_button([(missed, 0.0)])])
        if edit:
            await edit.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await msg.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    verdict = await llm.validate(res.components, parsed)
    profs = await db.profiles_for([c.fdc_id for c in res.components])
    totals = total_nutrients(res.components, profs)

    slug = _slugify(parsed.dish_name)
    # The clock decides the meal, not the model — see dsl.slot_for_hour. On a
    # backdated entry it is the clock of the meal, not of the typing.
    slot = dsl.slot_for_hour((when or _local_now(u)).hour, parsed.slot)
    dish_name = render._title(parsed.dish_name)
    dish_id = await db.upsert_dish(u["id"], slug, dish_name, slot, res.components)

    entry_id = await db.create_pending_entry(
        u["id"], dish_name, res.components, source=source, slot=slot,
        confidence=parsed.confidence, model=parsed.model,
        parse={**(parsed.raw or {}), "_weak": [w[0] for w in res.weak_matches]},
        photo_file_id=photo_file_id, dish_id=dish_id, tz=u["tz"],
        rollover_hour=u["day_rollover_hour"], grams_sources=res.grams_sources,
        when=when,
    )

    warnings = list(verdict.warnings)
    all_hard = bool(res.grams_sources) and all(
        src in ("scale", "stated", "package") for src in res.grams_sources
    )
    # A model's confidence is about the parse it made, and a declared portion
    # replaces the part it was unsure of.
    #
    # "0.33 slice of blondie" scored 50% because the model had guessed a 75 g
    # slice and said so — then the mass came from your own stated 88 g instead,
    # and the card showed the exact figure beside "low overall confidence —
    # check the foods matched". The food was a row you defined yourself,
    # matched by exact alias. Nothing on that card was uncertain, and a warning
    # that fires when nothing is wrong is worse than no warning: it is training
    # to dismiss the ones that mean something.
    own_food = all(c.fdc_id < 0 for c in res.components)
    if parsed.confidence < CONFIDENCE_FLOOR and not (all_hard and own_food):
        # "Check the masses" is the wrong instruction when you supplied every
        # mass yourself. What is left to doubt in that case is whether the right
        # USDA rows were picked.
        what = "check the foods matched" if all_hard else "check the masses"
        warnings.insert(0, f"low overall confidence ({parsed.confidence:.0%}) — {what}")
    for note in res.prior_notes or []:
        warnings.append(note)

    # Unresolved items are passed separately rather than appended to warnings:
    # the card puts them above the totals, because a total computed from part of
    # a plate must not be readable as the meal's total.
    text = render.confirm_card(
        parsed.dish_name, res.components, totals,
        confidence=None if (all_hard and own_food) else parsed.confidence,
        warnings=warnings,
        # The model's notes explain the parse. Where a declared portion
        # replaced its mass, the note explaining how it guessed that mass
        # describes reasoning that was thrown away, and printing it beside the
        # figure that replaced it reads as a disagreement with itself.
        notes=None if all_hard and res.prior_notes else parsed.notes,
        cost_usd=parsed.cost_usd + res.cost_usd, unresolved=res.unresolved,
        matched=await _matched_names(res.components),
        weak=res.weak_matches,
    )
    kb = kb_confirm(entry_id, res.weak_matches)
    if edit:
        await edit.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)
    return entry_id


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

    # A supplement named in the meal you just logged is a supplement you took.
    # "Protein shake with creatine" should not need ticking twice, and the
    # nutrients only reach the day's totals through supplement_log.
    #
    # Against the meal's own ingredients, exactly, and never against the dish
    # name. An ingredient the parser isolated and called "creatine" is strong
    # evidence; a word inside a dish name is weak — "zinc-rich beef stew"
    # contains "zinc" and involves no tablet.
    auto = await db.supplements_named_in(
        u["id"], _today(u), [c["label"] for c in _comps],
        free_text=entry["name"])
    if auto:
        await db.log_supplements(u["id"], _today(u), auto, via="from_meal")

    # Retire the card. Its text arrives back from Telegram with the markup
    # already stripped, so it is re-sent as plain text; the detail it held has
    # served its purpose and the progress card below replaces it.
    await cq.message.edit_text(
        (cq.message.text or "") + f"\n\n✅ logged — {totals.get(1008, 0):,.0f} kcal"
    )

    day = _today(u)
    if auto:
        p = await db.pool()
        names = await p.fetch(
            "SELECT name FROM supplement WHERE id = ANY($1::bigint[])", auto)
        await cq.message.answer(
            "💊 Also ticked off, because you named "
            + ("it" if len(names) == 1 else "them") + ": <b>"
            + render._esc(", ".join(r["name"] for r in names))
            + "</b>.\n<i>Untick in <code>/supp</code> if that is wrong.</i>",
            parse_mode="HTML")
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
