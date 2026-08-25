# SPEC-9 — Provenance, observability and versioning of a resolution

Scope: make a resolution failure diagnosable **after the fact, from the database
alone**, without reproducing the session. One user, one bot process, one laptop
that sleeps. No metrics backend, no dashboard, no alerting. Everything below is
SQL over tables that exist, plus a small number of columns that do not.

All figures measured against the live database on 25 Aug 2026, user 2:
160 entries (118 confirmed, 39 discarded, 3 pending), 363 components,
132 aliases, 214 `llm_call` rows.

---

## 1. What is knowable today about a past resolution

### 1.1 A real entry, traced end to end

Entry **24988**, logged 09:46:44 today, confirmed, still in today's totals.

**`log_entry`** gives: name `Cosmic cereal with coconut milk`, `source = text`,
`confidence = 0.6`, `model = claude-sonnet-5`, `status = confirmed`,
`photo_file_id = NULL`, and a `parse` blob:

```json
{"dish_name": "Cosmic cereal with coconut milk", "overall_confidence": 0.6,
 "notes": "Coconut milk quantity not stated; assumed typical cereal pour.",
 "_weak": [],
 "items": [
   {"label": "Cosmic cereal", "grams": 100, "state": "as_sold",
    "confidence": 0.85, "grams_source": "stated",
    "search_terms": "chocolate flavored cereal, Cosmic cereal"},
   {"label": "Vemondo coconut milk drink", "grams": 150, "grams_low": 100,
    "grams_high": 200, "state": "as_sold", "confidence": 0.4,
    "grams_source": "estimate",
    "search_terms": "coconut milk drink, plant-based, chilled"}]}
```

**`log_component`** gives:

| pos | fdc_id | label | grams | state | yf | grams_source | sigma |
|---|---|---|---|---|---|---|---|
| 0 | 2708443 | Cosmic cereal | 100 | `as_logged` | 1 | stated | 5 |
| 1 | -464 | Vemondo coconut milk drink | 140 | `as_logged` | 1 | prior | 8.4 |

**`llm_call`**: `entry_id IS NULL` on this row and on all 214 others. The only
link is a timestamp — one `text_parse` at 09:46:44.361, 3810 ms, $0.010117 —
and inferring the link is my inference, not a stored fact.

**`food_alias`**: `cosmic cereal → 2708443`, `hits = 1`,
`created_at = 09:46:44.406`, 45 ms after the parse call returned.

That is the whole record. Now the questions it cannot answer.

### 1.2 Exactly where the trail goes cold

**The winner is recorded. The decision is not.** Nothing stores which of the
three tiers ran, what the candidate list was, what anything scored, or what came
second. For component 0 I established the tier by *absence*: no `disambiguate`
call exists in the window, therefore tier 3 did not run, therefore — given a
component was produced — tier 2 auto-matched. That reasoning is available to me
because I read the source. It is not in the database and it does not survive.

Reconstructing the candidate list by hand against today's `food` table:

| fdc_id | description | data_type | sim(search_terms) | sim(label) |
|---|---|---|---|---|
| **2708443** | **Wheat cereal, chocolate flavored, cooked** | fndds | **0.63414633** | 0.195 |
| -565 | Lubella Cosmic Cereal | **user_product** | 0.333 | **0.61904764** |
| 2708472 | Cereal, K's, flavored | fndds | 0.457 | 0.269 |

`AUTO_MATCH_SIMILARITY = 0.62`. The user's own row, transcribed from the packet,
**lost by 0.00095**. The `own` guard in `resolve_items` requires
`sim >= AUTO_MATCH_SIMILARITY` before a `precedence = 0` row can pre-empt, and
0.61904764 is below it, so the guard did not fire and the pooled head
auto-matched at 0.63414633.

The consequence, per 100 g:

| | energy | protein | sugar | fibre |
|---|---:|---:|---:|---:|
| -565 Lubella Cosmic Cereal (the packet) | **376 kcal** | 8.5 g | 14 g | 14 g |
| 2708443 Wheat cereal, chocolate, **cooked** | **49 kcal** | 1.79 g | 0.08 g | 1.8 g |

100 g logged. **327 kcal and 13.9 g of sugar missing from today**, confirmed,
counted, and now cached as an alias. The Atwater cross-check on the matched row
computes 51.6 kcal against a stored 49 — 5.4% — and passes. `/audit` over the
last 30 days returns 39 findings and **not one of them names this entry**.

This is FAILURES.md case 3 recurring today, after the commit that was written to
fix it (`84d6eb8`, 23 Aug). Nothing in the store says so.

**Five specific holes, each demonstrated:**

1. **No tier.** `log_component` has no column for it and the parse blob has no
   field. Timing correlation is the only bridge and it is weak: of 98 text/photo
   entries, 44 have a `disambiguate` call within ±30 s, and 15 of those windows
   contain zero or two-plus entries, so the correlation is ambiguous for a sixth
   of the cases and never resolves *which component* the call decided.

2. **No score, no runner-up, no candidate list.** The margin here was 0.015 and
   the winner cleared the threshold by 0.014. A resolution decided in the third
   decimal place is a coin flip, and a coin flip that gets cached forever is the
   single most damaging event in this system. Nothing records that it happened.

3. **`llm_call.entry_id` is NULL on 214/214 rows.** The FK exists; nothing fills
   it. It cannot be filled where it is written — `_log()` runs during parse,
   before the entry row exists. `llm_call.ok` is hardcoded `True` at the one call
   site and `error` is never written, so "0 failed calls" means "failures are not
   recorded", not "there were none".

4. **`log_component.state` is `as_logged` on all 363 rows.** The parse returned
   `as_sold`; `_write_components` has no `state` in its INSERT. ARCHITECTURE §3
   calls raw-vs-cooked "as important as the number", the parser is asked for it,
   the card shows it, and the write path drops it. Here it is load-bearing: the
   matched row is *cooked* wheat cereal and the food was eaten dry. A stored
   `state` would make the mismatch a one-line query.
   `yield_factor` is 1.0 on 362/363 rows, and 1.0 is indistinguishable from
   "never considered".

5. **`_weak` stores labels and drops the scores.** `Resolution.weak_matches` is
   `list[tuple[str, float]]`; `bot.py:4062` writes
   `[w[0] for w in res.weak_matches]`. The number is computed, carried across a
   function boundary, and discarded one character before storage. 81 entries
   carry a `_weak` key, 16 non-empty, none with a score.

**And 45% of components never touch the resolver at all.** 162 of 363 components
arrive by `source = repeat`, whose `parse` blob is literally `{"ops": []}`. Their
provenance dead-ends at `dish_component`, which stores `fdc_id`, `label`,
`grams`, `state`, `yield_factor`, `grams_source` and **no provenance whatsoever**.

---

## 2. The provenance specification

### 2.1 The storage trade

Three options, argued.

**(a) Columns on `log_component`.** Cheap, indexable, snapshot semantics come
free. But a candidate list is a list, and `replace_components` **DELETEs the
component rows** — so anything stored there is destroyed by the `/fix` that
corrects it, which is exactly the moment the record is worth most.

**(b) A jsonb blob.** Flexible and needs no migration. But the precedent is
already in this repo and it decayed: `log_entry.parse` is a blob, and `_weak`
lost its scores inside it because nothing constrains a blob's shape. A column
that must exist gets noticed when it is NULL; a key that might exist does not.

**(c) A new table.** One row per resolution decision, independent of the
component's lifecycle.

**Take (a) and (c).** The scalars every measure filters on become columns,
because they are per-component facts of the entry and must be snapshotted with it
— the same argument invariant 2 makes for `log_nutrient` and CLAUDE.md's NOVA
note makes for the group. The candidate list goes in its own table, because it is
a list, because it must survive `replace_components`, and because it is
*deliberation*, not diary — the snapshot is sacred, the reasoning behind it is
not, so it may be aged out later without touching a single number.

Size is not an argument either way: 5 candidates × 363 components at ~120 bytes
is roughly 220 KB for the entire history to date. Keep it indefinitely; revisit
if it reaches a gigabyte, which at this rate is somewhere past the year 3000.

### 2.2 Columns on `log_component` (immutable, snapshotted with the entry)

| column | type | note |
|---|---|---|
| `resolved_by` | text NOT NULL | `alias` \| `user_product` \| `auto_match` \| `model` \| `repeat` \| `template` \| `manual`. **The tier.** No default — a default would let a future path write an untruthful one. |
| `match_score` | numeric | similarity the winner achieved. NULL for `repeat`/`manual`. |
| `runner_up_fdc_id` | integer | what nearly won. |
| `runner_up_score` | numeric | the margin is the coin-flip detector. |
| `alias_id` | bigint | which alias row served a tier-1 hit, so a later re-point is traceable to the entries it affected. |
| `resolver_version` | smallint NOT NULL | §4. |
| `state` | — | **exists already and is never written.** Fix `_write_components`; do not add a column. |

### 2.3 New table `resolution_event`

```sql
CREATE TABLE resolution_event (
    id            bigserial PRIMARY KEY,
    entry_id      bigint NOT NULL REFERENCES log_entry ON DELETE CASCADE,
    position      smallint NOT NULL,      -- matches log_component.position at resolve time
    label         text NOT NULL,
    search_terms  text,
    queries       text[] NOT NULL,        -- what _candidates actually asked
    candidates    jsonb NOT NULL,         -- [{fdc_id, description, data_type,
                                          --   precedence, sim, rank, has_energy}]
    chosen_fdc_id integer,                -- NULL when nothing was chosen
    tier          text NOT NULL,
    score         numeric,
    threshold     numeric NOT NULL,       -- the constant in force at the time
    resolver_version smallint NOT NULL,
    request_id    uuid NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX resolution_event_entry ON resolution_event (entry_id, position);
```

`threshold` is stored per event, not looked up. It is an env-overridable constant
(`AUTO_MATCH_SIMILARITY`), so reading today's value to interpret a year-old
decision is the same error as recomputing a historical entry from current USDA.

**No `ON DELETE` link to `log_component`** — that is the point. A `/fix` that
re-points a component leaves the event that produced the original in place, and
the correction becomes a second event whose `chosen_fdc_id` differs. That pair is
the highest-information signal the system can produce and today it is deleted at
the instant it is created.

### 2.4 `request_id`, and how `llm_call` gets joined

`llm_call.entry_id` cannot be filled at the call site because the entry does not
exist yet. Do not thread a return value up the stack and backfill.

**Generate one `uuid` when a Telegram update is received. Stamp it on every
`llm_call`, every `resolution_event`, and on `log_entry`.** One column on three
tables, no ordering dependency, no backfill, and it also joins the things
`entry_id` never could: the sonnet/opus escalation pair on one photo, the single
call behind a four-photo album, and a `disambiguate` call to the `text_parse` it
followed. Keep `entry_id` and fill it on `create_pending_entry` where it is known;
`request_id` is the one that always works.

While in there: `_log()` must be called on failure with `ok = false` and the
error text. Two dead columns are worse than none, because they answer a question
falsely.

### 2.5 `food_alias` — the cache's own provenance

| column | note |
|---|---|
| `resolved_by`, `match_score` | how the *current* pointing was decided. |
| `resolver_version` | §4. |
| `first_fdc_id` | what it originally pointed at, written once on insert, never updated. |
| `repointed_at`, `repoint_count` | set by `upsert_alias` when `fdc_id` actually changes. |

Today `created_at` is not the age of the match: `upsert_alias`'s `ON CONFLICT`
changes `fdc_id` and leaves `created_at` alone. **At least 8 of 132 aliases have
demonstrably been re-pointed** (below), so for those the date is provably wrong,
and for the other 124 it is unfalsifiable. `first_fdc_id` plus `repointed_at`
costs three columns and makes it answerable forever.

---

## 3. Measures

Six. Four run today against existing tables; two need §2. Each is tied to a
traced failure and states what it would have shown.

### M1 — Own-product bypass *(runs today)*

An alias or component sits on a generic row while an unretired `user_product`
belonging to this user scores highly against the same words.

```sql
SELECT a.alias, a.hits, f.description AS resolved_to,
       up.fdc_id, up.description AS your_own,
       round(similarity(up.description, a.alias)::numeric, 3) AS sim_own
  FROM food_alias a
  JOIN food af ON af.fdc_id = a.fdc_id
  JOIN food up ON up.owner_user_id = a.user_id AND up.retired_at IS NULL
 WHERE a.user_id = $1 AND af.owner_user_id IS NULL
   AND similarity(up.description, a.alias) >= 0.55
 ORDER BY sim_own DESC;
```

**What it shows now** — four rows, the top two both genuine and both within
0.005 of the auto-match threshold:

| alias | resolved to | your own row | sim |
|---|---|---|---:|
| cosmic cereal | Wheat cereal, chocolate flavored, cooked | Lubella Cosmic Cereal | 0.619 |
| valando coconut milk | Coconut milk, used in cooking | Vemondo Coconut Milk | 0.615 |
| sparkling water | Water, carbonated, plain | Muszynisnka Sparkling Water | 0.571 |
| protein powder | Beverages, Protein powder whey based | Olimp Whey Protein Powder | 0.560 |

Catches **FAILURES #3** (Devolay → `Chicken or turkey cordon bleu`) and the live
327 kcal miss from this morning. The threshold is 0.55 rather than 0.45 because
below that it starts pairing `lemon juice` with `Ginger-turmeric-lemon juice`.

### M2 — Coin-flip margin *(needs §2.2)*

`match_score - runner_up_score < 0.05`, **or** `match_score` within 0.03 of the
threshold in force.

**Cosmic cereal:** margin 0.015, and the winner cleared 0.62 by 0.014. Fires on
both limbs. **FAILURES #2 (butter):** 0.73 vs 0.67, margin 0.06 — fires on
neither limb, which is honest: butter's tell was not the margin, it was that the
winner had no energy row. M2 does not claim that case; M6 does.

This is the measure that cannot be built without the provenance record, and it is
the one that identifies the class the other five only sample.

### M3 — One label, two rows *(runs today)*

```sql
SELECT lower(c.label), count(DISTINCT c.fdc_id), count(*),
       string_agg(DISTINCT c.fdc_id::text, ', ')
  FROM log_component c JOIN log_entry e ON e.id = c.entry_id
 WHERE e.user_id = $1 GROUP BY 1 HAVING count(DISTINCT c.fdc_id) > 1;
```

**Six rows today, and four of them are traced failures:**

| label | rows |
|---|---|
| butter | `Butter, stick, unsalted` → `Butter, salted` — **FAILURES #2** |
| egg whites | `Egg, whole, cooked, fried` → `Egg white omelet…` — **FAILURES #1** |
| pickle juice | `Relish, pickle` → user's own `Pickle juice` — **FAILURES #6** |
| nesquik cereal | `Cereals, MALT-O-MEAL, chocolate, dry` → own `Nesquik cereal` — **#3 shape** |
| blondie | -249 → -289 — **FAILURES #7** |
| sugar | `Sugar, white, granulated` / `Sugars, granulated` |

A wider join against `food_alias` finds **8 aliases whose current `fdc_id`
differs from one a component was logged under** — including
`mixed meat (chicken and pork)` → `Chicken, stewing, meat and skin, cooked,
stewed`, and `garlic`, which has been pointed at two *different USDA rows with
the identical description* `Garlic, raw` (1104647 Foundation, 169230 SR Legacy).
Every one of these re-pointings is invisible in `food_alias` itself and
recoverable only by inference. `first_fdc_id` (§2.5) makes it a lookup.

### M4 — The same food twice in one meal *(runs today)*

FAILURES.md #8 ends: *"no check anywhere noticed one entry containing the same
`fdc_id` twice."* Six lines of SQL:

```sql
SELECT e.id, e.name, c.fdc_id, count(*), string_agg(c.label, ' + ')
  FROM log_component c JOIN log_entry e ON e.id = c.entry_id
 WHERE e.user_id = $1 GROUP BY 1,2,3 HAVING count(*) > 1;
```

**Four entries today, covering two traced failures:**

- 24598 `Baked turkey breast`: `baked turkey breast 400 g` + `turkey breast. 80 g`
  on 171492 — **FAILURES #8**, exactly.
- 18176 / 18177 / 18178: `whole egg` + `egg whites` both on
  `Egg, whole, cooked, fried` — **FAILURES #1**, and 18177 is *confirmed*.

Would also have caught **FAILURES #5** (one bottle photographed twice) if the two
descriptions had pooled to one row; where they resolve to two near-duplicate rows
it needs the album guard, which is the input layer's.

### M5 — Rejection rate per food row *(runs today)*

Discards are a labelled dataset nobody reads. 39 discarded entries for user 2,
and the `log_nutrient` snapshot splits them cleanly: **28 rejected at the confirm
gate** (no snapshot ever written) and **11 undone after being confirmed** — the
strongest correction signal the system can generate, a human who said yes and
then looked again.

```sql
SELECT c.fdc_id, f.description,
       count(*) FILTER (WHERE e.status='discarded') AS rejected,
       count(*) FILTER (WHERE e.status='confirmed') AS kept
  FROM log_component c JOIN log_entry e ON e.id=c.entry_id JOIN food f USING (fdc_id)
 WHERE e.user_id=$1 GROUP BY 1,2 HAVING count(*) >= 3
   AND count(*) FILTER (WHERE e.status='discarded') > 0
 ORDER BY 3::numeric/count(*) DESC;
```

**The top row of the output is `Egg, whole, cooked, fried` — 4 rejected, 3 kept,
57%. FAILURES #1, first in the list, from a query nobody has ever run.** Third is
`Chicken or turkey cordon bleu`, 2 rejected 1 kept — FAILURES #3.

The named discards read as a table of contents for FAILURES.md: `pickle juice`
×4, `Blondie` ×3, `Nesquik cereal`, `Tuna fillets from jar`,
`Coffee + orange juice drink`. Five of the eight traced cases announced
themselves by being thrown away, and the throwing-away was recorded as a single
status flag with no reason and no timestamp.

**Two cheap fixes to the signal itself:** `log_entry` has no `discarded_at` and no
`discard_reason`, so a gate-reject, a same-day undo and a week-later correction
are one undifferentiated bit. Add both. A free-text reason is optional and a
timestamp is not.

### M6 — Cache rows the current logic would refuse *(runs today)*

Any `food_alias` or `dish_component` pointing at a row that today's
`search_foods` predicate excludes — `UNUSABLE_ROW` (macros present, no energy) or
`retired_at IS NOT NULL`.

**Aliases: zero.** That is the interesting result, and §4 leans on it:
`resolve_alias` was given the `UNUSABLE_ROW` skip on 18 Aug, stale aliases were
bypassed rather than purged, and every one self-healed on next use. The `butter`
alias that FAILURES #2 describes now points at `Butter, salted`.

**`dish_component`: three, and nothing has ever checked it.**

| dish | times_logged | component | points at |
|---|---:|---|---|
| Baked potato, corn on the cob, meat and salad | 1 | butter | `Butter, stick, unsalted` — no energy |
| Baked potato, corn on the cob, green salad… | 1 | butter | `Butter, stick, unsalted` — no energy |
| Sparkling water | **7** | Muszynianka sparkling water | own row, no energy |

Plus a dormant `Fried egg, tomato slices, rye bread` still carrying
`egg whites → Egg, whole, cooked, fried`, the FAILURES #1 row, after the alias was
corrected.

`UNUSABLE_ROW` and `retired_at` are enforced in exactly three places in `db.py` —
`resolve_alias`, `search_foods`, `user_foods` — and **on no path the repeat
system touches**, which is where 45% of components come from and where an
unmodified repeat of a confirmed dish logs with no confirmation gate at all.
Repeating either butter dish re-injects the zero-calorie row today.

*(The `Sparkling water` row is a true negative for nutrition — mineral water has
no energy because it has none — and it is why the audit's existing
`no_energy_row` check has fired twice on a correct match. See §5.)*

### Not claimed here

**FAILURES #4** (sugar under two USDA ids) and **#7** (impossible recipe yield)
are not observability failures. #4's signal is nutrient coverage; #7's is
arithmetic — 160 g of macronutrient inside 100 g of food — and belongs to the
validation layer as a hard reject, not to a measure. Both are named so the
reconciling lead does not assign them here.

---

## 4. Cache and version invalidation

### 4.1 Can the 132 existing aliases be audited for which logic produced them?

**No, and this is not recoverable.** `upsert_alias` re-points `fdc_id` without
touching `created_at`, so the date is the age of the *name*, not of the *match*.
Eight aliases are provably younger than their `created_at`; the remaining 124 are
unfalsifiable in either direction.

The best available bound is a count, not an identification:

| | aliases |
|---|---:|
| created before the `user_product` precedence fix (`84d6eb8`, 23 Aug) | **93 / 132** |
| created before the energy-less-row exclusion (`73b30be`, 18 Aug) | **56 / 132** |

For context, **88 commits touched `llm/parse.py`, `db.py` or `config.py` since
1 Aug — 29 of them `llm/parse.py` directly — and the entire 160-entry corpus was
logged between 16 and 25 Aug.** The resolver changed roughly three times a day
throughout the period that produced every row it is being judged on. There is no
`schema_migrations` table either, so which `sql/0NN_*.sql` files have been applied
to this volume is also unrecorded.

**The honest disposition for the existing cache: stamp all 132 with
`resolver_version = 0` and let the floor re-resolve them lazily.** At the
observed disambiguate cost of $0.00195/call, re-resolving every alias in the
database is **under $0.26 worst case**, and most will re-hit tier 2 for free.
That price makes the decision trivial and it should be stated rather than debated.

### 4.2 The two version numbers

```python
RESOLVER_VERSION = 7   # bumped by hand when resolution behaviour changes
RESOLVER_FLOOR   = 5   # cached resolutions below this are re-resolved on next use
```

Two numbers because there are two relationships — the same shape as
CLAUDE.md's `canonical_id` / Atwater note. `RESOLVER_VERSION` **records**:
bump it in any commit that changes candidate generation, ranking, the tier logic
or a threshold. `RESOLVER_FLOOR` **invalidates**: raise it only when the change
would have produced a *different answer* for already-cached names. Most bumps
move the first number and not the second.

Not a git sha. A sha is 88 commits of noise and cannot be compared with `>=`. The
version is the author's explicit claim that behaviour changed.

### 4.3 Invalidation is lazy and predicate-based, never a purge

There is working precedent in this repo and §3/M6 measured it: `resolve_alias`
skips `UNUSABLE_ROW` rows, the stale ones were bypassed rather than deleted, and
**all of them self-healed to correct rows on next use**. Generalise exactly that.

```sql
-- in resolve_alias's WHERE clause
AND (a.pinned OR a.resolver_version >= $floor)
```

A stale alias is not returned; the name falls through to search; `upsert_alias`
writes it back stamped with the current version. No migration, no bulk
re-resolution job, no cost at all for a food never eaten again. The user sees a
confirm card for a food they have logged before, which is the correct amount of
friction for "the logic that matched this has changed".

**Rules:**

1. **A pinned alias is never invalidated, at any floor.** Pinning is a human
   assertion about a specific row and it outranks a logic change. This is already
   `upsert_alias`'s contract; the floor must not route around it.
2. **`verified_at` does not confer immunity.** It records that someone looked,
   not that they asserted. One alias of 132 carries it. Only `pinned` protects.
3. **`dish_component` is covered by the same floor**, and this is the change with
   the most reach: 162 of 363 components arrive that way and today nothing checks
   them at all. But a repeat must **not** silently re-resolve — that would change
   what a repeat means, and invariant 5's no-confirm exemption depends on the
   components being the ones a human already approved. So: if any component of a
   dish is below the floor or fails the current row predicate, **the repeat loses
   its no-confirm privilege** and goes through the gate with the affected
   component named. Cheap, honest, and it converts M6's three live rows into
   three visible questions.
4. **`log_component` is never invalidated.** Invariant 2. `resolver_version` is
   recorded there solely to answer "which historical rows came from the old
   logic" — and, once `resolution_event` exists, to make an offline re-resolution
   diff meaningful.
5. **`resolution_event` is never rewritten.** It records what was decided under
   the rules in force, including `threshold`. Re-interpreting an old decision
   against a new constant is the same class of error as recomputing a historical
   entry from current USDA.

---

## 5. How it surfaces

`/audit` exists, the user runs it, and it is the right place. But it cannot
absorb four more checks as it stands.

**Measured today, `/audit` (days=7) returns 33 findings across 21 distinct
summaries.** The most frequent single line —
`Lemon lime water: macros imply 17 kcal, stored 12` — appears **7 times**. Over
30 days it is 39 findings, 23 distinct, and 12 of them are three recurring
dishes restating themselves. The one genuine error in the list
(`fillets, is matched to a meat substitute`) is one line among 33. Two of the
three `no_energy_row` findings are false positives on mineral water, which
genuinely has no energy.

So the surfacing work is three changes to `render.audit_card` and `audit.py`,
and they must land **with** the new checks rather than after:

1. **Collapse by cause, not by entry.** Group on (code, dish name, rounded
   figure) and print `×7`. Seven identical lines about the same recurring drink
   are one finding with a frequency.
2. **An absolute floor beside every relative one.** A 5 kcal disagreement on a
   glass of lemon water is not evidence of a mis-resolution. `atwater_mismatch`
   needs `AND abs(delta) > 25` alongside its 12%.
3. **An `audit_finding` table so a finding can be adjudicated once.** Key on
   (user_id, code, entry_id | subject_key), with `dismissed_at` and an optional
   note. The Muszynianka row is correct, the user knows it, and there is
   currently no way to say so — which is how a check that fires wrongly twice
   trains its reader to skim the whole card.

**Do not schedule it.** CLAUDE.md retired the daily match check for being a wall
of database diagnostics arriving in the evening about foods logged days earlier,
and a daily audit is the same message. It stays pull. Adding these measures makes
it *worth pulling*; it does not earn it an interruption.

**One new pull command, `/trace <entry_id>`**, printing per component: label,
tier, chosen row, score, runner-up and score, and the flags M1/M2 raised. It is
one query against `resolution_event` and it is the whole point of §2 — the
command that makes "why did this become that" answerable in ten seconds instead
of the hour this document took.

### The cheaper surface, offered to the validation layer

M1 and M2 are both computable **before the confirmation card is drawn**, at zero
marginal cost, because `_candidates` has already run and the scores are in
memory. A card reading

> Cosmic cereal → **Wheat cereal, chocolate flavored, cooked** (0.63)
> your own **Lubella Cosmic Cereal** scored 0.62

would have stopped this morning's 327 kcal error at the gate, with the packet on
the table. `/audit` is for what escapes; the card is where the person who can
adjudicate is standing. I claim only the data — the card belongs to the
validation and rendering layer, and it should take this.

---

## 6. Explicit challenges to other layers

**To the thresholds layer.** `AUTO_MATCH_SIMILARITY = 0.62` decided today's
failure **in the fourth decimal place**: 0.63414633 beat 0.61904764. CLAUDE.md
says the constant is arbitrary and must be tuned against the eval set. My
challenge is stronger than "tune it": *no single scalar can carry this decision*,
because the distribution of correct and incorrect matches overlaps at every value
you could pick, and one user with 118 entries can never separate them. The
provenance record (§2) is the precondition for tuning it at all — you cannot
choose a threshold from data that never stored what anything scored. **Do not
propose a new number until `match_score` and `runner_up_score` have been written
for a fortnight.**

**To the candidate-generation and ranking layer.** Pooling `search_terms`, the
user's label and the dish name by *max* score means the winning query is never
recorded, and the same row's score depends on which of three phrases matched it.
Ranking on a max over heterogeneous queries is comparing scores that are not on
the same scale. `resolution_event.queries` plus per-candidate per-query scores
would let you test that claim; nothing today can.

**To the user-product / precedence layer.** The `own` guard requires
`sim >= AUTO_MATCH_SIMILARITY` before `precedence = 0` can pre-empt, and that
gate is doing the opposite of what its comment claims: *"a row you wrote from a
packet in your hand is not a candidate to be weighed against a national average"*
— and then it weighs it, against the same threshold, and loses by 0.00095. If the
principle is right, the comparison should be between the own row and the pooled
head, not between the own row and a constant. M1 shows two live cases sitting
within 0.005 of the line.

**To the repeat / dish layer.** `dish_component` is a second, independent cache
of resolutions, it carries no provenance, it is subject to no invalidation
predicate, and it supplies 45% of all components on a path that can log without a
confirm gate. Every guard added to `food_alias` this month left it untouched.
Three live rows today (§3/M6).

**To the parse-and-write layer.** `log_component.state` is `as_logged` on all
363 rows. The column exists, the parser fills the field, the card renders it, and
`_write_components` has no `state` in its INSERT. Today's failure matched a
**cooked** row to a food eaten dry, and the stored data cannot see it. One line.

**To the validation layer.** Take the confirm-card surface in §5. Also: M4
(duplicate `fdc_id` in one entry) is a pre-confirm check, not an audit check —
FAILURES #8 was confirmable and confirmed.

---

## 7. Deferred, and what genuinely needs a fleet

**Deferred — right idea, wrong time.**

- *Any rate, percentage or time-series of resolution quality.* n = 118 entries,
  96 distinct foods, 10 days. "Auto-match precision fell 4% this week" over six
  components is noise with a decimal point. Counts and named rows only, until
  the corpus is months rather than days.
- *Offline re-resolution diff* (re-run current logic over all 96 distinct foods,
  diff against stored `fdc_id`). Cheap and genuinely useful — but only becomes
  *interpretable* once `resolution_event` records what the old run saw. Write it
  as a one-off script after §2 lands, not as a system.
- *Sweeping `pending_action`.* 133 of 138 rows are expired and nothing deletes
  them. Real, trivial, unrelated to this failure class.
- *Photo retention for re-scoring.* `photo_file_id` is stored; whether Telegram
  file ids remain fetchable months later is unverified, and ARCHITECTURE §12's
  argument for retention is the input layer's to make.

**Genuinely needs a fleet — do not build here.**

- *A/B or holdout evaluation of thresholds and ranking.* Needs traffic that can
  be split. One user cannot be a control group for himself.
- *Shadow resolution against live traffic.* There is no live traffic; there is a
  man with a phone and a laptop that sleeps.
- *Prometheus, Grafana, alerting, latency SLOs, error-budget anything.* There is
  no on-call, no fleet, and no process running when the lid is shut. The p95
  latency of a resolver invoked six times a day is a number with no decision
  attached to it. `llm_call` already stores per-call latency and cost, which is
  the entirety of what that machinery would have told him.
- *A dashboard.* `/audit`, `/trace` and a psql prompt against a database he
  already opens in Adminer. Anything more is a second interface to keep truthful.
