# Assessment 7 — deprecated, legacy and superseded code

Scope: find code paths where one implementation has replaced another and both
remain; compatibility shims; parameters with no live caller; feature flags with
one permanent value; commented-out alternatives; superseded helpers.

Method: AST-level enumeration of every module-level function, class and constant
in `nutrai/`, `scripts/` and `tests/`, cross-referenced against word-boundary
occurrences everywhere else, then `git log -S` on each candidate to establish
*when* it stopped being called and *what* replaced it. Decorated aiogram
handlers (`@dp.message` / `@dp.callback_query`) are referenced only by the
decorator, so they show as orphans and were excluded by hand.

Baseline before any change: 294 passing (`pytest -q -m "not integration"`),
`ruff check .` → 211 findings.
After: **294 passing**, `ruff check .` → 204 findings (−5 `F401`, −2 `F841`;
no new rule codes).

---

## HIGH confidence — implemented

### 1. `nutrai/db.py:495` — `undo_last_entry()`

Dead. Zero references in `nutrai/`, `tests/`, `scripts/` or docs.

Superseded by the three functions immediately above it, all added in
`5792b37 "Tap to rate; /undo asks before reaching back hours"`:

- `db.last_confirmed_entry()` (`db.py:444`) — "Peek at what /undo would take,
  without taking it."
- `db.confirmed_entries_on()` (`db.py:457`) — "…for picking one to undo."
- `db.undo_entry(user_id, entry_id)` (`db.py:470`) — the write, by id.

That commit changed `/undo` from "silently discard the day's last confirmed
entry" to "peek, ask if it is not recent, then discard *that* id", and left the
old whole-operation-in-one-call version behind. `bot.undo` / `bot._do_undo` /
`cb_undo_ok` / `cb_undo_pick` use only the new three. The dish-counter
decrement logic is duplicated verbatim between the old and new functions, so
the dead copy was also a second place to keep in step.

**Removed.**

### 2. `nutrai/core/plan.py:180` — `render_proposal()`

Dead, and legacy in two independent senses.

- Zero callers. The live renderer is `render.plan_card()` (`render.py:2198`),
  used by `bot.py:2331` (`/report`) and `jobs/report.py:52` (the scheduled
  weekly review). `plan_card` was added in `b5d9387 "Wire the weekly review…"`;
  `render_proposal` dates from the original scaffold (`eaaa631`) and was never
  wired.
- It emits legacy Telegram **Markdown** (`*bold*`, `_italic_`, backtick spans).
  CLAUDE.md § "Outgoing message format" records that every outgoing message was
  moved to HTML precisely because legacy Markdown has no defined escape syntax.
  Calling this function would have produced the HTTP 400 that section describes.

Note this is **not** the "deliberately unwired `core/plan.py`" of CLAUDE.md's
Known gaps. That note is about `/improve` and `/targets`; `plan.evidence_pack`,
`plan.propose` and `plan.apply_recommendations` are all reachable today through
`/report` and `_consume_plan_apply`. Only this one renderer is dead.

**Removed.**

### 3. `nutrai/llm/parse.py:87,106` — the `str | list[str]` adapter on `parse_photo`

```python
images: str | list[str], ...
if isinstance(images, str):
    images = [images]
```

Introduced by `ea17bba "An album was parsed one photo at a time…"`, which
changed the signature from `image_b64: str` to a list. The union and the
one-line adapter were kept so an un-updated caller would still work. There is
exactly one caller — `bot.py:3244`, in `_handle_photos` — and it passes a list.
No test calls `parse_photo` directly. The two single-image model calls
(`read_supplement_label`, `read_food_label`) are separate functions with their
own `image_b64: str` parameters and are unaffected.

**Removed** — annotation narrowed to `list[str]`, adapter deleted.

### 4. `nutrai/bot.py:475-476` — `_BACK_WORDS`

```python
# How many days back a bare word means. Anything older is a date.
_BACK_WORDS = {"yesterday": 1, "yday": 1, "sat": None}
```

Born dead in `7e2c451 "/yesterday puts food into an earlier day…"` — the diff
adds it and adds no reader, and none has appeared since. The idea it sketches
is implemented, properly and with the weekday table filled in, in
`dsl.WORD_DAYS` and `dsl.WEEKDAYS` (`dsl.py:63-68`), consumed by
`dsl.parse_ops` → `dsl.SetDate` → `bot._when_from_ops`. The `"sat": None` entry
is the tell: a weekday mapped to nothing, in a dict typed as days-back.

**Removed.**

### 5. `nutrai/core/dsl.py:43` — `SLOTS`

```python
SLOTS = {"breakfast", "lunch", "dinner", "snack", "brunch", "supper", "drink"}
```

Scaffold-era constant (`eaaa631`), never referenced. The live slot vocabulary
is `dsl.SLOT_BOUNDARIES` + `dsl.slot_for_hour()` (added `b2ab822`), which is
where the meal slot is actually decided — from the clock, deliberately not from
the model. `RE_SLOT` accepts any `\w+` and never consulted this set.

**Removed.**

### 6. `scripts/bootstrap.py` — residue of the deleted notification seeding

`38a55fc "…no unprompted nagging"` deleted the six seeded `notification_rule`
rows and left behind:

```python
rules: list[tuple[int, str, int, int]] = []
...
print(f"user {user_id} ready: {len(targets)} targets, "
      f"{len(rules)} notification rules")
```

An empty list existing only so the print statement still compiles — a variable
with one permanent value, printing "0 notification rules" on every run — plus
five now-unused imports (`CARB`, `ENERGY_KCAL`, `FAT`, `PROTEIN`, `SODIUM`;
`ruff F401`) and a module docstring still promising "seed notification rules".

**Removed**, and the docstring corrected. The `DELETE FROM notification_rule`
is *kept*: it actively purges rules an earlier version of this script seeded,
which is the behaviour CLAUDE.md § "Unprompted messages" wants.

### 7. Two dead locals

- `nutrai/core/render.py:1898` — `units = {r["nutrient_id"]: r["unit"] …}` in
  `suggest_card`. Superseded by carrying `r["unit"]` in the `gaps` tuple
  directly (`gaps.append((…, r["unit"]))` two lines below). `ruff F841`.
- `nutrai/bot.py:2902` — `n = await db.log_supplements(…)` in `cb_supp_log`.
  The count stopped being used when the reply became a list of names read back
  from `supplements_logged_on`. `ruff F841`. The `await` is retained; only the
  binding is dropped.

**Removed.**

### 8. Comment residue from two replaced paths

- `nutrai/bot.py:2749-2751` — a comment describing the schedule-based
  pre-ticking of the supplement picker, immediately followed by a second
  comment beginning "Nothing is pre-ticked any more." Two contradicting
  comments over one code path; the first describes behaviour deleted in
  `67347d8 "A tick is a record of having taken it, not a plan"`. The
  surviving comment keeps the full *why*.
- `nutrai/core/render.py:1237` — a second, orphaned
  `# ---- day score` section banner with no section under it, plus runs of 12,
  20 and 11 blank lines around it, left by a function that moved out of that
  region.

**Removed** (banner and blank runs collapsed to the file's standard two).

---

## MEDIUM confidence — reported, not implemented

Each of these is genuinely superseded or dead, but removing it would require
deleting or rewriting a passing test, or would change live behaviour. Both were
out of bounds for this pass.

### M1. `render.supplement_pick_card`'s `reason` parameter — a flag with one live value

`render.py:1006` takes `reason: str = "schedule"`. The only production caller,
`bot._send_supp_picker` (`bot.py:2762`), hardcodes `reason = "logged"` — a local
assigned a constant and never varied. Everything from `elif n == total:` to the
end of the function (`render.py:1035-1045`) is the pre-tick-by-schedule
vocabulary, unreachable in production since `67347d8`.

Blocked by `tests/test_render.py:360 test_the_schedule_branch_names_what_is_not_due`,
which calls it with `reason="schedule"` explicitly. Removing the branch means
deleting that test. Worth doing together, deliberately.

### M2. `db.supplements_due()` (`db.py:1196`) — the query behind the removed pre-tick

Called from tests only (`tests/test_integration.py:2321,2330`). It answers
"which of the stack to pre-tick for a day", which is exactly the question
`67347d8` stopped asking. Its start-date guard is real logic, though, and
`test_a_supplement_with_a_future_start_date_is_not_due_yet` is a meaningful
assertion — so this is the same decision as M1 and should be taken with it.

### M3. `parse_photo`'s `escalate: bool = True` (`parse.py:88`)

No caller has ever passed it (scaffold-era). It is also redundant with
`CONFIDENCE_ESCALATE`: setting that to 0 gives byte-identical behaviour to
`escalate=False`. Two knobs for one decision. Kept because stage 4 of the order
of work is explicitly about scoring the escalation path, and a per-call switch
is plausibly wanted then; but if it survives stage 4 unused, delete it.

### M4. `sql/003_fasting.sql:35` — view `v_meal_gap`

Not referenced from any Python module or from any other view or function in
`sql/`. Gaps between intakes are computed in Python by
`core.fasting.fasts_from()` over `db.meal_times()` (which reads `v_meal_time`,
its sibling, and is live). Removing it means writing a new `DROP VIEW`
migration against a live database — correct per the "supersede, never rewrite"
rule, but a schema change, not code cleanup.

### M5. `core.fasting.eating_window()` vs the SQL view `v_eating_window`

The same computation exists twice: once in SQL (`sql/003_fasting.sql:47`) and
once in Python (`fasting.py:56`). Production uses the SQL one —
`bot.window` reads `db.eating_windows()` and builds `fasting.EatingWindow`
objects from the rows directly, never calling `fasting.eating_window()`. The
Python copy is referenced only by six assertions in `tests/test_fasting.py`,
where it serves as the readable specification. Not removed: the duplication is
real, but which copy is "the old way" is not established, and the tests are the
only thing pinning the semantics.

### M6. `core/estimate.py` propagation trio, and `core/nutrition.py` uncertainty

`estimate.propagate` (:133), `estimate.fmt_pm` (:150), `estimate.day_confidence`
(:157) and `nutrition.nutrient_uncertainty` (:150) have no production callers.
The live equivalents are SQL: `db.day_energy_sigma()` and the view
`v_day_mass_confidence`. `render.day_card:473` also re-implements `fmt_pm`'s
3%-relative-floor rule inline as a suffix.

Not removed: all four are covered by `tests/test_estimate.py` and
`tests/test_nutrition.py`, and they are per-*meal* functions while the SQL is
per-*day* — plausibly complementary rather than superseded. Worth a deliberate
decision, not a drive-by one.

### M7. `nutrition.mass_sanity()` (`nutrition.py:171`) — a documented guardrail that is not wired

`docs/ARCHITECTURE.md` §3 lists "Mass sanity. Component sum vs any stated or
weighed plate total, 15% tolerance" as one of four guardrails running "before
anything is shown". `llm.parse.validate()` implements the other three
(Atwater cross-check, implausibility, provenance flags) and does not call this
one. Test-only. This looks like a missing wire, not dead code — flagging it
rather than deleting it, because deleting it would silently ratify the gap.

### M8. `jobs/notify.py:274` — `daily_summary` at 19:00 vs CLAUDE.md's list

CLAUDE.md § "Unprompted messages" says what arrives unbidden is "the morning
note (07:30), supplement reminders at their scheduled slots, and the Sunday
report. Everything else is pull." `start_scheduler` also registers
`daily_summary` on `CronTrigger(hour=19)`, which pushes a full day card every
evening. Scaffold-era, never revisited. Either the doc or the job is stale —
but this is a live user-facing message and the call is the user's, not mine.

---

## LOW confidence / deliberately left alone

- **`db.day_is_complete()` (`db.py:927`)** — zero callers, added by
  `713c3f5 "…days that do not count"`. Not superseded: it is the natural helper
  for CLAUDE.md's rule that "anything new that draws a conclusion across days
  must filter on it too". A tool waiting for its second user, not a leftover.
- **`config.PHOTO_DIR` (`config.py:115`)** — read by nothing. It is the named
  hook for ARCHITECTURE §12's still-open photo-retention decision. Removing it
  would delete the decision's landing site.
- **`db.weak_labels`'s `json.loads(raw) if isinstance(raw, str) else raw`
  (`db.py:2107`)** — no jsonb codec is registered on the pool, so `raw` is
  always `str` and the `else` branch is unreachable. Defensive, not superseded;
  every other jsonb read in the file (`take_pending`, `latest_pending`) does the
  bare `json.loads`. Cosmetic inconsistency at most.
- **`llm.parse.visual_tokens` (`parse.py:67`)** — test-only, but it is the
  cost-model documented in ARCHITECTURE §0.1 and the probe in
  `test_photo_confidence_below_threshold_escalates_once`.
- **`http_api.post_activity` docstring** — still says "idempotent per (user,
  date, kind, minutes)", which `024_activity_identity` superseded with
  `external_id`. `db.record_activity`'s own docstring is correct and explains
  why both paths exist. Stale sentence, not stale code.
- **`config.PRICES` entries for `claude-haiku-4-5` (dateless) and
  `claude-fable-5`** — neither is routed to. A pricing table with spare rows is
  not a second code path, and `_check_models_are_priced` exists precisely so
  that adding a row is how you enable a model.
- **`search_foods`' `has_energy` column (`db.py:179`)** — selected but only read
  by `tests/test_integration.py:3070`. It is the assertion probe for the
  energy-less-row rule; the `ORDER BY` re-derives it because a SELECT alias is
  not available there.

### Explicitly checked and confirmed deliberate (not touched)

Per the task's guardrails and CLAUDE.md, all verified still present and intact:

- `core.nutrition.normalise_energy` and the hard-coded Atwater branch in
  `day_nutrient_coverage` — two relationships, two rules; not unified.
- `bot.resend_unformatted` (`bot.py:4238`) — unreachable diagnostic fallback.
- `core/plan.py` as a module, `db.meal_template` / `db.template_by_slug` /
  `bot._log_template` — complete and deliberately unwired.
- The `1253: (None, 300)` cholesterol ceiling in `core/profile.py`.
- `MODEL_CHEAP` pinned dated while `MODEL_PHOTO` / `MODEL_PLAN` are dateless.
- `off.py`'s mention of the legacy `/cgi/search.pl` endpoint. This lead did not
  pan out: the comment describes an endpoint **OpenFoodFacts** keeps alive, not
  one this repo calls. `off.search()` already points at
  `search.openfoodfacts.org` and `tests/test_off.py:61
  test_the_search_endpoint_is_the_current_one` pins it. Nothing to remove.
- `off._first_brand`'s `isinstance(brands, list)` — not a shim for an
  un-updated caller: the OFF product API returns a comma-joined string and the
  search API returns a list, and `tests/test_off.py:46
  test_brands_parse_from_either_api_shape` pins both. Two live shapes, one
  parser.
- Every `sql/*.sql` migration. Nothing rewritten, nothing deleted.
- No test weakened, skipped or deleted.
