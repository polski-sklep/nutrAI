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


def test_logging_something_had_before_is_listed_first():
    """It is the most-used path, and /r is muscle memory rather than a name.

    The command is `/again` since 31 Aug 2026: "repeat" reads as a whole day
    and "again" as one thing, which is the way round they are actually used.
    The list order did not change — only the two names did.
    """
    assert COMMANDS[0][0] == "/again"
    assert COMMANDS[1][0] == "/repeat"
    assert "/r " not in command_list()


def test_the_short_alias_still_works():
    """Dropping it from the menu must not drop it from the dispatcher.

    `/r` stays on the single-thing path across the rename. It is muscle memory
    for an action, and the action did not change — only its name did, so
    moving the alias with the word would have broken the habit to no purpose.
    """
    assert {"/r", "/a", "/again"} <= registered_commands()
    assert {"/repeat", "/block"} <= registered_commands()


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
    for expected in ("/why", "/next", "/training", "/profile", "/target",
                     "/supp", "/food"):
        assert expected in names, f"{expected} is built but not in the menu"

    # /stack and /schedule are deliberately not in the menu: both are buttons
    # on the /supp card, which is where you are standing when you want them.
    # The guarantee this test protects is reachability, not membership — so it
    # checks the buttons instead of the list.
    import inspect

    from nutrai import bot

    src = inspect.getsource(bot)
    for cb in ("supadd:", "supmanage:", "suptimes:"):
        assert f'callback_data="{cb}"' in src, f"{cb} button is gone"
        assert f'F.data.startswith("{cb}")' in src, f"{cb} has no handler"


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
    # `_ask` is reached from commands (`msg`) and from callbacks (`cq.message`)
    # alike. Matching only the first spelling would quietly stop covering every
    # prompt a button opens.
    opened |= set(re.findall(
        r'_ask\(\s*(?:cq\.message|msg),\s*u,\s*"([a-z_]+)"', src))

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
        "block_repeat",   # 🔁 log all N / ✋ never mind on a block of a day
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
    assert "hit a limit" in out and "console.anthropic.com" in out
    assert "try again in a moment" not in out
    # The local paths are unaffected, and that is the useful thing to know.
    assert "/again" in out


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
    import re

    from nutrai import bot

    src = inspect.getsource(bot)
    # The examples are one constant now, so the thing that has to hold is that
    # every recipe prompt inlines it rather than writing its own copy. Counting
    # the literal would pass on a comment that happens to quote it.
    assert "makes 850 g, 16 slices" in bot._RECIPE_EXAMPLES
    prompts = len(re.findall(r"what goes into it\?", src, re.IGNORECASE))
    assert prompts >= 3
    assert src.count("+ _RECIPE_EXAMPLES") == prompts


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


def test_count_is_read_off_the_message_not_guessed():
    """The model was asked to set `count` and on the first real use did not.

    "0.33 slice of blondie" came back as a 30 g estimate noting "standard slice
    assumed ~90g" — a guess at a quantity the database knew exactly (88 g).
    Asking the model more firmly makes that likelier, not certain, and the
    point of a declared portion is that it removes the guess.
    """
    from nutrai.llm.parse import count_from_text

    assert count_from_text("0.33 slice of blondie", "slice") == 0.33
    assert count_from_text("two slices of blondie", "slice") == 2.0
    assert count_from_text("a slice of blondie", "slice") == 1.0
    # "half a slice" must not match the "a slice" further along the string —
    # that turns a half into a whole, silently and in the wrong direction.
    assert count_from_text("half a slice of blondie", "slice") == 0.5
    # Likewise "1/2 slice" must not match the 2.
    assert count_from_text("1/2 slice", "slice") == 0.5
    assert count_from_text("blondie", "slice") is None
    assert count_from_text("400 slices", "slice") is None


def test_a_panel_must_agree_with_its_own_macros():
    """One energy-less row out of eight is worse than all eight being so.

    The all-or-nothing test caught only the latter. 340 g of butter matched
    "Butter, stick, unsalted" — 81.5 g of fat, no energy figure — and the
    blondie stored 337 kcal per 100 g against macros implying 524. Nothing
    about that panel looks wrong; it is simply a third low, for ever.
    """
    from nutrai.core.nutrition import energy_cross_check

    saved = {1008: 336.5625, 1003: 4.8762, 1004: 28.2412, 1005: 63.7733, 1079: 2.1438}
    check = energy_cross_check(saved)
    assert not check.ok and check.delta_pct > 50

    import inspect

    from nutrai import bot
    assert "energy_cross_check" in inspect.getsource(bot._consume_food_recipe)


def test_no_low_confidence_warning_for_your_own_food_at_a_stated_mass():
    """A warning that fires when nothing is wrong trains you to ignore them.

    "0.33 slice of blondie" scored 50% because the model had guessed a 75 g
    slice and said so — then the mass came from the stated 88 g portion
    instead, and the card printed the exact figure beside "low overall
    confidence — check the foods matched". The food was a row defined by the
    user and matched by exact alias. Nothing on that card was uncertain.
    """
    import inspect

    from nutrai import bot

    src = inspect.getsource(bot._present)
    guard = src[src.index("parsed.confidence < CONFIDENCE_FLOOR"):]
    assert "not (all_hard and own_food)" in guard[:120]
    # And the model's stale explanation of a mass it did not supply goes too.
    assert "notes=None if all_hard and res.prior_notes else parsed.notes" in src


def test_backdate_prompt_has_a_consumer_and_does_not_teach_syntax():
    """The failure this file has hit eight times: a card that explains a
    command form instead of doing the thing.

    /yesterday accepts `/yesterday 2 empanadas 19:00` because it is the
    fastest path, but the card asks a question and waits for the answer.
    """
    from nutrai.bot import PROMPT_CONSUMERS

    assert "backdate_food" in PROMPT_CONSUMERS


def test_trailing_time_is_read_off_the_meal_line():
    from nutrai.bot import _TRAILING_TIME

    assert _TRAILING_TIME.search("2 empanadas 19:00").groups() == ("19", "00")
    assert _TRAILING_TIME.search("toast at 8.30").groups() == ("8", "30")
    # A meal with no time must not have one invented from its digits.
    assert _TRAILING_TIME.search("2 empanadas") is None
    assert _TRAILING_TIME.search("250 g chicken") is None


def test_supplement_name_matching_ignores_punctuation():
    """"Vitamin D3 + K2" in the stack and "vitamin d3/k2" in the message are
    the same supplement, and a literal substring test says they are not.

    The capsule was named explicitly in the sentence and went unticked, which
    is this matcher doing the opposite of its job. The multi-word guard stays:
    a single-word name is still too easily an ingredient or an adjective, and
    "zinc-rich beef stew" involves no tablet.
    """
    import re

    def norm(v: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", v.lower()).split())

    assert norm("Vitamin D3 + K2") in norm("3 with vitamin d3/k2")
    assert norm("Vitamin D3 + K2") in norm("pickle juice with Vitamin D3 & K2")
    assert " " in norm("Vitamin D3 + K2"), "must stay multi-word to be searched"
    assert " " not in norm("Zinc"), "single-word names are not searched in text"


def test_qualifier_mismatch_is_caught():
    """99 g of "egg whites, fried" matched "Egg, whole, cooked, fried".

    Egg white has no cholesterol; the row carries 401 mg per 100 g. The day
    read 249% of its ceiling and the morning note advised fewer egg yolks, on
    a day containing one yolk. Trigram similarity cannot see this: the names
    share every token that matters and differ by the one word that decides
    what the food is.
    """
    from nutrai.jobs.audit import QUALIFIER_SETS, _qualifiers

    egg = next(f for f in QUALIFIER_SETS if "yolk" in f)
    assert _qualifiers("egg whites, fried", egg) == {"white"}
    assert _qualifiers("Egg, whole, cooked, fried", egg) == {"whole"}
    # Substrings must not count: "whole" is inside "wholemeal".
    assert _qualifiers("wholemeal bread", egg) == set()
    assert _qualifiers("egg yolk", egg) == {"yolk"}


def _block_meals(n=3):
    return [{"slug": f"s{i}", "label": f"Meal {i}", "icon": "🍽", "at": "08:0%d" % i}
            for i in range(n)]


def test_block_card_shows_ticks_only_while_choosing():
    """A row of ✅ against every line, before anything has been chosen, is
    decoration that looks like state. The summary is a list; the picker is a
    choice, and only the second needs boxes."""
    from nutrai.bot import _block_card

    meals = _block_meals()
    summary = _block_card(meals, [0, 1, 2], "Morning")
    assert "✅" not in summary and "⬜️" not in summary
    assert "3 meals" in summary

    picking = _block_card(meals, [0, 2], "Morning")
    assert picking.count("✅") == 2 and picking.count("⬜️") == 1
    assert "2 meals" in picking


def test_block_keyboard_counts_what_it_will_log():
    """"log all 6" after unticking two is a button that lies about its own
    effect, and the effect is six confirmation cards."""
    from nutrai.bot import _block_keyboard

    meals = _block_meals(6)
    summary = [b.text for row in
               _block_keyboard(1, meals, list(range(6)), picking=False).inline_keyboard
               for b in row]
    assert "🔁 log all 6" in summary and "☑️ choose which" in summary

    picked = [b.text for row in
              _block_keyboard(1, meals, [0, 1], picking=True).inline_keyboard
              for b in row]
    assert "🔁 log 2" in picked
    # And the choose button is gone once you are choosing.
    assert not [t for t in picked if "choose which" in t]
    # One toggle per meal.
    assert len([t for t in picked if t.startswith(("✅", "⬜️"))]) == 6


def test_photo_placeholders_say_what_is_being_read():
    """A photo of a banana announced "reading the label…".

    The wording came from the supplement-label path and stayed on the meal path
    after the routing bug above it was fixed. It is not cosmetic: it tells the
    reader the answer will come from a printed panel, when it will come from
    the model looking at food, and those have very different error modes.
    """
    import inspect
    import re

    from nutrai import bot

    src = inspect.getsource(bot)
    # Every "reading the label" placeholder must sit in a label handler.
    for m in re.finditer(r'answer\("[^"]*reading the label[^"]*"\)', src):
        before = src[:m.start()]
        fn = before.rsplit("async def ", 1)[1].split("(", 1)[0]
        assert "label" in fn, f"{fn} says 'reading the label' and is not a label path"
    assert "looking at the photo" in src


def test_the_api_client_has_a_real_retry_budget():
    """A few seconds of dead DNS lost a meal, twice.

    Docker's embedded resolver stopped answering for a moment. The SDK default
    of two retries with sub-second backoff exhausted itself inside a second,
    the parse failed, the food was retyped, and it failed again. The cost of
    waiting is a slower failure; the cost of not waiting is a failure.
    """
    from nutrai.llm.client import MAX_RETRIES, TIMEOUT_S, client

    c = client()
    assert c.max_retries == MAX_RETRIES >= 4
    assert c.timeout == TIMEOUT_S >= 60


def test_a_connection_failure_says_so_and_names_what_still_works():
    from nutrai.bot import _failure_reason

    class APIConnectionError(Exception):
        pass

    out = _failure_reason(APIConnectionError("Connection error."))
    assert "reach" in out.lower()
    assert "/again" in out


def test_food_new_without_a_name_waits_for_one():
    """It asked for a name and opened no wait, so the answer went to the meal
    parser: "Lemon water" came back as a confirmation card for a drink instead
    of naming the food being defined.

    Ninth instance of a card that instructs rather than asks.
    """
    import inspect

    from nutrai import bot
    from nutrai.bot import PROMPT_CONSUMERS

    assert "food_name_await" in PROMPT_CONSUMERS
    src = inspect.getsource(bot.food_cmd)
    assert "Name it first" not in src, "still teaching a syntax instead of asking"
    assert '_ask(' in src


def test_a_shortened_supplement_name_is_recognised():
    """The stack holds "Vitamin D3 + K2"; the message said "with vitamin d3".

    Every word of the shortened form is in the name, in order, and the whole
    string is not — so exact containment missed a capsule the user had named
    outright. Two consecutive words are enough; one is not, which is what keeps
    "zinc-rich beef stew" from ticking off zinc.
    """
    import re

    from nutrai.db import _names_supplement

    def norm(v: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", v.lower()).split())

    assert _names_supplement(norm("Vitamin D3 + K2"),
                             norm("Lemon lime water with vitamin d3"))
    assert _names_supplement(norm("Marine Collagen"), norm("coffee with marine collagen"))
    assert not _names_supplement(norm("Zinc"), norm("zinc-rich beef stew"))
    assert not _names_supplement(norm("Vitamin D3 + K2"), norm("vitamin c with breakfast"))
