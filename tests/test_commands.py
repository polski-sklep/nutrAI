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
                     "/profile", "/target", "/supp"):
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
