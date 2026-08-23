"""Stage 1 of docs/ARCHITECTURE.md, as an executable check.

    docker compose up -d db
    python scripts/load_usda.py <fdc_csv_dir>
    python scripts/bootstrap.py --telegram-id 123456789 ...
    pytest -q -m integration

Send one text message, get one confirmation card, press confirm, see it in
/today — plus the zero-token repeat path, which is the feature the whole design
rests on and the one a unit test cannot reach because it is mostly SQL.

Skipped, not failed, when there is no database. `pytest -q` stays DB-free.

The Anthropic client is stubbed. Everything below it is real: the resolver runs
against real USDA rows, the nutrient arithmetic is the real arithmetic, and the
messages are the ones a human would have read.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import subprocess
import sys
from typing import Any

import pytest

from tests.fake_telegram import CHAT_ID, FakeTelegram

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nutrai:nutrai@localhost:5432/nutrai")


# ------------------------------------------------------------------ skipping


def _db_ready() -> tuple[bool, str]:
    try:
        import asyncpg
    except ImportError:  # pragma: no cover
        return False, "asyncpg not installed"

    async def check() -> tuple[bool, str]:
        try:
            con = await asyncio.wait_for(asyncpg.connect(DATABASE_URL), timeout=5)
        except Exception as exc:
            return False, f"no database at {DATABASE_URL}: {exc}"
        try:
            foods = await con.fetchval("SELECT count(*) FROM food")
            targets = await con.fetchval("SELECT count(*) FROM target")
            if not foods:
                return False, "no USDA data loaded — run scripts/load_usda.py"
            if not targets:
                return False, "no user bootstrapped — run scripts/bootstrap.py"
            return True, ""
        finally:
            await con.close()

    return asyncio.run(check())


_READY, _WHY = _db_ready()
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _READY, reason=_WHY)]


# ---------------------------------------------------------------- LLM stub


class StubLLM:
    """Stands in for Anthropic. Counts calls so the zero-token paths can be
    asserted to be actually zero-token rather than merely cheap."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.meal: dict[str, Any] = {}
        self.pending_labels: list[str] = []
        self.label: dict[str, Any] = {"supplements": []}

    async def __call__(self, *, model: str, tool: dict, system: Any, content: list, **kw: Any):
        from nutrai.llm.client import ToolResult

        name = tool["name"]
        self.calls.append(name)

        if name == "record_meal":
            data = self.meal
        elif name == "choose_food":
            # Takes the head of the candidate list, which is what a
            # correctly-behaving Haiku does when the list is ranked best-first.
            # This is why db.search_foods must rank by relevance: a stub this
            # obedient logs whatever the resolver put in position one.
            #
            # It also echoes the *whole* prompt line back as `label`, because
            # that is what the real model does — "pickle (dill gherkin) (logged
            # as as_sold, 45 g)". The old stub helpfully trimmed at the first
            # bracket, which made a label-keyed lookup look like it worked while
            # in production it matched nothing and discarded every correct
            # answer this tier produced. A stub better behaved than the thing it
            # stands in for tests nothing.
            data = {"choices": []}
            for line in content[0]["text"].splitlines():
                stripped = line.strip()
                if re.match(r"^\[\d+\]", stripped):
                    self.pending_labels.append(stripped)
                elif stripped.startswith("candidates:") and self.pending_labels:
                    echoed = self.pending_labels.pop(0)
                    first = stripped.split("candidates:")[1].split("|")[0].strip()
                    data["choices"].append({
                        "index": int(re.match(r"^\[(\d+)\]", echoed).group(1)),
                        "label": echoed.split("]", 1)[1].strip(),
                        "fdc_id": int(first.split(":")[0]),
                        "yield_factor": 1.0,
                        "confidence": 0.8,
                    })
        elif name == "modify_dish":
            data = {"operations": []}
        elif name == "read_supplement_label":
            data = self.label
        else:
            raise AssertionError(f"stub has no answer for tool {name!r}")

        return ToolResult(
            data=data, model=model, input_tokens=500, output_tokens=120,
            cache_read_tokens=0, cache_write_tokens=0, latency_ms=900,
            cost_usd=0.0038, stop_reason="tool_use",
        )


MEAL = {
    "dish_name": "mince and rice",
    "slot": "dinner",
    "overall_confidence": 0.91,
    "notes": "",
    "items": [
        {"label": "minced beef", "search_terms": "beef, ground, 85% lean meat / 15% fat, raw",
         "grams": 250, "grams_source": "scale", "state": "raw", "confidence": 0.95},
        {"label": "rice", "search_terms": "rice, white, long-grain, regular, cooked",
         "grams": 164, "grams_source": "scale", "state": "cooked", "confidence": 0.95},
        {"label": "olive oil", "search_terms": "oil, olive, salad or cooking",
         "grams": 15, "grams_source": "estimate", "state": "as_sold", "confidence": 0.45},
    ],
}


# ------------------------------------------------------------------ harness


def _bootstrap_test_user(telegram_id: int = CHAT_ID) -> None:
    """Create the test user by running the real bootstrap script.

    The suite used to assume someone had bootstrapped this id by hand, so
    deleting that row — which is the correct thing to do the moment a real
    account exists — turned the whole suite red for a reason that had nothing to
    do with the code. Own the fixture instead, and own it by calling the real
    script rather than by writing a second version of it here.
    """
    subprocess.run(
        [
            sys.executable, "scripts/bootstrap.py",
            "--telegram-id", str(telegram_id), "--name", "integration-test",
            "--sex", "male", "--age", "34", "--height-cm", "183",
            "--weight-kg", "74.4", "--activity", "1.55", "--deficit", "500",
            "--protein-g", "180",
        ],
        env={**os.environ, "PYTHONPATH": ".", "DATABASE_URL": DATABASE_URL},
        capture_output=True,
        text=True,
        check=True,
    )


async def _reset(user_telegram_id: int = CHAT_ID) -> int:
    """Wipe this user's log, keep the USDA reference data and the targets."""
    import asyncpg

    con = await asyncpg.connect(DATABASE_URL)
    try:
        # Existence is not enough: the bot's own `get_or_create_user` will
        # happily create this row on first contact with no targets attached, and
        # a user with no targets makes day_progress() return nothing at all.
        # Gate on the thing actually needed rather than on the row being there.
        uid = await con.fetchval(
            """SELECT u.id FROM app_user u
                WHERE u.telegram_id = $1
                  AND EXISTS (SELECT 1 FROM target t WHERE t.user_id = u.id)""",
            user_telegram_id,
        )
        if uid is None:
            await con.close()
            _bootstrap_test_user(user_telegram_id)
            con = await asyncpg.connect(DATABASE_URL)
            uid = await con.fetchval(
                "SELECT id FROM app_user WHERE telegram_id = $1", user_telegram_id
            )
        await con.execute("DELETE FROM log_entry WHERE user_id = $1", uid)
        await con.execute("DELETE FROM dish WHERE user_id = $1", uid)
        await con.execute("DELETE FROM food_alias WHERE user_id = $1", uid)
        await con.execute("DELETE FROM pending_action WHERE user_id = $1", uid)
        await con.execute("DELETE FROM notification_log WHERE user_id = $1", uid)
        await con.execute("DELETE FROM llm_call WHERE user_id = $1", uid)
        # Superseded targets, which nothing else drops. Every recalculation
        # and every /target test closes ~22 rows and inserts ~22 more, so the
        # test user had accumulated 11,330 of them — more rows than the real
        # user has log entries, and enough to distort any look at the database
        # by table size. The live rows stay: tests that assert versioning
        # create their own history inside the test.
        await con.execute(
            "DELETE FROM target WHERE user_id = $1 AND effective_to IS NOT NULL", uid)
        await con.execute("DELETE FROM observation WHERE user_id = $1", uid)
        return uid
    finally:
        await con.close()


class Harness:
    def __init__(self) -> None:
        self.tg = FakeTelegram()
        self.llm = StubLLM()
        self.llm.meal = dict(MEAL)

    async def feed(self, text: str) -> None:
        from nutrai.bot import dp

        await dp.feed_update(self.tg.bot, self.tg.text_update(text))

    async def press(self, callback_data: str, message_id: int) -> None:
        from nutrai.bot import dp

        await dp.feed_update(
            self.tg.bot, self.tg.callback_update(callback_data, message_id)
        )

    @property
    def sent(self):
        return self.tg.session


def _confirm_id(card) -> int:
    """The entry id behind a confirmation card's ✓ button."""
    return int(next(b for b in card.buttons if b.startswith("ok:")).split(":")[1])


def run(coro):
    """One event loop per test, and the connection pool dies inside it.

    db.pool() memoises a pool bound to whatever loop created it. Closing it from
    a later asyncio.run() raises 'Event loop is closed' from deep inside
    asyncpg, which reads like a driver bug and is not one.
    """

    async def wrapper():
        from nutrai import db

        try:
            return await coro
        finally:
            await db.close()

    return asyncio.run(wrapper())


@pytest.fixture
def harness(monkeypatch):
    import nutrai.llm.parse as parse_mod

    h = Harness()
    monkeypatch.setattr(parse_mod, "call_tool", h.llm)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    return h


# -------------------------------------------------------------------- tests


def test_text_message_to_confirmed_entry_in_today(harness):
    """The whole of stage 1 in one test."""

    async def scenario():
        await _reset()

        await harness.feed("/start")
        assert harness.sent.sent, "no reply to /start"

        harness.sent.clear()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")

        card = harness.sent.last()
        assert "mince and rice" in card.text
        assert "kcal" in card.text
        # Provenance marks: two weighed, one guessed.
        assert card.text.count("⚖") == 2, card.text
        assert "≈" in card.text
        assert "Nothing is logged until you confirm." in card.text

        assert any(b.startswith("ok:") for b in card.buttons), card.buttons
        entry_id = _confirm_id(card)

        # Nothing counts before the button is pressed.
        from nutrai import db

        p = await db.pool()
        assert await p.fetchval("SELECT status FROM log_entry WHERE id=$1", entry_id) == "pending"
        assert await p.fetchval("SELECT count(*) FROM log_nutrient WHERE entry_id=$1", entry_id) == 0

        await harness.press(f"ok:{entry_id}", card.message_id)
        assert await p.fetchval("SELECT status FROM log_entry WHERE id=$1", entry_id) == "confirmed"
        n_nutrients = await p.fetchval(
            "SELECT count(*) FROM log_nutrient WHERE entry_id=$1", entry_id
        )
        # The snapshot is the point: a full panel, written once, never recomputed.
        assert n_nutrients > 30, f"only {n_nutrients} nutrients snapshotted"

        harness.sent.clear()
        await harness.feed("/today")
        day = harness.sent.find("kcal")
        assert day, harness.sent.texts()
        assert "Mince and rice" in day.text
        assert "weighed or stated" in day.text

        # Energy actually landed, and is in the right ballpark for
        # 250 g raw mince + 164 g cooked rice + 15 g oil.
        kcal = await p.fetchval(
            """SELECT sum(ln.amount) FROM log_entry e JOIN log_nutrient ln ON ln.entry_id = e.id
                WHERE e.user_id = (SELECT id FROM app_user WHERE telegram_id = $1)
                  AND ln.nutrient_id = 1008 AND e.status = 'confirmed'""",
            CHAT_ID,
        )
        assert 700 < float(kcal) < 1400, f"{kcal} kcal is not plausible for that plate"

    run(scenario())


def test_repeat_is_zero_token(harness):
    """`/r` then `1` must not touch a model, and must log without a gate."""

    async def scenario():
        await _reset()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"ok:{entry_id}", card.message_id)

        calls_before = len(harness.llm.calls)
        harness.sent.clear()

        await harness.feed("/r")
        menu = harness.sent.last()
        assert "Repeat" in menu.text
        # Names are shown with a capital: "pickle juice" sitting in a list of
        # proper names looked like a bug.
        assert "Mince and rice" in menu.text
        # And no "x3" beside them — it read as how many would be logged when
        # it was only how often the dish had ever been eaten.
        assert "×" not in menu.text

        harness.sent.clear()
        await harness.feed("1")

        assert len(harness.llm.calls) == calls_before, "the repeat path called a model"
        # An unmodified repeat of a confirmed dish logs immediately, no button.
        # Threshold notifications fire straight after the write, so the summary
        # is not necessarily the last thing on screen.
        confirmation = next(
            (s for s in harness.sent.sent if s.text.startswith("✅ <b>Logged</b>")), None
        )
        assert confirmation, harness.sent.texts()
        assert not confirmation.buttons

        from nutrai import db

        p = await db.pool()
        n = await p.fetchval(
            """SELECT count(*) FROM log_entry
                WHERE user_id = (SELECT id FROM app_user WHERE telegram_id=$1)
                  AND status='confirmed'""",
            CHAT_ID,
        )
        assert n == 2

    run(scenario())


def test_a_discarded_dish_cannot_be_repeated_without_a_gate(harness):
    """Invariant 5. `_present` upserts the dish before the entry exists, so a
    meal you look at and discard still leaves a repeatable dish behind.

    It is no longer offered in the numbered menu — that only lists things
    actually eaten — but it is still reachable by slug, and that path must gate.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"no:{_confirm_id(card)}", card.message_id)

        p = await db.pool()
        slug = await p.fetchval("SELECT slug FROM dish WHERE user_id=$1", uid)
        assert slug, "discarding should still leave the dish for later"
        assert not await db.top_dishes(uid), "a never-eaten dish was offered as a repeat"

        harness.sent.clear()
        await harness.feed(slug)

        gated = harness.sent.last()
        assert [b for b in gated.buttons if b.startswith("ok:")], gated.text
        assert "never been confirmed" in gated.text
        assert await p.fetchval(
            "SELECT count(*) FROM log_entry WHERE user_id=$1 AND status='confirmed'", uid
        ) == 0, "a never-confirmed dish was logged with no gate"

        # Confirm it once and the repeat becomes instant from then on.
        await harness.press(f"ok:{_confirm_id(gated)}", gated.message_id)
        harness.sent.clear()
        await harness.feed(slug)
        assert not harness.sent.last().buttons
        assert await p.fetchval(
            "SELECT count(*) FROM log_entry WHERE user_id=$1 AND status='confirmed'", uid
        ) == 2

    run(scenario())


def test_every_logging_path_reports_progress(harness):
    """The post-log summary must follow a zero-token repeat too, not just ✓."""

    async def scenario():
        await _reset()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)
        assert any("Today so far" in s.text for s in harness.sent.sent)

        await harness.feed("/r")
        harness.sent.clear()
        await harness.feed("1")
        assert any("Today so far" in s.text for s in harness.sent.sent), harness.sent.texts()
        assert any("Still to go today" in s.text for s in harness.sent.sent)

    run(scenario())


def test_escalation_cost_is_not_under_reported(harness):
    """The card used to show only the winning call's cost, hiding the escalation."""

    async def scenario():
        uid = await _reset()
        from nutrai.config import CONFIDENCE_ESCALATE
        from nutrai import db
        from nutrai.bot import dp

        harness.llm.meal = dict(MEAL, overall_confidence=CONFIDENCE_ESCALATE - 0.2)
        await dp.feed_update(harness.tg.bot, harness.tg.photo_update(_jpeg()))

        p = await db.pool()
        billed = float(
            await p.fetchval(
                "SELECT sum(cost_usd) FROM llm_call WHERE user_id=$1 AND purpose LIKE 'photo_parse%'",
                uid,
            )
        )
        # Two calls at the stub's 0.0038 each.
        assert billed == pytest.approx(0.0076)
        shown = harness.sent.last().text
        # 0.76 cents, not 0.38.
        assert "$0.0076" in shown, shown

    run(scenario())


def test_repeat_with_modifier_goes_through_the_gate(harness):
    """`1 x1.5` is a new claim about the world, so it must be confirmed."""

    async def scenario():
        await _reset()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)
        await harness.feed("/r")

        calls_before = len(harness.llm.calls)
        harness.sent.clear()
        await harness.feed("1 x1.5")

        assert len(harness.llm.calls) == calls_before, "x1.5 is in the grammar; it must not cost a call"
        gated = harness.sent.last()
        assert [b for b in gated.buttons if b.startswith("ok:")], gated.text
        # 250 -> 375 g of mince.
        assert "375" in gated.text, gated.text

    run(scenario())


def _jpeg(w: int = 1280, h: int = 960) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (140, 90, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def test_photo_to_confirmation_card(harness):
    """Stage 2: one photo, one parse, one card.

    Exercises the real download, the real downscale, and the real handler —
    which is where the largest-PhotoSize choice and the image budget live.
    """

    async def scenario():
        await _reset()
        from nutrai.bot import dp

        await dp.feed_update(
            harness.tg.bot,
            harness.tg.photo_update(_jpeg(), caption="mince and rice, weighed"),
        )

        card = harness.sent.last()
        assert "mince and rice" in card.text, harness.sent.texts()
        assert [b for b in card.buttons if b.startswith("ok:")]
        assert harness.llm.calls.count("record_meal") == 1, harness.llm.calls

        # The uploaded image must be the downscaled one. A stock 1280x960
        # Telegram photo is 1,610 visual tokens; 896x672 is 768 and identifies
        # a plate just as well.
        from nutrai.config import IMAGE_LONG_EDGE
        from nutrai.llm.parse import prepare_image, visual_tokens

        _b64, w, h = prepare_image(_jpeg())
        assert max(w, h) == IMAGE_LONG_EDGE
        assert visual_tokens(w, h) < visual_tokens(1280, 960)

    run(scenario())


def test_photo_confidence_below_threshold_escalates_once(harness):
    async def scenario():
        await _reset()
        from nutrai.bot import dp
        from nutrai.config import CONFIDENCE_ESCALATE

        harness.llm.meal = dict(MEAL, overall_confidence=CONFIDENCE_ESCALATE - 0.2)
        await dp.feed_update(harness.tg.bot, harness.tg.photo_update(_jpeg()))

        # Exactly one escalation, not a loop.
        assert harness.llm.calls.count("record_meal") == 2, harness.llm.calls

        from nutrai import db

        p = await db.pool()
        purposes = [
            r["purpose"]
            for r in await p.fetch("SELECT purpose FROM llm_call ORDER BY id")
        ]
        assert "photo_parse" in purposes
        assert "photo_parse_escalated" in purposes

    run(scenario())


def test_album_becomes_one_meal_not_four(harness):
    """Without the media_group_id buffer, a four-photo meal is four meals."""

    async def scenario():
        await _reset()
        from nutrai.bot import ALBUM_WAIT, dp

        harness.llm.calls.clear()
        for _ in range(3):
            await dp.feed_update(
                harness.tg.bot, harness.tg.photo_update(_jpeg(), media_group_id="album-1")
            )
        await asyncio.sleep(ALBUM_WAIT + 0.6)

        cards = [s for s in harness.sent.sent if s.buttons]
        assert len(cards) == 1, f"{len(cards)} confirmation cards for one album"

        # One card was never the whole guarantee. The three photos used to be
        # parsed separately and their items concatenated, so one meal became
        # one card listing everything three times — a drink photographed twice
        # was logged as 660 ml and 61 g of sugar for a 330 ml bottle.
        assert harness.llm.calls.count("record_meal") == 1, (
            f"{harness.llm.calls.count('record_meal')} parses for one album — "
            "items from separate parses get concatenated, not merged")

    run(scenario())


def test_no_slash_command_is_ever_dropped(harness):
    """Through the real dispatcher, so registration order is what is tested."""

    async def scenario():
        await _reset()
        from nutrai.bot import COMMANDS

        # Commands that do not exist come back with the list of ones that do.
        for typed in ("/improve", "/targets", "/nonsense", "/r0"):
            harness.sent.clear()
            await harness.feed(typed)
            assert harness.sent.sent, f"{typed} produced no reply at all"
            reply = harness.sent.last().text
            assert "is not a command here" in reply, reply
            assert "/insight" in reply

        # Commands that do exist are not swallowed by the catch-all.
        for name, _desc in COMMANDS:
            harness.sent.clear()
            await harness.feed(name)
            assert harness.sent.sent, f"{name} produced no reply at all"
            assert "is not a command here" not in harness.sent.last().text, name

        # And no model was called to work any of that out.
        assert not harness.llm.calls

    run(scenario())


def test_every_message_is_valid_html(harness):
    """Whatever the bot sends, Telegram must be able to parse it."""

    async def scenario():
        await _reset()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)
        for cmd in ("/start", "/today", "/today all", "/r", "/spend", "/fast", "/nope"):
            await harness.feed(cmd)

        for sent in harness.sent.sent:
            if sent.parse_mode != "HTML":
                continue
            _assert_balanced_html(sent.text)
            for block in re.findall(r"<pre>(.*?)</pre>", sent.text, re.DOTALL):
                assert "<" not in block, f"nested markup in <pre>:\n{block}"

    run(scenario())


def _assert_balanced_html(text: str) -> None:
    stack: list[str] = []
    for m in re.finditer(r"<(/?)([a-z]+)[^>]*>", text):
        closing, name = m.group(1), m.group(2)
        if closing:
            assert stack and stack[-1] == name, f"unbalanced </{name}> in:\n{text}"
            stack.pop()
        else:
            stack.append(name)
    assert not stack, f"unclosed {stack} in:\n{text}"


def test_an_unresolvable_meal_still_keeps_the_parse(harness):
    """A resolution failure is the most informative thing the pipeline emits.

    It has already cost a Sonnet call, often an Opus escalation and a Haiku
    disambiguation. Throwing the model's output away at that point means you can
    see that a meal failed but never what search terms lost, so the resolver
    cannot be improved against the case that beat it.
    """

    async def scenario():
        uid = await _reset()
        harness.llm.meal = {
            "dish_name": "unmatchable thing",
            "slot": "lunch",
            "overall_confidence": 0.55,
            "notes": "",
            "items": [
                {"label": "zzqqx", "search_terms": "zzqqxwv nonexistent foodstuff",
                 "grams": 100, "grams_source": "estimate", "state": "unknown",
                 "confidence": 0.3},
            ],
        }

        await harness.feed("some zzqqx please")

        reply = harness.sent.last().text
        assert "No match" in reply, reply
        # The failing label is named, so there is something to act on.
        assert "zzqqx" in reply
        buttons = harness.sent.last().buttons
        assert not [b for b in buttons if b.startswith("confirm:")], \
            "nothing to confirm — nothing resolved"
        assert any(b.startswith("deffood:") for b in buttons), \
            "a total miss is exactly when /food is worth offering"

        from nutrai import db

        p = await db.pool()
        row = await p.fetchrow(
            """SELECT status, parse, confidence, model FROM log_entry
                WHERE user_id = $1 ORDER BY id DESC LIMIT 1""",
            uid,
        )
        assert row is not None, "the parse was discarded — 5p of model output lost"
        assert row["status"] == "discarded", row["status"]
        assert row["parse"], "entry kept but the parse JSON was not"
        assert "zzqqx" in row["parse"], "the parse does not contain what the model said"

        # It must not count towards anything.
        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        assert not await db.day_entries(uid, today)
        kcal = await p.fetchval(
            """SELECT COALESCE(sum(ln.amount), 0) FROM log_entry e
                 JOIN log_nutrient ln ON ln.entry_id = e.id
                WHERE e.user_id = $1 AND ln.nutrient_id = 1008""",
            uid,
        )
        assert float(kcal) == 0.0

    run(scenario())


def test_weight_is_recorded_and_implausible_values_refused(harness):
    """The only input to body_metric, and the only thing that makes /insight work.

    A fat-fingered 782 for 78.2 would bend the weight regression for weeks and
    never look wrong in a list, so the impossible is refused rather than stored.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM body_metric WHERE user_id = $1", uid)

        await harness.feed("/weight 78.2")
        assert "78.2 kg" in harness.sent.last().text
        rows = await p.fetch(
            "SELECT kind, value FROM body_metric WHERE user_id = $1", uid
        )
        assert len(rows) == 1
        assert rows[0]["kind"] == "weight_kg"
        assert float(rows[0]["value"]) == pytest.approx(78.2)

        # A second reading reports the delta against the first.
        harness.sent.clear()
        await harness.feed("/weight 77.6")
        assert "-0.6 kg" in harness.sent.last().text

        # Nonsense is refused, and nothing is written.
        harness.sent.clear()
        await harness.feed("/weight 782")
        assert "Nothing was saved" in harness.sent.last().text
        assert await p.fetchval(
            "SELECT count(*) FROM body_metric WHERE user_id = $1", uid
        ) == 2

        # No argument reads rather than writes: a menu tap must not start a
        # write, and half the time the question is "what was I last?".
        harness.sent.clear()
        await harness.feed("/weight")
        card = harness.sent.last()
        assert "77.6 kg" in card.text, card.text
        assert [b for b in card.buttons if b.startswith("wnew:")], card.buttons

        # Recording is a deliberate second step.
        await harness.press("wnew:", card.message_id)
        assert "What do you weigh?" in harness.sent.last().text
        harness.sent.clear()
        await harness.feed("77.1")
        assert "77.1 kg" in harness.sent.last().text, harness.sent.texts()
        assert float(
            await p.fetchval(
                """SELECT value FROM body_metric WHERE user_id=$1
                    ORDER BY measured_at DESC LIMIT 1""",
                uid,
            )
        ) == pytest.approx(77.1)

        # And none of it costs a model call.
        assert not harness.llm.calls

    run(scenario())


def test_insight_refuses_until_the_weight_span_is_long_enough(harness):
    """Two weeks minimum: glycogen and water swamp fat over anything shorter."""

    async def scenario():
        uid = await _reset()
        from nutrai import db
        from nutrai.core import insight

        p = await db.pool()
        await p.execute("DELETE FROM body_metric WHERE user_id = $1", uid)

        # Three days of weigh-ins is not a trend, however tidy the numbers.
        for offset, kg in ((2, 78.4), (1, 78.1), (0, 77.9)):
            await p.execute(
                """INSERT INTO body_metric (user_id, measured_at, local_date, kind, value)
                   VALUES ($1, now() - ($2 || ' days')::interval,
                           current_date - $2::int, 'weight_kg', $3)""",
                uid, str(offset), kg,
            )

        assert await db.weight_span_days(uid) == 3
        assert insight.fat_loss_rate(await db.weight_series(uid), [2000.0] * 3) is None

        harness.sent.clear()
        await harness.feed("/insight")
        assert f"Need {insight.MIN_TREND_DAYS}+ days" in harness.sent.last().text

    run(scenario())


def test_the_fix_button_actually_corrects_the_entry(harness):
    """✎ used to print instructions and ignore the reply.

    Nothing consumed the fix_entry action, so the correction fell through to the
    text parser, cost a Sonnet call, and logged a *second* meal beside the one
    being corrected. Inert would have been an improvement.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)

        await harness.press(f"fix:{entry_id}", card.message_id)
        calls_before = len(harness.llm.calls)

        harness.sent.clear()
        await harness.feed("rice 200")

        # No new meal, no model call, same entry.
        assert len(harness.llm.calls) == calls_before, "a correction cost a parse"
        p = await db.pool()
        assert await p.fetchval(
            "SELECT count(*) FROM log_entry WHERE user_id=$1", uid
        ) == 1, "the correction created a second entry"

        grams = await p.fetchval(
            "SELECT grams FROM log_component WHERE entry_id=$1 AND label='rice'", entry_id
        )
        assert float(grams) == pytest.approx(200.0)
        assert await p.fetchval(
            "SELECT status FROM log_entry WHERE id=$1", entry_id
        ) == "pending"

        # A fresh card comes back, still confirmable.
        assert _confirm_id(harness.sent.last()) == entry_id

        # The action is consumed: the next message is a normal message again.
        harness.sent.clear()
        await harness.feed("oil 30")
        assert await p.fetchval(
            "SELECT grams FROM log_component WHERE entry_id=$1 AND label='olive oil'",
            entry_id,
        ) == 15, "a second correction applied with no ✎ pressed"

    run(scenario())


def test_a_fix_does_not_downgrade_untouched_provenance(harness):
    """Correcting one component must not turn its neighbours into guesses.

    `apply()` hardcoded "repeat" for every component it copied, so correcting
    the rice in "400 g rice and 100 g chicken" downgraded the untouched chicken
    from `stated` to `repeat`. It rendered as ≈, and portion_history() stopped
    counting it — that reads only scale/stated/package rows, so a mass you
    stated quietly stopped being able to inform a future estimate.
    """

    async def scenario():
        await _reset()
        from nutrai import db

        harness.llm.meal = {
            "dish_name": "rice and chicken", "slot": "dinner",
            "overall_confidence": 0.9, "notes": "",
            "items": [
                {"label": "rice", "search_terms": "rice, white, long-grain, regular, cooked",
                 "grams": 400, "grams_source": "stated", "state": "cooked", "confidence": 0.9},
                {"label": "chicken", "search_terms": "chicken, broilers or fryers, breast, meat only, cooked, roasted",
                 "grams": 100, "grams_source": "stated", "state": "cooked", "confidence": 0.9},
            ],
        }
        await harness.feed("400g rice and 100g chicken")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"fix:{entry_id}", card.message_id)
        await harness.feed("rice 500")

        p = await db.pool()
        rows = {
            r["label"]: (r["grams_source"], float(r["grams_sigma"]))
            for r in await p.fetch(
                "SELECT label, grams_source, grams_sigma FROM log_component WHERE entry_id=$1",
                entry_id,
            )
        }
        assert rows["chicken"][0] == "stated", rows
        assert rows["rice"][0] == "stated", rows
        # And sigma is recomputed, not zeroed — zero would claim the corrected
        # mass is exact and shrink the day's error bar.
        assert rows["rice"][1] > 0, rows
        assert rows["chicken"][1] > 0, rows

    run(scenario())


def test_fix_can_drop_a_component(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"fix:{entry_id}", card.message_id)

        await harness.feed("-oil")
        p = await db.pool()
        labels = [
            r["label"]
            for r in await p.fetch(
                "SELECT label FROM log_component WHERE entry_id=$1", entry_id
            )
        ]
        assert "olive oil" not in labels
        assert "minced beef" in labels

    run(scenario())


def test_fix_on_an_already_confirmed_entry_does_not_log_a_second_meal(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"fix:{entry_id}", card.message_id)
        # Confirm it before replying to the fix prompt.
        await harness.press(f"ok:{entry_id}", card.message_id)

        calls_before = len(harness.llm.calls)
        harness.sent.clear()
        await harness.feed("rice 200")

        assert "already dealt with" in harness.sent.last().text
        assert len(harness.llm.calls) == calls_before
        p = await db.pool()
        assert await p.fetchval(
            "SELECT count(*) FROM log_entry WHERE user_id=$1", uid
        ) == 1

    run(scenario())


def test_an_unreadable_correction_keeps_the_fix_open(harness):
    async def scenario():
        await _reset()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"fix:{entry_id}", card.message_id)

        harness.sent.clear()
        await harness.feed("hmm actually not sure")
        assert "could not read that as a correction" in harness.sent.last().text

        # Still in fix mode, so a proper correction lands.
        await harness.feed("rice 200")
        from nutrai import db

        p = await db.pool()
        assert float(
            await p.fetchval(
                "SELECT grams FROM log_component WHERE entry_id=$1 AND label='rice'",
                entry_id,
            )
        ) == pytest.approx(200.0)

    run(scenario())


def test_undo_removes_the_last_entry_without_deleting_it(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"ok:{entry_id}", card.message_id)

        p = await db.pool()
        assert await p.fetchval("SELECT times_logged FROM dish WHERE user_id=$1", uid) == 1

        harness.sent.clear()
        await harness.feed("/undo")
        assert "Unlogged" in harness.sent.sent[0].text

        # Discarded, not deleted — invariant 2 keeps the snapshot.
        assert await p.fetchval("SELECT status FROM log_entry WHERE id=$1", entry_id) == "discarded"
        assert await p.fetchval(
            "SELECT count(*) FROM log_nutrient WHERE entry_id=$1", entry_id
        ) > 0
        # And it counts towards nothing.
        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        assert not await db.day_entries(uid, today)

        # times_logged is decremented, so the dish cannot repeat without a gate.
        assert await p.fetchval("SELECT times_logged FROM dish WHERE user_id=$1", uid) == 0
        await harness.feed("/r")
        harness.sent.clear()
        await harness.feed("1")
        assert [b for b in harness.sent.last().buttons if b.startswith("ok:")], \
            "an undone dish repeated with no confirmation"

    run(scenario())


def test_undo_with_nothing_logged_says_so(harness):
    async def scenario():
        await _reset()
        harness.sent.clear()
        await harness.feed("/undo")
        assert "Nothing logged today" in harness.sent.last().text

    run(scenario())


def test_audit_catches_an_inverted_match(harness):
    """The failure that prompted the audit: a real food matched to an analogue.

    Internally consistent, so the Atwater check passes and nothing raises. The
    only evidence is a nutrient that does not belong.
    """

    async def scenario():
        uid = await _reset()
        from nutrai.jobs.audit import audit_user
        from nutrai import db

        p = await db.pool()
        meatless = await p.fetchval(
            "SELECT fdc_id FROM food WHERE description ILIKE 'Chicken, meatless%' LIMIT 1"
        )
        if meatless is None:
            pytest.skip("this USDA build has no meatless chicken row")

        harness.llm.meal = {
            "dish_name": "fried chicken", "slot": "dinner",
            "overall_confidence": 0.8, "notes": "",
            "items": [{"label": "fried chicken", "search_terms": "chicken, meatless, breaded, fried",
                       "grams": 400, "grams_source": "stated", "state": "cooked",
                       "confidence": 0.8}],
        }
        await harness.feed("400g fried chicken")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        codes = {f.code for f in await audit_user(uid, days=1)}
        assert "inverted_match" in codes, codes
        # And the alias that would repeat it silently.
        assert "inverted_alias" in codes, codes

    run(scenario())


def test_audit_is_quiet_on_a_clean_log(harness):
    async def scenario():
        uid = await _reset()
        from nutrai.jobs.audit import audit_user

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        serious = [
            f for f in await audit_user(uid, days=1) if f.severity in ("error", "warn")
        ]
        # A weighed, correctly-matched meal should raise nothing serious.
        assert not [f for f in serious if f.code == "inverted_match"], serious

    run(scenario())


def test_llm_calls_are_priced_and_recorded(harness):
    async def scenario():
        uid = await _reset()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")

        from nutrai import db

        p = await db.pool()
        rows = await p.fetch("SELECT purpose, model, cost_usd FROM llm_call WHERE user_id=$1", uid)
        assert rows, "no llm_call row written — /spend would report nothing"
        assert any(r["purpose"] == "text_parse" for r in rows)
        assert all(float(r["cost_usd"]) > 0 for r in rows)

    run(scenario())


def test_day_progress_and_thresholds_run_without_a_model(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db
        from nutrai.jobs.notify import evaluate_user

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        prog = await db.day_progress(uid, today)
        assert prog, "day_progress returned nothing"
        by_id = {r["nutrient_id"]: r for r in prog}
        assert float(by_id[1008]["amount"]) > 0
        assert by_id[1003]["state"] in ("under", "ok", "over")

        # Must not raise, must not call a model.
        msgs = await evaluate_user(uid, today)
        assert isinstance(msgs, list)

    run(scenario())


def test_supplements_count_toward_targets_and_stay_attributable(harness):
    """Counted, per the user's decision — but never blended into the food total.

    A micronutrient met by a capsule is different information from one met by
    food. Blending them would let /improve recommend fixing a deficiency that is
    already treated, or conclude a diet supplies something it does not.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id = $1", uid)
        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)

        before = {r["nutrient_id"]: r for r in await db.day_progress(uid, today)}
        assert before[1114]["state"] == "under"

        await db.upsert_supplement(uid, "D3", [(1114, 20.0)], serving_desc="1 capsule")
        # Defined is not taken: nothing counts until the stack is logged.
        mid = {r["nutrient_id"]: r for r in await db.day_progress(uid, today)}
        assert float(mid[1114]["amount_supplement"]) == 0.0
        assert mid[1114]["state"] == "under"

        # /supp asks rather than assumes: the stack is pre-ticked and logged
        # only when the button is pressed.
        harness.sent.clear()
        await harness.feed("/supp")
        picker = harness.sent.last()
        assert "Which did you take?" in picker.text
        # Nothing arrives pre-ticked, so ticking it is the act being tested.
        for toggle in [b for b in picker.buttons if b.startswith("supt:")]:
            await harness.press(toggle, picker.message_id)
            picker = harness.sent.last()
        log_btn = next(b for b in picker.buttons if b.startswith("suplog:"))
        await harness.press(log_btn, picker.message_id)

        after = {r["nutrient_id"]: r for r in await db.day_progress(uid, today)}
        assert float(after[1114]["amount_supplement"]) == pytest.approx(20.0)
        assert float(after[1114]["amount"]) == pytest.approx(
            float(after[1114]["amount_food"]) + 20.0
        )
        assert after[1114]["state"] == "ok"

        # Logging twice is not taking double.
        harness.sent.clear()
        await harness.feed("/supp")
        picker = harness.sent.last()
        await harness.press(
            next(b for b in picker.buttons if b.startswith("suplog:")), picker.message_id
        )
        again = {r["nutrient_id"]: r for r in await db.day_progress(uid, today)}
        assert float(again[1114]["amount_supplement"]) == pytest.approx(20.0)

        # And none of it costs a model call.
        assert not harness.llm.calls

    run(scenario())


def test_supplement_contribution_is_visible_on_the_day_card(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db
        from nutrai.core import render

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id = $1", uid)
        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        await db.upsert_supplement(uid, "D3", [(1114, 20.0)], serving_desc="1 capsule")
        await db.log_supplements(uid, today)

        card = render.day_card(today, await db.day_progress(uid, today), [], show_all=True)
        assert "💊" in card, card

    run(scenario())


def test_supplement_picker_lets_you_drop_one(harness):
    """The day you skip one is the day an assumed log invents a number."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id = $1", uid)
        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        await db.upsert_supplement(uid, "D3", [(1114, 20.0)], serving_desc="1 capsule")
        await db.upsert_supplement(uid, "B12", [(1178, 100.0)], serving_desc="1 tablet")

        harness.sent.clear()
        await harness.feed("/supp")
        picker = harness.sent.last()
        # Nothing is pre-ticked. A tick is a record of having taken it, which
        # is the only version that can carry a time and the only one where an
        # untaken capsule cannot reach a day's totals by default.
        assert "Nothing ticked yet today" in picker.text, picker.text

        toggle = next(b for b in picker.buttons if b.startswith("supt:"))
        await harness.press(toggle, picker.message_id)
        picker = harness.sent.last()
        assert "1 of 2 taken so far today" in picker.text, picker.text

        await harness.press(
            next(b for b in picker.buttons if b.startswith("suplog:")), picker.message_id
        )
        prog = {r["nutrient_id"]: r for r in await db.day_progress(uid, today)}
        supplied = [nid for nid in (1114, 1178) if float(prog[nid]["amount_supplement"]) > 0]
        assert len(supplied) == 1, "the deselected supplement was logged anyway"

    run(scenario())


def test_a_meal_can_be_backdated_from_the_fix_card(harness):
    """Food gets remembered late. Logging it on the wrong day corrupts two days."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"fix:{entry_id}", card.message_id)

        harness.sent.clear()
        await harness.feed("@yesterday")
        assert "moved to" in harness.sent.last().text

        p = await db.pool()
        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        assert await p.fetchval(
            "SELECT local_date FROM log_entry WHERE id=$1", entry_id
        ) == today - dt.timedelta(days=1)

        # Confirm it and it lands in yesterday's totals, not today's.
        await harness.press(f"ok:{_confirm_id(harness.sent.last())}", harness.sent.last().message_id)
        assert not await db.day_entries(uid, today)
        assert await db.day_entries(uid, today - dt.timedelta(days=1))
        # No model was needed to move a day.
        assert harness.llm.calls.count("record_meal") == 1

    run(scenario())


def test_backdating_never_goes_forward(harness):
    """A meal filed in the future is invisible until it silently arrives."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"fix:{entry_id}", card.message_id)
        await harness.feed("@2099-01-01")

        p = await db.pool()
        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        assert await p.fetchval("SELECT local_date FROM log_entry WHERE id=$1", entry_id) == today

    run(scenario())


def test_text_after_supp_add_is_a_label_not_a_meal(harness):
    """A prompt that ignores the answer is worse than no prompt.

    `/supp add` awaited a photo, so a written description of eight supplements
    fell through to the meal parser and became two nonsense meals — 4 kcal and
    0 kcal, both logged — while the stack stayed empty.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id = $1", uid)
        harness.llm.label = {
            "supplements": [
                {
                    "name": "Solgar Chelated Zinc 22 mg",
                    "serving_desc": "1 tablet",
                    "servings_per_day": 1,
                    "nutrients": [{"nutrient_id": 1095, "printed_label": "elemental zinc",
                                   "amount": 22, "unit": "mg"}],
                    "not_tracked": "",
                }
            ],
            "unreadable": "",
        }

        await harness.feed("/supp add")
        harness.sent.clear()
        await harness.feed("Solgar Chelated Zinc 22 mg, 1 tablet daily, 22 mg elemental zinc")

        assert harness.llm.calls[-1] == "read_supplement_label", harness.llm.calls
        assert await p.fetchval(
            "SELECT count(*) FROM log_entry WHERE user_id=$1", uid
        ) == 0, "a supplement description was logged as a meal"

        card = harness.sent.last()
        assert "product(s) read" in card.text
        await harness.press(
            next(b for b in card.buttons if b.startswith("supok:")), card.message_id
        )
        assert await p.fetchval(
            "SELECT count(*) FROM supplement WHERE user_id=$1", uid
        ) == 1

        harness.sent.clear()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        assert harness.llm.calls[-1] != "read_supplement_label"

    run(scenario())


def test_rate_offers_buttons_and_records_a_tap(harness):
    """Typing `/rate energy 6` on a phone is the point of failure.

    A rating you have to stop and type is one you postpone, and a rating
    invented later is exactly the noise the refusal gate exists to keep out.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM observation WHERE user_id = $1", uid)

        # /rate bare offers the kinds.
        harness.sent.clear()
        await harness.feed("/rate")
        card = harness.sent.last()
        assert "What are you rating?" in card.text
        kinds = [b for b in card.buttons if b.startswith("ratek:")]
        assert len(kinds) == 6, kinds

        # Choosing one offers a 1-10 keypad.
        await harness.press("ratek:energy", card.message_id)
        card = harness.sent.last()
        values = [b for b in card.buttons if b.startswith("ratev:")]
        assert len(values) == 10, values

        # Tapping records it.
        await harness.press("ratev:energy:7", card.message_id)
        rows = await p.fetch(
            "SELECT kind, value FROM observation WHERE user_id=$1", uid
        )
        assert len(rows) == 1
        assert rows[0]["kind"] == "energy" and float(rows[0]["value"]) == 7.0

        # Naming the kind skips the picker.
        harness.sent.clear()
        await harness.feed("/rate focus")
        card = harness.sent.last()
        assert "focus" in card.text
        assert all(b.startswith("ratev:focus:") for b in card.buttons), card.buttons

        # And typing the whole thing still works.
        await harness.feed("/rate focus 9")
        assert float(
            await p.fetchval(
                "SELECT value FROM observation WHERE user_id=$1 AND kind='focus'", uid
            )
        ) == 9.0

        assert not harness.llm.calls

    run(scenario())


def test_a_number_after_the_rating_keypad_is_the_rating(harness):
    """A bare number is also the repeat selector, and the keypad invites one.

    A rating prompt then "4" pulled up dish 4 from the repeat menu instead of
    recording focus 4 — the grammar had already claimed bare numbers.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM observation WHERE user_id = $1", uid)

        # Give the repeat menu something to collide with.
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)
        await harness.feed("/r")

        harness.sent.clear()
        await harness.feed("/rate focus")
        await harness.feed("1")

        assert float(
            await p.fetchval(
                "SELECT value FROM observation WHERE user_id=$1 AND kind='focus'", uid
            )
        ) == 1.0, "the number was eaten by the repeat grammar"
        # And no meal was logged by it.
        assert await p.fetchval(
            "SELECT count(*) FROM log_entry WHERE user_id=$1 AND status='confirmed'", uid
        ) == 1

        # Once consumed, a bare number is a repeat selector again.
        harness.sent.clear()
        await harness.feed("1")
        assert any("Logged" in s.text or s.buttons for s in harness.sent.sent), \
            harness.sent.texts()

    run(scenario())


def test_activity_endpoint_stores_and_deduplicates(harness):
    """A workout bot that retries on a timeout will eventually retry on a
    success, and a duplicated training day silently doubles a covariate."""

    async def scenario():
        uid = await _reset()
        import importlib
        from aiohttp.test_utils import TestClient, TestServer

        os.environ["NUTRAI_HTTP_TOKEN"] = "t"
        import nutrai.http_api as api

        importlib.reload(api)

        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM activity WHERE user_id = $1", uid)
        h = {"X-Nutrai-Token": "t"}
        body = {
            "telegram_id": CHAT_ID, "kind": "lifting", "minutes": 60,
            "kcal_burned": 420, "note": "push day", "local_date": "2026-08-16",
        }
        async with TestClient(TestServer(api.build_app())) as c:
            first = await c.post("/activity", json=body, headers=h)
            assert first.status == 201, await first.text()
            assert (await first.json())["created"] is True
            # The same session posted twice is one session.
            again = await c.post("/activity", json=body, headers=h)
            assert again.status == 200
            assert (await again.json())["created"] is False

        rows = await db.activity_on(uid, dt.date(2026, 8, 16))
        assert len(rows) == 1
        assert rows[0]["kind"] == "lifting"
        assert rows[0]["minutes"] == 60
        assert float(rows[0]["kcal_burned"]) == 420.0

    run(scenario())


def test_sleep_is_joined_to_the_day_before_not_the_morning_after(harness):
    """Sleep is the one rating whose cause precedes it by a day.

    The snapshot taken at rating time records the overnight fast, which says
    nothing about the dinner that might have disturbed it.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        for t in ("observation", "activity"):
            await p.execute(f"DELETE FROM {t} WHERE user_id = $1", uid)

        # A meal yesterday, a sleep rating this morning.
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"ok:{entry_id}", card.message_id)

        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        await p.execute(
            "UPDATE log_entry SET local_date = $2 WHERE id = $1", entry_id, today - dt.timedelta(days=1)
        )
        await p.execute(
            """INSERT INTO observation (user_id, local_date, kind, value)
               VALUES ($1, $2, 'sleep', 6)""",
            uid, today,
        )
        await db.record_activity(uid, today - dt.timedelta(days=1), "lifting", minutes=45)

        rows = await db.sleep_predictors(uid)
        assert len(rows) == 1, rows
        r = rows[0]
        assert float(r["sleep"]) == 6.0
        # Yesterday's food, not this morning's fast.
        assert float(r["kcal_yesterday"]) > 500, dict(r)
        assert int(r["training_minutes"]) == 45
        assert r["lifted"] is True

    run(scenario())


def test_the_repeat_menu_offers_only_things_actually_eaten(harness):
    """`_present` creates the dish before the entry is confirmed, so a meal you
    discarded because it was wrong still left a dish behind — and a cappuccino
    containing a phantom whisky cocktail sat in the menu at ×0, one tap from
    being logged again."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        # Parse a meal and throw it away.
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"no:{_confirm_id(card)}", card.message_id)

        p = await db.pool()
        assert await p.fetchval("SELECT count(*) FROM dish WHERE user_id=$1", uid) == 1
        assert not await db.top_dishes(uid), "a discarded meal was offered as a repeat"

        harness.sent.clear()
        await harness.feed("/r")
        assert "Nothing to repeat yet" in harness.sent.last().text

        # Confirm one and it appears.
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)
        assert len(await db.top_dishes(uid)) == 1

    run(scenario())


def test_afternoon_caffeine_is_measured_in_local_time(harness):
    """logged_at is stored UTC. Reading its hour raw put the "afternoon" cutoff
    at 14:00 Warsaw in summer and 13:00 in winter — a threshold that drifts with
    daylight saving is not a threshold."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        for t in ("observation", "activity"):
            await p.execute(f"DELETE FROM {t} WHERE user_id = $1", uid)

        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        yesterday = today - dt.timedelta(days=1)

        # 10:30 UTC == 12:30 Warsaw: afternoon locally, morning in UTC.
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"ok:{entry_id}", card.message_id)
        await p.execute(
            """UPDATE log_entry SET local_date = $2,
                   logged_at = ($2::date + time '10:30') AT TIME ZONE 'UTC'
                WHERE id = $1""",
            entry_id, yesterday,
        )
        await p.execute(
            """INSERT INTO log_nutrient (entry_id, nutrient_id, amount)
               VALUES ($1, 1057, 90)
               ON CONFLICT (entry_id, nutrient_id) DO UPDATE SET amount = 90""",
            entry_id,
        )
        await p.execute(
            """INSERT INTO observation (user_id, local_date, kind, value)
               VALUES ($1, $2, 'sleep', 5)""",
            uid, today,
        )

        rows = await db.sleep_predictors(uid)
        assert len(rows) == 1, rows
        assert float(rows[0]["caffeine_yesterday"]) == pytest.approx(90.0)
        assert float(rows[0]["caffeine_pm_yesterday"]) == pytest.approx(90.0), (
            "12:30 local was counted as morning because the hour was read in UTC"
        )

    run(scenario())


def test_under_rules_do_not_fire_in_the_morning(harness):
    """At 09:17 you are at 4% of a daily protein floor because you have had two
    coffees. Saying so describes the hour, not the eating."""

    async def scenario():
        uid = await _reset()
        from nutrai.jobs.notify import evaluate_user
        from nutrai import db

        today = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)
        p = await db.pool()
        await p.execute("DELETE FROM notification_log WHERE user_id = $1", uid)

        morning = dt.datetime(2026, 8, 16, 7, 17, tzinfo=dt.timezone.utc)   # 09:17 Warsaw
        evening = dt.datetime(2026, 8, 16, 17, 30, tzinfo=dt.timezone.utc)  # 19:30 Warsaw

        assert not [m for m in await evaluate_user(uid, today, now=morning) if "Protein" in m]
        assert [m for m in await evaluate_user(uid, today, now=evening) if "Protein" in m], \
            "an evening protein shortfall is real and should be said"

    run(scenario())


def test_an_unapplied_modifier_is_stated_not_swallowed(harness):
    """"1 decaffe espresso" was read, paid for, understood by nobody, and logged
    as ordinary espresso — 64 mg of caffeine — with the card showing the
    unmodified dish and no indication anything had been dropped."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)
        await harness.feed("/r")

        # The stub's modify_dish returns no operations — the real failure mode.
        harness.sent.clear()
        await harness.feed("1 with something the grammar cannot read")

        out = harness.sent.last()
        assert "could not apply" in out.text, out.text
        assert "something the grammar cannot read" in out.text
        # And it is gated, not logged.
        assert [b for b in out.buttons if b.startswith("ok:")], out.buttons

        p = await db.pool()
        assert await p.fetchval(
            "SELECT count(*) FROM log_entry WHERE user_id=$1 AND status='confirmed'", uid
        ) == 1, "an unapplied modifier logged the dish anyway"

    run(scenario())


def test_a_prompt_never_swallows_a_message_meant_as_food(harness):
    """The gate declines anything a numeric prompt cannot use, so an open
    prompt does not turn the next meal into an error."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM body_metric WHERE user_id = $1", uid)

        await harness.feed("/weight")
        harness.sent.clear()
        # Not a number, so it is still a meal.
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        assert harness.llm.calls[-1] == "record_meal", harness.llm.calls
        assert [b for b in harness.sent.last().buttons if b.startswith("ok:")]

    run(scenario())


def test_the_newest_prompt_is_the_one_being_answered(harness):
    """Two prompts open at once: the later one is what you are replying to.

    Both are opened by buttons rather than commands, since a command now
    cancels anything outstanding.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM body_metric WHERE user_id = $1", uid)

        await harness.feed("/weight")
        weight_card = harness.sent.last()

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        meal_card = harness.sent.last()
        await harness.press(f"fix:{_confirm_id(meal_card)}", meal_card.message_id)

        # Newer prompt, opened without a command in between.
        await harness.press("wnew:", weight_card.message_id)

        harness.sent.clear()
        await harness.feed("78")
        assert "78 kg" in harness.sent.last().text, harness.sent.texts()
        assert float(
            await p.fetchval("SELECT value FROM body_metric WHERE user_id=$1", uid)
        ) == pytest.approx(78.0)

    run(scenario())


def test_a_command_cancels_an_outstanding_prompt(harness):
    """Tap /supp add, change your mind, send a meal — and without this the meal
    is parsed as a supplement panel: expensively, and wrongly."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("/supp add")
        # A command means you moved on.
        await harness.feed("/today")

        harness.sent.clear()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        assert harness.llm.calls[-1] == "record_meal", harness.llm.calls
        assert [b for b in harness.sent.last().buttons if b.startswith("ok:")]

        p = await db.pool()
        assert await p.fetchval(
            "SELECT count(*) FROM pending_action WHERE user_id=$1 AND kind='supp_label'",
            uid,
        ) == 0

    run(scenario())


def test_profile_reads_sets_and_refuses_nonsense(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute(
            """UPDATE app_user SET sex=NULL, birth_date=NULL, height_cm=NULL,
                 activity_factor=NULL, deficit_kcal=NULL WHERE id=$1""", uid)

        await harness.feed("/profile")
        card = harness.sent.last()
        assert "Your profile" in card.text
        # A target exists (bootstrap seeded one) but nothing records what it
        # came from, and the card has to say so rather than look complete.
        assert "1." in card.text
        assert "sex" in card.text and "height" in card.text

        # A refused value changes nothing, rather than storing a plausible zero.
        harness.sent.clear()
        await harness.feed("/profile 4 twelve")
        assert "❌" in harness.sent.last().text
        assert await p.fetchval("SELECT height_cm FROM app_user WHERE id=$1", uid) is None

        await harness.feed("/profile 4 400")   # out of range
        assert "❌" in harness.sent.last().text
        assert await p.fetchval("SELECT height_cm FROM app_user WHERE id=$1", uid) is None

        await harness.feed("/profile 4 183")
        assert float(await p.fetchval(
            "SELECT height_cm FROM app_user WHERE id=$1", uid)) == 183.0

    run(scenario())


def test_recalculating_targets_needs_a_complete_profile_and_versions_them(harness):
    """Invariant 3: the old row is closed, never updated. /yesterday must keep
    saying what it said."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute(
            """UPDATE app_user SET sex=NULL, height_cm=NULL, measured_tdee_kcal=NULL
                WHERE id=$1""", uid)
        await harness.feed("/profile")
        card = harness.sent.last()

        harness.sent.clear()
        await harness.press("precalc:", card.message_id)
        assert "Cannot compute" in harness.sent.last().text, harness.sent.texts()

        await harness.feed("/profile 2 male")
        await harness.feed("/profile 3 1991-03-02")
        await harness.feed("/profile 4 183")
        await harness.feed("/profile 5 1.55")
        await harness.feed("/profile 8 500")
        await harness.feed("/weight 78")

        harness.sent.clear()
        await harness.press("precalc:", card.message_id)
        assert "recalculated" in harness.sent.last().text.lower(), harness.sent.texts()

        after = await p.fetchrow(
            """SELECT max_amount, rationale FROM target
                WHERE user_id=$1 AND nutrient_id=1008 AND effective_to IS NULL""", uid)
        assert after["rationale"] == "profile recalculation"

        # It matches the shared derivation rather than merely being different:
        # the test user happens to be bootstrapped with these same numbers, so
        # "the figure changed" would pass for the wrong reason.
        from nutrai.core import profile as prof
        expected, _w = prof.derive_targets(
            sex="male", weight_kg=78.0, height_cm=183.0,
            age=prof.age_years(dt.date(1991, 3, 2)), activity=1.55, deficit=500.0,
        )
        assert float(after["max_amount"]) == expected[1008][1]
        # The superseded row still exists, closed rather than deleted.
        assert await p.fetchval(
            """SELECT count(*) FROM target
                WHERE user_id=$1 AND nutrient_id=1008 AND effective_to IS NOT NULL""",
            uid) >= 1

    run(scenario())


def test_profile_lines_after_the_card_do_not_reach_the_food_parser(harness):
    """The routing branch was silently missing: the card said "reply 2. male",
    the reply went to the meal parser, and it cost a model call to be told
    "No match in the food database for: No meal provided".

    The unit tests covered _profile_edits and the validators directly and
    passed the whole time, because neither of them is what was broken.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute(
            """UPDATE app_user SET sex=NULL, birth_date=NULL, height_cm=NULL,
                 activity_factor=NULL, goal=NULL WHERE id=$1""", uid)

        await harness.feed("/profile")
        harness.llm.calls.clear()
        harness.sent.clear()

        await harness.feed("2. M\n3. 21/09/1991\n4. 173cm\n5. Moderate\n"
                           "6. Muscle gain and fat loss")

        assert not harness.llm.calls, f"a model was called: {harness.llm.calls}"
        reply = harness.sent.last().text
        assert "No match in the food database" not in reply, reply

        row = await p.fetchrow(
            """SELECT sex, birth_date, height_cm, activity_factor, goal
                 FROM app_user WHERE id=$1""", uid)
        assert row["sex"] == "male"
        assert row["birth_date"] == dt.date(1991, 9, 21)
        assert float(row["height_cm"]) == 173.0
        assert float(row["activity_factor"]) == 1.55        # "Moderate"
        assert row["goal"] == "recomp"                      # not lose, not gain

        # The prompt stays open: a profile is filled in over several messages.
        await harness.feed("8. 400")
        assert float(await p.fetchval(
            "SELECT deficit_kcal FROM app_user WHERE id=$1", uid)) == 400.0

        # But a meal still gets through while it is open.
        harness.sent.clear()
        await harness.feed("250 g minced beef, 164 g rice")
        assert harness.llm.calls, "the meal was swallowed by the profile prompt"

    run(scenario())


def test_replying_to_the_target_list_sets_a_target(harness):
    """Third time a card taught one syntax and refused the obvious reply.
    After reading a list of targets, "Alcohol 0g" is what a person sends."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await harness.feed("/target")
        harness.llm.calls.clear()
        harness.sent.clear()

        await harness.feed("Alcohol 0g")
        assert not harness.llm.calls, harness.llm.calls
        reply = harness.sent.last().text
        assert "ceiling" in reply, reply

        row = await p.fetchrow(
            """SELECT min_amount, max_amount, rationale FROM target
                WHERE user_id=$1 AND nutrient_id=1018 AND effective_to IS NULL""", uid)
        # A ceiling, not a floor: the standing target was a ceiling of 16 g and
        # reading "0" as a minimum would invert the meaning entirely.
        assert row["min_amount"] is None
        assert float(row["max_amount"]) == 0.0
        assert row["rationale"] == "manual"

        # A meal still gets through while the prompt is open.
        harness.sent.clear()
        await harness.feed("250 g minced beef, 164 g rice")
        assert harness.llm.calls, "the meal was swallowed by the target prompt"

    run(scenario())


def test_a_bare_number_follows_the_bound_already_there(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await harness.feed("/target")
        await harness.feed("Fibre 45")     # standing target is a minimum
        row = await p.fetchrow(
            """SELECT min_amount, max_amount FROM target
                WHERE user_id=$1 AND nutrient_id=1079 AND effective_to IS NULL""", uid)
        assert float(row["min_amount"]) == 45.0
        assert row["max_amount"] is None

    run(scenario())


def test_a_forwarded_session_can_be_removed_from_telegram(harness):
    """A bad forward used to need a psql prompt to undo — the same blind spot
    as the missing sync line, one layer down."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        day = dt.date.today()
        act_id = await p.fetchval(
            """INSERT INTO activity (user_id, local_date, kind, minutes, intensity, rpe)
               VALUES ($1,$2,'lifting',96,'hard',9.2) RETURNING id""", uid, day)

        harness.sent.clear()
        await harness.feed("/training")
        card = harness.sent.last()
        assert "hard" in card.text and "effort 9.2/10" in card.text
        assert [b for b in card.buttons if b.startswith("actdel:")], card.buttons

        # Asking first: a delete cannot be taken back.
        await harness.press(f"actdel:{act_id}", card.message_id)
        assert "Remove this session?" in harness.sent.last().text
        assert await db.activity_by_id(uid, act_id) is not None, "deleted before confirming"

        await harness.press(f"actdel!:{act_id}", harness.sent.last().message_id)
        assert await db.activity_by_id(uid, act_id) is None

        harness.sent.clear()
        await harness.feed("/training")
        assert "nothing logged yet" in harness.sent.last().text

    run(scenario())


def test_keeping_a_session_removes_nothing(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        act_id = await p.fetchval(
            """INSERT INTO activity (user_id, local_date, kind, minutes)
               VALUES ($1,$2,'cycling',45) RETURNING id""", uid, dt.date.today())
        await harness.feed("/training")
        card = harness.sent.last()
        await harness.press(f"actdel:{act_id}", card.message_id)
        await harness.press("actkeep:", harness.sent.last().message_id)
        assert await db.activity_by_id(uid, act_id) is not None
        await p.execute("DELETE FROM activity WHERE id=$1", act_id)

    run(scenario())


def test_another_users_session_cannot_be_deleted_by_id(harness):
    """The id arrives in callback data, which the client controls."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        other = await p.fetchval(
            """INSERT INTO app_user (telegram_id, tz) VALUES (999000111, 'UTC')
               ON CONFLICT (telegram_id) DO UPDATE SET tz='UTC' RETURNING id""")
        victim = await p.fetchval(
            """INSERT INTO activity (user_id, local_date, kind, minutes)
               VALUES ($1,$2,'lifting',60) RETURNING id""", other, dt.date.today())

        assert await db.activity_by_id(uid, victim) is None
        assert await db.delete_activity(uid, victim) is False
        assert await p.fetchval("SELECT 1 FROM activity WHERE id=$1", victim) == 1
        await p.execute("DELETE FROM activity WHERE id=$1", victim)
        await p.execute("DELETE FROM app_user WHERE id=$1", other)

    run(scenario())


def test_a_supplement_is_stopped_not_deleted(harness):
    """supplement_log references supplement ON DELETE CASCADE, so deleting one
    would erase the record of every day it was taken. Stopping is a fact about
    the future; it does not make the past untrue."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        sid = await p.fetchval(
            """INSERT INTO supplement (user_id, name, serving_desc, servings_per_day, source)
               VALUES ($1,'Test Boron','1 capsule',1,'label_photo') RETURNING id""", uid)
        day = dt.date.today()
        await p.execute(
            """INSERT INTO supplement_log (user_id, supplement_id, local_date, servings)
               VALUES ($1,$2,$3,1)""", uid, sid, day)

        harness.sent.clear()
        await harness.feed("/supp list")
        card = harness.sent.last()
        assert "Test Boron" in card.text
        assert [b for b in card.buttons if b.startswith("suppoff:")], card.buttons

        await harness.press(f"suppoff:{sid}", card.message_id)
        assert "Stop taking" in harness.sent.last().text
        assert (await db.supplement_by_id(uid, sid))["active"] is True, "stopped before confirming"

        await harness.press(f"suppoff!:{sid}", harness.sent.last().message_id)
        assert (await db.supplement_by_id(uid, sid))["active"] is False

        # The history survives. That is the whole reason this is not a DELETE.
        assert await p.fetchval(
            "SELECT count(*) FROM supplement_log WHERE supplement_id=$1", sid) == 1

        # Gone from the daily stack, still named on the list as stopped.
        assert sid not in [r["id"] for r in await db.supplement_stack(uid)]
        harness.sent.clear()
        await harness.feed("/supp list")
        assert "Stopped:" in harness.sent.last().text

        # And restorable.
        await harness.press(f"suppon:{sid}", harness.sent.last().message_id)
        assert (await db.supplement_by_id(uid, sid))["active"] is True

        await p.execute("DELETE FROM supplement_log WHERE supplement_id=$1", sid)
        await p.execute("DELETE FROM supplement WHERE id=$1", sid)

    run(scenario())


def test_supplement_slots_and_reminders(harness):
    """Three or four moments a day, each nudged once at its own local time."""

    async def scenario():
        uid = await _reset()
        from nutrai import db
        from nutrai.jobs import notify

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)
        ids = {}
        for name in ("Magnesium", "Boron"):
            ids[name] = await p.fetchval(
                """INSERT INTO supplement (user_id, name, serving_desc, servings_per_day, source)
                   VALUES ($1,$2,'1 capsule',1,'label_photo') RETURNING id""", uid, name)

        await harness.feed("/supp times")
        assert "Supplement times" in harness.sent.last().text

        # Numbered lines for the assignment, a bare slot and time for the clock.
        harness.sent.clear()
        await harness.feed("1. bed\n2. breakfast\nbed 22:00\nbreakfast 08:30")
        reply = harness.sent.last().text
        assert "before sleeping" in reply and "22:00" in reply

        # The card lists alphabetically, so line 1 is Boron — the numbers name
        # rows on the screen, not the order they were created in.
        rows = await db.supplements_in_slot(uid, "bed", dt.date.today())
        assert [r["name"] for r in rows] == ["Boron"]
        assert [r["name"] for r in
                await db.supplements_in_slot(uid, "breakfast", dt.date.today())] == ["Magnesium"]
        assert (await db.slot_times(uid))["bed"] == dt.time(22, 0)

        # Nothing fires before a moment's time. Anchored to the clock rather
        # than to a fixed hour: with "bed 22:00" hardcoded this passed all
        # afternoon and failed at 22:05, because the reminder was correct and
        # the test was not.
        import zoneinfo

        local = dt.datetime.now(dt.timezone.utc).astimezone(zoneinfo.ZoneInfo("Europe/Warsaw"))
        later = (local + dt.timedelta(hours=2)).time().replace(second=0, microsecond=0)
        await db.set_slot_time(uid, "bed", later)
        await p.execute("DELETE FROM supplement_reminder_log WHERE user_id=$1", uid)

        harness.sent.clear()
        await notify.supplement_reminders(harness.tg.bot)
        assert not [x for x in harness.sent.sent if "before sleeping" in x.text], \
            "a reminder fired before its time"

        await p.execute("DELETE FROM supplement_reminder_log WHERE user_id=$1", uid)
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)

    run(scenario())


def test_a_reminder_fires_once_and_only_when_something_is_outstanding(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)
        sid = await p.fetchval(
            """INSERT INTO supplement (user_id, name, serving_desc, servings_per_day, source, slot)
               VALUES ($1,'Magnesium','1 capsule',1,'label_photo','bed') RETURNING id""", uid)
        day = dt.date.today()

        # The once-per-day record is what makes a ten-minute sweep safe.
        assert await db.mark_reminder_sent(uid, "bed", day) is True
        assert await db.mark_reminder_sent(uid, "bed", day) is False
        assert await db.reminder_already_sent(uid, "bed", day) is True

        rows = await db.supplements_in_slot(uid, "bed", day)
        assert rows and rows[0]["logged"] is False
        await db.log_supplements(uid, day, [sid])
        rows = await db.supplements_in_slot(uid, "bed", day)
        assert rows[0]["logged"] is True, "a logged dose must stop the nudge"

        await p.execute("DELETE FROM supplement_reminder_log WHERE user_id=$1", uid)
        await p.execute("DELETE FROM supplement_log WHERE user_id=$1", uid)
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)

    run(scenario())


def test_the_deficit_warning_carries_a_button_that_fixes_it(harness):
    """The card knew the goal needed a deficit, knew the usual range, and
    still asked you to retype it — the same friction as every prompt that
    taught a syntax instead of doing the thing."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute(
            """UPDATE app_user SET sex='male', birth_date='1991-09-21', height_cm=173,
                 activity_factor=1.55, goal='recomp', deficit_kcal=NULL WHERE id=$1""", uid)
        await p.execute("DELETE FROM body_metric WHERE user_id=$1", uid)
        await harness.feed("/weight 75.2")

        await harness.feed("/profile")
        card = harness.sent.last()
        harness.sent.clear()
        await harness.press("precalc:", card.message_id)

        recalc = harness.sent.last()
        assert "⚠️" in recalc.text and "maintenance" in recalc.text
        btn = next(b for b in recalc.buttons if b.startswith("setdef:"))

        maintenance = await p.fetchval(
            """SELECT max_amount FROM target
                WHERE user_id=$1 AND nutrient_id=1008 AND effective_to IS NULL""", uid)

        harness.sent.clear()
        await harness.press(btn, recalc.message_id)

        assert float(await p.fetchval(
            "SELECT deficit_kcal FROM app_user WHERE id=$1", uid)) == 350.0
        after = await p.fetchval(
            """SELECT max_amount FROM target
                WHERE user_id=$1 AND nutrient_id=1008 AND effective_to IS NULL""", uid)
        assert float(maintenance) - float(after) == 350.0
        # And the warning is gone, because the contradiction is.
        assert "⚠️" not in harness.sent.last().text, harness.sent.last().text

    run(scenario())


def test_a_measured_tdee_can_be_adopted_from_insight(harness):
    """Seeded, not waited for. CLAUDE.md forbids lowering MIN_TREND_DAYS to
    make the feature work during development; this fakes the data instead.

    The gap this closes: fat_loss_rate() has always computed the TDEE your
    body actually has, and the energy target went on being an equation's guess
    times a multiplier picked off a list. The two numbers never met.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute(
            """UPDATE app_user SET sex='male', birth_date='1991-09-21', height_cm=173,
                 activity_factor=1.55, goal='recomp', deficit_kcal=350,
                 measured_tdee_kcal=NULL WHERE id=$1""", uid)
        await p.execute("DELETE FROM body_metric WHERE user_id=$1", uid)

        # 24 days losing ~0.35 kg/week, on a steady 2,100 kcal.
        start = dt.date.today() - dt.timedelta(days=23)
        for i in range(24):
            kg = 76.4 - 0.05 * i
            await p.execute(
                """INSERT INTO body_metric (user_id, kind, value, local_date, measured_at)
                   VALUES ($1,'weight_kg',$2,$3,$4)""",
                uid, kg, start + dt.timedelta(days=i),
                dt.datetime.combine(start + dt.timedelta(days=i), dt.time(7, 0),
                                    tzinfo=dt.timezone.utc))

        from nutrai.core import insight

        # A weight trend with no intake alongside it yields no TDEE: the
        # measurement is intake plus deficit, and one of those is missing.
        # Nothing is offered, rather than an offer built on a zero.
        harness.sent.clear()
        await harness.feed("/insight")
        assert "measured maintenance" not in harness.sent.last().text
        assert not [b for s_ in harness.sent.sent for b in s_.buttons
                    if b.startswith("usetdee:")]

        # Now the intake those weights were produced by.
        for i in range(24):
            d = start + dt.timedelta(days=i)
            eid = await p.fetchval(
                """INSERT INTO log_entry
                     (user_id, logged_at, local_date, name, source, status)
                   VALUES ($1,$2,$3,'seeded day','manual','confirmed') RETURNING id""",
                uid, dt.datetime.combine(d, dt.time(12, 0), tzinfo=dt.timezone.utc), d)
            await p.execute(
                """INSERT INTO log_nutrient (entry_id, nutrient_id, amount)
                   VALUES ($1, 1008, 2100)""", eid)

        weights = await db.weight_series(uid, 42)
        flr = insight.fat_loss_rate(weights, await db.daily_energy(uid, 42))
        assert flr and flr.days >= 14 and flr.implied_tdee_kcal > 0, flr

        harness.sent.clear()
        await harness.feed("/insight")
        offer = harness.sent.last()
        assert "measured maintenance" in offer.text, offer.text
        btn = next(b for b in offer.buttons if b.startswith("usetdee:"))

        harness.sent.clear()
        await harness.press(btn, offer.message_id)

        row = await p.fetchrow(
            """SELECT measured_tdee_kcal, measured_tdee_days, activity_factor
                 FROM app_user WHERE id=$1""", uid)
        assert row["measured_tdee_kcal"] is not None
        assert row["measured_tdee_days"] == flr.days
        # The factor is written back, so a later recalculation after a weight
        # change does not quietly revert to the one picked off a list.
        assert float(row["activity_factor"]) != 1.55

        target = float(await p.fetchval(
            """SELECT max_amount FROM target
                WHERE user_id=$1 AND nutrient_id=1008 AND effective_to IS NULL""", uid))
        assert abs(target - (float(row["measured_tdee_kcal"]) - 350)) < 1

        # And the card says which of the two it now rests on.
        harness.sent.clear()
        await harness.feed("/profile")
        assert "measured" in harness.sent.last().text

        await p.execute("DELETE FROM body_metric WHERE user_id=$1", uid)
        await p.execute(
            "DELETE FROM log_entry WHERE user_id=$1 AND name='seeded day'", uid)
        # Adopting a measurement is sticky by design — it must survive later
        # recalculations — so a test that adopts one has to put it back.
        await db.clear_measured_tdee(uid)

    run(scenario())


def test_a_supplement_with_a_future_start_date_is_not_due_yet(harness):
    """"Vitamin D3 + K2 — after breakfast, from 1 October" is a decision, not a
    dose. Pre-ticking it in August would put a capsule you did not swallow into
    the day's totals."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)
        now_id = await p.fetchval(
            """INSERT INTO supplement (user_id, name, serving_desc, servings_per_day,
                 source, slot) VALUES ($1,'Creatine','1 scoop',1,'label_photo','breakfast')
               RETURNING id""", uid)
        later_id = await p.fetchval(
            """INSERT INTO supplement (user_id, name, serving_desc, servings_per_day,
                 source, slot, starts_on)
               VALUES ($1,'Vitamin D3 + K2','1 capsule',1,'manual','breakfast',$2)
               RETURNING id""", uid, dt.date.today() + dt.timedelta(days=46))

        due = await db.supplements_due(uid, dt.date.today())
        assert now_id in due
        assert later_id not in due, "a supplement that has not started was pre-ticked"

        # And it is not in the moment's reminder either.
        rows = await db.supplements_in_slot(uid, "breakfast", dt.date.today())
        assert [r["id"] for r in rows] == [now_id]

        # It becomes due on the day it starts.
        assert later_id in await db.supplements_due(
            uid, dt.date.today() + dt.timedelta(days=46))

        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)

    run(scenario())


def test_why_attributes_a_nutrient_to_meals_and_ingredients(harness):
    """"250% of your cholesterol ceiling" is a fact about a number. Without an
    answer to which plate and which thing on it, a breach is something that
    happens to you rather than something you did."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        day = dt.date.today()
        rows = await db.nutrient_attribution(uid, day, 1004)   # fat
        assert rows, "nothing attributed"

        # The parts sum to the stored snapshot, not to whatever current USDA
        # rows happen to say today.
        for e in rows:
            stored = await p.fetchval(
                """SELECT ln.amount FROM log_nutrient ln JOIN log_entry le ON le.id=ln.entry_id
                    WHERE le.user_id=$1 AND le.local_date=$2 AND ln.nutrient_id=1004
                      AND le.name=$3""", uid, day, e["name"])
            assert abs(float(stored) - e["amount"]) < 0.01
            if e["parts"]:
                assert abs(sum(x["amount"] for x in e["parts"]) - e["amount"]) < 0.01

        harness.sent.clear()
        await harness.feed("/why fat")
        out = harness.sent.last().text
        assert "Fat" in out and "minced beef" in out.lower() or "beef" in out.lower()

        # A name the card shows, not only the one USDA stores.
        harness.sent.clear()
        await harness.feed("/why fibre")
        assert "Fibre" in harness.sent.last().text

    run(scenario())


def test_the_clock_decides_the_meal_slot_not_the_model():
    """A chia seed pudding eaten at 16:11 came back "breakfast", because the
    tool schema offered the enum with no description and no time of day, so the
    model classified by dish type."""
    from nutrai.core.dsl import slot_for_hour

    assert slot_for_hour(8) == "breakfast"
    assert slot_for_hour(13) == "lunch"
    assert slot_for_hour(16) == "snack"
    assert slot_for_hour(19) == "dinner"
    assert slot_for_hour(23) == "snack"
    # The model said breakfast about a 16:11 pudding; the clock overrules it.
    assert slot_for_hour(16, "breakfast") == "snack"
    # "drink" is a fact about the thing, not about the hour, so it survives.
    assert slot_for_hour(16, "drink") == "drink"


def test_why_on_its_own_asks_and_then_listens(harness):
    """The seventh instance of a command printing instructions and feeding the
    reply to the meal parser. The registry is the structural fix; this is the
    behaviour it buys."""

    async def scenario():
        uid = await _reset()

        await harness.feed("250 g minced beef, 164 g rice")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        harness.sent.clear()
        await harness.feed("/why")
        assert "Which nutrient" in harness.sent.last().text

        harness.llm.calls.clear()
        harness.sent.clear()
        await harness.feed("fat")
        assert not harness.llm.calls, f"the answer went to the parser: {harness.llm.calls}"
        assert "Fat" in harness.sent.last().text

        # A word that is not a nutrient still reaches the meal parser.
        await harness.feed("/why")
        harness.llm.calls.clear()
        harness.sent.clear()
        await harness.feed("a bowl of porridge with berries")
        assert harness.llm.calls, "a meal was swallowed by the why prompt"

    run(scenario())


def test_food_lists_and_then_listens(harness):
    """The eighth instance: /food printed "/food new pickle juice" and then
    sent the reply to the meal parser, which matched "juice" at 51 kcal.

    A registry stops a prompt going unconsumed. It cannot stop a card
    instructing without opening one at all — that is what this covers.
    """

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM food WHERE owner_user_id=$1", uid)

        harness.sent.clear()
        await harness.feed("/food")
        assert "Reply with a name" in harness.sent.last().text

        harness.llm.calls.clear()
        harness.sent.clear()
        await harness.feed("pickle juice")
        assert not harness.llm.calls, f"the name went to the parser: {harness.llm.calls}"
        assert "What goes into it" in harness.sent.last().text

        # And the escape hatch, because a name and a meal are the same string.
        assert [b for b in harness.sent.last().buttons if b.startswith("foodmeal:")]

    run(scenario())


def test_a_user_food_is_built_by_arithmetic_and_outranks_usda(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM food WHERE owner_user_id=$1", uid)
        fdc = await db.create_user_food(uid, "pickle brine", {1008: 1.0, 1093: 1050.0})

        assert fdc < 0, "user foods take negative ids so they cannot collide"
        row = await p.fetchrow(
            "SELECT data_type, precedence, owner_user_id FROM food WHERE fdc_id=$1", fdc)
        assert row["data_type"] == "user_product"
        assert row["precedence"] == 0, "your own row must outrank USDA's generic one"

        # Findable by you...
        hits = await db.search_foods("pickle brine", user_id=uid)
        assert fdc in [h["fdc_id"] for h in hits]
        # ...and invisible to anyone else.
        other = await p.fetchval(
            """INSERT INTO app_user (telegram_id, tz) VALUES (999000222,'UTC')
               ON CONFLICT (telegram_id) DO UPDATE SET tz='UTC' RETURNING id""")
        assert fdc not in [h["fdc_id"] for h in
                           await db.search_foods("pickle brine", user_id=other)]

        await p.execute("DELETE FROM food WHERE owner_user_id=$1", uid)
        await p.execute("DELETE FROM app_user WHERE id=$1", other)

    run(scenario())


def test_a_weak_match_offers_to_define_the_food(harness):
    """USDA has no pickle brine, so "pickle juice" matched "Relish, pickle" at
    0.35 — the top of a list that never contained the right answer. A weak best
    match is a missing food, not a mistaken choice, and the moment it shows is
    the only moment you know the database is short something."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM food WHERE owner_user_id=$1", uid)
        await p.execute("DELETE FROM food_alias WHERE user_id=$1", uid)

        harness.llm.meal = {
            "dish_name": "Pickle juice", "confidence": 0.85, "notes": "",
            "items": [{"label": "pickle juice", "search_terms": "pickle juice",
                       "grams": 100, "grams_source": "stated", "state": "as_logged",
                       "confidence": 0.85}],
        }
        harness.sent.clear()
        await harness.feed("100 ml of pickle juice")
        card = harness.sent.last()

        assert "Nothing in the food database is much like" in card.text, card.text
        define = next(b for b in card.buttons if b.startswith("deffood:"))

        # And it survives the discard, which is the strongest signal of all.
        await harness.press(f"no:{_confirm_id(card)}", card.message_id)
        assert [b for b in harness.sent.last().buttons if b.startswith("deffood:")]

        # Tapping it goes straight into /food with the name filled in.
        harness.sent.clear()
        await harness.press(define, card.message_id)
        assert "Making a food called" in harness.sent.last().text
        assert "pickle juice" in harness.sent.last().text

        harness.llm.calls.clear()
        await harness.feed("1000 ml water, 30 g salt")
        assert await p.fetchval(
            "SELECT count(*) FROM food WHERE owner_user_id=$1", uid) == 1

        # Through the real delete, which also clears the alias pointing at it.
        for f in await db.user_foods(uid):
            assert await db.delete_user_food(uid, f["fdc_id"])

    run(scenario())


def test_the_time_of_a_new_entry_can_be_corrected(harness):
    """Logging happens when you get round to it, not when you eat — and the
    fasting window, the caffeine-after-noon covariate and every sleep
    correlation read the timestamp, so a meal filed an hour late is a small
    error in four places at once."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await harness.feed("250 g minced beef, 164 g rice")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        assert [b for b in card.buttons if b.startswith("when:")], card.buttons

        harness.sent.clear()
        await harness.press(f"when:{entry_id}", card.message_id)
        assert "When did you have it" in harness.sent.last().text

        harness.llm.calls.clear()
        await harness.feed("08:30")
        assert not harness.llm.calls, "the time went to the meal parser"

        import zoneinfo
        row = await p.fetchrow(
            "SELECT logged_at, local_date FROM log_entry WHERE id=$1", entry_id)
        local = row["logged_at"].astimezone(zoneinfo.ZoneInfo("Europe/Warsaw"))
        assert (local.hour, local.minute) == (8, 30), local

        # A reply that is not a time is still a meal.
        await harness.press(f"when:{entry_id}", card.message_id)
        harness.llm.calls.clear()
        await harness.feed("a bowl of porridge")
        assert harness.llm.calls, "a meal was swallowed by the time prompt"

    run(scenario())


def test_a_time_is_never_moved_forwards(harness):
    """23:40 typed at 00:10 means last night. You cannot have eaten something
    you have not eaten."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await harness.feed("250 g minced beef, 164 g rice")
        card = harness.sent.last()
        entry_id = _confirm_id(card)
        await harness.press(f"when:{entry_id}", card.message_id)

        import zoneinfo
        now = dt.datetime.now(dt.timezone.utc).astimezone(
            zoneinfo.ZoneInfo("Europe/Warsaw"))
        ahead = (now + dt.timedelta(hours=3)).strftime("%H:%M")
        await harness.feed(ahead)

        moved = (await p.fetchrow(
            "SELECT logged_at FROM log_entry WHERE id=$1", entry_id))["logged_at"]
        assert moved < dt.datetime.now(dt.timezone.utc), moved

    run(scenario())


def test_a_supplement_that_has_not_started_cannot_be_logged(harness):
    """starts_on was honoured only where things are pre-ticked, so a product
    dated to October could be ticked by hand in August — and it contributed
    nothing, because a product you have not begun has no panel read off it."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)
        later = await p.fetchval(
            """INSERT INTO supplement (user_id, name, serving_desc, servings_per_day,
                 source, slot, starts_on)
               VALUES ($1,'Vitamin D3 + K2','1 drop',1,'manual','breakfast',$2)
               RETURNING id""", uid, dt.date.today() + dt.timedelta(days=45))
        day = dt.date.today()

        # Not in the daily picker...
        assert later not in [s_["id"] for s_ in
                             await db.supplement_stack(uid, on_day=day)]
        # ...but visible in /stack, which is where you check what is coming.
        assert later in [s_["id"] for s_ in await db.supplement_stack(uid)]

        # And refused even when named directly.
        assert await db.log_supplements(uid, day, [later]) == 0
        assert await p.fetchval(
            "SELECT count(*) FROM supplement_log WHERE supplement_id=$1", later) == 0

        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)

    run(scenario())


def test_repeat_offers_single_foods_as_well_as_dishes(harness):
    """A plate of six things becomes one dish you will never eat again in that
    combination, while the parts you do repeat sit inside it unreachable."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        harness.sent.clear()
        await harness.feed("/repeat")
        menu = harness.sent.last()
        assert "Or one thing" in menu.text, menu.text

        pending = await db.latest_pending(uid, "repeat_menu")
        n_dishes = len(pending["ids"])
        assert pending["components"], "no single foods offered"

        # The first number past the dish list logs one food on its own.
        harness.llm.calls.clear()
        harness.sent.clear()
        await harness.feed(str(n_dishes + 1))
        assert not harness.llm.calls, "a repeat cost a model call"
        one = harness.sent.last()
        assert [b for b in one.buttons if b.startswith("ok:")], one.buttons

        entry_id = _confirm_id(one)
        comps = await p.fetch(
            "SELECT label, grams, grams_source FROM log_component WHERE entry_id=$1", entry_id)
        assert len(comps) == 1, comps
        # A median of estimates is a prior, never something you stated.
        assert comps[0]["grams_source"] in ("stated", "prior")

    run(scenario())


def test_a_single_food_repeat_takes_a_modifier(harness):
    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)
        await harness.feed("/repeat")
        pending = await db.latest_pending(uid, "repeat_menu")
        n = len(pending["ids"]) + 1
        base = pending["components"][0]["grams"]

        harness.sent.clear()
        await harness.feed(f"{n} x2")
        p = await db.pool()
        grams = await p.fetchval(
            """SELECT lc.grams FROM log_component lc
                WHERE lc.entry_id = (SELECT max(id) FROM log_entry WHERE user_id=$1)""", uid)
        assert float(grams) == base * 2

    run(scenario())


def test_why_takes_several_nutrients_at_once(harness):
    """"fat and sodium" is one reply about two nutrients. It used to reach the
    meal parser, which paid for a model call to report "No match in the food
    database for: Unknown meal"."""

    async def scenario():
        uid = await _reset()

        await harness.feed("250 g minced beef, 164 g rice")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        await harness.feed("/why")
        harness.llm.calls.clear()
        harness.sent.clear()
        await harness.feed("fat and sodium")

        assert not harness.llm.calls, f"a model was called: {harness.llm.calls}"
        texts = harness.sent.texts()
        assert any("Fat" in t for t in texts), texts
        assert any("Sodium" in t for t in texts), texts

        # Commas and ampersands too.
        await harness.feed("/why")
        harness.sent.clear()
        await harness.feed("iron, calcium")
        assert len(harness.sent.sent) == 2

    run(scenario())


def test_a_meal_naming_one_nutrient_is_still_a_meal(harness):
    """All-or-nothing: a reply where one word is a nutrient and the rest is
    dinner is dinner. Answering the half that resolved would log nothing while
    looking like it had done something."""

    async def scenario():
        await _reset()
        await harness.feed("/why")
        harness.llm.calls.clear()
        harness.sent.clear()
        await harness.feed("chicken and rice")
        assert harness.llm.calls, "a meal was swallowed by the why prompt"

    run(scenario())


def test_why_offers_the_worst_ceilings_as_buttons(harness):
    """Nine times in ten you open /why to ask about something that is over,
    and typing the name is the slow way to say so."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute(
            """UPDATE target SET max_amount = 1 WHERE user_id=$1
                AND nutrient_id=1093 AND effective_to IS NULL""", uid)
        await harness.feed("250 g minced beef, 164 g rice")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        harness.sent.clear()
        await harness.feed("/why")
        ask = harness.sent.last()
        btns = [b for b in ask.buttons if b.startswith("whyn:")]
        assert btns, ask.buttons

        harness.llm.calls.clear()
        harness.sent.clear()
        await harness.press(btns[0], ask.message_id)
        assert not harness.llm.calls
        assert "Sodium" in harness.sent.last().text, harness.sent.texts()

    run(scenario())


def test_a_rating_can_carry_a_note(harness):
    """"sleep 4" is a number. A 4 from a late coffee, a 4 from a noisy street
    and a 4 from illness are three observations the permutation test sees as
    one — the note is the part it cannot recover."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        harness.sent.clear()
        await harness.feed("/rate sleep 4")
        card = harness.sent.last()
        btn = next(b for b in card.buttons if b.startswith("ratenote:"))

        await harness.press(btn, card.message_id)
        assert "What was going on" in harness.sent.last().text

        harness.llm.calls.clear()
        await harness.feed("woke at 3 and could not get back down")
        assert not harness.llm.calls, "the note went to the meal parser"

        note = await p.fetchval(
            """SELECT note FROM observation WHERE user_id=$1 AND kind='sleep'
             ORDER BY id DESC LIMIT 1""", uid)
        assert note == "woke at 3 and could not get back down"

        # And it reaches the weekly review.
        notes = await db.rating_notes(uid)
        assert any(n["note"] == note for n in notes)

    run(scenario())


def test_a_black_coffee_does_not_break_a_fast(harness):
    """Every confirmed entry used to reset the clock, whatever was in it — and
    hours_fasted is stamped onto every rating at the moment it is made, so a
    6 kcal lemon water was corrupting the fasting correlations rather than
    merely mis-stating a card."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        now = dt.datetime.now(dt.timezone.utc)
        # (hours ago, name, carbs g, protein g). Energy is deliberately not
        # the variable: a spoon of butter is 120 kcal and breaks nothing.
        for hours_ago, name, carbs, protein in (
            (10, "Dinner", 60.0, 40.0),
            (2, "Black coffee", 0.1, 0.1),
        ):
            eid = await p.fetchval(
                """INSERT INTO log_entry (user_id, logged_at, local_date, name,
                     source, status) VALUES ($1,$2,$3,$4,'text','confirmed')
                   RETURNING id""",
                uid, now - dt.timedelta(hours=hours_ago), dt.date.today(), name)
            await p.executemany(
                "INSERT INTO log_nutrient (entry_id, nutrient_id, amount) VALUES ($1,$2,$3)",
                [(eid, 1005, carbs), (eid, 1003, protein)])

        hours = float(await db.current_fast_hours(uid))
        assert hours > 9, f"the coffee reset the clock: {hours:.1f}h"

        # Raise the bar and the coffee still does not count; lower it and it does.
        await p.execute("UPDATE app_user SET fast_break_kcal=1, fast_break_carb_g=0.05, fast_break_protein_g=0.05 WHERE id=$1", uid)
        assert float(await db.current_fast_hours(uid)) < 3

        await p.execute("UPDATE app_user SET fast_break_kcal=50, fast_break_carb_g=5, fast_break_protein_g=2 WHERE id=$1", uid)
        await p.execute("DELETE FROM log_entry WHERE user_id=$1 AND name IN ('Dinner','Black coffee')", uid)

    run(scenario())


def test_a_supplement_named_in_a_meal_is_ticked_off(harness):
    """"Protein shake with creatine" should not need ticking twice, and the
    nutrients only reach the day's totals through supplement_log."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)
        await p.execute("DELETE FROM supplement_log WHERE user_id=$1", uid)
        sid = await db.upsert_supplement(uid, "Creatine", [(1008, 20.0)],
                                         serving_desc="4 capsules")
        day = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)

        harness.llm.meal = {
            "dish_name": "Protein shake with creatine", "confidence": 0.9, "notes": "",
            "items": [{"label": "creatine", "search_terms": "whey protein powder",
                       "grams": 5, "grams_source": "stated", "state": "as_sold",
                       "confidence": 0.9}],
        }
        harness.sent.clear()
        await harness.feed("protein shake with creatine")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        logged = await db.supplements_logged_on(uid, day)
        assert any(r["name"] == "Creatine" for r in logged), logged
        via = await p.fetchval(
            """SELECT logged_via FROM supplement_log
                WHERE user_id=$1 AND supplement_id=$2 AND local_date=$3""",
            uid, sid, day)
        # Its provenance is kept: your tick and the system's inference from a
        # sentence are different confidences.
        assert via == "from_meal"
        assert any("Also ticked off" in t for t in harness.sent.texts())

        await p.execute("DELETE FROM supplement_log WHERE user_id=$1", uid)
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)

    run(scenario())


def test_a_substring_does_not_tick_a_supplement_off(harness):
    """"zinc" inside "Chelated Magnesium" would be a false positive nobody
    could explain, and a capsule recorded because a sentence contained a
    substring is worse than one not recorded at all."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)
        await db.upsert_supplement(uid, "Zinc", [(1095, 22.0)], serving_desc="1 tablet")
        day = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)

        # Both of these are ingredient labels, and neither is the tablet.
        assert await db.supplements_named_in(uid, day, ["zinc-rich beef stew"]) == []
        assert await db.supplements_named_in(uid, day, ["beef", "onion"]) == []
        # An ingredient the parser isolated and called "zinc" is the tablet.
        assert await db.supplements_named_in(uid, day, ["zinc"]) != []

        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)

    run(scenario())


def test_each_of_the_three_rules_breaks_a_fast_on_its_own(harness):
    """No single quantity expresses it. Energy alone cannot tell honey from
    olive oil; carbohydrate alone lets a 24 g whey shake through at 3 g of
    carbs; and a spoon of butter provokes little insulin but is not a fast by
    any ordinary use of the word."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        now = dt.datetime.now(dt.timezone.utc)

        async def entry(hours_ago, name, kcal, carbs, protein):
            eid = await p.fetchval(
                """INSERT INTO log_entry (user_id, logged_at, local_date, name,
                     source, status) VALUES ($1,$2,$3,$4,'text','confirmed')
                   RETURNING id""",
                uid, now - dt.timedelta(hours=hours_ago), dt.date.today(), name)
            await p.executemany(
                "INSERT INTO log_nutrient (entry_id, nutrient_id, amount) VALUES ($1,$2,$3)",
                [(eid, 1008, kcal), (eid, 1005, carbs), (eid, 1003, protein)])

        await entry(12, "Dinner", 700, 60, 40)

        # Under all three: a brine at 5 kcal, 0.9 g carbs, 0.2 g protein.
        await entry(8, "Pickle juice", 5, 0.9, 0.2)
        assert float(await db.current_fast_hours(uid)) > 11, "a brine broke the fast"

        # Carbohydrate alone: 33 kcal of ginger tea, but nine grams of honey.
        await entry(6, "Ginger tea with honey", 33, 8.9, 0.3)
        broke = await db.fast_broken_by(uid)
        assert broke["broken_by"] == "carbohydrate", dict(broke)

        # Protein alone: under 50 kcal and barely any carbohydrate.
        await entry(4, "Bone broth", 40, 0.5, 9.0)
        assert (await db.fast_broken_by(uid))["broken_by"] == "protein"

        # Energy alone: fat, which moves neither of the other two.
        await entry(2, "Butter in coffee", 120, 0.1, 0.1)
        assert (await db.fast_broken_by(uid))["broken_by"] == "energy"
        assert float(await db.current_fast_hours(uid)) < 3

        await p.execute("DELETE FROM log_entry WHERE user_id=$1 AND source='text'", uid)

    run(scenario())


def test_the_dish_name_is_searched_on_a_one_ingredient_meal(harness):
    """"Pickle juice" parsed to a single component labelled "juice", which
    resolved to Fruit juice, NFS at 51 kcal and 12 g of carbohydrate — while
    the user's own brine row sat unconsulted, because nothing ever searched
    for the two words together."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM food WHERE owner_user_id=$1", uid)
        await p.execute("DELETE FROM food_alias WHERE user_id=$1", uid)
        fdc = await db.create_user_food(
            uid, "Pickle juice", {1008: 5.0, 1005: 0.95, 1003: 0.23, 1093: 757.0})

        harness.llm.meal = {
            "dish_name": "Pickle juice", "confidence": 0.9, "notes": "",
            "items": [{"label": "juice", "search_terms": "juice",
                       "grams": 100, "grams_source": "stated",
                       "state": "as_sold", "confidence": 0.9}],
        }
        harness.sent.clear()
        await harness.feed("100 ml pickle juice")
        card = harness.sent.last()
        await harness.press(f"ok:{_confirm_id(card)}", card.message_id)

        got = await p.fetchval(
            """SELECT lc.fdc_id FROM log_entry le JOIN log_component lc ON lc.entry_id=le.id
                WHERE le.user_id=$1 ORDER BY le.id DESC LIMIT 1""", uid)
        assert got == fdc, f"resolved to {got}, not the user's own row {fdc}"

        # The entry references the food, so it goes first — the foreign key is
        # the point of storing user foods in `food` rather than beside it.
        # The entry and the dish both reference the food, so they go first.
        await p.execute(
            """DELETE FROM log_entry WHERE user_id=$1 AND id IN
                 (SELECT entry_id FROM log_component WHERE fdc_id=$2)""", uid, fdc)
        await p.execute(
            "DELETE FROM dish WHERE id IN (SELECT dish_id FROM dish_component WHERE fdc_id=$1)",
            fdc)
        await p.execute("DELETE FROM food_alias WHERE user_id=$1", uid)
        await p.execute("DELETE FROM food WHERE owner_user_id=$1", uid)

    run(scenario())


def test_a_distinctive_supplement_name_is_recognised_in_free_text(harness):
    """"Vitamin D3 + K2" appearing in a sentence is unambiguous; "Zinc" is not,
    and "zinc-rich beef stew" involves no tablet. So free text is searched only
    for multi-word names."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        p = await db.pool()
        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)
        await p.execute("DELETE FROM supplement_log WHERE user_id=$1", uid)
        await db.upsert_supplement(uid, "Vitamin D3 + K2", [(1114, 25.0)],
                                   serving_desc="1 drop")
        await db.upsert_supplement(uid, "Zinc", [(1095, 22.0)], serving_desc="1 tablet")
        day = db.local_date_for(dt.datetime.now(dt.timezone.utc), "Europe/Warsaw", 4)

        # Multi-word: recognised in the sentence.
        found = await db.supplements_named_in(
            uid, day, [], free_text="pickle juice with vitamin d3 + k2 supplement")
        assert len(found) == 1, found

        # Single word: never from free text, however it appears.
        assert await db.supplements_named_in(
            uid, day, [], free_text="zinc-rich beef stew") == []
        assert await db.supplements_named_in(
            uid, day, [], free_text="took my zinc") == []
        # Only as an ingredient the parser isolated.
        assert await db.supplements_named_in(uid, day, ["zinc"]) != []

        await p.execute("DELETE FROM supplement WHERE user_id=$1", uid)

    run(scenario())


@pytest.mark.integration
def test_energyless_rows_are_not_candidates(database_url):
    """A row with macros and no energy is unusable, not merely lower quality.

    Demoting it only broke ties, and relevance leads: "unsalted butter" scores
    0.73 against `Butter, stick, unsalted` and 0.67 against `Butter, salted`,
    so the energy-less row won on merit and the tie-break was never consulted.
    It can only ever understate — total_nutrients skips a missing nutrient
    rather than zeroing it — so there is no query it is the right answer to.
    """
    from nutrai import db

    async def check() -> None:
        for query in ("unsalted butter", "butter", "butter, stick, unsalted"):
            rows = await db.search_foods(query, limit=8, user_id=None)
            assert rows, query
            assert all(r["has_energy"] for r in rows), (
                query, [r["description"] for r in rows if not r["has_energy"]])

        # And the food is still findable — the 48 excluded rows are all
        # Foundation, and SR Legacy and FNDDS carry the same foods with energy.
        names = [r["description"] for r in await db.search_foods("butter", limit=8)]
        assert any("Butter" in n for n in names), names

    run(check())


@pytest.mark.integration
def test_an_alias_cannot_resurrect_an_unusable_row(database_url):
    """Excluding a row from search while an alias still points at it fixes
    nothing.

    An alias is tier 1 of resolution — free, and it bypasses search entirely.
    "butter" had one, with five hits, pointing at `Butter, stick, unsalted`,
    so the identical wrong panel came back after search had been fixed and
    the bot restarted. An alias is a cache of a past resolution, and a past
    resolution can be wrong.
    """
    from nutrai import db

    async def check() -> None:
        p = await db.pool()
        bad = await p.fetchval(
            """SELECT fdc_id FROM food f
                WHERE NOT EXISTS (SELECT 1 FROM food_nutrient fn
                                   WHERE fn.fdc_id = f.fdc_id
                                     AND fn.nutrient_id IN (1008, 2048, 2047))
                  AND EXISTS (SELECT 1 FROM food_nutrient fn
                               WHERE fn.fdc_id = f.fdc_id
                                 AND fn.nutrient_id IN (1003, 1004, 1005)
                                 AND fn.amount > 0)
                LIMIT 1""")
        assert bad, "no energy-less row in the database to test against"

        uid = await p.fetchval(
            "SELECT id FROM app_user WHERE telegram_id = $1", CHAT_ID)
        await p.execute(
            """INSERT INTO food_alias (user_id, alias, fdc_id, hits)
               VALUES ($1, 'zzunusable', $2, 9)
               ON CONFLICT (user_id, alias) DO UPDATE SET fdc_id = EXCLUDED.fdc_id""",
            uid, bad)
        try:
            assert await db.resolve_alias(uid, "zzunusable") is None
        finally:
            await p.execute(
                "DELETE FROM food_alias WHERE user_id = $1 AND alias = 'zzunusable'", uid)

    run(check())


@pytest.mark.integration
def test_sugar_is_not_split_across_two_usda_ids(database_url):
    """USDA reports the same measurement under 1063 and 2000.

    FNDDS uses 1063 "Sugars, Total", SR Legacy uses 2000 "Total Sugars", and
    Foundation carries either. The target sits on 2000, so every FNDDS food's
    sugar went uncounted: a day whose snapshot totalled 43.25 g displayed 11 g
    at 19% of its ceiling, with no error anywhere. The only visible symptom was
    a coverage note reading "(from 32% of food)", which was accurate and
    answered the wrong question.
    """
    from nutrai import db

    async def check() -> None:
        p = await db.pool()
        canon = await p.fetchval(
            "SELECT canonical_id FROM v_nutrient_canonical WHERE id = 1063")
        assert canon == 2000
        # Nothing aggregates under the folded id any more.
        rows = await p.fetch(
            "SELECT DISTINCT nutrient_id FROM v_day_nutrient WHERE nutrient_id = 1063")
        assert not rows

    run(check())


@pytest.mark.integration
def test_no_targeted_nutrient_is_silently_split(database_url):
    """The general form: two ids for one measurement, unmapped.

    The signature is complementary coverage — foods carry one id or the other
    and almost never both, because the split runs along dataset lines. Nutrients
    that genuinely differ are measured together and overlap almost completely,
    which is why name similarity alone finds nothing but false positives among
    the fatty acids.

    Sugar was the only case. This fails if a future USDA load introduces
    another, rather than leaving it to be noticed as a number that looks low.
    """
    from nutrai import db

    async def check() -> None:
        p = await db.pool()
        suspects = await p.fetch(
            """
            WITH used AS (
                SELECT n.id, n.name, n.unit,
                       count(DISTINCT fn.fdc_id) AS foods
                  FROM nutrient n JOIN food_nutrient fn ON fn.nutrient_id = n.id
              GROUP BY 1,2,3 HAVING count(DISTINCT fn.fdc_id) > 500)
            SELECT a.id AS a_id, a.name AS a_name, b.id AS b_id, b.name AS b_name,
                   (SELECT count(*) FROM (
                        SELECT fdc_id FROM food_nutrient WHERE nutrient_id = a.id
                        INTERSECT
                        SELECT fdc_id FROM food_nutrient WHERE nutrient_id = b.id) x
                   ) AS overlap
              FROM used a JOIN used b ON a.unit = b.unit AND a.id < b.id
              JOIN v_nutrient_canonical ca ON ca.id = a.id
              JOIN v_nutrient_canonical cb ON cb.id = b.id
             WHERE similarity(lower(a.name), lower(b.name)) > 0.45
               AND ca.canonical_id <> cb.canonical_id
            """)
        # Pairs that look complementary and must not be folded, with the
        # reason, because the reason is the point. Folding means "these are the
        # same measurement, add them up", and that is wrong whenever one id
        # already contains the other.
        deliberate = {
            (1119, 1123): "1123 'Lutein + zeaxanthin' is a sum that already "
                          "includes 1119 'Zeaxanthin'. Adding them would count "
                          "zeaxanthin twice; the right rule here is prefer-one, "
                          "not fold, and neither is targeted.",
        }
        split = [s for s in suspects
                 if s["overlap"] < 100 and (s["a_id"], s["b_id"]) not in deliberate]
        assert not split, (
            "two ids look like one measurement and are not mapped: "
            + "; ".join(f"{s['a_id']} {s['a_name']} / {s['b_id']} {s['b_name']} "
                        f"(overlap {s['overlap']})" for s in split))

    run(check())


@pytest.mark.integration
def test_every_name_the_cards_print_can_be_targeted(database_url):
    """`/target sugar max 40` answered "I could not find a nutrient in sugar".

    DISPLAY_TO_USDA held "Sugars, total including NLEA" — the name USDA
    publishes in its documentation, and not the name this database stores. The
    word was on every card and on a live target, and the one command that
    changes it could not find it.

    So the mapping is checked against the database rather than against the
    documentation, for every display name the cards actually use.
    """
    from nutrai import db
    from nutrai.core.render import DISPLAY_TO_USDA, usda_name_for

    async def check() -> None:
        broken = []
        for term in DISPLAY_TO_USDA:
            rows = await db.find_nutrients(usda_name_for(term) or term)
            if not rows:
                broken.append(term)
        assert not broken, f"display names that resolve to nothing: {broken}"

    run(check())


@pytest.mark.integration
def test_a_folded_nutrient_is_never_offered_as_a_target(database_url):
    """A target on 1063 is a target nothing can ever satisfy.

    Every aggregate groups under the canonical id, so the row would sit on
    every card at 0% for ever and the cause would be invisible — the failure
    the fold was introduced to end, reappearing through the one command that
    creates targets.
    """
    from nutrai import db

    async def check() -> None:
        for row in await db.find_nutrients("sugar", limit=10):
            assert row["id"] != 1063, "the folded sugar id is offerable"
        p = await db.pool()
        folded = await p.fetchval(
            "SELECT count(*) FROM nutrient WHERE canonical_id IS NOT NULL")
        assert folded >= 1, "nothing is folded, so this test proves nothing"

    run(check())


@pytest.mark.integration
def test_day_energy_sigma_combines_in_quadrature_not_linearly(database_url):
    """The `±` on the day card, tested against the query that produces it.

    ARCHITECTURE §4.5 promises uncertainties add in quadrature: two components
    at ±35 g give a day at ±50, not ±70. That mattered enough to state, because
    it is what makes one weighed component shrink the whole bar rather than a
    fifth of it.

    A pure-Python `propagate()` used to carry this test and nothing called it —
    production has always read `db.day_energy_sigma`, which does the sum in SQL
    from the sigma stored on each row. Testing the twin proved nothing about
    the original, so this exercises the query itself.
    """
    from nutrai import db

    async def check() -> None:
        uid = await _reset()
        p = await db.pool()
        # A food whose energy is exactly 100 kcal/100 g, so a gram of sigma is
        # a kcal of sigma and the arithmetic is readable.
        fdc = await p.fetchval(
            """SELECT fdc_id FROM food_nutrient
                WHERE nutrient_id = 1008 AND amount > 50 LIMIT 1""")
        kcal_per_100 = float(await p.fetchval(
            "SELECT amount FROM food_nutrient WHERE fdc_id = $1 AND nutrient_id = 1008", fdc))
        assert kcal_per_100 > 0, "the fixture food has no energy, so this proves nothing"

        day = dt.date.today()
        entry = await p.fetchval(
            """INSERT INTO log_entry (user_id, local_date, name, source, status, logged_at)
               VALUES ($1,$2,'sigma probe','text','confirmed', now()) RETURNING id""",
            uid, day)
        # Two components, 30 g of sigma each.
        for i in (0, 1):
            await p.execute(
                """INSERT INTO log_component
                     (entry_id, position, fdc_id, label, grams, yield_factor,
                      grams_source, grams_sigma)
                   VALUES ($1,$2,$3,'probe',100,1.0,'estimate',30)""",
                entry, i, fdc)

        got = await db.day_energy_sigma(uid, day)
        one = 30.0 * kcal_per_100 / 100.0
        quadrature = (2 ** 0.5) * one
        linear = 2 * one
        assert abs(got - quadrature) < 0.01, (got, quadrature)
        assert got < linear * 0.75, "the sum is linear, not in quadrature"

        await p.execute("DELETE FROM log_entry WHERE id = $1", entry)

    run(check())


@pytest.mark.integration
def test_a_companion_is_offered_and_adds_at_the_mass_you_had(database_url):
    """Cornflakes alone and cornflakes with blueberries are one dish in your
    head and two rows here.

    The information was already stored — a dish containing what you just logged
    plus something else is a record of the two going together — and there was
    no route from the first to the second short of retyping it.
    """
    from nutrai import db

    async def check() -> None:
        uid = await _reset()
        p = await db.pool()
        base, extra = await p.fetch(
            "SELECT fdc_id FROM food_nutrient WHERE nutrient_id = 1008 AND amount > 50 LIMIT 2")
        base_id, extra_id = base["fdc_id"], extra["fdc_id"]

        dish = await p.fetchval(
            """INSERT INTO dish (user_id, slug, name, times_logged)
               VALUES ($1,'probe-combo','probe combo',3) RETURNING id""", uid)
        for i, (fdc, label, grams) in enumerate(
                [(base_id, "base", 60.0), (extra_id, "berries", 30.0)]):
            await p.execute(
                """INSERT INTO dish_component
                     (dish_id, position, fdc_id, label, grams, grams_source)
                   VALUES ($1,$2,$3,$4,$5,'stated')""", dish, i, fdc, label, grams)

        # Logging the base alone offers the berries, not the base again.
        offered = await db.companions(uid, [base_id])
        assert [int(c["fdc_id"]) for c in offered] == [extra_id]
        assert float(offered[0]["grams"]) == 30.0
        assert offered[0]["grams_source"] == "stated", (
            "provenance must ride along, or a suggestion launders a guess "
            "into a measurement")

        # Adding it lands on the pending entry at that mass.
        entry = await p.fetchval(
            """INSERT INTO log_entry (user_id, local_date, name, source, status)
               VALUES ($1, current_date, 'probe', 'text', 'pending') RETURNING id""", uid)
        await p.execute(
            """INSERT INTO log_component
                 (entry_id, position, fdc_id, label, grams, grams_source)
               VALUES ($1,0,$2,'base',60,'stated')""", entry, base_id)
        await db.add_component_to_entry(
            entry, extra_id, "berries", 30.0, grams_source="stated")
        _e, comps = await db.entry_with_components(entry)
        assert [c["label"] for c in comps] == ["base", "berries"]
        assert float(comps[1]["grams_sigma"]) > 0

        # A confirmed entry is a snapshot and must not gain components.
        await p.execute("UPDATE log_entry SET status='confirmed' WHERE id=$1", entry)
        await db.add_component_to_entry(
            entry, extra_id, "berries again", 99.0, grams_source="stated")
        _e, after = await db.entry_with_components(entry)
        assert len(after) == 2, "a confirmed entry was edited behind its snapshot"

        await p.execute("DELETE FROM log_entry WHERE id = $1", entry)
        await p.execute("DELETE FROM dish WHERE id = $1", dish)

    run(check())


@pytest.mark.integration
def test_a_message_that_is_a_dish_name_repeats_it(harness):
    """"pastel de choclo" reached the parser and came back as ground beef.

    The repeat grammar read it as selector "pastel" plus two modifiers nobody
    could read, so a dish already in the database was parsed as a novel meal —
    at 40% confidence, 912 kcal, and one component. The name is the most
    natural thing to type and was the one spelling that did not work.
    """
    async def scenario():
        uid = await _reset()
        from nutrai import db
        from nutrai.bot import dp

        p = await db.pool()
        fdc = await p.fetchval(
            "SELECT fdc_id FROM food_nutrient WHERE nutrient_id = 1008 AND amount > 50 LIMIT 1")
        dish = await p.fetchval(
            """INSERT INTO dish (user_id, slug, name, default_slot, times_logged)
               VALUES ($1,'probe-stew','Probe Stew','dinner',2) RETURNING id""", uid)
        await p.execute(
            """INSERT INTO dish_component
                 (dish_id, position, fdc_id, label, grams, grams_source)
               VALUES ($1,0,$2,'probe',150,'stated')""", dish, fdc)

        harness.sent.clear()
        harness.llm.calls.clear()
        await harness.feed("probe stew")

        assert any("Probe Stew" in t for t in harness.sent.texts()), harness.sent.texts()
        # The whole point: it costs nothing.
        assert not harness.llm.calls, f"a model was called: {harness.llm.calls}"
        logged = await p.fetchval(
            """SELECT count(*) FROM log_entry
                WHERE user_id = $1 AND dish_id = $2 AND status = 'confirmed'""",
            uid, dish)
        assert logged == 1, "an unmodified repeat of a confirmed dish should log"

        # A name plus an instruction is not the same message and must not be
        # silently stripped down to the dish.
        harness.sent.clear()
        harness.llm.calls.clear()
        await harness.feed("probe stew with extra potato")
        assert harness.llm.calls, "a modified dish was logged as the plain one"

        await p.execute("DELETE FROM dish WHERE id = $1", dish)

    run(scenario())


@pytest.mark.integration
def test_a_discarded_parse_cannot_overwrite_an_existing_dish(harness):
    """A meal typed and thrown away destroyed a dish it collided with by slug.

    `_present` wrote the dish before anyone accepted the parse, and the write
    deleted the existing components first. A twelve-component Pastel de Choclo
    became one 400 g item because a parse of the same name was produced and
    then discarded — nothing recorded it, because from the entry's point of
    view nothing had gone wrong.
    """
    async def scenario():
        uid = await _reset()
        from nutrai import db
        from nutrai.bot import dp

        p = await db.pool()
        a, b = await p.fetch(
            "SELECT fdc_id FROM food_nutrient WHERE nutrient_id = 1008 AND amount > 50 LIMIT 2")
        dish = await p.fetchval(
            """INSERT INTO dish (user_id, slug, name, default_slot)
               VALUES ($1,'mince-and-rice','Mince and rice','dinner') RETURNING id""", uid)
        for i, fdc in enumerate((a["fdc_id"], b["fdc_id"])):
            await p.execute(
                """INSERT INTO dish_component
                     (dish_id, position, fdc_id, label, grams, grams_source)
                   VALUES ($1,$2,$3,$4,120,'stated')""", dish, i, fdc, f"curated{i}")

        # The stub parses any text into its own MEAL, whose slug collides.
        harness.sent.clear()
        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"no:{_confirm_id(card)}", card.message_id)

        rows = await db.dish_components(dish)
        assert [r["label"] for r in rows] == ["curated0", "curated1"], (
            "a discarded parse rewrote the dish")
        assert all(r["grams_source"] == "stated" for r in rows)

        await p.execute("DELETE FROM dish WHERE id = $1", dish)

    run(scenario())


@pytest.mark.integration
def test_your_own_food_beats_a_generic_row(database_url):
    """A food defined from a packet lost to a national average of a different food.

    `_candidates` searches the model's `search_terms` as well as the user's
    words and ranks by the best score any query achieved. The model's phrase
    describes what it believes the food to be, so it matches a generic row
    almost exactly — a Devolay defined an hour earlier scored 0.84 against the
    user's own label and still lost to `Chicken or turkey cordon bleu`, which
    was then auto-matched and cached as an alias.
    """
    from nutrai import db
    from nutrai.config import AUTO_MATCH_SIMILARITY

    async def check() -> None:
        p = await db.pool()
        uid = await p.fetchval("SELECT id FROM app_user WHERE telegram_id = $1", CHAT_ID)
        fdc = await db.create_user_food(
            uid, "zzprobe cutlet (breaded stuffed thing)",
            {1008: 264.0, 1003: 11.8, 1004: 18.5, 1005: 13.0})

        cands = await db.search_foods(
            "zzprobe cutlet (breaded stuffed thing)", limit=8, user_id=uid)
        own = [c for c in cands if c["precedence"] == 0]
        assert own, "the user's own food is not even a candidate"
        assert float(own[0]["sim"]) >= AUTO_MATCH_SIMILARITY

        # precedence 0 is user_product and nothing else — the whole rule rests
        # on that, so it is asserted rather than assumed.
        kinds = await p.fetch(
            "SELECT DISTINCT data_type FROM food WHERE precedence = 0")
        assert [k["data_type"] for k in kinds] == ["user_product"]

        import inspect

        from nutrai.llm import parse
        src = inspect.getsource(parse.resolve_items)
        assert 'c["precedence"] == 0' in src, "own-food preference is gone"

        await p.execute("DELETE FROM food_nutrient WHERE fdc_id = $1", fdc)
        await p.execute("DELETE FROM food_alias WHERE fdc_id = $1", fdc)
        await p.execute("DELETE FROM food WHERE fdc_id = $1", fdc)

    run(check())
