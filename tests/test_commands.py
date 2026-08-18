"""Every command the bot advertises must exist, and nothing may be dropped.

`/start` listed `/improve`, `/targets` and `/week` for a while when none of the
three had a handler. Typing them did nothing at all — aiogram walks its handlers
in registration order, matched none, and discarded the update — which from the
user's side is indistinguishable from the bot being down. That was found by
reading the source. It should not need finding by reading the source twice.

No database and no network: this reads the dispatcher's registered filters.
"""

from __future__ import annotations

import re

import pytest
from aiogram.filters import Command, CommandStart

from nutrai.bot import COMMANDS, command_list, dp, start, unknown_command


def registered_commands() -> set[str]:
    """Every command string any handler on `dp` will actually answer."""
    found: set[str] = set()
    for handler in dp.message.handlers:
        for f in handler.filters or []:
            cb = f.callback
            if isinstance(cb, CommandStart):
                found.add("/start")
            elif isinstance(cb, Command):
                for c in cb.commands:
                    found.add("/" + (c if isinstance(c, str) else c.pattern))
    return found


def advertised_commands() -> set[str]:
    """Command tokens as they appear in the text a user is shown.

    Tags are stripped first: the message is HTML now, and `</code>` otherwise
    reads as a command called `/code`.
    """
    visible = re.sub(r"<[^>]+>", "", command_list())
    return set(re.findall(r"/[a-z]+", visible))


def test_every_advertised_command_has_a_handler():
    missing = advertised_commands() - registered_commands()
    assert not missing, (
        f"advertised in /start with no handler: {sorted(missing)} — "
        "typing these does nothing at all"
    )


@pytest.mark.parametrize("command", sorted(advertised_commands()))
def test_advertised_command_resolves(command: str):
    """Named individually so a failure says which command is broken."""
    assert command in registered_commands()


def test_the_commands_we_deliberately_do_not_have_are_not_advertised():
    """`core/plan.py` is written but deliberately unwired — stage 5 work.

    Advertising it is what made it look like a bug rather than a decision.
    `/week` was on this list until it was built; the guard that matters is the
    one above, which fails if anything advertised lacks a handler.
    """
    for gone in ("/improve", "/targets"):
        assert gone not in command_list()


def test_unknown_command_handler_is_registered_last():
    """It matches every `/…`, so anything after it would be unreachable."""
    callbacks = [h.callback for h in dp.message.handlers]
    assert callbacks[-1] is unknown_command, [getattr(c, "__name__", c) for c in callbacks]


def test_start_is_registered_before_the_catch_all():
    callbacks = [h.callback for h in dp.message.handlers]
    assert callbacks.index(start) < callbacks.index(unknown_command)


def test_command_list_is_not_empty_and_matches_the_table():
    assert COMMANDS
    rendered = command_list()
    for name, _desc in COMMANDS:
        assert name in rendered


def test_repeat_is_advertised_by_its_full_name_and_listed_first():
    """It is the most-used path, and /r is muscle memory rather than a name."""
    assert COMMANDS[0][0] == "/repeat"
    assert "/r " not in command_list()


def test_the_short_alias_still_works():
    """Dropping it from the menu must not drop it from the dispatcher."""
    assert {"/r", "/repeat"} <= registered_commands()


def test_menu_descriptions_fit_telegrams_limits():
    """set_my_commands rejects the whole batch if one entry is malformed, and
    the failure is a stale menu rather than an error anyone sees."""
    import re

    for name, desc in COMMANDS:
        cmd = name.lstrip("/")
        assert re.fullmatch(r"[a-z0-9_]{1,32}", cmd), cmd
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", desc)).strip()
        assert 1 <= len(plain) <= 256, (cmd, len(plain))


def test_the_menu_matches_the_command_table_exactly():
    """Three separate edits to COMMANDS today were `str.replace` calls whose
    anchor had already changed, so they matched nothing and reported nothing.
    The menu is pushed from this table, so a silent no-op here is a command
    that exists and cannot be found."""
    names = [name for name, _d in COMMANDS]
    assert len(names) == len(set(names)), "duplicate entry in COMMANDS"
    for expected in ("/why", "/next", "/stack", "/schedule", "/training",
                     "/profile", "/target", "/supp", "/food"):
        assert expected in names, f"{expected} is built but not in the menu"


def test_every_prompt_opened_has_something_that_consumes_it():
    """Six times today a command printed instructions and then fed the reply to
    the meal parser: the ✏️ button, the rating keypad, /weight, /supp add,
    /profile and /why. Opening a prompt and consuming its answer were two edits
    in two places and forgetting the second was silent.

    This scans for every wait the bot opens and asserts a consumer exists.
    """
    import inspect
    import re

    from nutrai import bot as botmod

    src = inspect.getsource(botmod)
    opened = set(re.findall(r'put_pending\(\s*u\["id"\],\s*"([a-z_]+)"', src))
    opened |= set(re.findall(r'_ask\(\s*msg,\s*u,\s*"([a-z_]+)"', src))

    # Kinds that are menus rather than typed prompts: their reply arrives as a
    # button press or through the repeat grammar, not as free text.
    # Each verified by reading its handler, not assumed: every one of these is
    # answered by an inline button, so free text arriving while it is open
    # genuinely is a meal and must reach the parser.
    not_typed = {
        "supp_pick",      # the tick-list keyboard
        "supp_confirm",   # ✅ save all / 🗑 discard
        "repeat_menu",    # answered by the repeat grammar, not free text
        "plan_proposal",  # core/plan.py, deliberately unwired
        "confirm_entry",  # ✅ / ❌ / ✏️ on a parse
        "off_product",    # ✅ save it / ✏️ rename / 🗑 no on a looked-up panel
        "off_choices",    # the numbered pick buttons under a search
        "food_panel",     # ✅ save it / 🗑 no on a transcribed panel
    }

    missing = {k for k in opened if k not in not_typed} - set(botmod.PROMPT_CONSUMERS)
    assert not missing, (
        f"prompts opened with nothing to consume the reply: {sorted(missing)} — "
        "the bot will print instructions and send the answer to the meal parser"
    )


def test_the_awaiting_list_cannot_drift_from_its_consumers():
    """AWAITING_KINDS is derived from the registry rather than written beside
    it, so a kind cannot be listed without a consumer or vice versa."""
    from nutrai import bot as botmod

    assert set(botmod.AWAITING_KINDS) == set(botmod.PROMPT_CONSUMERS)
    assert "why_await" in botmod.AWAITING_KINDS


def test_asking_for_an_unregistered_prompt_fails_loudly():
    """A typo in the kind is a prompt nothing answers, so it raises here rather
    than going quiet in production."""
    import asyncio

    from nutrai import bot as botmod

    with pytest.raises(KeyError):
        asyncio.run(botmod._ask(None, {"id": 1}, "not_a_real_prompt", "hi"))


def test_no_card_teaches_a_syntax_without_opening_a_prompt():
    """The registry stops a prompt going unconsumed. It cannot stop a card
    printing "/food new pickle juice" and opening nothing, which is how the
    eighth instance happened — the reply went to the meal parser and matched
    "juice" at 51 kcal.

    So: no user-facing card may instruct with a subcommand form. If a card
    wants input it asks for it plainly and opens a wait via `_ask`.
    """
    import inspect
    import re

    from nutrai.core import render

    src = inspect.getsource(render)
    # "<code>/something new ...</code>" and friends: a command with a
    # subcommand argument, printed at the user as an instruction.
    offenders = re.findall(r"<code>(/[a-z]+ (?:new|add|list|times) [^<]*)</code>", src)
    assert not offenders, (
        f"cards instructing with a subcommand instead of asking: {offenders}"
    )


def test_csv_does_not_print_decimal_noise():
    """asyncpg returns numeric as Decimal, and str(Decimal) prints all of it.

    A meal's energy is stored as the sum of per-100 g arithmetic and comes back
    as 11.879999999999999005240169935859739780426025390625 — correct, and
    unusable in a spreadsheet column. Six places is past anything anyone
    measured and short enough to read.
    """
    import datetime as dt
    import decimal

    from nutrai.bot import _csv

    class R(dict):
        def keys(self): return list(super().keys())
        def values(self): return list(super().values())

    rows = [R(kcal=decimal.Decimal("11.879999999999999005240169935859739780426025390625"),
              grams=decimal.Decimal("300"),
              day=dt.date(2026, 8, 16), missing=None)]
    out = _csv(rows).decode().splitlines()
    assert out[0] == "kcal,grams,day,missing"
    assert out[1] == "11.88,300,2026-08-16,"


def test_export_is_empty_for_no_rows():
    from nutrai.bot import _csv
    assert _csv([]) == b""


def test_out_of_credit_does_not_advise_retrying():
    """An exhausted balance is a 400, and "try again in a moment" never works.

    The message named the exception class — "BadRequestError" — and then gave
    the one piece of advice guaranteed to fail. Waiting and fixing are
    different responses and the message has to say which.
    """
    from nutrai.bot import _failure_reason

    class BadRequestError(Exception):
        pass

    out = _failure_reason(BadRequestError(
        "Error code: 400 - {'error': {'message': 'Your credit balance is too "
        "low to access the Anthropic API. Please go to Plans & Billing'}}"))
    assert "out of credit" in out
    assert "try again in a moment" not in out
    # The local paths are unaffected, and that is the useful thing to know.
    assert "/repeat" in out


def test_a_rate_limit_does_advise_retrying():
    from nutrai.bot import _failure_reason

    class RateLimitError(Exception):
        pass

    assert "try again" in _failure_reason(RateLimitError("429 rate_limit_error"))


def test_an_unrecognised_failure_still_names_itself():
    from nutrai.bot import _failure_reason

    class WeirdError(Exception):
        pass

    assert "WeirdError" in _failure_reason(WeirdError("no idea"))


def test_read_makes_splits_the_clause_out():
    """Left in the text, "makes 16 slices" reaches the meal parser.

    Sixteen slices of something then get resolved and added to the recipe,
    which is both wrong and invisible — the panel comes out plausible.
    """
    from nutrai.bot import _read_makes

    body, grams, pieces, unit = _read_makes(
        "340 g butter, 400 g brown sugar, 3 eggs. Makes a 850 g tray of 16 slices")
    assert "makes" not in body.lower() and "slices" not in body.lower()
    assert "340 g butter" in body
    assert (grams, pieces, unit) == (850.0, 16, "slice")


def test_read_makes_survives_a_decimal():
    """"1.2 kg" contains the character that ends the clause."""
    from nutrai.bot import _read_makes

    _body, grams, pieces, unit = _read_makes("500 g flour, makes 1.2 kg, 12 muffins")
    assert (grams, pieces, unit) == (1200.0, 12, "muffin")


def test_read_makes_leaves_an_ordinary_recipe_alone():
    from nutrai.bot import _read_makes

    text = "1000 ml water, 30 g salt, 100 ml white vinegar"
    assert _read_makes(text) == (text, None, None, "serving")


def test_cooking_loss_is_stated_not_implied():
    """A panel divided by raw mass understates a baked food uniformly.

    Every figure stays internally consistent while being too low, so nothing
    downstream can detect it. The card has to say which divisor it used.
    """
    from nutrai.core.render import user_food_made_card

    per_100g = {1008: 420.0, 1003: 5.0}
    baked = user_food_made_card("Blondie", per_100g, ["340 g butter"], 850.0,
                                raw_g=1115.0, pieces=16, portion_unit="slice")
    assert "1,115 g in, 850 g out" in baked and "265 g lost in cooking" in baked
    assert "1 slice = 53 g" in baked

    # No finished weight given: say what was assumed, and how to fix it.
    guessed = user_food_made_card("Blondie", per_100g, ["340 g butter"], 1115.0,
                                  raw_g=1115.0)
    assert "raw ingredient mass" in guessed


def test_every_recipe_prompt_mentions_the_makes_clause():
    """A syntax nobody is told about is a syntax nobody types.

    This is the "card asks, nothing listens" failure inverted: the handler
    listens perfectly and the card never mentions it, so the feature exists
    and is unreachable in exactly the same way.
    """
    import inspect

    from nutrai import bot

    src = inspect.getsource(bot)
    prompts = src.count("What goes into it?")
    assert prompts >= 2
    assert src.count("makes 850 g, 16 slices") >= prompts


def test_impossible_panel_is_refused():
    """100 g of food cannot hold 160 g of macronutrients.

    A stated finished weight is the one input nothing else checks, and
    understating it inflates every figure in exact proportion — the panel stays
    internally consistent all the way to absurdity. 1,587 g of blondie
    ingredients declared as an 850 g tray gave 105.6 g carbs, 46.8 g fat and
    8.1 g protein per 100 g, saved without complaint.
    """
    import inspect

    from nutrai import bot

    src = inspect.getsource(bot._consume_food_recipe)
    assert "macro_g > 100" in src
    # It must abort, not warn and carry on: a saved panel poisons every future
    # slice, and the person who typed the weight is the only one who can fix it.
    body = src[src.index("macro_g > 100"):]
    assert "return True" in body[:body.index("create_user_food")]


def test_a_total_miss_offers_to_define_the_food():
    """The weak-match path offered the button and the no-match path did not.

    A near-miss is ambiguous — the right row may be on the list, ranked badly.
    A complete miss is the strongest evidence USDA has no row at all, which is
    the exact case /food exists for, so offering the button on the weaker
    signal and withholding it on the stronger one had it backwards.
    """
    import inspect

    from nutrai import bot

    src = inspect.getsource(bot._present)
    miss = src[src.index("No match in the food database"):]
    assert "_define_button" in miss[:miss.index("return")]
