"""A Telegram that never leaves the process.

The point of this file is that the integration test drives the *real*
dispatcher — real handler registration, real filter evaluation, real
`msg.answer()` calls — rather than calling the handler bodies directly. Three of
the four things that break first in a bot like this (handler registration order,
callback data round-tripping, and message editing on a message that was created
by an earlier reply) are invisible to a test that skips aiogram.

Outbound API calls are recorded instead of sent, so a test can assert on exactly
the text a human would have seen.
"""

from __future__ import annotations

import datetime as dt
import itertools
from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    GetFile,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    File,
    Message,
    PhotoSize,
    Update,
    User,
)

BOT_ID = 424242
CHAT_ID = 123456789


@dataclass
class Sent:
    """One outbound API call, as the user would have experienced it."""

    method: str
    text: str
    parse_mode: str | None = None
    reply_markup: Any = None
    message_id: int | None = None

    @property
    def buttons(self) -> list[str]:
        if not self.reply_markup:
            return []
        return [b.callback_data for row in self.reply_markup.inline_keyboard for b in row]


class RecordingSession(BaseSession):
    """Answers every Bot API call locally and keeps a transcript."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[Sent] = []
        self._ids = itertools.count(1000)
        self._messages: dict[int, Message] = {}

        self.photo_bytes: bytes = b""

    async def close(self) -> None:  # pragma: no cover - nothing to close
        return None

    async def stream_content(
        self, url: str, headers: Any = None, timeout: int = 30,
        chunk_size: int = 65536, raise_for_status: bool = True,
    ):
        """Serve the photo bytes a test handed us, so bot.download_file works."""
        yield self.photo_bytes

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        name = type(method).__name__

        if isinstance(method, SendMessage):
            mid = next(self._ids)
            msg = _message(mid, method.text, bot)
            self._messages[mid] = msg
            self.sent.append(
                Sent(name, method.text, method.parse_mode, method.reply_markup, mid)
            )
            return msg

        if isinstance(method, EditMessageText):
            mid = int(method.message_id or 0)
            msg = _message(mid, method.text, bot)
            self._messages[mid] = msg
            # An edit replaces what the user is looking at. Model it as a
            # replacement of the original entry in the transcript, so a test
            # asserting on "what is on screen" cannot pass by matching a
            # placeholder like "parsing…" that was overwritten a second later.
            for i, s in enumerate(self.sent):
                if s.message_id == mid:
                    self.sent[i] = Sent(
                        name, method.text, method.parse_mode, method.reply_markup, mid
                    )
                    break
            else:
                self.sent.append(
                    Sent(name, method.text, method.parse_mode, method.reply_markup, mid)
                )
            return msg

        if isinstance(method, AnswerCallbackQuery):
            return True

        if isinstance(method, GetFile):
            return File(
                file_id=method.file_id,
                file_unique_id=f"u{method.file_id}",
                file_path=f"photos/{method.file_id}.jpg",
                file_size=len(self.photo_bytes),
            )

        raise AssertionError(f"unstubbed Telegram call: {name}")

    # ------------------------------------------------------------- helpers

    def texts(self) -> list[str]:
        return [s.text for s in self.sent]

    def last(self) -> Sent:
        return self.sent[-1]

    def find(self, needle: str) -> Sent | None:
        return next((s for s in reversed(self.sent) if needle in s.text), None)

    def clear(self) -> None:
        self.sent.clear()


def _user() -> User:
    return User(id=CHAT_ID, is_bot=False, first_name="Test", username="test")


def _chat() -> Chat:
    return Chat(id=CHAT_ID, type="private")


def _message(mid: int, text: str, bot: Bot) -> Message:
    return Message(
        message_id=mid,
        date=dt.datetime.now(dt.timezone.utc),
        chat=_chat(),
        from_user=User(id=BOT_ID, is_bot=True, first_name="nutrai"),
        text=text,
    ).as_(bot)


@dataclass
class FakeTelegram:
    bot: Bot = field(init=False)
    session: RecordingSession = field(init=False)
    _updates: itertools.count = field(default_factory=lambda: itertools.count(1))

    def __post_init__(self) -> None:
        self.session = RecordingSession()
        self.bot = Bot(token=f"{BOT_ID}:test-token-not-a-real-one", session=self.session)

    def text_update(self, text: str) -> Update:
        return Update(
            update_id=next(self._updates),
            message=Message(
                message_id=next(self.session._ids),
                date=dt.datetime.now(dt.timezone.utc),
                chat=_chat(),
                from_user=_user(),
                text=text,
            ),
        )

    def photo_update(
        self, jpeg: bytes, caption: str | None = None, media_group_id: str | None = None
    ) -> Update:
        """A photo message. Telegram sends several PhotoSizes; the bot must take
        the largest, because the smaller ones lose a scale display."""
        self.session.photo_bytes = jpeg
        fid = f"file{next(self._updates)}"
        return Update(
            update_id=next(self._updates),
            message=Message(
                message_id=next(self.session._ids),
                date=dt.datetime.now(dt.timezone.utc),
                chat=_chat(),
                from_user=_user(),
                caption=caption,
                media_group_id=media_group_id,
                photo=[
                    PhotoSize(file_id=f"{fid}-s", file_unique_id=f"{fid}-s",
                              width=90, height=68, file_size=900),
                    PhotoSize(file_id=fid, file_unique_id=fid,
                              width=1280, height=960, file_size=len(jpeg)),
                ],
            ),
        )

    def callback_update(self, data: str, on_message_id: int) -> Update:
        source = self.session._messages.get(on_message_id) or _message(
            on_message_id, "", self.bot
        )
        return Update(
            update_id=next(self._updates),
            callback_query=CallbackQuery(
                id=f"cb{next(self._updates)}",
                from_user=_user(),
                chat_instance="test",
                data=data,
                message=source,
            ),
        )
