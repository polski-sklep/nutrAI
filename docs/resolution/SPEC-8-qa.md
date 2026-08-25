# SPEC-8 — the golden evaluation set, and the suite that runs it

Agent 8. Investigation and specification only; nothing under `nutrai/`,
`tests/`, `sql/` or `scripts/` was modified. The dataset is
`docs/resolution/golden.yaml` (76 cases, 165 distinct `fdc_id`s, every one
verified present against the live database on 25 Aug 2026).

**This is stage 3 arriving early and by construction.** CLAUDE.md's order of
work says *collect the eval set, two weeks, build nothing else during it*. This
set was built by reading the code, the failure log and the database instead of
by waiting. That substitution buys a regression gate today and pays for it in
ways §6 sets out in full: a constructed set knows what I could imagine, and the
nine traced failures were found by eating, not by inspection. The fortnight is
still worth running. What changes is that it will be spent *weighting* and
*extending* a set that already exists rather than starting from nothing.

---

## 1. Suite design and how it runs

### 1.1 The chain, and where the model actually is

```
  text/photo ──[MODEL]──► items{label, search_terms, grams, grams_source, state, count}
       │
       ├─ resolve_alias(user, label)                              SQL, free
       ├─ _candidates → db.search_foods(search_terms) ∪ (label) ∪ (dish)   SQL
       ├─ select: own(precedence 0) │ sim ≥ 0.62 │ inverts_meaning gate    SQL
       │      └─ else ──[MODEL]──► DISAMBIGUATE_TOOL over top-5 (+yield_factor)
       ├─ _mass_for: portion_for → count_from_text → portion_history → choose_mass
       ├─ profiles_for → canonical fold (1063→2000) → normalise_energy (2048/2047)
       ├─ total_nutrients (missing ≠ zero) → coverage
       └─ validate: energy cross-check, no-energy row, mass, yield, state
```

Only two boxes contain a model. Everything else is SQL and arithmetic. That is
the whole design of the suite: **freeze the model's output once, and the other
seven stages become deterministic, free and fast.**

### 1.2 Three tiers of run

| tier | selector | count | needs | wall time | cost |
|---|---|---:|---|---|---|
| lint | `pytest -q` (default) | 76 | nothing | <0.1 s | $0 |
| resolve | `pytest -q -m integration` | 59 | Postgres | ~4 s | $0 |
| model | `pytest -q -m expensive` | 17 | API key | ~60 s | ~$0.07 |

**lint** runs in the existing DB-free suite. It loads the YAML and asserts the
dataset's own integrity: every case has an `id`, a `stage`, a `tier`; every
discriminator has a `reason` string; no two cases share an `id`; every
tolerance is one of the four permitted shapes. It does not touch the database,
so `pytest -q` stays DB-free as CLAUDE.md requires and grows from 293 to 294
tests (one parametrised lint, not 76 collected items — keep the default run's
output unchanged in shape).

**resolve** is the suite that matters. It runs under the existing
`integration` marker, alongside the 93 integration tests, and takes the frozen
`parse` block from each case as input. No model call, no network, fully
deterministic, four seconds for the lot. This is the gate a change to
`db.search_foods`, `_candidates`, `UNUSABLE_ROW`, `precedence`,
`AUTO_MATCH_SIMILARITY`, the canonical fold or `normalise_energy` must pass.

**model** is a new marker, deselected by default *and* by `-m integration`. It
covers the 17 cases where the assertion is about what the model does —
translation of Polish, expansion of `pb`, decomposition of a composite,
one-call-per-album. Responses are recorded as fixtures under
`tests/fixtures/golden/<case_id>.<model_id>.json`, keyed by model id and a hash
of the prompt. A run without `--refresh` replays fixtures and is then free and
deterministic; `pytest -m expensive --refresh` makes real calls and rewrites
them. Keying on model id means changing `MODEL_TEXT` invalidates every fixture
by construction — which is exactly what stage 4 ("score the models") needs, and
is a feature rather than an inconvenience.

### 1.3 Two seams the suite needs, which do not exist

Both are small and both are blocking.

**(a) `resolve_items` writes.** It calls `db.upsert_alias` on every successful
tier-2 and tier-3 resolution. An evaluation harness cannot call it without
mutating the alias table — which is why the baseline in §3 replicates the tier
logic rather than calling the function, and why the baseline is a
*reimplementation* and therefore weaker evidence than it should be. The fix is
a keyword-only argument:

```python
async def resolve_items(user_id, items, dish_name=None, text=None, *,
                        write_alias: bool = True) -> Resolution
```

with the suite passing `write_alias=False`. This also makes it possible to
assert `alias_not_written_on_weak_match`, which is a real invariant with no
current owner (§5.8).

**(b) Aliases short-circuit everything.** `resolve_alias` runs before any
search. User 2 has 132 aliases, so a case whose label matches one measures the
cache and not the resolver — `blondie`, `whole milk`, `salt`, `egg whites,
fried`, `eggs`, `egg yolk`, `tomato` and `pickle` are all in that set and all
appear in this dataset. **The suite must bootstrap a throwaway user with zero
aliases**, and be granted visibility of the `user_product` rows the
`composite_devolay`, `tiny_whey_powder`, `absent_pickle_juice` and
`fraction_numeric_slice` cases need. Alias behaviour is then tested explicitly
and only by the four `alias_*` cases, which seed exactly the alias they are
about.

`tests/conftest.py` already sweeps test users; the throwaway id joins
`TEST_TELEGRAM_IDS`.

### 1.4 One dependency

The dataset is YAML because the discriminator *reasons* are the load-bearing
part of it and a format without comments loses them. PyYAML is not currently
installed. Add it to the `dev` extra only — not to `dependencies`, since
nothing shipped reads it:

```toml
dev = ["pytest>=8", "pytest-asyncio>=0.24", "ruff>=0.6", "pyyaml>=6"]
```

Reason for the commit message: *the golden set is a document read by people at
least as often as by the runner; JSON would strip the reasoning that makes each
tolerance defensible.* If that is refused, the fallback with zero new
dependencies is a `tests/golden_data.py` module of plain dicts — it keeps the
comments and loses only the "data, not code" framing.

### 1.5 How a failure reports

A number differing is not a diagnosis. The runner walks the chain in order and
reports **the first stage that broke**, with the evidence for that stage:

```
FAIL egg_white_fried  [stage: SELECT]  traces FAILURES#1

  auto-matched  173423  Egg, whole, cooked, fried            sim 0.692  precedence 2
  expected      2707171  Egg, white, cooked, fat added        sim 0.600  precedence 3
                (present in the candidate set, ranked 2 of 5, 0.092 below the winner
                 and 0.020 below AUTO_MATCH_SIMILARITY = 0.62)

  discriminator that failed:
    1253 cholesterol   expected 0 mg/100 g (max 15)   got 401 mg/100 g
                       "Egg white has no cholesterol. 99 g carried 397 mg never
                        eaten and the day read 249% of its ceiling."
  discriminators that PASSED and would have hidden this:
    1008 energy        196 vs 100 kcal/100 g — inside a 25% tolerance? no, but
                       within the range a plausible frying-oil difference covers
    1003 protein       13.6 vs 9.99 — a 36% gap that reads as ordinary variation

  chain: parse OK → candidates OK (right row offered) → SELECT WRONG
```

The three lines that carry the value are: **which stage**, **the similarity
margin** (0.092 — a threshold change of that size flips this case, which tells
you whether to tune or to re-rank), and **which discriminator caught it while
which ones did not**. The last is the direct answer to "calories are not
sufficient": the report names, every time, the nutrients that would have let
the failure through.

Stage attribution rules, applied in order:

| observation | reported stage |
|---|---|
| expected row absent from the pooled candidate set | `CANDIDATES` |
| expected row present, a forbidden/other row won | `SELECT` |
| right row, `yield_factor` outside tolerance | `YIELD` |
| right row and yield, grams outside tolerance | `MASS` (naming the source: portion / count / prior / estimate) |
| right row, right grams, discriminator nutrient out | `NUTRIENT` (join, canonical fold or energy fallback — not the match) |
| all of the above right, expected warning absent | `VALIDATE` |
| entry-level assertion (duplicate fdc_id, macro sum, item count) | `ENTRY` |

### 1.6 The suite is also a threshold sweep

`AUTO_MATCH_SIMILARITY = 0.62` is documented as arbitrary and as
"tune it against the eval set, not against intuition". This *is* that eval set.
The runner takes `--sweep 0.50:0.90:0.02` and prints pass count and
model-call count per threshold. Do not wire the sweep into CI — it is an
analysis tool run when the number is next argued about. Its output is the only
honest basis for changing 0.62.

---

## 2. The dataset

`docs/resolution/golden.yaml`. 76 cases across the twelve required categories,
plus three the brief did not ask for and the failure log demands: the alias
layer, the nutrient-join layer, and entry-level invariants.

| category | cases |
|---|---:|
| whole foods, one obvious row | 3 |
| many near-identical rows | 3 |
| raw/cooked, dry/prepared | 5 |
| drained/undrained, with/without salt | 6 |
| form: white/whole/yolk, skin, bone | 5 |
| household measures | 7 |
| units g/kg/ml/oz, counts, fractions | 8 |
| liquids, oils, powders, spices at tiny mass | 4 |
| composite dishes and recipes | 5 |
| absent from USDA | 4 |
| misspellings, abbreviations, Polish, regional | 9 |
| contradictory and implausible | 7 |
| the alias layer | 4 |
| the nutrient join | 4 |
| entry-level | (folded into the above: 4 cases) |

**Id verification.** 165 distinct `fdc_id`s are referenced across `expect`,
`acceptable`, `forbidden` and `components`. All 165 exist. Exactly one is
retired — `-249`, the superseded Blondie, which is referenced *only* as a
forbidden row and must stay retired for `fraction_numeric_slice` to mean
anything. Re-verify with the `--verify-ids` pass before believing any failure;
a loader run can move FNDDS ids.

**No case expects a Branded row.** Branded is not loaded, and per
ARCHITECTURE §0.3 it deliberately should not be. Every expectation resolves
inside Foundation (411), SR Legacy (7,793), FNDDS (5,432) or the user's own 14
`user_product` rows.

### 2.1 Tolerance policy

Four shapes, chosen per nutrient, never global:

- `pct: n` — relative. For nutrients where dataset-to-dataset variation is real
  (energy across SR Legacy/FNDDS for the same food is routinely 5–10%).
- `abs: n` — absolute. **Required for any expected value near zero.** "±25% of
  6 mg of sodium" is not a test; "≤26 mg" is. Used for unsalted peanuts (6 mg),
  butter without salt (11 mg), plain pasta sodium (6 mg).
- `max: n` — an upper bound, for "this must be approximately none of it":
  cholesterol in egg white (0), vitamin A in plain pasta (0), cholesterol in a
  meat analogue (0).
- `exact: true` — no slack. Used only where the number is arithmetic, not
  measurement: a user_product panel, a declared portion weight.

`pct` and `abs` may both be given; the wider wins. That is what protects a
small number from a percentage and a large one from an absolute.

**Every tolerance carries its reason in the file.** A tolerance without a
stated reason is a number somebody will widen the next time the suite is red.

### 2.2 The discriminators, and why calories are not enough

The brief is right and the dataset is built around it. Six cases in this set
are *invisible* to energy:

| case | energy, right vs wrong | the discriminator | ratio |
|---|---|---|---|
| `pasta_dry_no_plain_row` | 371 vs 372 kcal | fibre 3.2 vs 10.6 g | 3.3× |
| `butter_unsalted` | 717 vs 717 kcal | sodium 11 vs 643 mg | 58× |
| `peanuts_unsalted` | 587 vs 587 kcal | sodium 6 vs 410 mg | 68× |
| `broccoli_boiled_nosalt` | 35 vs 35 kcal | sodium 41 vs 262 mg | 6.4× |
| `unit_oz` | 206 vs 213 kcal | protein 22.1 vs 10.8 g | 2.0× |
| `inverting_meatless` | 234 vs ~290 kcal | fibre 0.5 vs 4.3 g | 8.6× |

In the butter and peanut cases **every other value in the two rows is identical
to the decimal**. There is literally no observable except sodium. A suite that
scored on calories would report those two cases green while logging 400 mg of
sodium that was not eaten, six times a week.

The inverse also holds and the set covers it: `chickpeas_canned_drained` fails
today on a row (`Chickpeas, NFS`) whose fat is 3.2× the right one and whose
energy follows — that one *is* visible on calories, and the case says so, so a
reader can tell the two kinds of failure apart.

### 2.3 Paired cases

Nine cases are marked `pair_with`. A pair exists because either half alone can
be passed by a constant bias:

- `rice_cooked` / `rice_dry` — a resolver that always prefers "cooked" passes one.
- `butter_salted` / `butter_unsalted`, `peanuts_salted` / `peanuts_unsalted` —
  a resolver that always prefers the salted row passes one.
- `egg_white_fried` / `egg_whole_fried` — the fix for FAILURES 1 must not have
  created its inverse, where a real yolk lands on an egg-white row.
- `inverting_meatless` / `inverting_vegan_requested` — a guard that blocks
  analogues wholesale passes the first and fails the second. This is precisely
  why `inverts_meaning` checks the query as well as the description, and the
  pair is the only thing that keeps that true.
- `polish_kielbasa` / `regional_diacritic_stripping` — separates "the row is
  missing" from "the query cannot reach the row".

**A pair must be scored as one unit.** Half a pair passing is not half a pass.

---

## 3. Current pass rate — measured, honestly

Run 25 Aug 2026 against the live database, read-only, replicating the
deterministic tiers of `resolve_items` (see §1.3a for why replicating rather
than calling). No aliases consulted, no model calls, `user_id = 2` for
`user_product` visibility only.

```
IDS:   165 referenced,  0 MISSING,  1 retired (-249, deliberately)

TALLY: PASS 41   FAIL 8   MODEL-TIER 10   SKIP 17
```

- **41 of 49** decidable model-free cases pass — **84%**.
- **10** cases fall to the model tier, where the deterministic harness cannot
  render a verdict. Three of those carry a further finding: for
  `misspell_chicken` the candidate set is *headed by a forbidden row*
  (`Chicken breast, roll, oven-roasted`, 883 mg sodium), and for `unit_grams`,
  `implausible_mass` and `inverting_meatless` the **right row is not in the
  candidate set at all** — the model tier is being asked to choose correctly
  from five options none of which is right.
- **17** are `needs_model` or entry/nutrient-stage cases the read-only harness
  does not reach. They are specified, not yet measured.

### 3.1 The eight failures

| case | today's answer | sim | why it is wrong |
|---|---|---:|---|
| `egg_white_fried` | `Egg, whole, cooked, fried` | 0.692 | **FAILURES #1, reproducing live.** 401 mg cholesterol/100 g on a food with none. The correct `Egg, white, cooked, fat added` is second at 0.600 — 0.020 below the threshold |
| `chicken_breast_skin_on` | `Chicken, breast, meat and skin, RAW` | 0.769 | wrong state, and the row USDA publishes with a **negative** carbohydrate |
| `broccoli_boiled_nosalt` | `…drained, with salt` | 0.737 | 262 vs 41 mg sodium; every other value identical |
| `absent_local_bakery_bun` | `Roll, egg bread` | 0.733 | auto-matched with **no weak-match flag** on a food nobody can identify |
| `chickpeas_canned_drained` | `Chickpeas, NFS` | 0.714 | NFS silently includes added fat: 8.9 vs 2.8 g |
| `unit_oz` | `Salmon salad` | 0.700 | a mayonnaise dish for a fillet; protein halves, energy moves 3% |
| `pasta_dry_no_plain_row` | `Spaghetti, spinach, dry` | 0.700 | fibre 10.6 vs 3.2 g; energy and protein are indistinguishable |
| `near_chicken_breast_cooked` | `Chicken, breast, boneless, skinless, RAW` | 0.641 | cooked mass on a raw row at `yield_factor` 1.0 — 25% of his largest protein source |

Six of the eight auto-matched **above** `AUTO_MATCH_SIMILARITY`, which is the
finding underneath the finding: these are not near-misses that a model call
would rescue. The resolver was confident.

### 3.2 What the baseline says about the threshold

Every one of the eight failures sits between 0.641 and 0.769. Every one of the
ten model-tier cases sits between 0.258 and 0.614. **There is no value of
`AUTO_MATCH_SIMILARITY` that fixes this set.** Raising it to 0.78 would convert
all eight failures into model calls — and simultaneously demote 14 currently
correct auto-matches (`rice_cooked` 0.837, `peanuts_salted` 0.774,
`egg_white_raw` 0.737, `egg_yolk` 0.722, `measure_tsp_cinnamon` 0.696,
`tiny_black_pepper` 0.650 among them) into paid calls with no accuracy gain.

That is the single most useful number in this document: **the problem is not
where the threshold sits, it is that trigram similarity does not rank these
pairs in the right order at any threshold.** Tuning 0.62 is not the fix. §5.1
and §5.2 name what is.

---

## 4. The nine traced failures: caught, and not

| # | failure | covered by | verdict |
|---|---|---|---|
| 1 | egg whites → whole egg | `egg_white_fried`, `egg_white_raw`, `egg_yolk`, `egg_whole_fried` | **CAUGHT — and failing today.** The production fix was a hand-corrected alias for one exact phrase; the resolver still returns whole egg for a new phrasing. §5.1 |
| 2 | butter → row with no energy | `butter_salted`, `butter_unsalted`, `whole_olive_oil`, `alias_to_unusable_row_is_skipped`, `tiny_salt` | **CAUGHT, and extended.** Butter passes. The suite finds the unfixed variant: 12 rows still escape `UNUSABLE_ROW`. §5.3 |
| 3 | user's food lost to a generic row | `composite_devolay`, `composite_devolay_bare_word`, `tiny_whey_powder`, `absent_pickle_juice`, `fraction_numeric_slice` | **PARTIALLY.** `tiny_whey_powder` (0.760) and `absent_pickle_juice` (1.000) exercise the `own` shortcut and pass. `composite_devolay` does **not** reach it — 0.390 — so the guarantee the fix added is untested by the case that motivated it. §5.9 |
| 4 | sugar under one of two USDA ids | `sugar_canonical_fold`, plus 1063 discriminators on `pasta_cooked` and `unit_ml_water_like` | **CAUGHT.** Model-free, nutrient stage, and deliberately also tested on two ordinary foods so the fold stays under test outside the case that revealed it |
| 5 | one meal photographed twice | `album_one_meal` | **NOT CAUGHT beyond what already exists.** `test_album_becomes_one_meal_not_four` already asserts one `record_meal` call per album with a stubbed model. The golden case adds a sugar-total assertion and no detection power. Real photo fixtures would be needed and this set has none. §6 |
| 6 | pickle juice → pickle relish | `absent_pickle_juice`, `absent_pickle_brine_before_food_row` | **CAUGHT.** The first passes (the `/food` row wins at 1.000); the second, run with that row hidden, reproduces the pre-fix world and confirms the candidate scores 0.368 — below `WEAK_MATCH_SIMILARITY`, so it should surface as weak and never auto-resolve |
| 7 | recipe divided by an impossible yield | `recipe_yield_impossible`, `fraction_numeric_slice`, `measure_slice_bread` | **CAUGHT — by a check that does not exist yet.** The case specifies the macro-sum identity (protein + fat + carbohydrate + fibre ≤ 100 g per 100 g). It also records that `energy_cross_check` **passes** on the bad entry, so a suite running only today's guardrails scores it green |
| 8 | `_label_match` appended instead of replacing | `duplicate_fdc_in_entry` | **PARTIALLY.** The case asserts the entry-level invariant — no two components sharing an `fdc_id` — which would have caught the *consequence* (907 kcal of a bird eaten once). It would not have found the `_label_match` bug itself; that is a DSL-level test and belongs to whoever owns `core/dsl.py`. FAILURES.md itself says this is not a resolution failure |
| — | the audit table (`atwater_mismatch` 18, `fibre_implausible` 9, `unpinned_alias` 5, `no_energy_row` 3, `inverted_match` 2, `qualifier_mismatch` 1) | see below | **5 of 6 covered** |

Audit-finding coverage: `no_energy_row` → `whole_olive_oil`,
`alias_to_unusable_row_is_skipped`. `inverted_match` → `inverting_meatless` /
`inverting_vegan_requested`. `qualifier_mismatch` → the whole salt/state/form
block, 16 cases. `unpinned_alias` → `alias_not_written_on_weak_match`,
`alias_never_repointed_when_pinned`. `fibre_implausible` → the fibre
discriminators on `pasta_dry_no_plain_row`, `inverting_meatless`,
`measure_tsp_cinnamon`, `no_zero_fill_micronutrient`.
**`atwater_mismatch` (18 findings, the largest category) is the one not
covered**, because it is a *day-level* consistency signal computed over whatever
was logged, and this set is per-case. Constructing a day whose Atwater check
fails is easy; constructing one that reproduces why *his* days fail is not, and
would be guessing. That needs the fortnight.

---

## 5. Challenges to other layers, by layer

Each of these was found while building the set. Each names the layer that owns
it. None is a suggestion about code I did not read.

### 5.1 Candidates / ranking — FAILURES #1 was never fixed, only cached

**Layer: `db.search_foods` + `parse._candidates`.**

Measured today. Label `egg whites`, search_terms `egg white, cooked, fried`:

```
173423  0.692  Egg, whole, cooked, fried        ← auto-matched
2707171 0.600  Egg, white, cooked, fat added    ← correct
2707170 0.545  Egg, white, cooked, no added fat
```

The production fix was an alias correction on the exact string
`egg whites, fried`. The resolver is unchanged. Any new phrasing — "fried egg
whites", "egg white omelette", a photo caption — re-creates the failure **and
caches it again**, because tier-2 auto-matches write an alias. FAILURES.md's own
pattern note 2 predicts this exactly: "a wrong match is not one wrong meal, it
is every future meal containing that food."

The word that decides the food is `whole` versus `white`, and trigram
similarity scores the row containing `whole` higher because it is shorter and
shares more of the query's mass. This is not tunable. It needs the same
treatment `INVERTING_TERMS` got: a named set of **partitioning qualifiers**
whose presence in the query and absence in the candidate (or vice versa)
disqualifies an auto-match. white/whole/yolk, salted/unsalted, raw/cooked/dry,
drained/rinsed, skinless/skin-on, boneless/bone-in. Six pairs would move
`egg_white_fried`, `butter_unsalted`, `broccoli_boiled_nosalt`,
`peanuts_*`, `chicken_breast_skin_on` and `rice_*` from "ranked by chance" to
"cannot auto-match on the wrong side".

### 5.2 Candidates — the pooling fix introduced a new failure

**Layer: `parse._candidates`.**

`_candidates` searches on `search_terms` *and* the bare label, and ranks by the
best score either achieved. That fixed the salami case. It also means a short
label inflates short wrong descriptions:

```
label "salmon" + search_terms "salmon, atlantic, farmed, cooked"
  2706826  0.700  Salmon salad                                  ← auto-matched
  175168   0.690  Fish, salmon, Atlantic, farmed, cooked, dry heat  ← correct
```

`Salmon salad` wins by 0.010 because the two-word query scores well against a
two-word description. Protein halves (22.1 → 10.8 g); energy moves 3% and the
Atwater check sees nothing. The pooling rule "best score any query achieved"
is scale-free and should not be: a score from a query with fewer tokens than
the candidate description is weaker evidence, not equal evidence. Whoever owns
`_candidates` should decide whether to length-normalise, or to rank the pooled
set by the *search_terms* score with the label score used only for inclusion.

### 5.3 Row filter — `UNUSABLE_ROW` misses the case it was written for

**Layer: `db.UNUSABLE_ROW`.**

The filter excludes a row with macros and no energy. It does **not** exclude a
row with *neither*. Twelve rows in this database qualify:

```
748608   Oil, olive, extra virgin      30 nutrient rows, no 1008/2047/2048, no 1004
1750348  Oil, peanut          1750349  Oil, sunflower       1750350  Oil, safflower
1750351  Oil, olive, extra light       748278  Oil, canola  748323  Oil, corn
748366   Oil, soybean         2705383  Milk, human
2727588  Juice, pomegranate, from concentrate, shelf-stable
321505   Salt, table, iodized          -465  Muszynisnka Sparkling Water
```

`748608` carries `1085 Total fat (NLEA)` = 93.7 g and `1258` saturated fat =
15.4 g. Nothing maps `1085` to `1004`. So `15 g olive oil` matched to that row
contributes **0 kcal, 0 g fat, and 2.3 g of saturated fat** — it does not
merely understate, it moves saturated fat up while moving energy to zero. That
is a worse shape of wrong than the butter case, which only understated.

Eight of the twelve are oils, which is precisely the class ARCHITECTURE §0.2
singles out as the one where a low bias hurts most: 15 g of oil is 135 kcal, a
quarter of his deficit. `whole_olive_oil` currently passes only because the
FNDDS `Olive oil` row scores 1.000 on the plain query; `olive oil, extra
virgin` resolves to the empty row.

Two fixes, both for the owner of that filter: extend the energy test to
`1085`-style alternates, or — simpler and stricter — exclude any row with no
`1008/2047/2048` **and** no `1004`, rather than requiring a positive macro.

### 5.4 Yield — the auto-match path can never set a yield factor

**Layer: `parse.resolve_items._accept`.**

```python
async def _accept(label, fdc_id, it, yf: float = 1.0)
```

Tier 2 calls it without `yf`. Only the tier-3 model path ever passes one. So
every auto-match applies `yield_factor = 1.0` regardless of state. Measured:

| case | logged state | auto-matched row | sim |
|---|---|---|---:|
| `near_chicken_breast_cooked` | cooked | `Chicken, breast, boneless, skinless, **raw**` | 0.641 |
| `near_chicken_thigh_cooked` | cooked | `Chicken, thigh, boneless, skinless, **raw**` | 0.744 |
| `chicken_breast_skin_on` | cooked | `Chicken, breast, meat and skin, **raw**` | 0.769 |

250 g of roasted breast on the raw row is 56 g of protein instead of 75, and
112 kcal/100 g (via the Atwater fallback) instead of 161. ARCHITECTURE §2 calls
`yield_factor` "where the real error lives" and says getting it wrong makes you
"33% wrong on your largest protein source". The cheap path structurally cannot
set it. Either the auto-match tier must derive a yield factor from the state
mismatch, or a state mismatch must disqualify an auto-match and fall to the
model tier that can.

### 5.5 Mass — 36,682 USDA household measures are loaded and never read

**Layer: `db.portion_for`.**

```sql
SELECT unit, gram_weight FROM food_portion WHERE fdc_id = $1 AND id < 0
```

`id < 0` restricts this to *user-declared* portions. There are two. The table
holds 36,684 rows. Everything USDA knows about slices, cups, tablespoons,
teaspoons, cloves and mediums is invisible to the resolver:

```
173944 Bananas, raw   extra small 81 / small 101 / medium 118 / large 136 / extra large 152 g
173410 Butter, salted tbsp 14.2 / pat 5 / cup 227 / stick 113 g
168878 Rice, cooked   cup 158 g
172183 Egg white raw  large 33 g
```

This is FAILURES #7's mechanism one table over. The blondie bug was the model
writing "standard slice assumed ~90 g" while `food_portion` held 88 g exactly;
the code comment in `count_from_text` says so in as many words — "the whole
point of a declared portion is that it removes the guess". The same guess is
being made for every USDA food, every time. Seven cases in this set
(`measure_*`, `fraction_written`) assert against the USDA figure and currently
depend on a model estimate landing near it.

The owner of `_mass_for` should decide whether to widen the filter, and how to
pick among a food's several units — but "1 cup of rice" having an exact answer
in the database and getting a guess instead is not a judgement call.

### 5.6 Mass — no code parses kg, ml, oz or fl oz

**Layer: parse prompt / `_mass_for`.**

`count_from_text` reads counts. Nothing reads units. kg→g, ml→g (with density),
oz→28.35 g and fl oz→29.57 ml are entirely model-side and entirely untested.
Three failure shapes, all silent:

- `0.5 kg potatoes` returned as 0.5 g — a meal 1/1000 of its size, and 0.5 g of
  anything is plausible.
- `330 ml orange juice` as 330 g — a 3–4% understatement (juice is ~1.04 g/ml)
  that recurs on every drink, every day, and never trips anything.
- `4 oz salmon` as 4 g, or as a fluid ounce (118 g rather than 113).

The ml case matters more than it looks: milk, juice, coffee and water are the
most frequently logged liquids and the convention is currently *whatever the
model felt like*. Pin it, wherever it is pinned.

### 5.7 Parse — Polish returns zero candidates, and zero means silently dropped

**Layer: parse prompt (translation), and `db.search_foods` (reachability).**

Measured against the live database. These return **no candidates at all**:

```
kasza gryczana   twaróg   twarog   biały ser   kiełbasy   kabanos   pb   skyr
```

`resolve_items` appends a no-candidate label to `unresolved`. `DISAMBIGUATE_SYSTEM`
states the consequence precisely: "an unmatched ingredient is dropped from the
meal entirely and contributes zero of every nutrient — a 100% error on that
item, invisible in the total." For a user who logs Polish food, the entire
defence is `PARSE_SYSTEM`'s instruction to write labels in English. That
instruction is one line of a prompt, it has no fallback, and there is no test
anywhere that it holds.

Two separable problems, and the set separates them (`polish_kielbasa` versus
`regional_diacritic_stripping`):

1. **Translation**, which is model work and can only be tested with a model
   call — five `needs_model` cases cover it.
2. **Reachability**, which is not. `kiełbasa` returns nothing while `kielbasa`
   returns four rows. `unaccent` in the search path costs one extension and
   fixes the second problem entirely, independent of the model.

There is also a live wrong alias worth someone's attention:
`brownie → Pie, chocolate creme, commercially prepared` (175014), 3 hits.

### 5.8 Alias — every resolution writes one, including ones nobody confirmed

**Layer: `parse.resolve_items` + `db.upsert_alias`.**

132 aliases, 1 verified, 0 pinned. Tier 2 and tier 3 both call `upsert_alias`
unconditionally. A tier-3 match made at the model's own stated confidence of
0.6 — which `DISAMBIGUATE_SYSTEM` explicitly calls "honest and useful" —
becomes a permanent cache entry the user never saw or agreed to. Combined with
§5.1 (the resolver is still wrong about egg whites), this is how one bad ranking
becomes a year of bad data.

`alias_not_written_on_weak_match` asserts the invariant. It cannot be
implemented without the `write_alias` seam in §1.3a, and the policy question —
write on confirm rather than on resolve? write with a `verified_at` of NULL and
refuse to *reuse* an unverified alias more than N times? — belongs to whoever
owns the alias layer. Invariant 5 says nothing is logged without a human
confirm; an alias written before the confirm gate is the same rule leaking.

### 5.9 The `own` shortcut does not fire on the case that motivated it

**Layer: `parse.resolve_items`.**

The precedence-0 shortcut requires `sim >= AUTO_MATCH_SIMILARITY`. Measured:

- `whey protein powder` → `Olimp Whey Protein Powder` at 0.760 — fires. Good.
- `devolay` → `Devolay chicken (breaded stuffed chicken)` at **0.258** — does
  not fire, even though it is the only candidate returned at all.
- `chicken cordon bleu, breaded, stuffed` → the Devolay row at 0.561 — does not
  fire either; the generic `Chicken or turkey cordon bleu` sits at 0.442.

So FAILURES #3's own example still pays for a model call to choose from a list
of one, and the shortcut that was built for it never engages. A user's own row
is not a candidate to be scored against a threshold designed for 13,000
national averages — if it is the only precedence-0 candidate and it came back
at all, it is the answer. That is the owner's call, but the current threshold
makes the guarantee narrower than the commit message claims.

### 5.10 Entry level has no owner

**Layer: nobody, currently.**

Three invariants with no code behind them, all producing plausible numbers:

- **No two components in one entry share an `fdc_id`.** FAILURES #8 logged 907
  kcal of a turkey eaten once and nothing noticed. (`duplicate_fdc_in_entry`)
- **Macro sum ≤ 100 g per 100 g.** The blondie held 160. This is a closed
  arithmetic identity, not a heuristic, and it is the only check that catches a
  proportional error — the exact class `energy_cross_check` passes on.
  (`recipe_yield_impossible`)
- **A nutrient total that goes negative is visible.** USDA publishes `2727569
  Chicken, breast, meat and skin, raw` with carbohydrate = **−0.43 g/100 g**
  (carbohydrate-by-difference on a fatty cut). `food_nutrient` is a faithful
  copy and must not be edited — but a component quietly netting −0.9 g off
  another food's carbohydrate is a wrong day total with no trace.
  (`negative_nutrient_value`)

### 5.11 Notes for the reconciling lead

- `resolve_items` needs the `write_alias` seam (§1.3a) before any of this can be
  tested. It is the one change that blocks the rest.
- `unaccent` (§5.7) and the `food_portion` filter (§5.5) are each a one-line
  change with a disproportionate effect and no design argument against them.
- §5.1 and §5.4 interact: a partitioning-qualifier guard that demotes a state
  mismatch to the model tier also fixes the yield-factor gap, because the model
  tier is the only path that sets one. Whoever takes either should take both.

---

## 6. What a constructed set cannot tell us

The honest part. Seven things this set does not know, in rough order of how
much they matter.

**1. Frequency.** All 76 cases weigh the same. The real distribution does not:
ARCHITECTURE §0.3 estimates forty foods account for ~90% of a year's eating,
and the measured history is 96 distinct foods across 283 components. A resolver
that is flawless on saffron and wrong about rice scores identically to its
inverse here. Two weeks of real logging produces the weights, and weighted is
the only score that means anything. **This is the largest single thing the
fortnight buys and the set cannot manufacture.**

**2. What the model actually emits.** 59 cases freeze a `parse` block that *I
wrote*. I chose `search_terms` a competent model would plausibly produce. The
real distribution is unknown, and it is a large part of the failure surface —
FAILURES #3 is precisely a `search_terms` failure, where the model's phrase
matched a generic row better than the user's own words matched his own product.
By freezing the parse I have made the suite deterministic and simultaneously
assumed away one of the two model-shaped failure modes. The `needs_model` tier
partly compensates; it does not close the gap.

**3. Photographs.** Zero photo cases. ARCHITECTURE §0.2 names photo portion
estimation as the weakest component in the system, biased low on calorie-dense
items, and this set tests none of it. `album_one_meal` is specified against a
stubbed model and adds nothing to the integration test that already exists.
Real photo fixtures — his photos, of his food, with the scale in some frames
and not others — cannot be constructed. They have to be collected.

**4. The set is biased toward failures I could imagine.** Every case here came
from reading `FAILURES.md`, the code comments, and 20-odd database probes. All
nine traced failures were found by eating and none by inspection. It is
reasonable to expect the next nine to arrive the same way, and there is no
reason to think this set anticipates them. What it does guarantee is that the
*previous* nine cannot come back — which is a real thing to have and is not the
same thing as correctness.

**5. The steady state.** The suite runs as a fresh user with no aliases and no
portion history, so it tests the cold path. Real traffic is the warm one: ~80%
repeats, alias hits, `portion_history` priors, `v_dish_rank`. Four `alias_*`
cases and nothing at all for priors — `portion_prior` needs ≥3 weighings with
spread ≤0.25, which means seeding fake history, which means testing the code
against data I invented. That is a worse test than no test, so I did not write
it. It is a genuine hole and the fortnight fills it with real weighings.

**6. Whether the number is right *in the world*.** Every expected value is a
USDA figure. If USDA's row is wrong about the food he actually ate — Polish
twaróg standing in as American dry-curd cottage cheese, one FNDDS `Pierogi` row
covering ruskie and z mięsem alike — the suite passes with a confident wrong
answer. `polish_twarog` says so explicitly in its own tolerances (±20% protein,
±50% sodium, and flagged as a near neighbour rather than a match), which is the
best a constructed case can do: be loudly uncertain rather than quietly wrong.

**7. Calibration.** Nothing here says whether `overall_confidence: 0.7` means
70%. That is a reliability-diagram question over hundreds of real parses with
known outcomes. It needs the fortnight and then some, and it is the input
stage 4's routing decision actually wants.

### The recommendation

Run this set now, as a regression gate, at 84% on the model-free subset with
the eight failures in §3.1 open. **Then still collect the fortnight** — but
spend it differently than CLAUDE.md envisaged: not building a set from nothing,
but logging normally against a set that already exists, so that at the end of
it there are frequency weights, real `search_terms`, real photos, real portion
history, and however many cases nobody thought of. That is a better fortnight
than the one originally scoped, and it is only available because the set was
built first.
