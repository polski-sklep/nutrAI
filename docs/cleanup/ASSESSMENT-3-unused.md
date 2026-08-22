# Assessment 3 — unused code

Scan date: 22 Aug 2026. Baseline `a9240ff`. Test baseline before and after:
**294 passed, 88 deselected** (`pytest -q -m "not integration"`).

## What was scanned, and how

`knip` is a JS/TS tool and does not apply. Four independent passes:

1. **`vulture` 2.16** (scratch venv, project `.venv` untouched) over `nutrai/`
   and `scripts/` at `--min-confidence 60`. Output is dominated by aiogram
   handlers — 90-odd `cb_*` / command functions that are registered by
   decorator and never called by name — so it is unusable raw.
2. **`pyflakes`** for unused imports and unused local bindings, which vulture
   does not report.
3. **A purpose-written `ast` cross-reference.** Every top-level `def`, `class`,
   assignment and method in `nutrai/` and `scripts/` is extracted with its
   decorator list, then counted by word-boundary regex across *every* text file
   in the repo — `.py`, `.sql`, `.md`, `.yml`, `.toml`, `.sh`, `Makefile`,
   `Dockerfile`. Counting raw text rather than resolving imports is deliberate:
   it catches the dynamic references a static resolver misses — callback-data
   prefixes, `@consumes(...)` string keys, SQL function names inside query
   strings, nutrient ids in SQL literals. Production and test references are
   tallied separately, and self-references within the defining file are
   separated from external ones, so "appears exactly once, at its own
   definition" is a directly readable result.
4. **A SQL object scan** — every `CREATE VIEW / FUNCTION / TABLE` in `sql/*.sql`
   counted against Python, SQL and docs.

Traps checked explicitly and cleared: decorator registration (`@dp.message`,
`@dp.callback_query`), the `@consumes(...)` / `PROMPT_CONSUMERS` registry,
callback-data string prefixes, APScheduler job references, SQL functions and
views named in query strings.

### The guardrail cases, confirmed untouched

| symbol | why kept |
|---|---|
| `core/plan.py` (`render_proposal` et al.) | Deliberately unwired, stage 5 (CLAUDE.md "Known gaps"). Still imported by `jobs/report.py:21`. |
| `meal_template`, `template_by_slug`, `_log_template` | Deliberately unreachable. |
| `bot.resend_unformatted` | Deliberate fallback; a log line from it is a diagnostic signal. |
| `bot.AWAITING_KINDS` | Derived from `PROMPT_CONSUMERS`; asserted by `tests/test_commands.py:183`. |
| `config.PHOTO_DIR` | Unused in code, but ARCHITECTURE.md §12.4 provisions it as the knob for open decision 4 (photo retention). Documented intent. |

---

## HIGH confidence — removed

Every item below was proved by exhaustive `grep` across `nutrai/`, `scripts/`,
`tests/`, `sql/`, `docs/`, `Makefile`, `docker-compose.yml`, `README.md` and
`CLAUDE.md`. For the first four, the symbol's **only** occurrence in the entire
repository was its own definition line.

### 1. `nutrai/db.py:495` — `undo_last_entry()` (39 lines)

Superseded, not merely unused. The live `/undo` path is
`db.last_confirmed_entry()` to find the entry, then `db.undo_entry(user_id,
entry_id)` to discard it (`bot.py:2980`, `bot.py:_do_undo`). `undo_last_entry`
collapsed those two steps into one — find the last confirmed entry of a day and
discard it without asking.

That single-shot behaviour is precisely what the current design **rejects**.
`bot.undo`'s docstring: *"typing /undo at 20:58 silently removed a meal logged
at 14:10. In a system where nothing is logged without a confirm, unlogging
something from seven hours ago without one is the wrong way round."* The
function is the old behaviour left in place where it could be wired back up.

Proof: `grep -rn "undo_last_entry"` over the whole repo returns exactly one
line — `nutrai/db.py:495`, the `def`. No test, no SQL, no doc, no string.

**Comment preservation.** Its docstring carried reasoning that still applies to
the surviving `undo_entry`, which had only a one-line docstring. Per CLAUDE.md
("do not strip [comments] as noise") the two load-bearing pieces were moved
onto `undo_entry` rather than deleted:

- the *discarded, never deleted / invariant 2* paragraph, which describes
  exactly what `undo_entry` does;
- the inline `# times_logged gates the no-confirmation repeat path…` comment
  above the `UPDATE dish` block, which `undo_entry` performs identically and
  was missing.

The day-scoping paragraph was not carried over — it described the deleted
function's own semantics, and the "undo means the thing you just did" reasoning
already lives in `bot.undo`'s docstring.

### 2. `nutrai/db.py:927` — `day_is_complete()` (6 lines)

Reads a `day_quality` row. Nothing calls it. CLAUDE.md's "Days that do not
count" records that the exclusion is applied in `db.daily_energy` and
`db.observations` — both of which filter inline in SQL rather than through this
helper. Not named in "Known gaps" or "Decided, not yet done"; no docstring or
reasoning is lost.

Proof: `grep -rn "day_is_complete"` repo-wide returns one line, the `def`.

### 3. `nutrai/bot.py:475-476` — `_BACK_WORDS` and its comment

```python
# How many days back a bare word means. Anything older is a date.
_BACK_WORDS = {"yesterday": 1, "yday": 1, "sat": None}
```

A half-finished duplicate of live code. `core/dsl.py:63` holds the working
version — `WORD_DAYS = {"yesterday": 1, "yday": 1, "today": 0, "tonight": 0}` —
consumed at `dsl.py:267`, with weekdays handled separately by `WEEKDAYS` and
`SetDate.weekday`. The `"sat": None` entry is inert: `None` is not a day count,
and weekday resolution never went through this dict.

Proof: `grep -rn "_BACK_WORDS"` repo-wide returns one line, the assignment.

### 4. `nutrai/core/dsl.py:43` — `SLOTS`

```python
SLOTS = {"breakfast", "lunch", "dinner", "snack", "brunch", "supper", "drink"}
```

The abandoned model-supplied slot vocabulary. `RE_SLOT` (`dsl.py:69`) is
`^#(\w+)$` and matches at `dsl.py:286` without consulting `SLOTS`; nothing
validates against it. The comment above `SLOT_BOUNDARIES` (`dsl.py:513`)
records why it was abandoned: the model classified by dish type rather than
hour, so slots are now derived from the clock by `slot_for_hour()`.

Not a mirror of a database constraint — `log_entry.slot` is a bare `text`
column with no `CHECK` (`sql/001_schema.sql:137`). The similarly-named
`db.SUPPLEMENT_SLOTS` is a different, live constant.

Proof: `grep -rn "SLOTS"` repo-wide returns only `SUPPLEMENT_SLOTS` uses and
this one definition line.

### 5. `scripts/bootstrap.py:23` — five unused imports

`CARB`, `ENERGY_KCAL`, `FAT`, `PROTEIN`, `SODIUM` were imported and never
referenced; each appeared exactly once in the file, on the import line.
`DATABASE_URL` is used and is retained. These are the residue of the
notification-rule seeding that CLAUDE.md records as removed — *"Threshold
notifications are deliberately off and no longer seeded by `bootstrap.py`."*
Flagged by pyflakes, confirmed by per-name grep.

### 6. `scripts/load_usda.py:21` — `import os`

`grep -n "\bos\b"` over the file returns only the import line.

### 7. `nutrai/core/render.py:1898` — dead local `units`

```python
units = {r["nutrient_id"]: r["unit"] for r in progress}
```

Built and never read inside `suggest_card`; the sibling `names` dict is used.
A pure dict comprehension over an already-materialised sequence, so removing it
has no side effect. Confirmed by pyflakes plus a grep of the whole function
body — `units` occurs once.

### 8. `nutrai/bot.py:2902` — dead binding `n`

`n = await db.log_supplements(...)` → `await db.log_supplements(...)`. The call
performs the write and is kept; only the unused binding was dropped. The count
is not read — the message that follows re-queries via
`db.supplements_logged_on`.

---

## MEDIUM confidence — not removed

Eleven functions have **no production caller** but are covered by tests.
Removing any of them would mean deleting a passing test, which is out of
bounds. Several are also documented in ARCHITECTURE.md as intended behaviour,
which makes the absent caller a wiring gap rather than dead weight.

| symbol | tests | note |
|---|---|---|
| `core/nutrition.py:171 mass_sanity` | 4 | ARCHITECTURE §3 lists it as one of four guardrails run "before anything is shown". No production caller. |
| `core/nutrition.py:150 nutrient_uncertainty` | 3 | §4.5 uncertainty machinery. |
| `core/estimate.py:133 propagate` | 4 | §4.5 "combined in quadrature". No production caller. |
| `core/estimate.py:150 fmt_pm` | 3 | renders the `±` the day card is described as printing. |
| `core/estimate.py:157 day_confidence` | 2 | |
| `core/fasting.py:56 eating_window` | 6 | Production uses the SQL view instead — `db.eating_windows` → `v_eating_window` (`bot.py:842`). Parallel Python implementation. |
| `llm/parse.py:67 visual_tokens` | 3 | cost-estimation helper. |
| `db.py supplements_due` | 2 | |
| `db.py activity_on` | 1 | |
| `db.py clear_measured_tdee` | 1 | |
| `db.py delete_user_food` | 1 | related to the "Retiring a user food" design. |

**This cluster is worth a look independently of dead-code cleanup.** The §3 and
§4.5 groups describe behaviour the architecture presents as active — a mass
sanity check on every parse, a `±` range on the day total. Tests pass because
they call the functions directly. Nothing else does. Either the wiring is
missing or the docs overstate what ships; a subagent's cleanup pass is the
wrong place to decide which, so nothing was changed.

---

## LOW confidence — not removed

- **`sql/003_fasting.sql:35` `v_meal_gap`** — no Python reads it; the only
  other mention is the file map in `README.md:141`. Not removed for three
  reasons: `sql/*.sql` is applied on first boot only, so editing an
  already-applied file changes no live database while desynchronising the file
  from reality; the DB-free suite cannot prove a SQL object unused; and a view
  is plausibly queried by hand through psql or Adminer, which CLAUDE.md
  documents as a normal workflow.
- **`nutrai/core/dsl.py:473` — pyflakes "undefined name `dt`"**. Investigated
  and *not* a bug: `resolve_date(op, today: "dt.date")` is a string annotation
  under `from __future__ import annotations`, so it is never evaluated; the
  function imports `datetime as _dt` locally at line 485. Cosmetic only.
- Loop variables shadowing imports (`zoneinfo` at `bot.py:3132`, `field` at
  `render.py:1529`) and three placeholder-free f-strings. Pre-existing, not
  dead code, and inside the "resting state" CLAUDE.md asks not to churn.

---

## Verification

- `pytest -q -m "not integration"` → **294 passed**, unchanged from baseline.
  Integration tests deliberately not run (shared live Postgres).
- Every module imports: `nutrai.bot`, `nutrai.db`, `nutrai.core.dsl`,
  `nutrai.core.render`, `nutrai.http_api`, `nutrai.jobs.{report,audit,notify}`.
- `python -m py_compile` clean on all three `scripts/`.
- `ruff check nutrai`: **115 → 113**. Net −2 (the two dead locals); no new
  findings introduced. No `--fix` was run.
- The `ast` cross-reference re-run after the edits reports zero remaining
  symbols with no reference and no test, other than `core/plan.py`'s
  deliberately unwired surface.

Net: **−55 lines, +6 lines** across 6 files.
