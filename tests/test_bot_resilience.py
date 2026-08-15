"""The bot must not go silent when a food name upsets the HTML parser.

Every outbound message is HTML, assembled from names the user typed and USDA
descriptions nobody vetted for markup. A rejected message is worse than an ugly
one: the confirmation card never arrives, the entry is left sitting in
`pending`, and from the user's side the bot simply ignored them.
"""

from __future__ import annotations

import asyncio
import re
from html import unescape

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage

from nutrai.bot import resend_unformatted
from nutrai.core.render import _esc, day_card
from tests.test_render import DAY, PROGRESS


class Recorder:
    """Rejects anything with a parse_mode, exactly once per message."""

    def __init__(self, always_fail: bool = False) -> None:
        self.attempts: list[str | None] = []
        self.always_fail = always_fail

    async def __call__(self, bot: Bot, method):
        self.attempts.append(getattr(method, "parse_mode", None))
        if self.always_fail or method.parse_mode is not None:
            raise TelegramBadRequest(
                method=method,
                message="Bad Request: can't parse entities: Can't find end of Italic entity",
            )
        return "delivered"


def _send(text: str, parse_mode: str | None = "HTML") -> SendMessage:
    return SendMessage(chat_id=1, text=text, parse_mode=parse_mode)


def test_rejected_markup_is_resent_as_plain_text():
    rec = Recorder()
    out = asyncio.run(resend_unformatted(rec, None, _send("<b>chicken</b")))
    assert out == "delivered"
    assert rec.attempts == ["HTML", None], rec.attempts


def test_a_message_with_no_parse_mode_is_not_retried():
    rec = Recorder(always_fail=True)
    with pytest.raises(TelegramBadRequest):
        asyncio.run(resend_unformatted(rec, None, _send("plain", parse_mode=None)))
    assert len(rec.attempts) == 1


def test_unrelated_bad_requests_are_not_swallowed():
    """Retrying a genuinely malformed call would hide a real bug."""

    async def boom(bot, method):
        raise TelegramBadRequest(method=method, message="Bad Request: chat not found")

    with pytest.raises(TelegramBadRequest, match="chat not found"):
        asyncio.run(resend_unformatted(boom, None, _send("hi")))


def test_retry_happens_at_most_once():
    """No loop: the second failure propagates instead of retrying forever."""
    rec = Recorder(always_fail=True)
    with pytest.raises(TelegramBadRequest):
        asyncio.run(resend_unformatted(rec, None, _send("<b>x</b")))
    assert len(rec.attempts) == 2


@pytest.mark.parametrize(
    "name",
    [
        "chicken_breast",
        "Beef, ground, 85% lean *raw*",
        "yoghurt [plain]",
        "rice `arborio`",
        "a_b_c_d",
        "salt & pepper",
        "<b>not a tag</b>",
        "1 < 2 > 0",
        "Farmer's cheese",
    ],
)
def test_escaping_neutralises_every_html_metacharacter(name: str):
    """Only `& < >` carry meaning in Telegram HTML, and all three must go.

    An unescaped `<` is what produces "can't parse entities" and a dropped
    message. Markdown's `_` and `*` are now ordinary characters and must
    survive untouched — mangling food names was the cost of the old scheme.
    """
    escaped = _esc(name)
    assert "<" not in escaped
    assert ">" not in escaped
    # Every surviving & must open a real entity, not sit bare.
    assert not re.search(r"&(?!(amp|lt|gt|quot|#x27);)", escaped)
    # Markdown metacharacters are left alone now.
    for ch in ("_", "*", "`", "[", "]"):
        assert escaped.count(ch) == name.count(ch), f"{name!r} -> {escaped!r} altered {ch!r}"


def test_escaping_is_reversible_to_the_original_text():
    """What the user sees must be what they typed."""
    for name in ("salt & pepper", "1 < 2", "chicken_breast", "<b>x</b>"):
        assert unescape(_esc(name)) == name


def test_rendered_cards_are_well_formed_html():
    """Unbalanced tags are the new version of an unbalanced underscore."""
    out = day_card(DAY, PROGRESS, [], coverage={1178: 0.0}, pct_measured=97.0)
    _assert_balanced(out)


def _assert_balanced(html: str) -> None:
    stack: list[str] = []
    for tag in re.finditer(r"<(/?)([a-z]+)[^>]*>", html):
        closing, name = tag.group(1), tag.group(2)
        if closing:
            assert stack and stack[-1] == name, f"unbalanced </{name}> in:\n{html}"
            stack.pop()
        else:
            stack.append(name)
    assert not stack, f"unclosed {stack} in:\n{html}"


def test_pre_blocks_contain_no_nested_tags():
    """Telegram does not accept markup inside <pre>."""
    out = day_card(DAY, PROGRESS, [], coverage={1178: 0.42}, pct_measured=97.0)
    for block in re.findall(r"<pre>(.*?)</pre>", out, re.DOTALL):
        assert "<" not in block, f"nested markup inside <pre>:\n{block}"
