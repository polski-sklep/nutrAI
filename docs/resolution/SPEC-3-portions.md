# SPEC-3 — Portion and gram weight

Agent 3. Investigation and specification only; nothing under `nutrai/`,
`tests/`, `sql/` or `scripts/` was changed. Cases 5, 7 and 8 of
`docs/resolution/FAILURES.md`.

Every count below is measured against the live database on 25 Aug 2026:
283 confirmed components, 118 entries, 96 distinct foods, user 2.

**The one-line finding.** A gram figure can be produced by thirteen different
pieces of code, only one of which consults the 36,684-row table USDA ships for
exactly this purpose, and the mass provenance that decides everything
downstream is asserted rather than derived — sometimes by a model, sometimes by
a `or 100` fallback. 57% of every calorie ever logged (11,206 of 19,656 kcal)
rests on the weakest of those routes, and 105 of those 120 components name a
food that `food_portion` already knows the household weight of.

---

## 1. Every current path to grams

### 1.1 The thirteen routes

Routes A–J write `log_component.grams`. Routes K–M set the **basis** a
per-100 g profile is expressed in, which is the other half of the same
arithmetic and is where case 7 happened.

| | Route | Code | Provenance written | Sigma |
|---|---|---|---|---|
| A | Model asserts a measured mass | `parse._mass_for` short-circuit → `estimate.choose_mass` first branch | the model's own `grams_source` (`scale`/`stated`/`package`) | 0.5% / 5% / 3% |
| B | Declared portion × count | `db.portion_for` (id<0) × (`item["count"]` ∥ `parse.count_from_text`) | forced `package` | 3% |
| C | Portion prior | `db.portion_history` → `estimate.portion_prior` | `prior` | observed spread, floor 6% |
| D | Model visual/textual estimate | `choose_mass` final return | forced `estimate` | `(high−low)/4` or 35% |
| E | DSL set-one-component | `dsl.SetComponent` via `dsl.apply` | forced `stated` | recomputed by `sigma_for` |
| F | DSL scale / total | `dsl.Scale`, `dsl.TotalGrams` | **untouched — inherited** | recomputed from the new grams |
| G | DSL add with a mass | `dsl.AddComponent(label, grams)` → alias or `llm.resolve_items` | hardcoded `stated` | 5% |
| H | DSL add without a mass | same, `alias["default_grams"] or 100` | hardcoded `stated` | 5% |
| I | Repeat a dish | `db.dish_components` → `dish_component.grams` | inherited from the dish (`sql/008`) | recomputed |
| J | Repeat one component | `bot._log_one_component` ← `db.top_components` | `stated` if from `portion_history`, else `prior` | from that source |
| K | Recipe basis | `bot._consume_food_recipe`: `Σ ingredient g ÷ yield_g × 100` | n/a (sets the per-100 g row) | n/a |
| L | Printed panel basis | `parse.per_100g`: `× 100 ÷ serving_grams` | n/a | n/a |
| M | OpenFoodFacts | `off._panel`, `*_100g` fields only | n/a (no conversion) | n/a |

### 1.2 What produced the 283 stored components

`log_component` records *how the mass was arrived at* but not *which code path
recorded it*, so attribution is the crosstab plus the cases that are
individually identifiable.

```
 entry source | grams_source | n   | grams
--------------+--------------+-----+-------
 text         | estimate     |  69 |  5126
 text         | stated       |  63 |  7159
 text         | package      |   6 |   180
 text         | prior        |   1 |   140
 repeat       | stated       |  91 |  9753
 repeat       | estimate     |  46 |  2796
 repeat       | prior        |   1 |    29
 photo        | estimate     |   5 |   495
 photo        | stated       |   1 |   600
```

Identified precisely:

- **Route B (declared portion × count): 4 components.** All four are Blondie
  (`fdc_id` −289/−249), at 29.04 g, 29.04 g, 44 g and 17.6 g — exactly
  0.33 × 88, 0.33 × 88, 0.5 × 88 and 0.2 × 88 against the one declared portion
  in the database. **1.4% of all components.**
- **Route A with `package`: 2 components** (Kinder Pingui, 30 g each — a net
  weight the model read, not a portion lookup).
- **Route C (prior overriding an estimate): 1 component** (140 g Vemondo
  coconut milk, replacing the model's 150 g estimate).
- **Route J: 1 component** (29 g lemon).
- **Route E: at least 6 components**, all in entry 18 177's successor — see §2.1.
- Everything else is A/D/E/G/I, indistinguishable in the stored row.

Two structural facts fall out of the same query:

- `yield_factor = 1.0` on **all 283 components**. `log_component.state` is
  `'as_logged'` on all 283. The mechanism ARCHITECTURE.md §"`yield_factor` is
  where the real error lives" describes has never fired once in production.
- Only **two** components in the entire history were ever logged as `prior`,
  and only **six** foods currently have enough measured history for
  `portion_prior` to return anything at all (Blondie n=5, Vemondo coconut milk
  n=4, Milk whole n=4, Coconut milk n=4, Nestle Corn Flakes n=3, Water n=3).

### 1.3 Materiality: where the calories actually are

```
 grams_source |  n  | grams | kcal   | share of logged energy
--------------+-----+-------+--------+------------------------
 estimate     | 120 |  8417 | 11206  | 57.0%
 stated       | 155 | 17511 |  7232  | 36.8%
 package      |   6 |   180 |   834  |  4.2%
 prior        |   2 |   169 |    32  |  0.2%
```

The `stated` mass is mostly water, milk and coffee. **The majority of the
energy record comes from the route with the widest error bar and the fewest
checks.**

### 1.4 `food_portion`: what is in it, and can the parser reach it

`food_portion` holds **36,684 rows across 13,046 of 13,650 foods** and is read
by exactly one query — `db.portion_for`, which filters `WHERE id < 0`. USDA's
own rows all have positive ids. **No USDA portion has ever been read by this
system.**

Content, by whether the household measure is legible:

| | rows | foods | `unit` | text carrying the measure |
|---|---:|---:|---|---|
| SR Legacy | 14,449 | — | `undetermined` on all 14,449 | `modifier`, e.g. `medium (7" to 7-7/8" long)` |
| FNDDS | 22,046 | — | `undetermined` | `modifier` is a **numeric FNDDS portion code** — `90000`, `63546` |
| Foundation | 187 | — | real (`cup`, `tbsp`, …) on all 187 | `unit` + `modifier` |
| user-declared | 2 | 2 | `slice` | — |

- **14,636 rows across 7,649 foods carry usable text.** 22,046 (60%) carry
  only an opaque code.
- The code rows are a **loader defect, not a data limitation**.
  `scripts/load_usda.py:206` writes
  `units.get(r.get("measure_unit_id","")) or r.get("portion_description")`.
  For FNDDS rows `measure_unit_id` is 9999, whose name is `"undetermined"` —
  truthy — so the `or` never fires and `portion_description` (which holds
  `"1 cup"`, `"1 medium"`) is discarded on every FNDDS row. The text exists in
  the source CSV. A one-line loader fix plus a reload recovers 22,046 portions.
  FNDDS is also the **largest single dataset in the log** (126 of 283
  components), so this is the half that matters most.
- **`amount` is not always 1.** 3,481 of the 14,636 usable rows have
  `amount ≠ 1`, and `gram_weight` is the weight of `amount` units, not of one.
  `Pie, Dutch Apple` carries `amount 0.12, modifier "pie 1 pie (1/8 of 9" pie)",
  gram_weight 131`. Reading `gram_weight` as "one unit" is an 8× error. All
  22,046 FNDDS rows have `amount IS NULL`.
- **`db.portion_for` has no `user_id` and no `retired_at` filter.**
  `food_portion` has no user column, so "one declared portion per food" is
  global. Harmless with one user; a schema-level hazard the moment there are
  two. A retired food's declared portion still resolves.

Coverage against what is actually eaten — 96 distinct logged foods:

| dataset | logged foods | with any portion row | with usable text today |
|---|---:|---:|---:|
| SR Legacy | 35 | 35 | 104 rows |
| FNDDS | 43 | 43 | 0 (all 214 rows are codes) |
| Foundation | 9 | 3 | 3 rows |
| user_product | 9 | 1 | — |

**Of the 120 estimated components, 105 name a food with a USDA portion row and
69 name one whose text is legible today.** That is the unexploited source, and
it is large.

### 1.5 How volumes become grams

**There is no density constant anywhere in the codebase.** `grep -rn` for
`density`, `g/ml`, `1.03`, `0.91` returns nothing. Volume is converted in two
places and neither states an assumption:

1. **Inside the model.** `PARSE_TOOL` has one mass field, in grams. "250 ml of
   milk" arrives as `grams: 250`. Whatever density the model used is invisible,
   unrecorded and unauditable. The implicit assumption is water. In the live
   data, 17 components are milk at exactly 100 g `stated` — almost certainly
   "100 ml", which is 103 g of whole milk. A systematic 3% understatement that
   is nowhere written down.
2. **`core/dsl.py:44`.** `_UNIT = r"(?:g|gram|grams|gr|ml|kg|l)?"` — the regex
   *accepts* `ml`, `kg` and `l` and then **throws the unit away**:

   ```
   '1kg rice'      -> SetComponent(label='rice',           grams=1.0)
   '0.5l milk'     -> SetComponent(label='milk',           grams=0.5)
   '250ml milk'    -> SetComponent(label='milk',           grams=250.0)
   '2 tbsp olive oil' -> SetComponent(label='tbsp olive oil', grams=2.0)
   '1 cup rice'    -> SetComponent(label='cup rice',       grams=1.0)
   ```

   `1kg rice` logs **one gram** of rice, as `stated`, with a ±5% error bar.
   `tests/test_dsl.py::test_grams_with_unit` covers `g` only. Compare
   `bot._MAKES_MASS`, thirty lines away, which handles `kg` correctly — the two
   grammars disagree about what `kg` means.

The right conversion already exists in the database and is per-food, so it
needs no constants at all:

```
Milk, whole 3.25%    1 cup        = 244 g   (244 / 236.6 ml = 1.031 g/ml)
Milk, whole 3.25%    1 tbsp       =  15 g
Oil, olive           1 tablespoon = 13.5 g  ( 13.5 / 14.79 ml = 0.913 g/ml)
Oil, olive           1 cup        = 216 g
```

USDA measured the density of each food and shipped it. Vocabulary available in
the 14,636 legible rows: `cup` 2,980 · `oz` 4,304 · `serving` 935 · `fl oz` 843
· `tbsp` 730 · `slice` 571 · `tsp` 227 · `medium` 192.

### 1.6 `yield_factor`

**Meaning.** Multiply logged grams by it to get grams of the USDA row *as
described*. 200 g of cooked mince against a raw row is `yield_factor = 1.33`.

**Who sets it.** One writer only: `parse.py:498`,
`yf = float(pick.get("yield_factor", 1.0) or 1.0)` — the disambiguation tool's
return value, on the tier-3 path. Routes A, B, C, D via alias or auto-match all
call `_accept(...)` with the default `yf = 1.0`. So the field is settable only
by the most expensive and least-travelled resolution path.

**Is it applied twice, or never?** **Exactly once, everywhere, and in practice
never at all.** Verified two ways:

- `core/nutrition.scale_profile` multiplies by `grams × yield_factor / 100`
  once; `total_nutrients` calls it once per component; `db.confirm_entry`
  calls `total_nutrients` once and writes the result to `log_nutrient`.
  `v_day_nutrient` (both `sql/002` and the `sql/025` replacement) reads
  `log_nutrient` and only sums. No view re-applies it.
- Of the 118 confirmed entries, 113 can be recomputed directly in SQL
  (`Σ grams × yield_factor × food_nutrient.amount / 100`); that recomputation
  reproduces the stored `log_nutrient` 1008 figure for 107 of them to within
  0.5 kcal. The six that
  differ (entries 18177, 20199, 22222, 23792, 24100, 24597; worst 41 kcal) all
  contain a component with **no nutrient 1008**, where the snapshot correctly
  used `nutrition.normalise_energy`'s 2048/2047 fallback and raw SQL cannot.
  None is a double multiplication.

The SQL consumers — `db.day_energy_sigma`, `db.nutrient_attribution`,
`db.food_contributions`, `sql/004`/`026` coverage — all spell
`c.grams * c.yield_factor * fn.amount / 100.0` and agree with
`scale_profile`. They agree on `yield_factor` and disagree with Python on the
energy fallback (§5, Agent 6).

### 1.7 Double-scaling: four traces, proved

Verified numerically against the database, not read off the code.

**(a) Stated mass.** "100 g Greek yoghurt" → `PARSE_TOOL` item
`grams:100, grams_source:'stated'` → `_mass_for` short-circuits on
`MEASURED_SOURCES` → `MassEstimate(100, 5.0, 'stated')` → `log_component.grams
= 100, yield_factor = 1` → `confirm_entry` → `scale_profile` ×1 →
`log_nutrient`. Entry 20199: stored 1008 = 61.0 for the yoghurt component
against `food_nutrient` 61.0/100 g. **One multiplication.**

**(b) Estimated mass.** Same shape; the only difference is that
`choose_mass` may substitute the prior's median for the model's grams *before*
the single multiplication. `MassEstimate` replaces, never scales. **One.**

**(c) Declared portion.** Entry 23888, Kinder Pingui: `grams 30`,
`yield_factor 1`, `food_nutrient 1008 = 374/100 g`. Expected
`30 × 1 × 374 / 100 = 112.200`; stored `log_nutrient.amount = 112.200`.
**One.** The count multiplication in `_mass_for`
(`count × portion.gram_weight`) happens *inside* the grams figure and
`ResolvedComponent.count` is display-only and is not a `log_component` column,
so it cannot be applied a second time.

**(d) Repeat.** `dish_component.grams` → `dsl.Component` → `dsl.apply` (which
may scale) → `ResolvedComponent` → `_write_components` → `confirm_entry`. The
DSL scales grams in place, then the single `scale_profile` runs. **One.**

**Conclusion: there is no double-scaling in the current code or in the stored
history.** The exposure is not that a quantity is converted twice; it is that
it is often **converted zero times** — the unit is discarded (§1.5) — or
converted against a **wrong basis** (§2.2).

---

## 2. Defects, ranked by materiality

### 2.1 A count is silently read as a mass — live in the record (critical)

The DSL has no notion of a count. A bare number before a food name is
unconditionally grams (`dsl.py:340-360`). Entry for "Tuna mayo salad",
2026-08-24, confirmed:

```
 position | label       | grams | grams_source | grams_sigma
        6 | fillets,    |     1 | stated       | 0.05
        7 | yoghurt,    |     1 | stated       | 0.05
        8 | pickle,     |     1 | stated       | 0.05
        9 | jalapeños,  |     1 | stated       | 0.05
       10 | onion,      |     1 | stated       | 0.05
       11 | chilli,     |     1 | stated       | 0.05
```

Six foods entered as "1 <food>" — one onion, one pickle — stored as **one gram
each**, marked `stated`, with a ±5% error bar asserting precision on a figure
wrong by two orders of magnitude. A medium onion is ~110 g.

Three consequences compound:

1. The day's totals are short by roughly 300 g of vegetables.
2. `portion_history` reads `grams_source IN ('scale','stated','package')`, so
   each of these is now **evidence** about the portion of that food. Three more
   and `portion_prior` returns 1 g with a tight spread and starts overriding
   the model's estimate. This is invariant 7 breached through the front door:
   the filter keeps estimates out and lets misparses in.
3. `food_alias.default_grams` is set from the first resolution and never
   updated (`ON CONFLICT` does not touch it). Seven aliases now carry
   `default_grams = 1` — `onion,`, `jalapeños,`, `chilli,`, `yoghurt,`,
   `fillets,`, `garlic, minced`, `fresh parsley, chopped`. `+onion` on the fix
   path will add one gram of onion, as `stated`, for ever.

The trailing commas in the labels are the tell: the tokeniser kept the
punctuation, so `_label_match` will also never place a correction against them.

### 2.2 `per_100g()` divides by a model-transcribed number with no check (critical)

`parse.per_100g` computes `scale = 100.0 / serving_grams` where `serving_grams`
came out of a photograph via `FOOD_LABEL_TOOL`. `bot.cb_food_panel_save` stores
the result with `db.create_user_food` and **no macro-sum check and no Atwater
check** — neither of the two guards `bot._consume_food_recipe` runs 400 lines
earlier for exactly this failure.

This is case 7 on a different path, and it is worse than case 7, because a
`user_product` row sits at `precedence` 0 (above Foundation) and wins every
future resolution of that name. A `30 g` serving misread as `3 g` inflates
every nutrient tenfold, permanently, silently.

`off._panel` reads only `*_100g` fields and performs no division — it is safe,
and it is the model for what the other two should be.

### 2.3 The DSL accepts `kg`, `l` and `ml` and discards the unit (critical)

§1.5. `1kg rice` → 1 g. A 1000× error, written as `stated`, with the
`before_g/3 ≤ after_g ≤ before_g×3` plate-total warning as the only backstop —
and that fires on the plate total, so a `2kg` correction inside a 500 g meal
passes in silence.

### 2.4 `stated` is asserted by the model and never verified (high)

`PARSE_SYSTEM` rule 3 instructs the model to set `grams_source: 'stated'` when
the user gives a mass in text. Nothing checks that the user's message contained
that number. `stated` buys a 5% error bar and **admission to
`portion_history`**, so a model that rounds "a splash of milk" to
`100 g, stated` writes a permanent measurement into the prior.

`parse.count_from_text` exists precisely because the model got a count wrong
once and the fix was to read it off the message locally. The same argument
applies to the number itself and has not been made.

Aggravating: the user's original message text is **not stored anywhere**.
`log_entry.parse` holds the tool *output*; there is no column for the input. A
`stated` mass cannot be audited after the fact, by the audit job or by a human.

### 2.5 `or 100` — the "one serving is 100 g" default, written as `stated` (high)

Four sites:

```
bot.py:3717  grams = add.grams or float(alias["default_grams"] or 100)   -> 'stated'
bot.py:3723  {"grams": add.grams or 100, "grams_source": "stated", ...}
bot.py:3932  grams = add.grams or float(alias["default_grams"] or 100)   -> 'stated'
bot.py:3937  {"grams": add.grams or 100, "grams_source": "stated", ...}
```

Two failures in one line. A default is not a statement, and 100 g is not a
serving of anything in particular — 100 g of butter is 717 kcal. And because
`default_grams` is the mass of the *first ever* logging of that alias whatever
its provenance, the defaults are already poisoned in both directions:
`light brown sugar` → 400 g (6 hits), `mineral water` → 750 g, and the seven
1 g rows from §2.1.

Also: when route G/H calls `llm.resolve_items` with `grams_source: "stated"`,
`_mass_for` short-circuits on `MEASURED_SOURCES` and **never consults
`portion_for` or `portion_history`** — the one place a default could have been
replaced by a real portion is skipped by the lie about provenance.

### 2.6 36,684 USDA portions unread; 22,046 of them destroyed at load (high)

§1.4. The largest unexploited source of correct gram weights in the system, and
the only density data it will ever need. The loader line that discards
`portion_description` should be fixed before anything is built on top of the
table, or two thirds of it stays invisible.

### 2.7 `dsl.TotalGrams` and `dsl.Scale` preserve a provenance they invalidate (medium)

`apply()` deliberately carries `grams_source` through — correct for
`DropComponent`, wrong for `Scale` and `TotalGrams`. After `250` (redistribute
the plate proportionally), a component you stated at 100 g holds 83 g and still
says `stated`, and `portion_history` records 83 g as a weighing of that food.
`Scale` has a defensible reading (half of a stated amount is still stated);
`TotalGrams` does not — the new component masses are a derived apportionment
nobody observed.

### 2.8 `yield_factor` is unreachable in practice (medium)

Set only by the tier-3 disambiguation call; `1.0` on all 283 stored components;
`log_component.state` `'as_logged'` on all 283. The documented largest error
source in the system has no working input path. Agent 4 owns the semantics; the
gram layer owns the fact that the column exists, is applied exactly once, and
is never populated.

### 2.9 The model's `count` is preferred over the unit-anchored local read (low)

`_mass_for`: `count = it.get("count") or count_from_text(text, portion["unit"])`.
`count_from_text` is anchored on the food's own unit word and therefore cannot
count the wrong thing; the model's `count` is not, and the comment directly
above explains that the model got this exact field wrong on its first real use.
The precedence is backwards.

### 2.10 `grams_source` has no CHECK constraint (low)

`PARSE_TOOL`'s enum includes `reference_object`, which is not in
`MEASURED_SOURCES` and not in the documented column set. It survives only
because `choose_mass` hardcodes `"estimate"` in its final return. Nothing in
the schema would stop a future writer storing it, and `sql/002`, `sql/008` and
`core/estimate.MEASURED_SOURCES` each hold their own copy of the list.

### 2.11 `portion_for` ignores `retired_at` and has no owner (low)

§1.4. Also: OpenFoodFacts returns `serving_size` (`"30 g"`, `"1 bar (25 g)"`),
`off.summarise` captures it, `cb_off_save` discards it. A free declared portion
for exactly the foods that most need one.

---

## 3. The canonical portion-conversion specification

### 3.1 The formula every nutrient value must be explainable by

For every row of `log_nutrient`:

```
log_nutrient(entry, n)  =  Σ over components c of
                              ( grams_c × yield_factor_c / 100 ) × profile_c(n)

where   grams_c        =  quantity_c × grams_per_unit_c
        profile_c(n)   =  the per-100-g amount of n for fdc_id_c,
                          after canonical folding and energy normalisation
```

and `grams_per_unit` is resolved by exactly one of:

```
  unit is grams                    -> 1
  unit is another mass unit        -> a fixed constant
                                      kg 1000 · lb 453.592 · oz 28.3495
  unit is a household or volume
     measure                       -> food_portion.gram_weight / food_portion.amount
                                      for this fdc_id and this unit
  no unit given, count given, food
     has a declared portion        -> the declared portion's gram_weight
  no unit and no count             -> the prior, or the model's estimate
```

**Invariant M1 — one multiplication.** Between a `food_nutrient.amount` and the
`log_nutrient.amount` it contributes to, there is exactly one multiplication by
a mass and exactly one division by 100. Any code that computes a nutrient
amount must be expressible in the form above. *Testable:* recompute every
confirmed entry from `log_component` and `food_nutrient` and require agreement
with `log_nutrient` for every nutrient other than 1008 (which has the
documented Atwater fallback), and for 1008 too once §5's SQL/Python
divergence is closed.

**Invariant M2 — one conversion.** A quantity is converted from its stated
unit to grams exactly once, at the point of parse, and the result is grams for
ever after. `log_component.grams` is grams. No consumer re-interprets it.

### 3.2 Rules

Each is stated so it can be a test.

**R1 — A unit is never discarded.** The DSL quantity grammar must either
convert a recognised unit or refuse the token into `unparsed`. `1kg rice` is
1000 g or it is a parse failure; it is never 1 g.
*Test:* `parse_ops("1kg rice")` yields `SetComponent('rice', 1000.0)`;
`parse_ops("8oz steak")` yields either 226.8 g or an unparsed token, never a
silent number.

**R2 — A volume is converted per food, never by a global density.** `ml`,
`l`, `cup`, `tbsp`, `tsp`, `fl oz` resolve through `food_portion` for that
`fdc_id`. When the food has no such row, the conversion **fails to a question**
rather than to 1.0 g/ml.
*Test:* 250 ml of `Milk, whole 3.25%` is 258 g (244 g/cup × 250/236.6), not
250; 1 tbsp of `Oil, olive` is 13.5 g, not 15.

**R3 — `gram_weight` is divided by `amount`.** Grams per unit is
`gram_weight / COALESCE(amount, 1)`, and a row whose `amount` is NULL and whose
measure text is a bare numeric code is not a usable portion.
*Test:* the Dutch apple pie row (`amount 0.12`, `gram_weight 131`) yields
1,092 g per pie, not 131.

**R4 — A count is never a mass.** A bare number immediately preceding a food
name is a count when the number is small (≤ 20), the food has a portion for a
countable unit, and no mass unit was written. `1 onion` is one onion. When no
portion is available, it is an unresolved quantity that must be asked about —
never a gram figure.
*Test:* `1 onion` does not produce a 1 g component.

**R5 — Provenance is derived, never asserted.** `grams_source` is set by the
code that produced the number, from a closed enum, and is a `CHECK` constraint
on the column. `stated` requires that the numeral appears in the user's own
message; the model's claim alone is not sufficient. A default, a fallback, an
apportionment and a model estimate are all `estimate`.
*Test:* a parse whose item says `grams_source: 'stated'` for a mass absent from
the message text is stored as `estimate`.

**R6 — Nothing derived enters `portion_history`.** The filter stays
`scale`/`stated`/`package`, and R5 makes it mean what it says. In addition,
a component whose grams were produced by `TotalGrams` apportionment is
downgraded to `estimate` at the moment `apply` rewrites it.
*Test:* after `250` on a three-component dish, no component reports `stated`.

**R7 — There is no 100 g default.** `alias["default_grams"] or 100` and
`add.grams or 100` are removed. An addition with no mass resolves, in order:
declared portion × 1 → USDA portion for a natural unit → portion prior →
**ask**. Whatever it lands on is `package`, `package`, `prior` or a question —
never `stated`.
*Test:* `+butter` with no history produces a question, not 100 g.

**R8 — A declared portion outranks a USDA portion outranks a prior outranks
the model.** One ordering, in one function. Currently split between
`_mass_for` and `choose_mass`; it should be one place with one documented
precedence list.
*Test:* a food with a declared portion and a tight prior uses the declared
portion.

**R9 — The count is read from the user's words, anchored on the unit.**
`count_from_text` first; the model's `count` only as a fallback, and only when
the model named the same unit.

**R10 — A per-100 g basis produced by division is checked before it is
stored.** §4.1. Applies identically at all three sites: recipe (K), printed
panel (L), and any future divisor.

**R11 — `yield_factor` is applied exactly once, in `scale_profile`, and its
value is recorded with the reason.** No consumer may apply it a second time; no
consumer may omit it. Agent 4 specifies when it is not 1.

**R12 — The user's message is stored.** `log_entry` gains the raw input text
(or `parse` gains an `input` key). Without it R5 cannot be audited and a wrong
mass cannot be traced to whether the user or the model produced it.

### 3.3 What the resolution order becomes

One function, `resolve_mass(user, fdc_id, item, text)`:

```
1. explicit mass unit in the user's text        -> grams, 'stated'
2. explicit volume/household unit + count       -> food_portion, 'package'
       user-declared portion (id < 0) first, USDA rows second
3. bare count + a countable declared/USDA portion -> gram_weight × count, 'package'
4. model says scale / package, with digits       -> grams, that source
5. portion prior (>= 3 measured, spread <= 25%,
   model within 0.4x-2.5x)                      -> median, 'prior'
6. model's point estimate + interval             -> grams, 'estimate'
7. nothing usable                                -> ask; log nothing
```

Steps 2 and 3 are the ones that do not exist today.

---

## 4. Validation rules

### 4.1 Component-level, and the general form of case 7's check

Case 7 was caught because 105.6 + 46.8 + 8.1 exceeded 100 g inside 100 g of
food. The general statement is:

> **Any per-100 g basis is a closed mass budget of 100 g, and any per-100 g
> basis obtained by dividing by a human- or model-supplied number must be
> tested against that budget before it is stored. The check is arithmetic, not
> a heuristic, so it may refuse outright.**

Concretely, for a per-100 g profile `P`:

- **V1 — mass conservation.** `P(protein) + P(fat) + P(carbohydrate) +
  P(water) + P(ash) + P(alcohol) ≤ 100 g`, over whichever of those are
  present. The macro-only form (`protein + carb + fat ≤ 100`) is the weakest
  usable version and is what `bot.py:2357` implements today.
- **V2 — no single nutrient exceeds the whole.** Any nutrient reported in
  mass units is ≤ 100 g per 100 g.
- **V3 — containment.** `fibre ≤ carbohydrate`, `sugars ≤ carbohydrate`,
  `saturated fat ≤ total fat`, each named fatty acid ≤ total fat,
  `folic acid ≤ total folate`. (This subsumes the `fibre_implausible`
  audit finding, which currently fires 9 times.)
- **V4 — energy ceiling.** `P(1008) ≤ 900 kcal/100 g`. Pure fat is 884.
- **V5 — Atwater agreement.** `energy_cross_check(P).ok`, already implemented
  and already applied at site K.
- **V6 — the divisor is reported.** When a basis was obtained by division, the
  card names the divisor and the direction ("read from the per-serving column
  and scaled up from 30 g"). `per_100g` does this; `_consume_food_recipe`
  does this; neither refuses on V1–V4.

V1–V5 must run at **K (recipe), L (printed panel) and M (OFF)**. Today only K
runs V1 and V5, which is why §2.2 is open.

Per-component, at parse time:

- **V7 —** `grams ≤ 1500` for one component (exists).
- **V8 —** `0.3 ≤ yield_factor ≤ 3.0` (exists).
- **V9 —** a component under 5 g whose `grams_source` is `stated` and whose
  food is not a spice, salt, sugar or oil is a probable count-read-as-mass.
  This alone would have caught §2.1.
- **V10 —** a mass more than 5× or less than 1/5 of the food's own median
  USDA portion is questioned. `food_portion` gives a free plausibility band
  for 13,046 foods, at zero cost, for the first time.
- **V11 —** `grams_sigma > 0` for every component, and
  `grams_sigma / grams` consistent with the recorded `grams_source`. Six stored
  `stated` components have `grams_sigma = 0`.

### 4.2 Entry-level — case 8's lesson

Nothing validates an entry against itself. That remains true today:

- **V12 — no `fdc_id` twice in one entry.** Still violated in confirmed
  history: entry 18177 (`Fried egg with tomato and rye bread`, 2026-08-19)
  holds `fdc_id 173423` twice, as `whole egg, fried` 50 g and
  `egg whites, fried` 99 g. Case 1 and case 8 in one row. The rule is: two
  components with the same `fdc_id` are one component; merge them and say so,
  or refuse and ask.
- **V13 — no two components that are the same food under different rows.**
  V12 is too narrow. The discarded entry 20198 held `Beverages, Orange juice
  drink` 330 g **and** `Beverages, coffee, ready to drink, iced, mocha, milk
  based` 330 g — case 5's double-counted bottle — with two different
  `fdc_id`s, identical masses and near-identical labels. The check is: two
  components in one entry with equal masses and label similarity above a
  threshold, or trigram-similar `food.description`s, are queried.
- **V14 — the entry's mass is plausible for one sitting.** Σ grams ≤ 3,000 g
  and, when a photograph exists, consistent with a plate.
- **V15 — `log_entry.total_grams = Σ log_component.grams`.** Currently true
  for all 118 confirmed entries; make it a constraint or a confirm-time assertion so it
  stays true when a fix path is added.
- **V16 — the day's energy per gram is plausible.** A day totalling 19,656 kcal
  over 26,277 g averages 75 kcal/100 g; a day above ~400 kcal/100 g is either
  a very unusual day or a mass that was misread downward. This is the entry-
  level analogue of V4 and would have flagged the 1 g components as a group.

### 4.3 Where the checks run

Parse-time (`llm.parse.validate`) for V7–V11, because that is the only place a
human can still answer a question. Confirm-time assertion for V12–V15, because
that is the last point before an immutable snapshot. `jobs/audit.py` for all of
them over the last seven days, because the historical record contains
violations that no future check will revisit.

---

## 5. Challenges to other layers

**Agent 4 (preparation state).** `yield_factor` is 1.0 on all 283 stored
components and `state` is `'as_logged'` on all 283, so whatever you specify has
to include an input path that is not the tier-3 disambiguation call — today
that is the only writer, and it is the path a repeat, an alias hit and an
auto-match all skip. Two questions I am deliberately not answering: (a) does
`state` describe the mass or the food, given that `log_component.state` and
`ParsedMeal.item['state']` are different columns with the same name and only
one is stored; (b) when a raw weight is applied to a cooked row, is the
correction a `yield_factor` or a different `fdc_id`? The gram layer's
commitment is R11: `yield_factor` multiplies grams exactly once, in
`scale_profile`, and no consumer may apply or omit it independently. If your
answer needs a second factor, say so — do not overload this one.

**Agent 6 (arithmetic).** Three items.

1. **Python and SQL disagree about energy.** `nutrition.normalise_energy` fills
   1008 from 2048/2047; no SQL consumer does. Recomputing 1008 in SQL
   disagrees with the stored snapshot on 6 of 113 entries, worst case 41 kcal.
   `db.nutrient_attribution` inherits this and then hides it, because it
   rescales the parts to sum to the stored whole — so a component with no 1008
   silently transfers its share of the calories to the components that have
   one. `/why` currently attributes calories to foods that did not provide
   them.
2. **`db.nutrient_attribution` does not fold `canonical_id`.** It joins
   `food_nutrient` on a bare `nutrient_id` while `v_day_nutrient` folds
   1063→2000. A sugar breakdown will not sum to the sugar total.
3. **Own the "one multiplication" test.** I have proved it holds for all 283
   current components (§1.7); making it a standing test over the whole log,
   for every nutrient, belongs with you.

**Agent 2 / whoever owns resolution ranking.** `food_portion` is a free
correctness signal you are not using: a candidate row that has no portion at
all, for a food a person eats in units, is weak evidence about the row. More
importantly, my R2 needs the *matched* row to have portion data, so a ranking
that prefers a portion-less row makes a volume unconvertible. Please treat
"has a usable `food_portion` row" as a tie-break, not a filter.

**Agent 1 / whoever owns aliases.** `food_alias.default_grams` is written on
first resolution and never updated, and seven aliases currently hold 1 g and
one holds 400 g. Under R7 nothing reads `default_grams` any more. If you keep
it, it needs the same provenance discipline as `log_component.grams_source`,
and it should probably just be the median of `portion_history`.

**Whoever owns the loader.** `scripts/load_usda.py:206` discards
`portion_description` for every FNDDS row because `units.get(...)` returns the
truthy string `"undetermined"`. 22,046 portions — 60% of the table, and the
dataset that supplies 126 of 283 logged components — are stored as opaque
numeric codes. One line, plus a reload. Everything in §3.2 R2/R3 is half as
useful until this lands.

---

## 6. What I would defer

- **Ripeness, cut, and any per-food density table.** `food_portion` supersedes
  the need, and CLAUDE.md already records the ripeness decision.
- **Imperial units beyond `oz`/`lb`.** One user, metric locale. `oz` is worth
  having only because USDA's portion text is full of it.
- **Backfilling the 283 stored components.** `log_nutrient` is immutable
  (invariant 2). The 1 g onion stays 1 g. What must be fixed retroactively is
  the *derived* state that feeds future decisions: the seven poisoned
  `food_alias.default_grams` rows, and — if R6 is to mean anything —
  a decision about whether the six 1 g `stated` components should be excluded
  from `portion_history` by a targeted correction. I would exclude them and
  record why, rather than rewrite them.
- **Multi-user `food_portion` ownership.** Add the column when there is a
  second user; note the hazard now.
- **Reaching `food_portion` from the photo path.** A photograph gives no unit
  word to anchor on. Text first.
- **A `/portion` command for declaring arbitrary portions.** The `makes 850 g,
  16 slices` grammar already covers the case that arose. Wait for a second.

---

## Appendix — queries used

```sql
-- provenance split of the 283 confirmed components
SELECT grams_source, count(*), sum(grams) FROM log_component c
  JOIN log_entry e ON e.id=c.entry_id WHERE e.status='confirmed' GROUP BY 1;

-- energy carried by each provenance
SELECT c.grams_source, count(*), sum(c.grams),
       sum(c.grams*coalesce(fn.amount,0)/100)
  FROM log_component c JOIN log_entry e ON e.id=c.entry_id
  LEFT JOIN food_nutrient fn ON fn.fdc_id=c.fdc_id AND fn.nutrient_id=1008
 WHERE e.status='confirmed' GROUP BY 1;

-- one-multiplication proof
WITH comp AS (SELECT c.entry_id, sum(c.grams*c.yield_factor*fn.amount/100.0) r
                FROM log_component c
                JOIN food_nutrient fn ON fn.fdc_id=c.fdc_id AND fn.nutrient_id=1008
               GROUP BY 1)
SELECT count(*), count(*) FILTER (WHERE abs(ln.amount-comp.r)>0.5)
  FROM comp JOIN log_nutrient ln
    ON ln.entry_id=comp.entry_id AND ln.nutrient_id=1008
  JOIN log_entry e ON e.id=comp.entry_id WHERE e.status='confirmed';

-- portion text usability
SELECT count(*) FILTER (WHERE modifier ~ '^[0-9]+$')  AS numeric_code,
       count(*) FILTER (WHERE modifier !~ '^[0-9]+$') AS usable_text
  FROM food_portion;

-- duplicate fdc_id within one entry
SELECT e.id, c.fdc_id, count(*) FROM log_entry e
  JOIN log_component c ON c.entry_id=e.id WHERE e.status='confirmed'
 GROUP BY 1,2 HAVING count(*)>1;
```
