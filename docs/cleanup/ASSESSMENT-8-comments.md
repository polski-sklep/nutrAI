# Assessment 8 — comment quality

Scope: every `#` comment and every docstring in `nutrai/` (13,637 lines across
23 modules), `scripts/` (3 files) and the `sql/` headers. Method: mechanical
extraction of every comment run with its following two code lines, plus every
docstring with its owning symbol, then reading each against the code it sits on.
Roughly 340 comment runs and 180 docstrings were examined.

## Headline

**This is the best-commented codebase I have audited, and almost nothing here
should be touched.** The house style — a comment names the bug, quotes the wrong
number it produced, and says why the fix is shaped the way it is — is followed
with unusual discipline, and it is doing exactly the job CLAUDE.md claims for
it. The long comments are the good ones. I found no restated code
(`# increment i`), no commented-out alternatives, no print-debugging, no
parameter-relisting docstrings, no `TODO`/`FIXME`, and no stub pretending to be
an implementation. The `git grep` for "work in motion" phrasing returns ~45
hits, and on inspection **every single "used to" in `nutrai/` is a bug
narrative** — the keeper form — except the three cases listed below.

What I did find is a small number of *mechanical* defects: comment blocks that
have drifted onto the wrong statement, one orphan section banner, one block that
was superseded and not deleted, and two docstrings that describe a dedup key the
code has since changed. Six of those are fixed. The rest are recorded and left
alone.

---

## HIGH confidence — implemented

### 1. `nutrai/bot.py:2749-2751` — a stale block contradicted by the next line

```python
# Ask rather than assume, and pre-tick by each supplement's own cadence:
# daily always, alternate only when yesterday was a rest day, occasional
# never. Anything already logged today stays ticked.
# Nothing is pre-ticked any more. A tick used to mean "this is on your
# daily list" and now means "I took this", ...
await _send_supp_picker(msg, u, stack, day)
```

Two blocks jammed together where the second explicitly repeals the first.
Verified against `_send_supp_picker` (`bot.py:2759`): it sets
`selected = [s["id"] for s in stack if s["name"] in today_names]` and
`reason = "logged"` — nothing consults a cadence, and `db.supplements_due()` is
not called from production code at all. The first block is a description of
deleted behaviour sitting above the code that replaced it, which is the "worse
than none" case. **Removed the first three lines; kept the second block, which
carries the reasoning.**

### 2. `nutrai/core/render.py:1237` — orphan duplicate section banner

```
1214: return "\n".join(out)
1215-1236: (22 blank lines)
1237: # ------------------------------------------------------------- day score
1238-1243: (6 blank lines)
1244: # --------------------------------------------------------- weekly report
```

An exact duplicate of the live banner at line 1062, marooned in a 28-line blank
gap with no code under it. It tells a reader a day-score section follows, and
what follows is the weekly report. Leftover from a deleted block. **Removed the
banner and collapsed the blank run to the file's standard two lines.**

### 3. `nutrai/bot.py:138-145` — comment attached to the wrong statement

```python
u = await db.get_or_create_user(...)
# Typing another command means you moved on. ... only a command clears one.
# When you first speak each day, ... a measurement rather than a guess.
await db.note_first_contact(u["id"], _today(u))
if (msg.text or "").startswith("/"):
    await db.clear_awaits(u["id"], tuple(PROMPT_CONSUMERS))
```

The first block describes `clear_awaits` two statements down; the second
describes `note_first_contact`. As written, the load-bearing prompt-clearing
rationale reads as an explanation of first-contact recording. **Swapped the two
blocks so each sits on the statement it describes. Both facts preserved
verbatim.**

### 4. `nutrai/core/dsl.py:152-160` — comment attached to the wrong constant

The block "Words that say 'this is a change to that dish' rather than 'this is a
food' … any ingredient name added to this set would make its own dish
unloggable" sat above `SIGIL_NUM = re.compile(r"^[x*×]\d")` and described
`MODIFIER_WORDS`, defined two lines below it. The one line that *does* describe
`SIGIL_NUM` ("x1.5 mistyped as x1.5.2 is still an attempt at a scale factor")
was the last line of that block. **Split the block so each half sits on its own
constant. No text changed.**

### 5. `nutrai/db.py:1679-1680` — docstring stale about the dedup key

```
Note the workout bot can re-post it — deduplication keys on (user, date,
kind, minutes, intensity), and after a delete there is nothing left to match.
```

`record_activity` (`db.py:1255-1268`) keys on `external_id` when the client
supplies one and only falls back to the shape heuristic otherwise — its own
docstring says so, and CLAUDE.md calls the `external_id` path load-bearing.
`delete_activity` describes only the fallback, so a reader learns the wrong rule
for the primary path. **Rewritten to name both, keeping the point that a delete
leaves nothing for either to match.**

### 6. `nutrai/http_api.py:74-76` — same staleness, same fix

```
Append-only and idempotent per (user, date, kind, minutes): ...
```

Wrong on two counts: `intensity` is part of the heuristic, and `external_id`
takes precedence over the whole tuple. The comment at `http_api.py:164-168`
already explains `external_id` correctly forty lines below, so the docstring is
the odd one out. **Rewritten to name both keys; the retry-on-success reasoning
is untouched.**

### 7. `nutrai/llm/parse.py:645, 665` — vestigial scaffolding (code, not comment)

```python
from ..config import CORE_NUTRIENTS   # line 645
names = {...}
del CORE_NUTRIENTS                    # line 665
return "\n".join(...)
```

An import that is never read and is deleted five lines later, inside a function
whose module already imports from `..config` at the top. It does nothing, and
the `del` is what stops a linter from saying so. This is a code change rather
than a comment change; I include it because it is textbook leftover scaffolding
and the removal has no behavioural surface. **Both lines removed.**

---

## MEDIUM confidence — recorded, deliberately NOT changed

### M1. `nutrai/core/render.py:583-584`

```python
# One clause. The long version explained the same fact three ways
# depending on the number, and the number already says it.
tail = "" if pct_measured >= 80 else \
    " — the rest is my estimate" if pct_measured >= 50 else \
    " — most of the rest is guesswork"
```

Read one way the comment is contradicted by the three-branch expression directly
under it. Read the other way — "one clause" meaning each *tail* is now a single
clause, against a previously longer sentence per band — it is accurate. I cannot
resolve the ambiguity from the code, and rewriting it risks replacing a specific
statement with a vaguer one. Left alone.

### M2. `nutrai/db.py:1196-1207` — `supplements_due` docstring

The function is correct about itself, but its opening line ("Which of the stack
to pre-tick for a day") describes a role nothing in production fills any more —
its only callers are `tests/test_integration.py:2321,2330`. The reasoning it
carries ("Pre-ticking everything trains you to untick, and the day you forget is
the day an untaken capsule lands in your totals") is genuinely valuable and now
duplicated at `bot.py:2749`. Touching this means deciding the fate of the
function, which is a design call, not a comment cleanup. Recorded only.

### M3. `nutrai/off.py:27-28` vs `nutrai/off.py:142-146`

The fact that `/cgi/search.pl` answers 503 under load and is kept for
compatibility is stated twice, near-verbatim, once on the `SEARCH` constant and
once in `search()`'s docstring. Harmless duplication; the constant needs its own
justification and the docstring needs to explain the ordering. Kept both.

### M4. `nutrai/bot.py:79-80` vs `nutrai/bot.py:92-93`

"Offered at the moment the gap is visible, which is the only moment you know the
database is missing something" appears verbatim in `_define_button` and in
`cb_define_food`. The button and its callback are a genuine pair, so the
repetition is defensible; a reader arriving at either one gets the reason.

### M5. `nutrai/core/render.py:505-508` and `512-520`

The "an unbreached ceiling is not a nutrient where it should be — which is how
an empty day claimed six were fine" argument is made twice, on adjacent
branches of the same `if`. Both branches genuinely need it (one lists, one
counts), and the bug narrative is worth having at both. Kept.

### M6. `nutrai/config.py:31-36`

`_check_models_are_priced`'s docstring says "`price()` falls back to Sonnet's
rate for an unknown model, which is the right behaviour there". True of the code
today (`llm/client.py:47`), but CLAUDE.md's "Decided, not yet done" section says
that fallback is to become `None`. Accurate now; it becomes wrong the day that
change lands. Not a defect yet — flagged so it is not missed then.

---

## LOW confidence — noted for completeness, no action

- **`nutrai/core/render.py:483-490`, `606-610`, `622-628`; `bot.py:323-328`,
  `1939-1943`, `4192-4197`** — adjacent comment blocks concatenated without a
  blank `#` separator. Unlike HIGH-3 and HIGH-4, in every one of these both
  blocks genuinely describe the code immediately below, so nothing is misplaced;
  it is purely a formatting inconsistency against the `#\n#` style used
  elsewhere in the same files. Not worth the diff.
- **Section banners** (`# ----- users`, `# ----- fasting`, etc., ~30 of them).
  Navigational rather than explanatory, but consistent and cheap. Only the
  orphaned duplicate (HIGH-2) was a defect.
- **`nutrai/core/nutrition.py:70`** — `"""profile is per 100 g of the USDA row.
  Returns absolute amounts."""` is close to restating the code, but the "per
  100 g" basis is exactly the unit contract a caller cannot see from the
  signature. Keep.
- **`nutrai/core/render.py:1980-1983`** and **`833-835`** — both are
  "the old version said X, which was wrong because Y" comments. They read as
  work-in-motion at a glance, but each states a rule for the next person editing
  that string (don't put implementation detail in the footer; the heading is
  about matching, not about eating). Keepers under the stated test.

---

## Comments I evaluated and explicitly preserved

Evidence that this was a read, not a sweep. Each of these is long, each would
fail a naive length or tone filter, and each carries a fact the code cannot.

| Location | What it preserves |
|---|---|
| `core/nutrition.py:37-51` | 276 of 411 Foundation rows carry no nutrient 1008; interacts with `food.precedence` ranking Foundation first, so the resolver prefers exactly the rows that report no energy, and `energy_cross_check` cannot flag it because its guard skips zero-energy rows. The single most load-bearing comment in the repo. |
| `core/dsl.py:425-434` | Why `apply()` carries provenance through instead of hardcoding `"repeat"`: correcting rice in "400 g rice and 100 g chicken" silently downgraded the untouched chicken from `stated` to `repeat`, which removed it from `portion_history()` (invariant 7). |
| `llm/parse.py:90-104` | The 330 ml bottle that became 660 g and 61 g of sugar when album photos were parsed separately. Nothing downstream can catch it. |
| `llm/parse.py:324-339` | `INVERTING_TERMS`: "Chicken, meatless, breaded, fried" auto-matched 400 g of real fried chicken; macros close enough to pass Atwater; only tell was 17 g of fibre. |
| `llm/parse.py:461-466` | Why disambiguation matches by index, not label — the model echoes the whole prompt line, so exact-string lookup discarded every correct answer the tier produced. |
| `llm/parse.py:272-283` | The measured trigram numbers: `salami, Italian, organic, sliced` → 0.34 vs `Italian salami slices` → 0.58 against the same target row. |
| `db.py:36-48` (`num`) | asyncpg hands Postgres the float's exact binary expansion; 75.2 stores as 75.2000000000000028…; rounding the float does not help. |
| `db.py:151-171` (`search_foods`) | Why precedence must not outrank relevance, with the measured rice example (0.48 raw/no-energy beating 0.84 cooked/130 kcal). |
| `db.py:79-85` (`UNUSABLE_ROW`) | Why the predicate is defined once: excluding rows from search while an alias still pointed at one is how "butter" kept resolving to 81.5 g of fat and no calories. |
| `db.py:1290-1301` (`sleep_predictors`) | Why the join goes backwards a day, and why the rollover hour makes it free. |
| `db.py:2239-2256` (`supplements_named_in`) | Why matching is exact and never against the dish name: "zinc-rich beef stew" contains "zinc" and involves no tablet. |
| `bot.py:38-49` (`PROMPT_CONSUMERS`) | The same bug fixed six times in six handlers, and why the registry makes a seventh impossible. |
| `bot.py:2218-2230` | 1,587 g of blondie ingredients declared as an 850 g tray → 160 g of food inside 100 g of food; why the macro-sum check can refuse outright. |
| `bot.py:2247-2259` | Why the all-or-nothing energy test was insufficient: one energy-less row in eight stored the blondie at 336 kcal against macros implying 528. |
| `bot.py:3809-3818` | Why `times_logged == 0` gates the no-confirm repeat path — discarding a photo then sending `1` logged 947 kcal with no gate, the exact thing invariant 5 forbids. |
| `bot.py:3886-3899` | Why a fully-unresolved parse is stored as a discarded entry rather than thrown away: ~5p of model output was the one artefact worth keeping. |
| `bot.py:3270-3281` (`_FAILURES`) | Why matching is on message text and not status code — 400 covers both "out of credit" (never retry) and "malformed image". |
| `core/estimate.py:88-89` | Why `quantiles(..., method="inclusive")`: hand-rolled index arithmetic on five samples calls a bimodal history "consistent". |
| `core/suggest.py:93-126` | Two measured ranking failures — the chia pudding ranked first for closing 2% of calcium on a day 118 g short of protein, and pickle juice outranking a protein shake because the fat penalty was unbounded. |
| `core/render.py:98-105` | Why unmatched items print above the total: a real meal with three of four items missing was confirmed on the strength of a tidy 160 kcal. |
| `core/render.py:606-610` | Pad-before-escape, plus `_short()` existing and never being called, so the raw column truncated to "Carbohydrate, by diffe". |
| `core/render.py:1154-1155` | Unsorted breaches came out in nutrient-id order, so the morning note named carbs at 103% on a day with cholesterol at 208%. |
| `jobs/audit.py:1-19` and `42-54` | The module preamble on why every check exists, and the egg-white/whole-egg case: 397 mg of cholesterol, 249% of ceiling, advice to eat fewer yolks on a day with one yolk in it. |
| `jobs/notify.py:86-93` | Why dedup happens *after* the crossing test, not before. |
| `http_api.py:117-122` | Why `rpe` goes through `Decimal`: 9.2 stored as 9.1999999999999992894…, and `round()` cannot fix what 9.2 *is* in binary. |
| `llm/client.py:14-23` | Docker's embedded resolver failing for a few seconds; three SDK retries inside one second all hit the same dead DNS and the meal was typed twice. |
| `llm/client.py:87-94` | `temperature` is rejected outright by Claude 5 models — killed every parse on the first live call — and the forced tool call was the load-bearing determinism mechanism anyway. |
| `config.py:76-89` (`CONFIDENCE_ESCALATE`) | Why 0.75 was wrong: escalation fired on essentially every plate, at 74% of a photo's cost, and the first measured escalation *lost*. |
| `config.py:152-155` | Caffeine and alcohol were being recorded and never shown; 127 mg went into a day's log without a word. |
| `core/fasting.py:112-132` (`phase_label`) | The whole refusal: meal timestamps cannot measure substrate oxidation, and a fasting phase is not a fat-loss rate. |
| `scripts/load_usda.py:109-116` | FNDDS numbers its rows with INFOODS tagnames (203/204/208) against FDC internal ids; skipping them would give 5,432 foods that resolve happily and contribute zero of everything. |

## Test result

`pytest -q -m "not integration"` — **294 passed, 88 deselected**, unchanged from
baseline. `ruff check` reports 211 findings before and after the change, i.e.
untouched.
