# Assessment 2 — type definitions and what should be shared

Scope: `nutrai/`, `scripts/`, `tests/`. Line numbers are as of this commit.

## 0. Summary of the shape of the codebase

- **28 dataclasses.** That is the entire type vocabulary.
- **Zero** `TypedDict`, `NamedTuple`, `Protocol`, `Enum`/`IntEnum`/`StrEnum`,
  and zero explicit `TypeAlias`. One `Literal` (`dsl.RepeatCommand.selector_kind`).
- One union alias: `dsl.Op` (`core/dsl.py:126`).
- Query results are `asyncpg.Record` throughout, by deliberate choice
  (CLAUDE.md Style: "Raw SQL via asyncpg. No ORM. The schema is the source of
  truth."). No dataclass mirrors a table, and none should.

The absence of enums is not an oversight to correct wholesale. Most of the
string vocabularies here are *database column values* — `grams_source`,
`log_entry.status`, `activity.intensity`, `supplement.slot` — and the schema,
not Python, is their authority. An `Enum` would put a second authority beside
the first without removing either.

---

## 1. Inventory

### `nutrai/core/`

| type | file:line | what it is |
|---|---|---|
| `ResolvedComponent` | `core/nutrition.py:17` | a component that has a USDA row: label, `fdc_id` (required), grams, yield factor, sigma, `grams_source`, display `count` |
| `EnergyCheck` | `core/nutrition.py:120` | result of the Atwater cross-check |
| `MassEstimate` | `core/estimate.py:59` | one component's mass with its 1-sigma and its provenance |
| `Scale` | `core/dsl.py:77` | repeat op: multiply |
| `TotalGrams` | `core/dsl.py:82` | repeat op: set the plate total |
| `SetComponent` | `core/dsl.py:87` | repeat op: set one component |
| `AddComponent` | `core/dsl.py:93` | repeat op: add a component |
| `DropComponent` | `core/dsl.py:99` | repeat op: drop a component |
| `SetTime` | `core/dsl.py:104` | repeat op: override the clock |
| `SetSlot` | `core/dsl.py:110` | repeat op: override the meal slot |
| `SetDate` | `core/dsl.py:115` | repeat op: file it on an earlier day |
| `Op` | `core/dsl.py:126` | union alias over the eight above |
| `RepeatCommand` | `core/dsl.py:132` | selector + ops + unparsed tokens |
| `Component` | `core/dsl.py:405` | a component *as the DSL manipulates it*: `fdc_id` may be `None`, carries `state`, no sigma |
| `DayScore` | `core/render.py:1066` | floors reached / assessable / short / breached, plus coverage |
| `Suggestion` | `core/suggest.py:35` | a dish ranked against today's outstanding gaps |
| `Fast` | `core/fasting.py:16` | one gap between intakes |
| `EatingWindow` | `core/fasting.py:28` | first bite to last bite on one day |
| `Finding` | `core/insight.py:83` | one correlation: rho, p, verdict, caveat |
| `FatLossRate` | `core/insight.py:145` | regression of weight on date, converted to an energy rate |
| `Converted` | `core/supplements.py:32` | one label line accepted, in the system's own unit |
| `Rejected` | `core/supplements.py:39` | one label line refused, with the reason |

### `nutrai/llm/`, `nutrai/jobs/`, top level

| type | file:line | what it is |
|---|---|---|
| `ToolResult` | `llm/client.py:61` | one API call: data, model, four token counts, latency, cost |
| `ParsedMeal` | `llm/parse.py:75` | model output before resolution — items are raw tool JSON |
| `Resolution` | `llm/parse.py:184` | resolved components + grams sources + unresolved + weak matches |
| `Verdict` | `llm/parse.py:505` | ok + warnings from the deterministic pre-confirm checks |
| `Finding` | `jobs/audit.py:77` | one audit hit: code, severity, summary, detail, entry id |
| `Settings` | `config.py:160` | env-derived runtime settings |

`scripts/` (`bootstrap.py`, `load_usda.py`, `pin_foods.py`) defines **no**
types at all — plain functions over asyncpg rows.

### `tests/`

| type | file:line | what it is |
|---|---|---|
| `Sent` | `tests/fake_telegram.py:45` | one outbound Bot API call, as the user would see it |
| `FakeTelegram` | `tests/fake_telegram.py:163` | dispatcher harness |
| `Recorder` | `tests/test_bot_resilience.py:25` | plain class, records `answer()` calls |
| `_Row(dict)` | `tests/test_profile.py:70` | `asyncpg.Record` stand-in |
| `R(dict)` | `tests/test_commands.py:234` | `asyncpg.Record` stand-in |
| five `class C` | `tests/test_render.py:81, 109, 125, 294, 303` | minimal component stand-ins |

### String-literal vocabularies (the enum-shaped things)

| vocabulary | definitions | notes |
|---|---|---|
| measured grams sources | **was** four separate literals; now `estimate.MEASURED_SOURCES` (`core/estimate.py:55`) | also hard-coded in `sql/002_views.sql` and `sql/008_repeat_provenance.sql`, which cannot import it |
| full `grams_source` vocabulary | `llm/schemas.py:59` enum (`scale, stated, package, estimate, reference_object`); `core/estimate.py:63` comment (`scale, stated, package, prior, estimate`); `core/render.py:128` mark table (`scale, stated, package, prior`) | **three different sets on purpose** — `reference_object` is only a model output, `prior` is only ever produced in Python. Not one enum. |
| meal slots | `dsl.SLOTS` (`core/dsl.py:43`, 7 words accepted from the user); `dsl.SLOT_BOUNDARIES` (`core/dsl.py:513`, 4 written from the clock); `llm/schemas.py:26` (5 offered to the model); `render.SLOT_ABBREV` (`core/render.py:434`, 5); `render.SLOT_FALLBACK` (`core/render.py:691`, 5) | five sets, three sizes |
| supplement slots | `db.SUPPLEMENT_SLOTS` (`db.py:1713`); `bot.SLOT_ASSIGN`/`bot.SLOT_TIME` regexes (`bot.py:1735, 1737`); `render.SLOT_LABELS` (`core/render.py:1801`); `render.SLOT_SHORT` (`core/render.py:1818`); a bare tuple at `core/render.py:1862` | six enumerations of the same four words |
| audit severity | `jobs/audit.py:79` (comment), `jobs/audit.py:258`, `core/render.py:826, 829, 839` | `error / warn / info` |
| training intensity | `http_api.INTENSITIES` (`http_api.py:57`); `render._INTENSITY_MARK` (`core/render.py:1730`); `("hard","max")` at `core/render.py:1772` and in SQL at `db.py:1343`, `core/plan.py:109` | validated in one place, rendered in another |
| nutrient ids | `config.py:117-127` named constants; bare literals remain at `off.py:157`, `core/render.py:2357, 2382` | `bot.py`'s two bare `1008`s are fixed below |

---

## 2. Recommendations

### HIGH confidence — implemented in this commit

**H1. One `MEASURED_SOURCES` tuple instead of four copies of
`("scale", "stated", "package")`.**

The literal appeared at `core/estimate.py:115` (`choose_mass`),
`core/estimate.py:164` (`day_confidence`), `llm/parse.py:245` (`_mass_for`)
and `bot.py:3948` (`all_hard`). All four ask the same question — *did this mass
come from the world or from a guess?* — and all four are load-bearing:

- `choose_mass` uses it to decide whether a portion prior may override;
- `day_confidence` uses it for the measured fraction of the day, "the single
  most useful number in the whole summary" by its own docstring;
- `_mass_for` uses it to decide whether to look up a declared portion at all;
- `all_hard` uses it to decide whether a parse is offered for one-tap confirm.

This is the strongest case in the codebase because divergence would not crash.
It would produce four subtly different definitions of "weighed" giving four
different answers about one plate, and it is the same set invariant 7 turns on.
Now `nutrai/core/estimate.py:55`, with the reasoning and a pointer to the SQL
copies that cannot import it.

Layering is clean: `core/estimate.py` imports nothing from the package;
`llm/parse.py` already imported from `core.estimate`; `bot.py` already imported
the `estimate` module.

**H2. `bot.py` re-imported `ResolvedComponent` inside a function under the
alias `_RC`** (was `bot.py:3557`) while the same name is imported at module
level (`bot.py:28`) and used unaliased 70 lines later. One concept, two spellings,
in one function. Removed; the local list comprehension now uses
`ResolvedComponent` like the other three construction sites.

**H3. Two bare `1008` literals in `bot.py`** (`bot.py:1838`, `bot.py:4165`)
replaced with `ENERGY_KCAL`, which the module already imports and already uses
at `bot.py:2261`. Zero behavioural change; it removes the last magic energy id
from a module that had otherwise named it.

Not done for `off.py:157` and `core/render.py:2357, 2382`: neither module
imports `config` today, and `core/render.py` deliberately imports nothing from
the package at all. Adding an import there is a layering decision, not a
cleanup — see M4.

### MEDIUM confidence — recommended, not done

**M1. `SUPPLEMENT_SLOTS` is enumerated six times.** `db.py:1713` is the
validator; `bot.py:1735` and `bot.py:1737` repeat the four words inside regex
alternations; `core/render.py:1862` repeats them as a bare tuple beside two
dicts (`SLOT_LABELS`, `SLOT_SHORT`) that are keyed on them. The dicts are
legitimate per-slot data and should stay; the *ordering* and the *membership*
should have one source. A fifth slot added to `db.py` today would be
unassignable (the regex would not match it), invisible in the settings table,
and would `KeyError` at `core/render.py:1864`.

The natural home is `core/supplements.py` (imports nothing, is the supplement
domain module), re-exported from `db.py` so `db.SUPPLEMENT_SLOTS` keeps
working. Left undone because it makes `core/render.py` import from a sibling
core module for the first time, and that is the owner's call, not a mechanical
one.

**M2. Training intensity has a validator (`http_api.INTENSITIES`) and a
renderer (`render._INTENSITY_MARK`) with the same four keys, plus `("hard",
"max")` written out at `core/render.py:1772` and in SQL twice.** Same shape of
problem as M1 and same layering obstacle. Lower stakes: an unknown intensity
renders as an empty mark rather than raising.

**M3. Four near-identical `asyncpg.Record` → `ResolvedComponent` conversions**
at `db.py:398`, `bot.py:3559`, `bot.py:3798` and (from a `dsl.Component`)
`bot.py:3632`. A `ResolvedComponent.from_row(r)` classmethod would collapse the
three row-shaped ones. Held back because the three rows are not identical —
`db.py:398` and `bot.py:3559` read `grams_sigma` from the row, `bot.py:3798`
recomputes sigma from provenance on purpose (there is a comment saying why:
storing 0 would make a corrected meal look better measured than an uncorrected
one). A shared constructor that hid that difference would be worse than the
duplication.

**M4. Bare nutrient ids outside `bot.py`:** `off.py:157` and
`core/render.py:2357, 2382` compare against `1008`. Both would need a new
`config` import. `core/render.py`'s zero-import posture looks deliberate
(invariant 4: template and SQL only), so this needs a decision rather than an
edit.

**M5. Meal-slot vocabularies have diverged and it is visible.** `dsl.SLOTS`
accepts `brunch` and `supper` from `#slot`, but `render.SLOT_ABBREV` and
`render.SLOT_FALLBACK` know only the five that `slot_for_hour` can produce. A
`#supper` entry therefore renders with a blank slot column in `/today` and a
generic `•` icon. This is a small display bug wearing a type-consolidation
costume; recorded here rather than fixed because the right answer might be to
narrow `dsl.SLOTS` instead of widening the two dicts, and that changes what
input is accepted.

### LOW confidence — recorded, not recommended

**L1. `dsl.Component` and `nutrition.ResolvedComponent` must stay separate.**
They look mergeable — five overlapping fields — and are not the same thing.
`Component.fdc_id` is `int | None` because the DSL manipulates a plate that may
still contain an unresolved addition; `ResolvedComponent.fdc_id` is `int`
because nutrition is a join and a component without a row has no nutrients.
`Component` carries `state` (raw/cooked), which the DSL needs and the arithmetic
does not; `ResolvedComponent` carries `sigma` and `count`, which the arithmetic
and the card need and the DSL cannot know. The conversion at `bot.py:3630-3636`
is exactly where "resolved" starts being true, and `if c.fdc_id` in that
comprehension is the filter that makes it true. Merging them would delete that
boundary. **Do not merge.**

**L2. The two `Finding` classes must stay separate.** `core/insight.py:83` is a
statistical finding (rho, p, verdict, caveat); `jobs/audit.py:77` is a data
integrity finding (code, severity, summary, detail, entry id). No field
overlaps, and only the name collides. Neither is imported alongside the other.
Renaming one for tidiness would churn two modules to fix nothing.

**L3. The eight `dsl` op dataclasses should not become an `Enum` or a single
tagged struct.** They carry different payloads, `Op` already unions them, and
`dsl.apply` and `bot._when_from_ops` dispatch on `isinstance`. A single class
with eight optional fields is the version that admits invalid states.

**L4. `bot.py:3549` enumerates five op classes inline** — "ops that change the
plate", as against the three that change when or where it is filed. That
distinction is real and unnamed, but it appears once, so a `dsl.COMPONENT_OPS`
constant would add a definition to save no repetition.

**L5. The five `class C` stand-ins in `tests/test_render.py` should not become
`ResolvedComponent`.** They are minimal on purpose: `render.confirm_card` reads
its inputs with `getattr(c, ..., default) or c[...]`, so it accepts rows,
dataclasses and objects with three attributes. The stand-ins are what proves
that. Substituting the real dataclass would quietly stop testing the
duck-typing and would not fail if `confirm_card` grew a hard requirement on a
field a `Record` does not have.

**L6. `_Row(dict)` in `tests/test_profile.py:70` and `R(dict)` in
`tests/test_commands.py:234` are the same three-line `asyncpg.Record` stand-in
under two names.** Genuinely duplicated, and genuinely not worth a shared
fixture: they are three lines each, in unrelated test modules, and a shared
one in `conftest.py` would couple two suites so that neither can adjust its
fake without touching the other's.

**L7. No `TypedDict` for `ParsedMeal.items`.** The items are raw tool JSON,
their schema is `llm/schemas.py:PARSE_TOOL`, and `bot.py:3618` and
`bot.py:3780` construct synthetic ones by hand. A `TypedDict` would document
the shape but would not validate it, and would create a second, silently
drifting copy of a schema the API already enforces via `tool_choice`. The tool
definition is the right single source.

---

## 3. What changed

- `nutrai/core/estimate.py` — added `MEASURED_SOURCES` (+ reasoning comment);
  two call sites now read it.
- `nutrai/llm/parse.py` — imports and uses `MEASURED_SOURCES`.
- `nutrai/bot.py` — uses `estimate.MEASURED_SOURCES`; dropped the local
  `ResolvedComponent as _RC` re-import; two `1008` → `ENERGY_KCAL`.

No behaviour changes. No type was merged, renamed, moved or deleted.

`pytest -q -m "not integration"`: 294 passed.
`ruff check`: 211 findings tree-wide before the change and 211 after — this
change introduces none. (Aside, not acted on: CLAUDE.md says the resting state
is "around thirty". It is 211 tree-wide, 115 under `nutrai/`. The description
is stale, not the tree; nothing here was fixed to move it, per the standing
instruction not to run `ruff --fix` across the codebase.)
