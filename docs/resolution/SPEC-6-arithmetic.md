# SPEC-6 — Nutrient arithmetic and unit integrity

Agent 6. Investigation only; nothing under `nutrai/`, `tests/`, `sql/` or
`scripts/` was modified. Every number below was computed against the live
database on 25 Aug 2026: 118 confirmed entries, 283 confirmed components,
96 distinct food rows in use, 10 distinct days, user 2.

**Headline.** The arithmetic is correct. Python and SQL agree to the last
significant figure on all 118 entries, and there is no double-scaling anywhere
in the chain. What is wrong is everything around the arithmetic: the one
guardrail that exists (`energy_cross_check`) is mathematically incapable of
detecting the errors it is credited with, its 18 findings are 18 false
positives, and the transcription path writes a printed unit into a column that
means something else. A 28-fold mass error passes the cross-check at −1.3%.

---

## 1. The arithmetic chain, as equations

### 1.1 The single scaling identity

Everything a card shows about food traces to one expression, applied exactly
once per (component, nutrient):

```
amount(n, c) = profile[c.fdc_id][n] × (c.grams × c.yield_factor) / 100
```

`nutrai/core/nutrition.py:69` (`scale_profile`) is the only place this
multiplication occurs; `total_nutrients` (`:75`) sums over it, and
`db.confirm_entry` (`nutrai/db.py:489`) writes the sum into `log_nutrient`.

`profile` is built once, in `db._profiles_con` (`nutrai/db.py:527`):

```
profile[f][n] = Σ { food_nutrient.amount : fn.fdc_id = f
                                         , canonical_id(fn.nutrient_id) = n }
then  profile[f][1008] ← profile[f][2048] or profile[f][2047]   if 1008 absent
```

(`normalise_energy`, `nutrai/core/nutrition.py:54`.)

### 1.2 Multiplication counts, by mass provenance

I traced each path to the point where `ResolvedComponent.grams` is fixed, then
counted the multiplications applied to the USDA figure. `M` = the number of
times a nutrient amount is multiplied by anything.

| path | how `grams` is arrived at | M | evidence |
|---|---|---:|---|
| **stated / scale** | `choose_mass(grams, source)` — the model's number, taken as given | **1** | `parse.py:237` `_mass_for`, non-portion branch |
| **estimate** | `choose_mass` with an optional low/high; the point estimate is a pass-through | **1** | same |
| **declared portion** | `grams = count × food_portion.gram_weight` — one multiplication *of the mass*, none of the nutrient | **1** | `parse.py:270`; `db.portion_for:2179` |
| **repeat / `/fix`** | `c.grams *= op.factor` (Scale) or `*= target/total` (TotalGrams), then sigma recomputed from provenance | **1** | `core/dsl.py:441`, `:445`; `bot.py:3736`, `bot.py:3954` |
| **supplement** | `supplement_nutrient.amount × supplement_log.servings` | **1** | `sql/025:v_day_supplement_nutrient`; `db.log_supplements:1218` |
| **transcribed panel** | `per_100g` scales the per-serving column by `100/serving_grams`, once; then the food is logged like any other | **1 + 1** (panel creation, then logging) | `llm/parse.py:721` |
| **recipe** | `totals / yield_g × 100` once at creation; then like any other food | **1 + 1** | `bot.py:2342` |

**Double-scaling is absent, and I can prove it rather than assert it.** For all
118 confirmed entries I recomputed `total_nutrients` in Python from the stored
components against the current profiles and compared it, nutrient by nutrient,
with the `log_nutrient` snapshot folded through `v_nutrient_canonical`:

```
mismatching (entry, nutrient) pairs = 0        (of ~4,900 pairs)
entries affected                    = 0
```

A double-scale anywhere would have shown as a factor-of-`k` divergence in
exactly the affected class. Likewise at day level against `v_day_nutrient`:
0 mismatches across 10 days.

### 1.3 The two near-misses that are not bugs, and why

**`food_portion.amount` is not 1 for a quarter of USDA's rows.** Row 81567 is
`2 waffles = 70 g`. `_mass_for` computes `count × gram_weight`, which for that
row would mean "2 waffles" → 140 g → four waffles. It is safe *only* because
`db.portion_for` (`:2179`) filters `WHERE id < 0`, and `declare_portion`
(`:2157`) always writes `amount = 1`. Measured: of USDA's 36,682 portion rows,
**11,155 have `amount = 1`, 3,481 have `amount ≠ 1`, and 22,046 have `amount`
NULL.** Anyone who widens `portion_for` to fall back on USDA's own portions —
an obvious and tempting improvement — introduces a silent factor-of-`amount`
error on 24% of the rows it would newly reach. Constrain it in the query, not
in a comment.

**`Scale` does not rescale `grams_sigma`.** It does not need to: sigma is
recomputed from provenance at `bot.py:3739` and `bot.py:3956` rather than
carried. Doubling a meal correctly doubles its error bar.

---

## 2. Do Python and SQL agree?

Yes, on the data that exists — and one arm of the agreement has never been
exercised.

**`yield_factor = 1.0` on all 283 confirmed components.** The yield-factor arm
of every formula is production-untested. That matters because the definitions
of "the day's mass" disagree across three places:

| expression | uses yield factor? | file |
|---|---|---|
| `log_entry.total_grams` | no — `sum(c.grams)` | `db.py:461` |
| `v_day_mass_confidence.total_grams` / `mass_sigma` | no | `sql/002_views.sql:77` |
| `day_nutrient_coverage` denominator | yes — `sum(c.grams * c.yield_factor)` | `sql/026:mass` |
| `nutrition.coverage()` | yes | `nutrition.py:97` |
| `day_energy_sigma` | yes | `db.py:806` |

Today all five agree because the factor is 1. The first time a cooked-mince
component carries 1.33, mass confidence and coverage will be computed over
different denominators for the same day and nothing will say so. This is a
definition that has to be settled once — `grams` is what you ate, `grams ×
yield_factor` is the mass of the USDA row as described, and only one of them
is "the day's mass". My reading: `grams`. Coverage and `day_energy_sigma`
should use `grams` in their denominators and `grams × yield_factor` only inside
the per-100 g scaling.

**Canonical-id folding agrees, and it reaches history.** Snapshots written
before `sql/025` stored sugar under 1063; the write path now folds to 2000
(`db._profiles_con:527`) and the read path folds again in `v_day_nutrient`.
Idempotent, verified: folding the snapshot before comparison drove the
mismatch count from 72 pairs across 39 entries to zero.

**`day_energy_sigma` disagrees with `normalise_energy` in principle and not yet
in practice.** It joins `food_nutrient ... nutrient_id = 1008` (`db.py:816`)
with no Atwater fallback, so a component whose row reports energy only under
2047/2048 is dropped from the quadrature entirely rather than contributing.
Measured: **10 of 283 components (3.5%)** sit on such rows — pineapple,
raspberries, blueberries, roma tomato, Anjou pear. Their sigma contribution is
currently below the 0.5 kcal threshold I tested at, so no day differs today. It
is a latent understatement of the day's error bar that grows with the share of
Foundation rows, and Foundation is ranked first by precedence.

---

## 3. Defects, ranked by materiality

### D1 — `llm/parse.py::per_100g` never reads the unit it is given. (critical)

`FOOD_LABEL_TOOL` requires a `unit` on every nutrient line
(`llm/schemas.py:373`, `required` at `:379`). `per_100g`
(`llm/parse.py:721`) reads `nutrient_id` and `amount` and **discards `unit`**:

```python
out[int(n["nutrient_id"])] = float(n["amount"]) * scale
```

The result goes straight into `food_nutrient` via `db.create_user_food`
(`:2186`), whose column means whatever `nutrient.unit` says. Run against the
real function:

| printed | stored | column unit | error |
|---|---|---|---|
| `Sodium 0.08 g` | `1093 = 0.08` | MG | **1,000× low** |
| `Calcium 0.12 g` | `1087 = 0.12` | MG | **1,000× low** |
| `Vitamin D 1000 IU` | `1114 = 1000` | UG | **40× high** (1000 IU = 25 µg) |

No warning is emitted for any of them. Two modules away,
`core/supplements.convert` (`core/supplements.py:45`) does exactly this
conversion correctly, refuses vitamin A and E in IU, and is not called from
this path.

**It has already happened.** `food` row **−464 "Vemondo Coconut Milk"**, saved
from a transcribed panel, carries `1093 = 0.08 MG`. Coconut drink is 10–40 mg
sodium per 100 ml. The signature is a gram figure landing in a milligram
column.

The confirm card makes it worse, not better. `food_label_card`
(`render.py:2488`) prints the verbatim `as_printed` string beside the stored
figure *with no unit on the figure*:

```
Vitamin D 1000 IU                    1000.0
```

The line the user is asked to check against the packet reads as confirmation.
The as-printed column, which exists to make transcription checkable, is here
the mechanism by which a unit error is certified.

### D2 — `energy_cross_check` cannot detect a mass error, and its 18 findings are all false positives. (critical)

The check is exactly scale-invariant in mass. From §1.1, for an entry:

```
Δ = kcal_atwater − kcal_db
  = Σᵢ (gᵢ·yᵢ/100) · ( atwater(rowᵢ) − energy(rowᵢ) )
```

Measured residual of that identity across the 18 firing entries:
`max |Σ contributions − entry Δ| = 3.6 × 10⁻¹⁵`. Every term is the *row's own*
inconsistency scaled by mass. A self-consistent row contributes nothing at any
mass. Therefore:

- a wrong mass is undetectable, at any tolerance;
- a wrong row is detectable only if the wrong row is itself internally
  inconsistent;
- the entry-level check is strictly weaker than the same check run once per
  food row, and adds nothing over it.

Simulated against real entry 10027 (817 kcal, 7 components):

| perturbation | stored kcal | Atwater | delta | `ok`? |
|---|---:|---:|---:|:--:|
| baseline | 817 | 806 | −1.3% | ✅ |
| largest component duplicated (case 5) | 1,033 | 1,016 | −1.6% | ✅ |
| whole meal doubled | 1,634 | 1,612 | −1.3% | ✅ |
| 10× mass on one component | 2,761 | 2,701 | −2.2% | ✅ |
| **every mass read as ounces (×28.35)** | **23,158** | 22,847 | **−1.3%** | ✅ |

Case 7, the blondie divided by 850 g instead of 1,587 g: delta is `+2.9%` at
*both* divisors — identical, because dividing a panel by a wrong yield cancels
out of a ratio. Case 1, the egg-white entry (18177): passes at −1.9% while
storing 597 mg of cholesterol in one meal.

Now the false positives. All 18 `atwater_mismatch` findings, classified:

| cause | count |
|---|---:|
| a USDA row that is internally inconsistent | 15 |
| several small row inconsistencies summing | 3 |
| **a wrong row** | **0** |
| **a wrong mass** | **0** |

Blame concentrates on three rows: **`Lemon juice, raw` (167747) — 15 of 18**
(db 22 kcal/100 g, Atwater 30.6), `Mixed salad greens, raw` (2709792) — 2, and
`Pickles, dill` (2710078) — 1.

The absolute energy error of all 118 entries:

```
max |Δ| across all 118 confirmed entries = 5.3 kcal
the 18 findings, sorted: 0.8 2.5 2.5 2.6 4.1 4.1 4.1 4.1 4.4
                         4.7 4.7 4.7 4.7 4.7 4.7 4.7 4.7 5.3
```

Tuning sweep:

| relative | absolute floor | fires | rate |
|---:|---:|---:|---:|
| 12% | 0 kcal | 18 | 15.3% |
| 12% | **10 kcal** | **0** | **0.0%** |
| 20% | 0 kcal | 11 | 9.3% |
| 20% | 10 kcal | 0 | 0.0% |

A relative-only test on a 12 kcal entry containing 29 g of lemon juice is a
percentage of nothing. At day level the check is silent and correct: every one
of the 10 days lands within ±1.9%.

### D3 — the case-7 invariant guards one of three writes into `food`. (high)

`bot.py:2357` refuses a per-100 g panel whose protein + carbohydrate + fat
exceeds 100 g, and `bot.py:2386` refuses one that fails Atwater. Both live
inside `_consume_food_recipe` only. The two other paths that call
`db.create_user_food` — `cb_food_panel_save` (`bot.py:2737`, transcribed
panel) and `cb_off_save` (`bot.py:2631`, OpenFoodFacts) — apply neither.

Of the 14 `user_product` rows now in the database, the recipe gate would have
refused 3 had it been applied to all of them:

| fdc_id | food | stored kcal/100 g | Atwater | delta | verdict |
|---:|---|---:|---:|---:|---|
| −249 | Blondie | 336.6 | 524.5 | **+56%** | known-bad, logged once |
| −565 | Lubella Cosmic Cereal | 376.0 | 319.9 | −15% | transcribed, unchecked |
| −465 | Muszynisnka Sparkling Water | *(none)* | 0.0 | n/a | no energy row at all |

The other 11 land within ±9%.

### D4 — `_profiles_con` double-counts sugar for rows carrying both 1063 and 2000. (high)

`canonical_id` means "the same measurement, add them up", and `_profiles_con`
(`db.py:534`) implements it as `sum(fn.amount)` grouped by canonical id. That
is right when the two ids are complementary and wrong when a row carries both.
**7 rows in the corpus carry both**, and five of them are apples:

| fdc_id | row | 1063 | 2000 | folded total |
|---:|---|---:|---:|---:|
| 1750339 | Apples, red delicious, with skin, raw | 12.221 | 12.220 | **24.44** |
| 1750340 | Apples, fuji | 13.332 | 13.330 | **26.66** |
| 1750341 | Apples, gala | 11.835 | 11.830 | **23.67** |
| 1750342 | Apples, granny smith | 10.651 | 10.650 | **21.30** |
| 1750343 | Apples, honeycrisp | 12.368 | 12.370 | **24.74** |
| −289 | Blondie | 40.744 | 0.158 | 40.90 ✅ |
| −249 | Blondie | 40.744 | 0.144 | 40.89 ✅ |

The two Blondies are *correctly* summed — they are pre-canonical user products
whose ingredients genuinely split across both ids. The five Foundation apples
would double. None has been logged yet; an apple is not an exotic food.

`tests/test_integration.py::test_no_targeted_nutrient_is_silently_split`
detects splits by complementary coverage and by construction cannot see this:
7 rows out of 11,611 is still overwhelmingly complementary. The missing test is
the *opposite* one — no row may carry two ids that fold to the same canonical
id — and it costs one query.

### D5 — the supplement half of `day_progress.amount` is not snapshotted. (high)

`v_day_supplement_nutrient` (`sql/025`) reads live `supplement_nutrient`, and
`db.upsert_supplement` (`db.py:1145`) replaces a supplement's whole panel on
re-read: *"The panel is replaced wholesale rather than merged."* Re-photograph
a label and every past day's supplement contribution silently changes.

`day_progress.amount = COALESCE(d.amount,0) + COALESCE(s.amount,0)`. Half of
that expression is an immutable snapshot and half is a live view. Invariant 2
is stated as a property of `log_nutrient`; it is in fact a property of one of
two summands. 64 `supplement_log` rows over 11 days are currently exposed.

### D6 — `ATWATER[ALCOHOL]` is defined, documented as load-bearing, and never used. (medium)

`config.py:133` defines `ALCOHOL: 7.0`. `energy_cross_check`
(`nutrition.py:138`) filters the generator to `(PROTEIN, CARB, FAT)`, so the
alcohol term is dropped; `jobs/audit.py:191` omits it too. The comment at
`config.py:153` says alcohol *"already counts toward energy via ATWATER"* — it
does not. 166 food rows carry ethanol; 2 of the 96 rows in use do. Materially
nil today, structurally a hole: a 500 ml beer would present as a 91 kcal
Atwater shortfall and be blamed on the wrong thing.

### D7 — `user_food_made_card` zero-fills a panel. (medium)

`render.py:2226-2231` prints `per_100g.get(FIBER, 0)`, `get(SODIUM, 0)` and so
on. A recipe whose constituent rows report no sodium is shown as `Sodium 0 mg`
at the exact moment the figure is being accepted. `off_product_card`
(`render.py:2219`) gets this right — `if nid in panel` — and `food_label_card`
gets it right by iterating the transcribed lines. One card out of three.

Confirmed clean elsewhere: `day_progress`'s `COALESCE(...,0)` produces exactly
**7 zero rows out of 220** (nutrient, day) target rows, all of them
`Alcohol, ethyl`, which is in `render.ABSENT_MEANS_ZERO` and therefore shown
without a coverage annotation. Invariant 6 holds at the day card.

### D8 — coverage is mass-weighted, and water is heavy. (medium)

`day_nutrient_coverage` weights by component mass. Energy coverage on the two
days containing a 1,000 g bottle of mineral water:

```
2026-08-21   76.0 %
2026-08-23   68.6 %
all other days  ≥ 99.8 %
```

The day card therefore annotates a correct calorie total with
`(from 69% of food)`, which reads as "this is a lower bound over two thirds of
what you ate". The missing third is water, which has no calories to miss.
`ABSENT_MEANS_ZERO` already encodes the idea that absence sometimes means zero;
it is keyed on nutrient, and this case needs it keyed on (food, nutrient) — a
row with no energy line that also has no macronutrients is water, not a gap.

Also: coverage reads live `food_nutrient` and live `log_component`, so a
corrected panel rewrites a historical day's coverage figure while leaving its
totals alone. The two then describe different worlds.

### D9 — salt is not sodium, and only one of two panel paths knows. (medium)

`off._panel` (`off.py:96`) converts `salt_100g / 2.5 × 1000` when sodium is
absent. The transcription path has no such rule, and `_nutrient_menu`
(`parse.py:669`) offers the model `1093 = Sodium (mg)` with nothing said about
salt. Row **−296 "Nestle Corn Flakes"** carries `1093 = 1330 MG`, which is
3.3 g of salt per 100 g of corn flakes; the printed salt figure for that
product is ~1.33 g, and `1.33 → 1330` is the arithmetic signature of a salt
line transcribed as sodium and converted g → mg. If so the row overstates
sodium by 2.5×. Consistent with, not proven; the packet settles it.

### D10 — `ResolvedComponent.count` is dead. (low)

Documented as "display only" (`nutrition.py:37`). It is set in
`parse.py:381`, written nowhere by `_write_components` (`db.py:432`) and read
by no renderer. Harmless, but the docstring's "nothing downstream multiplies"
is currently true by absence rather than by design.

---

## 4. Proposed invariant suite, with measured hit rates

Every rate below is measured against the real data. An invariant is stated as
what it forbids, with the evidence it can and cannot see.

### Tier A — arithmetic refusals. These can block a write.

**A1. No stored per-100 g row may contain more than 100 g of matter per 100 g.**
`protein + carbohydrate + fat + alcohol > 100`.

- Hit rate over the **entire corpus**: 3 of 13,649 rows (**0.02%**) — 2 SR
  Legacy, 1 FNDDS, 0 user products. Over the 96 rows in use: 0.
- Would have refused the case-7 blondie: at the correct 1,587 g divisor the
  sum is 97.0 g; at the stated 850 g it is **181.3 g**. Fires.
- False positives: the three USDA rows are genuine data errors, so the correct
  action there is to refuse the *row*, not the meal. Zero cost to run — it is
  three lookups in a profile already in memory.
- Currently implemented only at `bot.py:2357`. Extend to `cb_food_panel_save`,
  `cb_off_save`, and to profile load.

**A2. A transcribed line whose unit cannot be converted to the nutrient's own
unit is rejected, not stored.** Route `per_100g` through
`core/supplements.convert`.

- Hit rate: cannot be measured retrospectively — the unit was discarded at
  parse time and is not in the database. Forward-looking. On synthetic
  reconstruction of three ordinary label lines, **3 of 3** were stored wrong
  (§D1).
- False positives: by construction none — a refusal is a gap, and `Rejected`
  already carries a reason string to show on the card.

**A3. No food row may carry two nutrient ids that fold to the same
`canonical_id`.** Checked at load and at `create_user_food`.

- Hit rate: **7 of 11,611** distinct rows carrying either sugar id (**0.06%**), of which
  5 are Foundation apples that would double and 2 are legitimately-summed
  pre-canonical user products.
- False positives: the two Blondies. That is not a flaw in the invariant, it is
  the invariant finding a second bug — those rows should have been folded at
  write time and were written before `sql/025` existed. Refusing them at
  creation is right; the existing two need repair, not exemption.

**A4. `count × gram_weight` may only use a portion row whose `amount = 1`.**

- Hit rate: 0 today (the `id < 0` filter enforces it accidentally).
- Guards against a change that is 24% wrong on the 3,481 USDA rows with
  `amount ≠ 1`. Cost: one `AND amount = 1` in `db.portion_for`.

### Tier B — row-level plausibility. Warn, and name the row.

**B1. Food-row Atwater: `|atwater − energy| > 20%` **and** `> 15 kcal per
100 g`.**

- Hit rate over the entire corpus: **65 of 13,649 (0.48%)** — 52 SR Legacy,
  12 FNDDS, 1 user product, 0 Foundation.
- Over the 96 rows in use, at a looser 20%-only threshold: 3 — `Vinegar`
  (−82%), `Lime juice, raw` (+41%), `Lemon juice, raw` (+39%).
- False-positive assessment: these are true findings about the *row*. They are
  false findings about the *meal*, which is precisely what D2 documents. Report
  as "USDA's own figures for this row disagree by X%", once per row, cached
  forever, and never as "your meal does not add up".
- Replaces the entry-level check entirely. §2.1's identity proves the entry
  check is a mass-weighted restatement of this one.

**B2. Entry Atwater with an absolute floor: `> 12%` **and** `> 25 kcal`.**

- Hit rate: **0 of 118 (0.0%)**, against 18 today.
- False-positive assessment: zero, by measurement. The largest true Atwater
  error in the whole history is 5.3 kcal.
- It should be kept despite firing on nothing. It is the only thing standing
  between the user and a component whose row is *very* inconsistent at *large*
  mass, which is a real if unobserved failure. An invariant that fires on
  nothing today and would fire loudly on a 200 kcal discrepancy is doing its
  job; one that fires 18 times on ≤5.3 kcal is not.

**B3. A component contributing mass and no energy at all** (no 1008, no 2047,
no 2048).

- Hit rate: **3 of 283 components (1.1%)** — 5 g `Butter, stick, unsalted`
  (case 2) and 1,000 g `Muszynisnka Sparkling Water` twice.
- Over the corpus: **58 of 411 Foundation rows (14.1%)** have no energy under
  any id, and 276 of 411 (67.2%) lack 1008 — matching CLAUDE.md's figure
  exactly, with `normalise_energy` rescuing 218 of the 276.
- Already implemented in `jobs/audit.py:159`. Its weakness is timing: it runs
  daily on confirmed entries, after the fact. It should also run at the
  confirm gate, where the answer is still "pick a different row".
- False positives: sparkling water. Distinguishable — a row with no energy and
  no macronutrients is water; a row with no energy and 81.5 g of fat is a
  mistake. That two-line refinement takes B3's precision from 1/3 to 1/1.

**B4. The same `fdc_id` twice within one entry.**

- Hit rate: **1 of 118 entries (0.8%)** — entry 18177, `whole egg, fried` 50 g
  and `egg whites, fried` 99 g **both on fdc 173423** (`Egg, whole, cooked,
  fried`). That is FAILURES cases 1 and 8 sitting in the confirmed record, and
  the entry stores **597 mg of cholesterol**.
- False positives: a meal genuinely containing the same food twice is a meal
  with one component of the summed mass, so this is close to arithmetically
  sound. It is the cheapest check in this document and the only one that
  catches a live failure. Ship it.

### Tier C — measured, and not recommended as gates

**C1. Component exceeding a daily ceiling on its own.** Cholesterol > 300 mg:
**6 of 283 components (2.1%)**. One of the six is the known-bad egg-white row;
the other five are ordinary egg meals. Sodium > 2,300 mg, saturated fat > 22 g,
sugar > 57 g: **0 fires each**. Precision ≈ 17% on the one nutrient that fires
at all. This is an identity failure wearing an arithmetic costume — the tell is
that the label says "egg whites" and the row says "whole" — and belongs to
Agent 1's `qualifier_mismatch`, which already catches it. Do not gate on it.

**C2. Micronutrient above a food-plausible per-100 g ceiling.** Tested vitamin
D > 2,000 µg, B12 > 500 µg, vitamin A > 50,000 µg RAE, vitamin C > 3,000 mg,
iron/zinc > 200 mg, calcium > 5,000 mg, magnesium > 2,000 mg, cholesterol
> 3,000 mg. **0 of 96 rows.** Fires on nothing — as a check on USDA it is
redundant, because USDA rows are assays. It becomes worth having the moment
A2 is *not* implemented, because it is the only thing that would have caught
`Vitamin D 1000 IU → 1000 µg`. Recommend it as a *post-transcription* check on
`user_product` rows only, where the numbers did not come from a lab.

**C3. Energy density > 9 kcal/g.** 0 of 283 components, 0 of 118 entries. Pure
fat is 8.84 kcal/g, so the ceiling is real arithmetic, but nothing in a food
database can exceed it and no mass error changes a density. Worthless as
written; the useful form is an *entry* mass or energy ceiling, which is a
plausibility heuristic and not arithmetic.

**C4. Sodium > 8,000 mg per 100 g.** 0 of 96. Would not have caught D1's
1,000× *understatement*, which is the direction the transcription bug actually
goes. A floor is what is wanted, not a ceiling, and a floor cannot be stated
without knowing the food. Drop.

### What the suite catches, together

| historical case | caught by |
|---|---|
| 1 — egg whites → whole egg | **B4** (duplicate fdc_id), plus Agent 1's qualifier check |
| 2 — butter with no energy row | **B3** |
| 3 — user food lost to a generic row | *nothing here* — Agent 1 |
| 4 — sugar split across two ids | fixed; **A3** prevents the inverse |
| 5 — one meal photographed twice | **B4** if the duplicate resolves to one row; otherwise *nothing here* |
| 6 — pickle juice → relish | *nothing here* — Agent 1 |
| 7 — impossible declared yield | **A1** |
| 8 — turkey appended not replaced | **B4** |

Three of eight, and B4 alone carries two of the three. Arithmetic is not where
most of these live, and this suite should not pretend otherwise.

---

## 5. Unit-handling rules

**The units that exist.** `nutrient.unit` holds 12 distinct values across 477
rows: `G` (205), `MG` (186), `UG` (70), `IU` (3), `KCAL` (3), `UMOL_TE` (3),
`MCG_RE` (2), `SP_GR`, `MG_GAE`, `MG_ATE`, `PH` (1 each), and **`kJ`** — the
only lowercase value in the table (nutrient 1062, Energy).

Rules, in order of how much they cost to break:

1. **Every path that writes an amount into a nutrient column converts through
   one function.** That function is `core/supplements.convert`
   (`core/supplements.py:45`). It is already correct: it lowercases both sides
   (so `MG`/`mg`/`kJ` all work), treats `mcg` and `ug` as the same unit, and
   returns `(None, reason)` rather than guessing. `llm/parse.py::per_100g` must
   call it. `off._panel` already does the equivalent inline with an explicit
   multiplier table; that is acceptable because the source unit is fixed by the
   API, and it should say so in the comment.

2. **IU converts for vitamin D and for nothing else.** `_IU_TO_UNIT`
   (`supplements.py:26`) holds `1114 → ug × 0.025`. Vitamin A depends on
   retinol vs β-carotene (a 12× spread) and vitamin E on natural vs synthetic
   tocopherol, so `1104`, `1106`, `1109` and `1124` in IU are refused. Correct,
   documented, and matches CLAUDE.md. **Do not extend this table.**

3. **A refusal is recorded, shown, and not filled in.** `Rejected` carries a
   reason; `food_label_card` must render rejected lines the way it renders
   `unreadable` ones. An unrecorded nutrient is a gap; a wrongly-converted one
   is a lie, and the gap is already visible through coverage.

4. **A figure shown for checking carries its unit.** `food_label_card`
   (`render.py:2488`) prints a bare number beside the printed text. Use
   `render.fmt_amount(value, nutrient.unit)` — which already handles KCAL, G,
   MG, UG and falls through to `unit.lower()` for the rest — so that
   `Vitamin D 1000 IU → 25.0 µg` is legible as a conversion the user can reject.

5. **Salt is not sodium.** `SUPPLEMENT_SYSTEM` rule 6 already forces the
   elemental figure over the compound weight for minerals. `FOOD_LABEL_SYSTEM`
   needs the same sentence for salt: report the printed salt figure as salt, or
   divide by 2.5 in Python as `off._panel` does. Not in the model.

6. **Non-mass units are display-only.** `PH`, `SP_GR`, `UMOL_TE`, `MG_GAE` and
   `MCG_RE` scale linearly with mass in `scale_profile` and are meaningless
   when summed across a plate (a day does not have a pH). None is in
   `CORE_NUTRIENTS` or in any target, so nothing shows them today. If
   `/nutrient <name>` can reach them, they should be excluded from day
   aggregation explicitly rather than by nobody having asked.

---

## 6. Challenges to other layers

**To Agent 1 (bases and ids).**

- `canonical_id` is not a total function. It says "add these up", and it is
  wrong on any row carrying both ids. Seven such rows exist and five of them
  are apples (§D4). Whatever else Agent 1 does with the nutrient namespace,
  the folding rule needs a companion constraint at load time, and the existing
  complementary-coverage test cannot supply it.
- The 2047/2048 fallback is implemented three times — `normalise_energy`
  (`nutrition.py:54`), the hard-coded branch in `day_nutrient_coverage`
  (`sql/026`), and *not at all* in `day_energy_sigma` (`db.py:806`), which is
  the divergence in §2. Three implementations of one rule, one of them missing.
- `_nutrient_menu` (`parse.py:669`) is the id whitelist for both label tools,
  and it disagrees with `CORE_NUTRIENTS`: the menu offers `2000` for sugars,
  never `1063`, which is correct — but nothing enforces that agreement. Live
  example of what happens when it slips: supplement 677 "Vitamin D3 + K2"
  carries `1183 = 100 µg`, and 1183 is specifically menaquinone-4. Almost every
  D3+K2 product is MK-7. The menu warns about exactly this in its own comment
  and the row went in anyway.

**To Agent 3 (grams).**

- **Arithmetic cannot check your work, and you should not expect it to.** §D2
  proves the energy cross-check is exactly scale-invariant in mass: a ×28.35
  error on every component of a real meal produces 23,158 kcal at a −1.3%
  delta. There is no tolerance at which the Atwater check catches a mass error,
  because there is no term in it that depends on mass except linearly through
  both sides. Every guard on mass must come from a prior over portions, from
  `portion_history`, or from the user. If any part of your spec assumes the
  cross-check is a backstop, it is not.
- `yield_factor` is 1.0 on all 283 confirmed components. Three definitions of
  "the day's mass" coexist and agree only because of that (§2). If your spec
  starts populating yield factors, `v_day_mass_confidence` and
  `day_nutrient_coverage` begin dividing by different denominators the same
  week. Pick one meaning and state it.
- `db.portion_for` is safe only because of `WHERE id < 0`. If your spec reaches
  for USDA's 36,682 portion rows, `count × gram_weight` is wrong by a factor of
  `amount` on 3,481 of them and undefined on 22,046 (§1.3).
- 155 of 283 components are `stated` and 120 are `estimate`; `package` accounts
  for 6 and `prior` for 2. The declared-portion machinery has fired twice in
  the whole history, on two Blondie rows.

**To whoever owns the audit job.**

`jobs/audit.py:191` reconstructs the Atwater sum in SQL with INNER JOINs to
`log_nutrient` for protein, carbohydrate and fat. An entry missing any one of
those rows is not checked at all — it is dropped from the result set rather
than flagged. That is the invariant-6 failure mode inverted: absence silently
disables the check that absence should trigger.

**To whoever owns notification and reporting.**

`day_progress.amount` is half snapshot and half live view (§D5). Anything that
draws a conclusion across days from `amount` rather than from `amount_food` is
reading a figure that changes when a supplement label is re-photographed.

---

## 7. What I would defer

- **A NOVA-style plausibility model for micronutrients.** C2 fires on nothing
  and would only earn its place once A2 is *not* done. Do A2.
- **Recomputing or repairing the 12 existing `user_product` panels.** Two are
  provably wrong (−464 sodium, −249 blondie energy) and one is probably wrong
  (−296 sodium). They are referenced by `log_component` and by `log_nutrient`
  snapshots; `food.retired_at` is the mechanism and the retirement design is
  already written down. This is a data-repair task with a human in the loop and
  a packet in a cupboard, not a code change, and it should not be bundled with
  the code change.
- **Unifying the three mass definitions.** Cost-free today because
  `yield_factor` is 1 everywhere. Do it when Agent 3's spec lands and the
  factor starts moving, so the change is made against a case that exercises it.
- **`llm/client.py:price()` returning `None`.** Already decided in CLAUDE.md,
  unrelated to nutrient arithmetic, and not mine.
- **Alcohol in the Atwater sum (D6).** Two food rows in use carry ethanol and
  the day-level effect is nil. Fix the comment now, because it asserts
  something false; fix the arithmetic when a drink is logged.
- **Coverage's mass weighting (D8).** The 1,000 g water bottle is one food and
  the fix is a two-line predicate, but "which absences mean zero" is a
  presentation question that overlaps whoever owns the day card. Flag the
  numbers, let them decide the rule.

---

## Appendix — reproducing the measurements

All queries are read-only.

```sql
-- D4: rows folding two ids onto one canonical id
SELECT fdc_id FROM food_nutrient WHERE nutrient_id IN (1063, 2000)
 GROUP BY fdc_id HAVING count(DISTINCT nutrient_id) = 2;                    -- 7

-- B1/A1: row-level plausibility over the whole corpus
WITH p AS (SELECT f.fdc_id, f.data_type,
    coalesce(max(amount) FILTER (WHERE nutrient_id=1008),
             max(amount) FILTER (WHERE nutrient_id=2048),
             max(amount) FILTER (WHERE nutrient_id=2047))            AS k,
    coalesce(max(amount) FILTER (WHERE nutrient_id=1003),0)*4
  + coalesce(max(amount) FILTER (WHERE nutrient_id=1005),0)*4
  + coalesce(max(amount) FILTER (WHERE nutrient_id=1004),0)*9
  - coalesce(max(amount) FILTER (WHERE nutrient_id=1079),0)*2
  + coalesce(max(amount) FILTER (WHERE nutrient_id=1018),0)*7        AS atw,
    coalesce(max(amount) FILTER (WHERE nutrient_id=1003),0)
  + coalesce(max(amount) FILTER (WHERE nutrient_id=1005),0)
  + coalesce(max(amount) FILTER (WHERE nutrient_id=1004),0)
  + coalesce(max(amount) FILTER (WHERE nutrient_id=1018),0)          AS ms
  FROM food f JOIN food_nutrient fn USING (fdc_id) GROUP BY 1,2)
SELECT data_type, count(*),
       count(*) FILTER (WHERE k IS NULL),                             -- B3: 58 Foundation
       count(*) FILTER (WHERE k>0 AND abs(atw-k)>0.20*k AND abs(atw-k)>15),  -- B1: 65
       count(*) FILTER (WHERE ms>100)                                 -- A1: 3
  FROM p GROUP BY 1;

-- B4: the same food row twice in one entry
SELECT entry_id, fdc_id, count(*) FROM log_component c
  JOIN log_entry e ON e.id = c.entry_id AND e.status='confirmed'
 GROUP BY 1,2 HAVING count(*) > 1;                                    -- entry 18177
```

The Python/SQL agreement proof, the Atwater decomposition and the perturbation
simulations were run from scratch scripts against `nutrai.core.nutrition` and
`v_nutrient_canonical`; each is ~40 lines and reconstructible from §1.1 and
§D2.
