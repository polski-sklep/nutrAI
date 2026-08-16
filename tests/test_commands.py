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
