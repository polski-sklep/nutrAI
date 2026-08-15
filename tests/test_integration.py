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
        assert "mince and rice" in day.text
        assert "% of today's mass was weighed or stated" in day.text

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
        assert "repeat" in menu.text.lower()
        assert "mince and rice" in menu.text

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
    meal you look at and discard still leaves a repeatable dish behind. That
    dish has never been through a human, and repeating it must not log."""

    async def scenario():
        uid = await _reset()
        from nutrai import db

        await harness.feed("250 g minced beef, 164 g rice, a splash of olive oil")
        card = harness.sent.last()
        await harness.press(f"no:{_confirm_id(card)}", card.message_id)

        p = await db.pool()
        assert await p.fetchval(
            "SELECT count(*) FROM dish WHERE user_id=$1", uid
        ) == 1, "discarding should still leave the dish for later"

        await harness.feed("/r")
        harness.sent.clear()
        await harness.feed("1")

        # It must offer a confirm gate, not log.
        gated = harness.sent.last()
        assert [b for b in gated.buttons if b.startswith("ok:")], gated.text
        assert "never been confirmed" in gated.text
        assert await p.fetchval(
            "SELECT count(*) FROM log_entry WHERE user_id=$1 AND status='confirmed'", uid
        ) == 0, "a never-confirmed dish was logged with no gate"

        # Confirm it once, and the repeat becomes instant from then on.
        await harness.press(f"ok:{_confirm_id(gated)}", gated.message_id)
        harness.sent.clear()
        await harness.feed("1")
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
        assert "0.76¢" in shown, shown

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

        for _ in range(3):
            await dp.feed_update(
                harness.tg.bot, harness.tg.photo_update(_jpeg(), media_group_id="album-1")
            )
        await asyncio.sleep(ALBUM_WAIT + 0.6)

        cards = [s for s in harness.sent.sent if s.buttons]
        assert len(cards) == 1, f"{len(cards)} confirmation cards for one album"

    run(scenario())


def test_no_slash_command_is_ever_dropped(harness):
    """Through the real dispatcher, so registration order is what is tested."""

    async def scenario():
        await _reset()
        from nutrai.bot import COMMANDS

        # Commands that do not exist come back with the list of ones that do.
        for typed in ("/improve", "/targets", "/week", "/nonsense", "/r0"):
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
        assert not harness.sent.last().buttons, "nothing to confirm — nothing resolved"

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

        # No argument is a usage hint, not a crash.
        harness.sent.clear()
        await harness.feed("/weight")
        assert "/weight 78.2" in harness.sent.last().text

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
        # Both pre-ticked.
        assert picker.text.count("✅") == 2, picker.text

        toggle = next(b for b in picker.buttons if b.startswith("supt:"))
        await harness.press(toggle, picker.message_id)
        picker = harness.sent.last()
        assert picker.text.count("✅") == 1, picker.text

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
