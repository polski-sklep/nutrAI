# SPEC-1 — USDA FoodData Central: ingestion and interpretation

Agent 1 of nine. Investigation and specification only; no code was changed.
Every number below was produced by a read-only query against the live database
on 25 Aug 2026, or read out of the file cited. Where I could not settle a
question with a query I say so.

Baseline for reproduction: `pytest -q -m "not integration"` → **293 passed, 93
deselected, 3.04 s**.

---

## 1. What is actually true today

### 1.1 What is loaded, and in what proportion

`scripts/load_usda.py:31` fixes the datasets:

```python
DEFAULT_TYPES = ("foundation_food", "sr_legacy_food", "survey_fndds_food")
```

Branded is opt-in behind `--branded` and has not been loaded.

```
     data_type     | count           fdc_id range          contiguous?
-------------------+-------          -------------------   -----------
 sr_legacy_food    |  7793           167512 – 175304       no
 survey_fndds_food |  5432           2705383 – 2710814     YES (span 5431, count 5432)
 foundation_food   |   411           321358 – 2727589      no
 user_product      |    14           -565 – -3             n/a
                     -----
 total food rows     13650   (13649 live, 1 retired)
 food_nutrient rows  1017178
 food_portion rows    36684
```

The FNDDS block is *exactly* contiguous. That is not decoration; it is the
single most important fact in section 1.8.

Usage is the inverse of quality ranking. Over 283 confirmed components:

```
     data_type     | components |   grams   | aliases
-------------------+------------+-----------+--------
 survey_fndds_food |        126 |  14,818.9 |      53
 sr_legacy_food    |        100 |   4,787.5 |      54
 user_product      |         35 |   4,167.7 |      15
 foundation_food   |         22 |   2,503.0 |      13
```

FNDDS — ranked third of four by `food.precedence` — supplies **45% of components
and 57% of logged mass**. Foundation, ranked first, supplies 8%.

**Are rows with different semantics mixed without the difference being
represented? Yes, completely.** `food.data_type` appears in exactly one place in
the entire application outside `db.py`'s own SQL:

```
nutrai/llm/parse.py:468:   f"{c['fdc_id']}: {c['description']} [{c['data_type']}]" for c in cands
```

— the candidate string handed to the disambiguation model. It never reaches the
confirmation card, never reaches the day card, never reaches `/why`, never
appears in a warning, and is used in Python control flow nowhere. The only
structural expression of dataset semantics is `food.precedence`
(`sql/014_user_foods.sql:20-27`), and section 4.1 shows precedence decides
essentially nothing.

The three datasets are not three grades of the same thing:

- **SR Legacy** (7,793 rows, final release 2018) is a *reference* table of
  ingredients, explicit about raw/cooked/drained state in the description.
- **FNDDS** (5,432 rows) is *survey* data: foods as consumed, already prepared,
  built around household portions. It carries 22,046 of the 36,684
  `food_portion` rows.
- **Foundation** (411 rows) is *analytical*: full panels where they exist,
  and frequently incomplete where they do not.

None of that distinction survives into the system.

### 1.2 The per-100 g basis: verified, and violated only by our own writes

`sql/001_schema.sql:46` asserts it as a comment; `core/nutrition.py:69-73`
relies on it:

```python
def scale_profile(profile, grams, yield_factor=1.0):
    """profile is per 100 g of the USDA row. Returns absolute amounts."""
    k = (grams * yield_factor) / 100.0
```

The loader does nothing to the amount column — `recs.append((fid, nid,
float(amt)))` at `scripts/load_usda.py:163` — so the claim rests entirely on
FDC. I tested it against the data by proximate closure (protein + fat +
carbohydrate + water + ash + alcohol per 100 g, which must be ≲ 100):

```
     data_type     | rows | >105 g | >120 g | worst    | max kcal/100g
-------------------+------+--------+--------+----------+--------------
 foundation_food   |  403 |      0 |      0 | 101.8    |    833
 survey_fndds_food | 5431 |      0 |      0 | 101.3    |    902
 sr_legacy_food    | 7793 |      3 |      0 | 106.5    |    902
 user_product      |   13 |      3 |      0 | 116.5    |    510
```

**The USDA claim holds.** The three SR Legacy outliers are known FDC artefacts
(`Fish, salmon, chinook, cooked` 106.5 g — protein by nitrogen conversion and
water measured separately). Max energy 902 kcal/100 g is pure fat, exactly as
it should be.

**Our own rows do not hold.** 3 of 13 `user_product` rows exceed 100 g of food
per 100 g of food. Detail:

```
 fdc_id | description                   | P+C+F | +water+ash | kcal | retired
--------+-------------------------------+-------+------------+------+--------
   -108 | Mixed meat (chicken and pork) |  30.5 |      116.5 |  163 | no
   -289 | Blondie                       |  97.0 |      112.2 |  510 | no
   -249 | Blondie                       |  96.9 |      111.9 |  337 | YES
```

`-289 Blondie` is the live alias target (`blondie → -289`, 6 hits, 5 confirmed
components, 137.7 g logged). It is ~11% over-dense and has never been retired;
`-249` was.

Places that rely on per-100 g, all of which inherit the violation:

| location | expression |
|---|---|
| `core/nutrition.py:71` | `k = (grams * yield_factor) / 100.0` |
| `db.py:814` | `c.grams_sigma * c.yield_factor * fn.amount / 100.0` |
| `db.py:1507,1509,1523` | `c.grams * c.yield_factor / 100.0 * fn.amount` |
| `db.py:2117` | `c.grams * c.yield_factor * fn.amount / 100.0` |
| `bot.py:2342` | `per_100g = {nid: amount / yield_g * 100 ...}` |
| `off.py:34-59` | OFF `*_100g` fields mapped straight in |
| `llm/parse.py:744` | `scale = 100.0 / float(grams)` for per-serving panels |

### 1.3 Nutrient ids and the canonical fold

`nutrient` holds 205 G, 186 MG, 70 UG, 3 IU, 3 KCAL, plus `UMOL_TE`, `MCG_RE`,
`SP_GR`, `MG_GAE`, `MG_ATE`, `kJ`, `PH` — 12 distinct units.

One fold exists (`sql/025_canonical_nutrients.sql`): `1063 Sugars, Total →
2000 Total Sugars`. The dataset alignment is exact:

```
 id   | name          | FNDDS | SR   | Foundation
------+---------------+-------+------+-----------
 1063 | Sugars, Total |  5431 |    0 |   160
 2000 | Total Sugars  |     0 | 6007 |     5
```

The fold is applied in three places, as CLAUDE.md says:
`v_day_nutrient` and `v_day_supplement_nutrient` (`sql/025`), and
`db._profiles_con` (`db.py:539-543`, the write path). `day_nutrient_coverage`
(`sql/026`) also consults `v_nutrient_canonical`. Section 2.2 shows two further
places that need it and do not have it.

**Is any other id pair silently split?** I ran the detection without the name
filter, across all nutrients used by >50 foods, and separately tabulated every
nutrient's presence by `data_type`. The answer is:

- **No unmapped same-measurement pair remains where both ids share a unit.**
  The dataset-aligned candidates are `1063/2000` (folded) and `1119
  Zeaxanthin` / `1123 Lutein + zeaxanthin` (FNDDS 5431/0 vs SR 0/5294 —
  perfectly complementary, correctly on the exceptions list, because 1123 is a
  sum containing 1119; neither is targeted or in `CORE_NUTRIENTS`).
- Several **cross-unit** same-measurement pairs exist and are *not* splits in
  practice: `1104 Vitamin A, IU` (SR only, 7,356 rows) beside `1106 Vitamin A,
  RAE` (5,431 + 6,918 + 78); `1110 Vitamin D IU` (SR only, 5,181) beside
  `1114 Vitamin D µg` (5,431 + 5,185 + 62); `1062 Energy kJ` (SR + Foundation)
  beside `1008 Energy kcal`. In every case the targeted id is carried by every
  dataset that matters, so nothing goes uncounted. `1062` causes a different
  problem — see 2.1.
- **Coverage asymmetries that are not splits but behave like them.** Foundation
  reports `1177 Folate, total` on 146 rows and `1186/1187/1190` on **zero**;
  `1268 MUFA 18:1` on 7 rows of 411 while SR has 7,015; `1180 Choline` on 42.
  These are genuine measurement gaps and the coverage machinery is the right
  answer to them, not folding.

### 1.4 Assessment of `test_no_targeted_nutrient_is_silently_split`

`tests/test_integration.py:3151-3203`. Its filters are: both ids used by >500
distinct foods, same `nutrient.unit`, `similarity(name_a, name_b) > 0.45`,
canonical ids differ, and overlap < 100 foods.

**Its exceptions list is correct.** `(1119, 1123)` is the only pair that reaches
the assertion, and the stated reason — 1123 is a sum already containing 1119, so
the rule is prefer-one rather than fold — is right.

**Its method is sound in outcome and mislabelled in the docstring.** The
docstring says the signature is complementary coverage and that name similarity
"finds nothing but false positives among the fatty acids". Running the query
with the name filter removed returns 60+ pairs at the same overlap thresholds —
`1063 Sugars, Total` against every single amino acid, `1002 Nitrogen` against
five saturated fatty acids. Complementary coverage on its own is almost pure
noise, because *any* two nutrients whose datasets differ look complementary.
The discriminator that does the work is name similarity; complementary coverage
is the confirmer. The docstring has it backwards, which matters because someone
loosening the name filter to "widen the net" would get 60 failures and delete
the test.

Three blind spots, each statable and each currently harmless:

1. **`count(DISTINCT fdc_id) > 500` makes Foundation-only ids undetectable.**
   Foundation has 411 rows total. `2047` (322 rows) and `2048` (312) can never
   be flagged. They are handled deliberately elsewhere, but the test cannot see
   a *future* Foundation-only id.
2. **`a.unit = b.unit` makes every cross-unit pair undetectable** — the vitamin
   A IU/RAE and vitamin D IU/µg families, and `1062 kJ` vs `1008 kcal`. Those
   need convert-then-prefer-one, not fold, so excluding them is defensible; the
   test just should not be read as covering them.
3. **`similarity > 0.45` misses a split whose two names are not trigram-close.**
   No such pair exists in the current load. It is a real gap on a future one.

### 1.5 Energy: two folding rules, both correct, inconsistently applied

Measured, by dataset:

```
     data_type     | foods | has 1008 | has 2048 | has 2047 | no energy at all
-------------------+-------+----------+----------+----------+-----------------
 sr_legacy_food    |  7793 |     7793 |        0 |        0 |        0
 survey_fndds_food |  5432 |     5431 |        0 |        0 |        1
 foundation_food   |   411 |      135 |      312 |      322 |       58
 user_product      |    14 |       13 |        3 |        3 |        1
```

411 − 135 = **276 Foundation rows lack 1008**, matching the comment at
`core/nutrition.py:44`. Note the correction to `docs/resolution/FAILURES.md`
case 2, which reads "276 of 411 Foundation rows have no 1008 **and no Atwater
fallback**": only **58** have no fallback. 218 of the 276 are rescued by
`normalise_energy`.

The two rules are both right and both stated:

- **Sum** (`canonical_id`): same measurement under two ids.
- **Prefer one** (`ENERGY_FALLBACKS = (2048, 2047)`, `core/nutrition.py:61`):
  alternative estimates of the same thing. Summing 1008+2047+2048 would treble
  a Foundation row. Preferring 2048 (specific Atwater factors) over 2047
  (general) is correct — specific factors are derived per food.

Applied consistently in the read/write path (`db._profiles_con:548`), the
coverage function (`sql/026`, `n.id = 1008 AND fn.nutrient_id IN (2047,2048)`,
with `EXISTS` rather than a join precisely so a row carrying both does not
double its mass), and the candidate filter (`db.py:107, 197, 237`). **Not**
applied in `db.day_energy_sigma` (`db.py:814`) — see 2.3.

A consequence nobody appears to have intended: because energy is deliberately
outside `canonical_id`, `_profiles_con` returns 2047 and 2048 as *separate keys*
alongside the filled 1008, `total_nutrients` sums all keys, and the snapshot
gets all three. Live proof:

```
 nutrient_id | name                              | unit | entries | total
-------------+-----------------------------------+------+---------+--------
        1008 | Energy                            | KCAL |     127 | 22227.4
        1062 | Energy                            | kJ   |      91 | 48737.9
        2047 | Energy (Atwater General Factors)  | KCAL |      28 |  1630.3
        2048 | Energy (Atwater Specific Factors) | KCAL |      28 |  1574.2
```

`log_nutrient` carries four energy rows per entry. `day_progress` only reports
nutrients with a `target` row so none of the three extras display there, but
`db.find_nutrients` has no such protection — 2.1.

### 1.6 Units: read correctly in three places, ignored in one

- `render.fmt_amount` (`core/render.py:105-115`) switches on `nutrient.unit`
  from the database. Correct.
- `core/supplements.convert` (`core/supplements.py:45-76`) is the model of how
  this should be done: `_MASS` scale table, `mcg`/`ug` normalised, IU refused
  for every nutrient except `1114 Vitamin D` (`_IU_TO_UNIT`, 0.025 µg/IU by
  definition) because vitamin A IU spans 12× on source form and vitamin E IU
  differs natural vs synthetic. `nutrient.unit` is passed in as the target.
- `off.py:34-59` hard-codes the multiplier per OFF field (`sodium_100g` ×1000
  for g→mg, `vitamin-b12_100g` ×1e6 for g→µg). Correct today but it assumes the
  USDA unit rather than reading it.
- **`llm.per_100g` (`llm/parse.py:721-758`) ignores units entirely.** See 2.1.

No IU-unit nutrient is in `CORE_NUTRIENTS` or `RDA_MALE`, and
`llm/parse.py:_nutrient_menu()` offers the model only metric ids, so nothing
targeted is denominated in IU.

### 1.7 Missing vs zero

Invariant 6 holds where it was designed to:

- `core/nutrition.py:total_nutrients` skips absent nutrients (`if not prof:
  continue`; only keys present are summed).
- `core/plan.py:_median_row` renders an absent median as `-` with the text
  "no data — nothing logged in this window reports it", never 0.
- `day_nutrient_coverage` exists and `/today` consults it (`bot.py:626`), as
  does the morning note (`jobs/notify.py:249`).

Places that do conflate the two, in descending order of consequence, are listed
as defects in 2.3, 2.5 and 2.6.

### 1.8 Reload safety, and the absence of any data version

**There is no record anywhere of which FDC release is loaded.** No table, no
column, no file. `\dt` lists 30 tables and none is a version or metadata table;
`grep -rn "release\|fdc_version\|data_version\|loaded_at" sql/ scripts/` returns
nothing. The only trace is the docstring example path in
`scripts/load_usda.py:6`, which names `FoodData_Central_csv_2025-04-24`, and the
comment at `core/nutrition.py:45` citing "the 2025-04-24 release". Neither is
data.

What `load_usda.py:39-79` actually does on a re-run is stage-and-upsert, never
delete. That has three consequences:

1. **Existing `log_component.fdc_id` and `food_alias.fdc_id` never break.** No
   row is removed, so no foreign key is violated and no history becomes
   unreadable. This is the good half and it is deliberate — the docstring at
   `load_usda.py:41-49` explains why `TRUNCATE nutrient CASCADE` would take
   `target` and `log_nutrient` with it.
2. **`nutrient.canonical_id`, `food.owner_user_id`, `food.retired_at`,
   `food.yield_grams` all survive a reload**, because `copy()` builds its `SET`
   clause only from the columns it was given
   (`load_usda.py:69`) and none of those is in the list. Verified by reading;
   worth an explicit test.
3. **A newer FNDDS release will double the survey corpus rather than replace
   it.** The current FNDDS block is 2705383–2710814: 5,432 rows in a span of
   5,432. FDC issues each FNDDS release as a fresh contiguous id block, so a
   reload adds ~5,400 new rows and leaves ~5,400 stale ones. `food` becomes
   ~19,000 rows containing two vintages of the same survey foods, both
   `data_type = 'survey_fndds_food'`, both scoring identically on trigram, and
   `precedence` cannot tell them apart. Every alias then points at the *old*
   vintage forever, because an alias is a cache and nothing invalidates it.

   Foundation accretes similarly (id range 321358–2727589 is not contiguous).
   SR Legacy is frozen at its 2018 final release and is safe.

Additionally, if `--branded` is ever passed once, the ~2M branded rows are
permanent: dropping the flag on a later run does not remove them.

### 1.9 Aliases: 135 rows, 1 verified, 0 pinned

```
 user_id | aliases | total_hits | hits >= 5 | max_hits | pinned | verified
---------+---------+------------+-----------+----------+--------+---------
       2 |     132 |        265 |        15 |        7 |      0 |        1
       3 |       3 |          3 |         0 |        1 |      0 |        0
```

`upsert_alias` (`db.py:143-159`) protects `pinned` rows and nothing else; with
zero pinned rows, **the protection has never engaged**. `resolve_alias`
(`db.py:115-131`) filters retired foods and `UNUSABLE_ROW`, so the two classes
of alias that were caught in production cannot be re-served. Nothing else
invalidates an alias: not age, not hit count, not a change in the underlying
row, not a reload.

What "132 aliases, 1 verified, 0 pinned" means for correctness over time,
stated plainly: **every alias is an unreviewed cached judgement with unbounded
future reach, and there is no recorded evidence of what any of them was checked
against.** `food_alias` has `created_at` and `verified_at`, but neither records
the FDC release or the `food.description` at the time. If a reload changes a
description under an alias, nothing anywhere can detect it. 15 aliases have
already been served 5+ times each; the highest-traffic ones are exactly the ones
the pinning pass was designed for and none has been pinned.

Illustrative live rows: `flour → Wheat flour, white, all-purpose, **unenriched**`
(5 hits) — enrichment is the entire folate and iron content; `alpro coconut milk
→ Coconut milk` (5 hits, FNDDS) — the drink and the cooking ingredient differ by
a factor of ~4 on fat; `blondie → -289` (6 hits) — the over-dense row from 1.2.

35 aliases point at foods never actually logged.

---

## 2. Defects, ranked by capacity to produce a materially wrong nutrient value

### D1 — A transcribed food label's unit is required, collected, and discarded

`llm/schemas.py:379` requires `unit` on every nutrient line of
`FOOD_LABEL_TOOL`. `llm/parse.py:751` throws it away:

```python
out[int(n["nutrient_id"])] = float(n["amount"]) * scale
```

There is no unit conversion anywhere on this path. `core/supplements.convert`
does exactly this job, correctly, for the supplement panel — the food-label path
does not call it.

Magnitude: a label reading "Vitamin D 1000 IU" is stored as 1000 µg against a
15 µg target and a 100 µg UL — 40× and above the tolerable upper intake. Sodium
printed in g rather than mg is 1000×. The confirm card
(`core/render.py:2484-2491`) prints `as_printed` verbatim beside the stored
number **without a unit on the stored number**, so "Vitamin D 1000 IU | 1000.0"
reads as correct and the human gate cannot catch it.

Worse alternative already available to the model: `_nutrient_menu()`
(`llm/parse.py:660-685`) states the target unit in each label ("Vitamin D
(ug)"), so the model may silently do the conversion itself — an unlogged,
uncheckable arithmetic step performed by a model, which is invariant 1's line
in a different suit.

No such row exists in the database today. It is first-ranked because nothing
prevents one.

### D2 — `/why <anything about energy>` reports kilojoules

Reproduced against the live database with the real code path:

```
'energy'   -> lookup 'Energy' picks 1062 Energy [kJ]
'calories' -> lookup 'Energy' picks 1062 Energy [kJ]
'kcal'     -> lookup 'Energy' picks 1062 Energy [kJ]
   candidates = [(1062,'kJ'), (1008,'KCAL'), (2047,'KCAL'), (2048,'KCAL')]
```

`db.find_nutrients` (`db.py:1720-1736`) orders by exact match, then prefix, then
`length(name)`. 1062 and 1008 are both named exactly `Energy`, so the tie is
broken by nothing and Postgres returns 1062 first. `bot._explain_nutrient`
(`bot.py:2104-2126`) takes `exact[0]` or `matches[0]` — either way, 1062.
`log_nutrient` holds 48,737.9 kJ across 91 entries, so a full, plausible,
four-digit card renders.

`_set_one_target` (`bot.py:1349-1364`) escapes this only by accident: its
`owned` filter narrows to the id that already has a standing target. On a user
with no energy target yet, `/target calories max 2200` answers "calories matches
several".

The `length(name)` tie-break is not deterministic. This can change under
`VACUUM` or a plan change without any code change.

### D3 — `create_user_food` writes into the shared reference table with no basis check

`db.py:2186-2224` inserts arbitrary `per_100g` values into `food_nutrient` under
a negative `fdc_id`, with no validation at all. Every downstream reader — the
`/ 100.0` list in 1.2, coverage, `portion_history`, the audit, `/why` — then
treats those rows as if they carried FDC's per-100 g guarantee, which is the
explicit design intent of `sql/014_user_foods.sql:9-12`.

The only guard is in the caller, `bot.py:2357`, and it checks the wrong
quantity:

```python
macro_g = sum(per_100g.get(n, 0) for n in (PROTEIN, CARB, FAT))
if macro_g > 100:
```

Protein + carbohydrate + fat is not the mass of the food. `-108 Mixed meat` has
P+C+F of 30.5 g and a proximate total of 116.5 g — it passes. `-289 Blondie` has
P+C+F of 97.0 g and a proximate total of 112.2 g at 510 kcal/100 g — it passes,
and is live, unretired, aliased, and behind 5 confirmed components. The correct
constraint is proximate closure (P + F + carbohydrate + water + ash + alcohol),
whose observed maximum across 13,627 USDA rows is 106.5 g.

Neither the OpenFoodFacts path (`off.py`) nor the label-panel path applies even
the weak guard.

### D4 — `/why sugar` silently omits and then redistributes 53% of components

`db.nutrient_attribution` (`db.py:2093-2135`), the `/why` breakdown, joins
`food_nutrient` on `fn.nutrient_id = $2` with **no canonical fold**, and reads
entry totals from `log_nutrient` on `ln.nutrient_id = $3`, also unfolded.

```
components on a row carrying 1063 and not 2000:  150 of 283  (53%)
confirmed entries with a 1063 snapshot row and no 2000 row:  13
```

So for `nutrient_id = 2000`:

- Those 13 entries return **nothing at all**, while `/today` counts their sugar
  (`v_day_nutrient` folds). `/why sugar` and `/today` disagree by construction.
- Within the entries that do return, the 150 FNDDS-backed components contribute
  zero parts, and `db.py:2129` then rescales what is left to match the stored
  total: `scale = stored / total_parts`. The missing sugar is therefore not
  merely dropped — it is **silently attributed to whichever components happened
  to use id 2000**. The screen names the wrong food as the source.

This is the fourth site the fold needs and does not have. Note that the *other*
attribution function, `db.nutrient_drivers` (`db.py:1490-1526`, used by the week
card and the morning note), folds correctly at line 1515-1518 and also excludes
days marked incomplete. Two attribution functions, one right and one wrong, and
the wrong one is on the interactive command.

### D5 — the day's `±` error bar drops any component whose row lacks 1008

`db.day_energy_sigma` (`db.py:806-821`):

```sql
JOIN food_nutrient fn ON fn.fdc_id = c.fdc_id AND fn.nutrient_id = $3
```

No `(2047, 2048)` fallback, unlike every other energy site. A Foundation row
carrying only Atwater energy contributes kcal to the day (via `normalise_energy`
at snapshot time) and **zero uncertainty** to the day's error bar. 10 of 22
confirmed Foundation components are in exactly that state.

Direction of the error is always the same: the `±` understates. ARCHITECTURE
§4.5 makes that bar the headline honesty signal, so an understatement is the
worst direction available.

Second, smaller problem in the same query: it reads *current* `food_nutrient`
rather than the stored snapshot, so a reload changes historical error bars.
`log_nutrient` is immutable (invariant 2); its error bar is not.

### D6 — `pin_foods.py` scores dataset-aligned ids as missing

`scripts/pin_foods.py:44-45` counts `fn.nutrient_id = ANY(CORE_NUTRIENTS)` with
no fold and no energy fallback. `CORE_NUTRIENTS` contains 2000, so every FNDDS
row loses a point for reporting sugar under 1063; Foundation rows lose one for
carrying only 2048.

```
     data_type     | avg raw | avg folded | thin (<15) raw | thin folded
-------------------+---------+------------+----------------+------------
 foundation_food   |   11.30 |      12.21 |            352 |         334
 sr_legacy_food    |   19.83 |      19.83 |            567 |         567
 survey_fndds_food |   21.00 |      22.00 |              1 |           1
 user_product      |   15.07 |      15.14 |              7 |           7
```

The effect on the thin/not-thin call is small (18 Foundation rows flip). The
effect on the number a human reads while deciding whether to re-point an alias
is systematic and dataset-aligned. The script also prints "/20 core nutrients"
where `CORE_NUTRIENTS` has 22 entries (`nutrient.is_core` count = 22).

### D7 — `config.CORE_NUTRIENTS` mislabels 1177, and the folate target means something else

`config.py:149` comments `1177,  # Folate, food`. 1177 is **Folate, total**;
1187 is Folate, food. The comment is wrong, and `render._SHORT_NAMES:421` maps
`"Folate, total": "Folate"` correctly, so only the comment misleads.

Substantively: `core/profile.py:38` sets `1177: (400, None)  # Folate µg`. The
400 figure is the RDA in **µg DFE** (id 1190), which weights folic acid 1.7× for
bioavailability. Applied to `Folate, total` it is a stricter target than the RDA
it cites. Foundation reports 1177 on 146 rows and 1190 on **zero**, so switching
the target to 1190 would lose Foundation entirely — this is a real trade-off,
not an obvious fix. It should be a recorded decision, not an unnoticed
mismatch.

### D8 — 36,682 loaded USDA portion rows are never read

`food_portion` holds 22,046 FNDDS rows, 14,449 SR Legacy, 187 Foundation. The
only reader in the codebase is `db.py:2183`, `WHERE fdc_id = $1 AND id < 0` —
user-defined portions only. The USDA rows are loaded, indexed, backed up, and
inert.

This is not wrong; it is an unexploited asset, and it belongs in this spec
because the layer that needs it (portions) does not know it exists. Filed as a
challenge in section 4, not as a defect to fix here.

### D9 — `window_medians` takes the median over only the days a nutrient appears

`db.py:824-840` groups `v_day_nutrient` by `(local_date, nutrient_id)` and takes
`percentile_cont(0.5)` over whatever rows exist. A nutrient reported on 3 of 28
days yields a median over those 3 days, labelled `median_28d` in the `/improve`
evidence pack.

`core/plan.py:_median_row` correctly renders an *absent* median as `-`. It
cannot render a *present but unrepresentative* one as anything, and the pack's
"## Coverage" section (`plan.py:90-95`) reports **logging** coverage — days
logged, entries per day — not per-nutrient **measurement** coverage. So
`day_nutrient_coverage`, which exists and is correct, does not reach the one
artefact where a model is asked to draw conclusions.

Zero-filling would understate; day-omission overstates. The pack does the second
and says neither.

### D10 — `v_day_nutrient` does not exclude days marked incomplete

CLAUDE.md's "Days that do not count" requires the exclusion to reach *every*
analysis. `v_day_nutrient` (`sql/025`) has no `day_quality` filter, and
`window_medians` reads it directly, so `/improve`'s 7- and 28-day medians
include days the user explicitly flagged as not properly logged.
`nutrient_drivers` does filter (`db.py:1518-1521`). Adjacent to my layer rather
than in it; recorded so the lead can route it.

---

## 3. The canonical ingestion / interpretation spec

Each rule is testable as written. Rules are numbered U1… so other specs can
cite them.

### Basis and identity

- **U1.** Every `food_nutrient.amount` is **per 100 g of the food as
  described**, in the unit given by `nutrient.unit` for that `nutrient_id`.
  There is no second basis and no per-serving row in this table.
  *Test:* for every `fdc_id`, protein + fat + carbohydrate + water + ash +
  alcohol ≤ 108 g, and energy ≤ 950 kcal. Current worst: 116.5 (a
  `user_product`), 106.5 (USDA).
- **U2.** Any code path that writes a row into `food_nutrient` — the loader,
  `create_user_food`, the OFF importer, the label transcriber, the recipe
  calculator — **must satisfy U1 before the write commits**, and must refuse
  rather than warn. A basis violation is arithmetic, not judgement.
  *Test:* `create_user_food` raises on a payload failing U1.
- **U3.** `food.data_type` carries semantics, not quality grades, and those
  semantics **must be visible wherever a human adjudicates a match**. FNDDS is
  a survey composite as consumed; SR Legacy is a reference ingredient with
  explicit state; Foundation is an analytical panel that is frequently
  incomplete; `user_product` is a locally-defined row.
  *Test:* the confirmation card names the dataset of every component's row.
- **U4.** `food.precedence` is a tie-break and must never be described as the
  mechanism that selects the better-measured row. It is not doing that job
  (see 4.1).

### Nutrient ids

- **U5.** Two relationships exist between nutrient ids and they must not be
  merged:
  - **fold** (`nutrient.canonical_id` / `v_nutrient_canonical`): two ids are
    the same measurement; **sum** them.
  - **prefer-one** (`ENERGY_FALLBACKS`, and any future IU/metric pair): two ids
    are alternative estimates of one quantity; **take the first that exists**,
    never sum.
  Energy (1008 / 2047 / 2048) is prefer-one and must stay out of
  `canonical_id`.
- **U6.** **Every** aggregation, attribution, coverage calculation and
  completeness score over nutrient ids applies the fold and the energy
  prefer-one rule. There is no "display-only" exemption; `/why` is where a
  wrong attribution is acted on.
  *Test:* one enumerated list of the sites, asserted against `grep`. Today it
  should contain `v_day_nutrient`, `v_day_supplement_nutrient`,
  `db._profiles_con`, `day_nutrient_coverage`, `db.nutrient_drivers`,
  `db.nutrient_attribution`, `db.day_energy_sigma`, `scripts/pin_foods.py`.
- **U7.** A nutrient id that is not its own canonical form is never offered as
  a target, never named on a card, and never returned by `find_nutrients`.
  Already enforced for the fold (`db.py:1729`); **must be extended to the
  energy alternates 2047/2048 and to 1062 kJ**, which are not folds and are
  currently reachable.
- **U8.** `find_nutrients` must return a deterministic single answer for every
  term in `render.DISPLAY_TO_USDA`. Where two `nutrient` rows share a name,
  the unit decides and the choice is explicit, not an ORDER BY tie.
  *Test:* for every key of `DISPLAY_TO_USDA`, exactly one candidate survives,
  and its unit is the expected one.

### Units

- **U9.** No code assumes a nutrient's unit. The unit is read from
  `nutrient.unit`, or supplied by a table that is checked against
  `nutrient.unit` at import (`off.FIELDS` qualifies if such a check is added).
- **U10.** Any externally-supplied amount — printed panel, barcode, transcribed
  label — passes through a single conversion function with the nutrient's own
  unit as target, and **refuses** what it cannot convert exactly.
  `core/supplements.convert` is that function and is correct; the food-label
  path must call it rather than reimplement or skip it.
  *Test:* a `read_food_label` payload with `unit: "IU"` on vitamin D converts
  at 0.025; on vitamin A it is rejected, not stored.
- **U11.** Wherever a transcribed number is shown for human confirmation, the
  **stored** value is shown with its unit beside the printed line, so the two
  can disagree visibly.

### Missing vs zero

- **U12.** A nutrient a food row does not report is **absent**. It is never
  summed as zero, never averaged as zero, and never rendered as `0` without a
  coverage figure beside it.
- **U13.** A day, week or window figure computed over a subset of days is
  labelled with the number of days it came from. Omitting days where nothing
  reported the nutrient overstates by exactly as much as zero-filling
  understates; both are U12 violations and neither is currently named.
- **U14.** Every artefact from which a conclusion is drawn — the `/improve`
  evidence pack above all — carries per-nutrient measurement coverage, not only
  logging coverage.

### Reload

- **U15.** The FDC release loaded is **recorded in the database**, with the
  release identifier, the datasets included, the row counts per table, and the
  load timestamp. This is one table and one insert at the end of
  `load_usda.py`. Everything below depends on it.
- **U16.** `load_usda.py` is upsert-only and must remain so — no `TRUNCATE`, no
  `DELETE` — because `log_component`, `log_nutrient`, `target` and `food_alias`
  reference `food` and `nutrient`. The consequence, that stale rows accumulate,
  is handled by U17 rather than by deleting.
- **U17.** Rows present in a previous release and absent from the new one are
  **marked superseded, not removed**: excluded from `search_foods`,
  `resolve_alias` and candidate generation, retained for history. `retired_at`
  already provides the mechanism; the loader must set it.
  *Rationale, measured:* the FNDDS block is a contiguous 5,432-id range. A
  release bump adds a second block and doubles the survey corpus with
  indistinguishable duplicates.
- **U18.** Columns the loader does not own — `nutrient.canonical_id`,
  `food.owner_user_id`, `food.retired_at`, `food.retired_reason`,
  `food.yield_grams`, and every negative `fdc_id` — survive a reload untouched.
  True today by construction (`load_usda.py:69`); assert it, because it is one
  careless `columns` edit away from being false.
- **U19.** A `food_alias` records the FDC release it was resolved against and
  the `food.description` at that moment. A reload that changes either
  invalidates the alias for automatic use — it becomes a suggestion needing
  confirmation, not a cache hit.

### Alias lifecycle

- **U20.** An alias is a cached judgement, and its authority must be a stored
  property rather than an assumption. Three states, all already representable:
  *unverified* (automatic, re-checkable), *verified* (a human confirmed the
  row), *pinned* (never re-pointed). 132 of 135 are unverified and 0 pinned;
  the code protecting `pinned` has never once executed.
- **U21.** The confirm card names the `food.description`, `fdc_id` and
  `data_type` of the row an alias resolved to, every time, not only on first
  resolution. An alias that is never shown cannot be corrected.

---

## 4. Challenges to other layers

Each names the layer, the belief about USDA I think it holds, and why it is not
true.

### 4.1 To the identity-resolution layer — `data_type` is not a quality gradient, and you are using it as one

`food.precedence` ranks Foundation 1, SR Legacy 2, FNDDS 3. That ordering
encodes "best measured first". It is wrong twice over.

First, **Foundation is the *least* complete dataset in this database**, not the
most: mean 11.30 of 22 core nutrients per row against SR Legacy's 19.83 and
FNDDS's 21.00; 352 of 411 Foundation rows report fewer than 15; 276 lack
`1008`; 58 have no energy figure under any id; 48 are excluded outright by
`UNUSABLE_ROW`. Ranking it first is ranking the thinnest panels first. The
`butter` failure was not a fluke of relevance scoring — it is what precedence
asks for.

Second, **precedence decides nothing anyway.** Both `db.search_foods:238-244`
and `llm.parse._candidates:294-297` sort by continuous trigram similarity first
and use precedence only to break an exact tie in a float. Exact float ties do
not occur. The observed result is that FNDDS — third of four — supplies 45% of
components and 57% of mass. If you want dataset semantics to influence
selection, precedence is not the instrument; it has never been consulted.

What I think you actually want and cannot get from `data_type`: a per-row
completeness figure. It is one query
(`count(*) FILTER (nutrient_id IN CORE)`, folded per U6) and it is stable, so
it can be a materialised column.

### 4.2 To the portion layer — FNDDS rows are already as-eaten, and `yield_factor` has never once been used

`yield_factor` is 1.0 on **all 283 confirmed components**, across all four
datasets, min 1.0 max 1.0. ARCHITECTURE §2 calls it "where the real error
lives" and §11 lists raw/cooked confusion as a systematic 25–35% protein error.
The mechanism exists, is stored, is multiplied through six SQL expressions, and
has never carried a value other than the identity.

Two things follow. The disambiguation model is either not returning a yield
factor or the resolve path is discarding it — that is your bug to find, not
mine. And the yield factor is *dataset-dependent* in a way nothing represents:
an FNDDS row describes the food as consumed, so a yield factor against it is
usually 1.0 and correctly so; an SR Legacy row names its state explicitly in
the description and a yield factor is often required. Applying one uniform
policy to both is wrong in one of the two cases whichever policy you pick.
100 of 283 components sit on SR Legacy rows.

Separately: **22,046 FNDDS and 14,449 SR Legacy `food_portion` rows are loaded
and no code reads them** (`db.py:2183` reads only user-defined `id < 0` rows).
FNDDS is survey data built around household measures; that is the dataset's
whole purpose and its portion table is the largest of the three. Before adding
any new portion-estimation machinery, this table is free, exact, and already in
the backup.

### 4.3 To the nutrient-arithmetic and display layer — the fold reaches three of five places that need it

`db.nutrient_attribution` (`/why`) and `db.day_energy_sigma` (the `±` on every
day card) both read `food_nutrient` and `log_nutrient` by raw `nutrient_id`.
Consequences measured in D4 and D5: `/why sugar` omits 13 entries entirely and
misattributes the sugar of 150 of 283 components onto the wrong foods; the
day's energy uncertainty silently drops 10 of 22 Foundation components.

The system already contains a correct implementation of the same query —
`db.nutrient_drivers` folds at line 1515 and excludes incomplete days at 1518.
The two functions differ only in that one was written after the fold existed.

Also yours: `log_nutrient` currently stores **four** energy rows per entry (1008,
1062, 2047, 2048; 22,227 kcal / 48,738 kJ / 1,630 / 1,574 in the totals), because
energy is deliberately outside `canonical_id` and `total_nutrients` sums every
key `_profiles_con` returns. Nothing displays them today only because
`day_progress` joins `target_on`. `find_nutrients` has no such filter, which is
D2.

### 4.4 To the user-food / product layer — you are writing into USDA's namespace without USDA's guarantee

`sql/014_user_foods.sql:9-12` states the design goal exactly: "nothing
downstream can tell the difference between a row you made and a row USDA made."
That is the strength and the exposure. Three of 13 `user_product` rows violate
per-100 g closure and one of them (`-289 Blondie`, 112.2 g/100 g, 510 kcal/100 g)
is live, aliased at 6 hits, and behind 5 confirmed components — while its
predecessor `-249` at 111.9 g was retired for a different reason.

The guard you have (`bot.py:2357`) sums protein, carbohydrate and fat only, and
`-108 Mixed meat` passes it at 30.5 g while carrying 116.5 g of proximate mass —
because the recipe arithmetic summed the constituents' *water* as though nothing
evaporated. Water is not targeted, so the visible symptom is nil; the invisible
symptom is that the row's density is unverifiable.

The check belongs in `db.create_user_food`, not in one caller, because the OFF
importer and the label transcriber reach the same table by other routes.

### 4.5 To the parse / transcription layer — you demand a unit and then discard it

D1. `FOOD_LABEL_TOOL` requires `unit` on every nutrient line
(`llm/schemas.py:379`) and `llm/parse.py:751` never reads it. The supplement
path solves the identical problem correctly in `core/supplements.py:45-76`,
including the genuinely hard part — refusing vitamin A and E in IU because the
conversion depends on the form, and accepting vitamin D at exactly 0.025 µg/IU.

The label path should call `supplements.convert` with `nutrient.unit` as target.
Until it does, `_nutrient_menu()`'s helpful "(ug)" annotations invite the model
to convert silently, which is a model performing nutrient arithmetic —
invariant 1 in substance if not in letter.

### 4.6 To the planning layer — your evidence pack reports logging coverage and calls it coverage

`core/plan.py:90-95` emits "days with any log in last 28" and "mean entries per
logged day". Neither says what fraction of the *mass* sat on rows that report
the nutrient. `day_nutrient_coverage` computes exactly that, correctly, folding
included, and `/today` and the morning note both use it — the one artefact that
asks a model to draw conclusions does not.

Compounding it, `window_medians` takes the median over only the days a nutrient
appears (D9). A nutrient present on 3 of 28 days produces a `median_28d` that is
the median of three days. `_median_row`'s careful "no data" handling covers the
zero case and has no vocabulary for this one.

And `v_day_nutrient`, which `window_medians` reads, does not filter
`day_quality` (D10), so days the user flagged incomplete are in the medians. The
rule in CLAUDE.md is that the exclusion must reach every analysis or it is worse
than none.

---

## 5. What I would defer, and why

**Defer, with reasons:**

- **Re-pointing the folate target from 1177 to 1190 (D7).** Foundation reports
  1190 on zero rows, so the "correct" id costs the dataset. This needs the
  eval-set view of what actually gets logged, not a decision made from the
  reference tables. Fix the comment at `config.py:149`; leave the id.
- **A per-row completeness column on `food` (4.1).** Correct and useful, but it
  is a schema change plus a backfill plus a refresh hook, and the immediate
  wins (D1–D5) need none of that. It is also the natural companion to the
  release-version table (U15), so build both or neither.
- **Reading `food_portion` (D8/4.2).** 36,682 free portion rows are a real
  asset, but consuming them is portion-layer design, not USDA interpretation,
  and it should not be attempted while `yield_factor` is uniformly 1.0 — two
  unvalidated mass mechanisms interacting is how you get an error nobody can
  attribute.
- **Backfilling `retired_at` on superseded rows (U17).** Cannot be done until
  there is a second release to compare against. What is *not* deferrable is
  U15: without a recorded release, the first reload is unrecoverable, because
  nothing will be able to say which of two identical-looking FNDDS blocks is
  the current one.
- **Reworking `test_no_targeted_nutrient_is_silently_split`'s thresholds
  (1.4).** Its exceptions list is right and it currently passes for the right
  reason. Correct the docstring — which has the discriminator and the confirmer
  backwards — and add the three blind spots as comments. Do not loosen the
  filters; that returns 60+ false positives and the test gets deleted.

**Named and explicitly not designed, per the scale of this system:** dataset
drift dashboards, a shadow reload environment, automated FDC release polling, a
nutrient-mapping admin UI. One user, 13,650 foods, no CI. The version table is
one insert; everything above it is machinery with no host here.

**Do not defer:** D1 (unit discarded — 40× on a micronutrient with a UL), D2
(kJ reported as calories, reproducible today), D3 (unvalidated writes into the
reference table, with a live wrong row), D4 (`/why` misattributing 53% of
components), D5 (the honesty bar understating). D1 and D3 can put a permanently
wrong number into `food_nutrient`, which every other layer treats as ground
truth; that is the whole reason this spec exists.
