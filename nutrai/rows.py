"""The one shape every rendering and ranking function actually depends on.

`asyncpg` returns query results as `asyncpg.Record`, which is subscriptable by
column name and by position but is *not* a `Mapping` — it does not inherit from
one and it does not register as one. Annotating a render function's rows as
`Mapping[str, Any]` would therefore be false: it would reject every real call
site in `bot.py` and `jobs/notify.py`.

`asyncpg.Record` alone would be false in the other direction. The card tests
(`tests/test_render.py`, `tests/test_suggest.py`) build their rows as plain
dicts, deliberately — a card is a pure function of named columns, and forcing a
live database into a display test would buy nothing and cost the seam. Both
callers are legitimate.

What both have in common, and all these functions ever use, is subscripting by
column name. That is what this protocol says, and nothing more.

`__contains__` is here too, because several cards ask whether an optional
column is present at all (`"amount_supplement" in r`). That one was checked
against a live `Record` rather than assumed: `"alpha" in record` is True and
`7 in record` is False, so `in` tests keys on a Record exactly as it does on a
dict.

The caveat that keeps the protocol this small: iteration does *not* agree.
`for x in some_dict` yields keys; `for x in some_record` yields values (checked
the same way). So `__iter__`, `keys`, `values` and `items` stay out, and
anything added here later needs the same check first.

Note also that `asyncpg` 0.31 ships `.pyi` files but no `py.typed` marker, so a
type checker sees `asyncpg.Record` as `Any` and this protocol cannot catch a
mistake on the database side. It still catches the ones on the other side — a
list of tuples, a bare dataclass — and it documents the contract for the reader,
which is the part `Any` was failing to do.
"""

from __future__ import annotations

from typing import Any, Protocol


class Row(Protocol):
    """A database row, or a dict standing in for one, addressed by column name."""

    def __getitem__(self, key: str) -> Any: ...
    def __contains__(self, key: object) -> bool: ...
