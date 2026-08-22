# Assessment 5 — weak types

What `Any`, bare `dict`/`list`, and missing annotations were actually holding in
`nutrai/`, how each was verified, and what was changed.

The rule applied throughout: **a wrong annotation is worse than `Any`**, because
`Any` admits it knows nothing and a wrong name claims a guarantee the code does
not have. Three annotations were reverted to `Any` during this work for exactly
that reason, and one wrong guess was caught by mypy before it shipped (§5).

---

## 1. Inventory, before

Counted over `nutrai/**/*.py` with comments stripped.

| weak form | before | after |
|---|---:|---:|
| bare `Any` in an annotation position (`x: Any`, `-> Any`, `**kw: Any`) | 58 | 4 |
| `Sequence[Any]` | 36 | 1 |
| `list[Any]` | 13 | 2 |
| bare `dict` / `list` / `tuple` / `set` as an annotation | 30 | **0** |
| functions with a missing or incomplete annotation | 15 | **0** |
| `dict[…, Any]` | 33 | 58 |

The last row goes *up*, and that is the change working rather than failing: 30
bare `dict`s became `dict[str, Any]`. The `Any` there is the value type of a
decoded `jsonb` payload or of an Anthropic tool result, and it is honest — see
§6.

Distribution of `Any` before, by file: `bot.py` 59, `render.py` 36, `parse.py`
18, `client.py` 8, `db.py` 8, `off.py` 5, `plan.py` 4, `notify.py` 3,
`suggest.py` 2.

### The 15 unannotated functions

`off.py:63` · `jobs/audit.py:264` · `jobs/report.py:30,57` ·
`jobs/notify.py:131,191,240,255,274,293` · `bot.py:53,54,60,4242`

Twelve of the fifteen were one parameter: `bot`, the aiogram `Bot`.

---

## 2. What the research established

### 2.1 asyncpg ships stubs but no `py.typed` — so `Record` is `Any` to a checker

`/Users/Jacob/Projects/nutrAI/.venv/lib/python3.14/site-packages/asyncpg/` at
version 0.31.0 contains `protocol/record.pyi`, `protocol/protocol.pyi` and
`pgproto/pgproto.pyi` — but **no `py.typed` marker**, so PEP 561 says a checker
must ignore them. Verified: mypy reports
`Skipping analyzing "asyncpg": module is installed, but missing library stubs
or py.typed marker`.

The consequence is load-bearing for every decision below. Annotating a row as
`asyncpg.Record` is *documentation for a reader* and buys **zero** checking: to
mypy the type is `Any`, assignable to and from anything. That is a reason to
prefer it over `Any` (it names the runtime class truthfully) and not a reason to
expect it to catch bugs.

`record.pyi` declares the surface: `__getitem__` (overloaded on `str`, `int`,
`slice`), `get`, `keys`, `values`, `items`, `__iter__`, `__contains__`,
`__len__`. `Record` is **not** a `Mapping` — it neither subclasses nor registers
as one — so `Mapping[str, Any]` would be a false annotation for any function
that real code calls with a query result.

### 2.2 `in` agrees between `dict` and `Record`; iteration does not

Several cards do `"amount_supplement" in r`, which only works if `in` tests
*keys* on a `Record`. Rather than assume, this was checked against a live
`Record` (one read-only `SELECT 7 AS alpha, 'beta' AS gamma`, no table touched):

```
'alpha' in r  -> True     (key)
7 in r        -> False    (value)
'beta' in r   -> False    (value)
list(iter(r)) -> [7, 'beta']        <- values, not keys
dict(r)       -> {'alpha': 7, 'gamma': 'beta'}
```

So `in` is key-based on both, and safe to rely on. **Iteration diverges**:
`for x in some_dict` yields keys, `for x in some_record` yields values. That is
the trap that keeps the `Row` protocol (§3) minimal, and it is recorded in
`nutrai/rows.py` so the next person widening it checks first.

### 2.3 The render layer is called with *both* Records and dicts, deliberately

`tests/test_render.py:15` and `tests/test_suggest.py:14` build their rows as
plain dicts. Production calls the same functions with `asyncpg.Record`. Neither
caller is wrong — a card is a pure function of named columns, and the dict is
the seam that keeps a display test out of the database.

So for `core/render.py` and `core/suggest.py`, **neither** `asyncpg.Record`
**nor** `Mapping[str, Any]` is true. That is what §3 solves.

---

## 3. `nutrai/rows.py` — a `Row` protocol, new file

```python
class Row(Protocol):
    def __getitem__(self, key: str) -> Any: ...
    def __contains__(self, key: object) -> bool: ...
```

Two members, both verified present and semantically identical on `dict` and
`Record` (§2.2). Nothing else: `keys`/`values`/`items`/`__iter__` are excluded
because iteration disagrees.

Verified with a mypy probe that `list[asyncpg.Record]` and `list[dict[str,
Any]]` both satisfy `Sequence[Row]` and `list[tuple[str, float]]` does not.

It replaces 35 of the 36 `Sequence[Any]` annotations. It cannot catch a mistake
on the database side (§2.1) but it does catch one on the other side — a list of
tuples, a bare dataclass — and it tells the reader what the function needs,
which is the job `Any` was failing.

---

## 4. Changes made — HIGH confidence

Every one below was verified by reading the producing function's own return
annotation or by reading every call site.

| what | where | verified how |
|---|---|---|
| `u: Any` → `asyncpg.Record`, 45 sites | `bot.py` | every `u` in the module comes from `_user()` or `db.get_or_create_user()`; the latter is already annotated `-> asyncpg.Record`. Grepped for any other producer: none. |
| `_user(msg) -> Any` → `-> asyncpg.Record` | `bot.py:150` | same |
| `payload: dict` → `dict[str, Any]`, 15 sites | `bot.py` | the `pending_action.payload` `jsonb` column, decoded by `json.loads` in `db.take_pending`/`latest_pending` |
| `put_pending(payload: dict)`, `take_pending() -> dict \| None`, `latest_pending() -> dict \| None` | `db.py:991,999,1045` | same column, both ends |
| `PROMPT_CONSUMERS: dict[str, Any]` → `dict[str, PromptConsumer]`, with `consumes`/`register` typed | `bot.py:65-73` | all 15 `@consumes`-decorated functions share the exact signature `(Message, Record, str, dict[str, Any]) -> Awaitable[bool]`; enumerated by grepping `-A1 "@consumes("` |
| `bot` (unannotated) → `Bot`, 8 sites | `jobs/notify.py`, `jobs/report.py`, `jobs/audit.py` | the single producer is `bot.py:4324 Bot(settings.telegram_token)`, threaded through `start_scheduler(bot)` and `sched.add_job(..., args=[bot])` |
| `sched` (unannotated) → `AsyncIOScheduler` | `jobs/report.py:62` | sole caller is `notify.start_scheduler`, which constructs `AsyncIOScheduler(timezone="UTC")` |
| `resend_unformatted(make_request, bot, method)` fully typed | `bot.py:4265` | copied from aiogram's own `RequestMiddlewareType` protocol in `aiogram/client/session/middlewares/base.py`; proved by mypy accepting `bot.session.middleware(resend_unformatted)` |
| `price(usage: Any)` → `Usage` | `llm/client.py:42` | sole caller passes `msg.usage` where `msg` is `anthropic.types.Message`; `anthropic.types.Usage` imported and confirmed present in 0.122.0 |
| `_candidates(...) -> list[Any]` → `list[asyncpg.Record]`; `pooled`, `need_model` likewise | `llm/parse.py:269,288,377` | rows come from `db.search_foods`, annotated `-> list[asyncpg.Record]` |
| `crossed`, `best` tuples `Any` → `asyncpg.Record` | `jobs/notify.py:71,100` | elements are rows from `p.fetch(...notification_rule...)` |
| `_profiles_con(con: Any)` → `asyncpg.Pool \| asyncpg.Connection` | `db.py:421` | two call sites, one passes the pool (`db.py:230`), one a connection (`db.py:404`) — both is the truth, not one |
| `ops: list[Any]` → `list[dsl.Op]` | `bot.py:3371,3401` | `dsl.Op` is an existing union at `core/dsl.py:128`; sources are `dsl.parse_ops()` and `RepeatCommand.ops`, both already `list[Op]` |
| `tpl: tuple[Any, list[Any]]` → `tuple[asyncpg.Record, list[asyncpg.Record]]` | `bot.py:3875` | `db.template_by_slug` is annotated `-> tuple[asyncpg.Record, list[asyncpg.Record]] \| None` |
| `flr: Any` → `insight.FatLossRate \| None`; `tuple[str, Any]` → `tuple[str, InlineKeyboardMarkup]` | `bot.py:1890,3111` | `insight.fat_loss_rate` is annotated `-> FatLossRate \| None`; the second element is built inline as `InlineKeyboardMarkup(...)` |
| `PROFILE_VALIDATORS: dict[str, Any]` → `dict[str, Callable[[str], Any]]` | `bot.py:1151` | all 13 values read; every one is a callable of one `str`. Applied as `PROFILE_VALIDATORS[field](raw)` |
| various row params `Sequence[Any]`/`list[Any]` → `Sequence[asyncpg.Record]` | `bot.py` `_csv`, `_training_keyboard`, `_describe_activity`, `_supp_manage_keyboard`, `_send_supp_picker`, `_button_label`, `_supp_keyboard`, `_matched_names` | each call site traced to a `db.*` function with an `asyncpg.Record` return annotation |
| 35 × `Sequence[Any]` → `Sequence[Row]`, plus `dict[Any, list[Any]]` → `dict[dt.date, list[Row]]` | `core/render.py`, `core/suggest.py` | §3 |
| `findings: Sequence[Any]` → `Sequence[Finding]`, `suggestions` → `Sequence[Suggestion]`, `flr` → `FatLossRate` | `core/render.py:828,1907,2006` | attribute access (`f.severity`), not subscripting; imported under `TYPE_CHECKING` because audit/suggest/insight all import render back |
| bare `dict` params parameterised | `render.py` (`ctx`, `names`, `units`, `times`, `panel`, `per_100g`, `data`, `p`, `by_day`, `by_name`, `grouped`), `off.py` (`product`, `_get`), `bot.py` (`meals`, `comp`, `p`) | each traced to its producer: `db.week_context -> dict[str, Any]`, `db.slot_times -> dict[str, dt.time]`, `db.nutrient_units -> dict[int, str]`, `llm.per_100g -> tuple[dict[int, float], …]`, `db.day_coverage -> dict[int, float]` |
| `_first_brand(brands: Any)` → `object` | `off.py:107` | the body `isinstance`-narrows; it genuinely accepts anything, and `object` says that while still forbidding attribute access |

Also added: an **advisory** `[tool.mypy]` section in `pyproject.toml`
(`ignore_missing_imports = true` only). mypy is deliberately *not* added to the
dev extra and nothing runs it; the section exists so an ad-hoc run is readable
rather than opening with eight import-untyped notices about asyncpg and
apscheduler. It cannot fail the build because no build invokes it.

---

## 5. Deliberately left as `Any`, and why

### `render.confirm_card(components: Sequence[Any])` — reverted

This one was annotated `Sequence[ResolvedComponent]` and mypy immediately proved
it a lie:

```
bot.py:     error: Argument 2 to "confirm_card" has incompatible type
                   "list[Component]"; expected "Sequence[ResolvedComponent]"  (x2)
render.py:  error: Value of type "ResolvedComponent" is not indexable  (x3)
```

The function is called with `nutrition.ResolvedComponent` from the parse path
and with `dsl.Component` from the repeat path — two unrelated dataclasses
sharing no base — and its body then falls back to subscripting
(`getattr(c, "label", None) or c["label"]`) for a row-shaped component.
`Sequence[ResolvedComponent | dsl.Component]` would be narrower than the code's
own intent and would mark the subscript fallback dead. `Any` is the honest type
and now carries a comment saying so.

### `db.set_profile_field(value: Any)` (`db.py:1515`)

One function writes to any of thirteen `app_user` columns of six different
types. The union is `str | int | float | dt.date | None`, but the value arrives
from `PROFILE_VALIDATORS[field](raw)` where the validator is chosen by a runtime
string — so a union would be checked at neither end and would only look precise.

### `db.record_llm_call(**kw: Any)` and `db.args: list[Any]` (`db.py:961,222,1129`)

`**kw` is spread straight into an INSERT column list; `args` is a heterogeneous
asyncpg parameter list built conditionally. Both are `list[Any]`/`Any` in the
same sense asyncpg's own `execute(*args)` is.

### `bot._ask(**kw: Any)` (`bot.py:76`)

Straight passthrough to `aiogram`'s `Message.answer(**kwargs)`. Typing it means
restating aiogram's signature and going stale the next time it changes.

### `dict[str, Any]` on Anthropic tool payloads (`llm/parse.py`, `llm/client.py`)

`ParsedMeal.items`, `ParsedMeal.raw`, `tool`, `system`, `content`, and the return
of `modifier_ops`/`per_100g`'s input are the model's own tool output and the
request blocks going the other way. A `TypedDict` is *possible* here — the
schemas are in `llm/schemas.py` — and is listed as MEDIUM below rather than
done, because the readers use `.get()` throughout precisely because a field can
be absent, and a non-`total` `TypedDict` full of `NotRequired` would document
less than the schema file already does.

---

## 6. mypy, before and after

Run from a scratch venv (`mypy 2.3.1`) against the project interpreter; the
project `.venv` was not modified.

```
mypy --python-executable /Users/Jacob/Projects/nutrAI/.venv/bin/python nutrai/
```

| flags | before | after |
|---|---:|---:|
| defaults (no config) | 206 | 210 |
| `--ignore-missing-imports` | 202 | 202 |
| `--ignore-missing-imports --disallow-untyped-defs --disallow-incomplete-defs` | **217** | **202** |
| of which `no-untyped-def` | **15** | **0** |

The +4 on the first row is entirely `import-untyped` **notices** — `asyncpg` is
now imported by three more modules and `apscheduler.schedulers.asyncio` by one,
and neither ships `py.typed`. Zero new *type* errors were introduced: every new
line in the diff was inspected and the only ones that were real (the
`confirm_card` mismatch, `Row` needing `__contains__`, a `Mapping` vs `dict`
narrowing on `morning_note`) were fixed before this was written.

The 202 that remain are almost entirely (154) one pre-existing hazard that is
**not** in scope here and is worth its own pass: aiogram types
`CallbackQuery.message` as `Message | InaccessibleMessage | None` and
`Message.from_user` as optional, and every callback handler in `bot.py`
dereferences them unguarded. That is a real `AttributeError` waiting on an
inaccessible message, not a typing nit.

`ruff check nutrai/` produces byte-identical findings per rule before and after
(115 with the installed ruff; CLAUDE.md's "~thirty" predates this version). The
resting state was not disturbed.

---

## 7. Recommendations not implemented

### MEDIUM confidence

1. **`TypedDict` per `pending_action.payload` kind.** The writers *are*
   enumerable — every one is a `db.put_pending(user_id, kind, {...})` literal —
   so a `TypedDict` per kind is buildable. Worth it for `supp_pick`
   (`selected`/`day`/`reason`) and `repeat_menu` (`ids`/`components`), which are
   read in several places. Not done here because it wants a
   `put_pending`/`take_pending` overload pair keyed on `kind` to be useful, and
   that is a design change rather than an annotation.

2. **`ParsedMeal.items` as a `TypedDict`.** The shape is fixed by `PARSE_TOOL`
   in `llm/schemas.py`. See §5 for why it would document less than it looks.

3. **`_matched_names(components: Sequence[ResolvedComponent])`** (`bot.py:3891`)
   is annotated but the body uses `getattr(c, "fdc_id", None)` — the same
   polymorphic hedge that made `confirm_card` wrong. Its one call site passes
   `res.components` (`list[ResolvedComponent]`), so the annotation is currently
   true; if a second caller appears, check it rather than trusting this.

4. **`core/plan.py`'s `dict[str, Any]` proposal payload.** Deliberately unwired
   code (CLAUDE.md, Known gaps). Type it when it is wired, against the
   `PLAN_TOOL` schema, not before.

### LOW confidence

5. **`suggest.rank(snapshots: Mapping[int, Mapping[str, Any]])`** — the inner
   mapping has a known shape (`id`/`name`/`slug`/`slot`/`times_logged`/
   `nutrients`) but the only producer is a `db` function returning rows built in
   Python, and the test builds it by hand. A `TypedDict` would work; the gain
   over the current annotation is small.

6. **`bot.resend_unformatted`'s test passes `None` for `bot: Bot`.** That
   annotation predates this work and is mildly false in the test's eyes. The
   production call site is correct. Not worth widening the annotation to
   `Bot | None` to accommodate a fake.

7. **Vendoring an `asyncpg` `py.typed`.** Would turn every `asyncpg.Record`
   annotation from documentation into a checked type, and every `Pool`/
   `Connection` method call into a checked call. It is a patch against a
   third-party package and would need re-applying on every upgrade. Only worth
   it if the aiogram-optional hazard in §6 is also being addressed and a checker
   is being put in the loop for real.
