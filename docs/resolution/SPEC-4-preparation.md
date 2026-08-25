# SPEC-4 — Preparation state as a first-class dimension

Agent 4 of nine. Scope: raw / dry / cooked / as-sold, the `state` column, the
`yield_factor` column, and what it costs when they are wrong.

Every number below was measured against the live database on 25 Aug 2026.
Queries are given so they can be re-run. Nothing under `nutrai/`, `tests/`,
`sql/` or `scripts/` was modified.

Case 1 in `FAILURES.md` — egg white matched to whole egg — is the shape of this
problem on a different axis. Two rows share every token that matters, differ by
one word, and the word decides the number. Preparation is the same failure with
a larger blast radius, because it applies to grains and meat rather than to one
breakfast, and because unlike white/yolk it is a *systematic* bias: the user
weighs cooked, and a large part of the reference data is raw.

---

## 1. What is represented today

### 1.1 `state` is a column that has never held a value

```sql
SELECT state, count(*) FROM log_component GROUP BY 1;
SELECT state, yield_factor, count(*) FROM dish_component GROUP BY 1,2;
```

| table | rows | distinct `state` values |
|---|---:|---|
| `log_component` | 363 (283 confirmed, 73 discarded, 7 pending) | `as_logged` ×363 |
| `dish_component` | 172 | `as_logged` ×172 |

Not "mostly `as_logged`". Exclusively. The column has carried exactly one value
since the schema was created, and it is the default.

The reason is not that the model declines to answer. It is that **no INSERT
anywhere in the codebase names the column.** `db._write_components`
(`nutrai/db.py:450`) and `db.add_component_to_entry` (`nutrai/db.py:1970`) both
list `(entry_id, position, fdc_id, label, grams, yield_factor, grams_source,
grams_sigma)` and stop. `db.upsert_dish_components` (`nutrai/db.py:308`) copies
`yield_factor` and `grams_source` from `log_component` into `dish_component`
and omits `state`, which is why the dish table is uniform too.

`add_component_to_entry` is worse than silent: it **accepts** `state: str =
"as_logged"` as a parameter, `bot.py:4328` passes a real value into it
(`state=match["state"]`), and the function drops it on the floor. A caller
reading the signature would reasonably believe it is stored.

The type system loses it one step earlier. `core.nutrition.ResolvedComponent`
— the dataclass every write path funnels through — has fields `label, fdc_id,
grams, yield_factor, sigma, grams_source, count` and **no `state` at all**.
`core.dsl.Component` does have `state`, it is read out of the database at
`bot.py:3689` and `bot.py:3889`, and it is discarded at every point where a
`dsl.Component` becomes a `ResolvedComponent` (`bot.py:3954`, `bot.py:3736`).
So state survives a round trip through the repeat path and dies at the write.

### 1.2 The model does emit state, with real variance

```sql
SELECT it->>'state', count(*) FROM log_entry e,
  jsonb_array_elements(e.parse->'items') it
 WHERE e.status='confirmed' GROUP BY 1;
```

| `parse.items[].state` | count |
|---|---:|
| `as_sold` | 58 |
| `cooked` | 37 |
| `raw` | 28 |
| `unknown` | 13 |
| `dry` | 4 |

140 items across the 65 confirmed entries that carry a parse. This is not a
field the model ignores or fills with a constant — it discriminates, and
`unknown` is used sparingly (9%), which is what `PARSE_SYSTEM` rule 4 asks for.

**The information exists, is paid for, is stored in `log_entry.parse` as raw
JSON, and is thrown away before anything can act on it.** Recovering it costs
one column in an INSERT.

### 1.3 `yield_factor` has been 1.0 for every meal ever confirmed

```sql
SELECT yield_factor, count(*) FROM log_component GROUP BY 1;
```

362 rows at exactly 1.0. One row at 2.4 — `log_component.id = 35839`, label
`x`, 3 g, matched to `Spaghetti, protein-fortified, dry, enriched`, on a
**discarded** entry named "Espresso with milk and sugar". That is a test
artefact, not a meal.

Across all 283 confirmed components, `yield_factor` is 1.0 without exception.
`ARCHITECTURE.md:192` calls it "where the real error lives"; measured, it is
where no value has ever been written.

Only one code path can set it. `parse._accept()` takes `yf: float = 1.0`, and
of the four callers only the tier-3 disambiguation branch passes anything
(`parse.py:498`). Tier 1 (alias hit) and tier 2 (auto-match ≥ 0.62) hardcode
1.0. Since tier 1 is the documented steady state — "after a few weeks of normal
eating the model is barely involved in resolution at all" — the only mechanism
that can produce a yield factor is the one designed to stop firing.

### 1.4 A yield factor cannot survive its own meal

`food_alias` is `(user_id, alias, fdc_id, default_grams, hits, pinned,
verified_at)`. There is no `yield_factor` column and no `state` column.

So when tier 3 correctly returns "this is the raw row, multiply by 1.33", that
1.33 is applied to today's meal and then written to `food_alias` as *nothing*.
The second time the food is eaten, tier 1 hits the alias, returns the same raw
`fdc_id`, and applies 1.0.

**The single most expensive correction the system can make is retained for
exactly one meal, and the mistake it corrects is retained forever.** That is
the reverse of what `FAILURES.md` observes about caching ("a wrong match is not
one wrong meal, it is every future meal containing that food") — here the
*right* answer is the one that does not persist.

### 1.5 State never reaches candidate retrieval

`parse._candidates()` (`parse.py:284`) builds its query list from
`search_terms`, `label` and `dish_name`. `it["state"]` is not among them and is
not consulted anywhere in ranking, filtering or acceptance. A component the
model labelled `cooked` and a component it labelled `raw` generate identical
candidate sets and are accepted on identical thresholds.

State appears in exactly two places downstream of the parse:

1. As decoration in the tier-3 prompt line — `"— logged as {state}, {grams} g"`
   (`parse.py:472`). Advisory text to a model that is separately told to
   "prefer the row whose preparation state matches".
2. In the ambiguity warning in `parse.validate()` (`parse.py:569-593`).

### 1.6 The ambiguity warning promises something no code path can deliver

```python
STATEFUL = ("raw", "dry", "uncooked", "cooked", "boiled", "roasted", "prepared")
...
warnings.append(f"{label}: was that weighed before or after cooking? "
                f"say “dry” or “cooked” and I will use it")
```

Three separate defects.

**The reply cannot be used.** `MODIFIER_SYSTEM` in `llm/schemas.py` instructs
the model: *"If the phrase describes something you cannot express as set, add,
drop or scale_all — a cooking method, a brand, a comment — return no operations
for it."* The `MODIFIER_TOOL` op enum is `["set", "add", "drop", "scale_all"]`.
There is no state operation, and `core/dsl.py` contains no `dry` / `cooked` /
`raw` token. Typing "cooked" at this prompt is guaranteed to do nothing. The
message is the only place in the codebase that promises an action the system
cannot perform.

**The trigger is substring matching on a description.**

```sql
SELECT count(*) FILTER (WHERE lower(description) LIKE '%raw%')              -- 1754
     , count(*) FILTER (WHERE description ~* '(^|[ ,(])raw([ ,).]|$)')      -- 1694
  FROM food;
```

60 rows match `"raw" in desc` without containing the word: every *Straw*berry
row in the database — `Strawberry milk, whole`, `Candies, TWIZZLERS Strawberry
Twists`, `Toaster Pastries, fruit, frosted (include apples, blueberry, cherry,
strawberry)`. `audit._qualifiers` already solved this exact problem two modules
away and says why in its docstring; `validate` does not use it.

**The tuple is missing the largest swing in the dataset.**

```sql
SELECT count(*) FROM food
 WHERE description ~* '(fried|baked|grilled|steamed|braised|stewed|broiled|toasted|sauteed|microwav)'
   AND lower(description) NOT LIKE ALL (ARRAY['%raw%','%dry%','%uncooked%','%cooked%','%boiled%','%roasted%','%prepared%']);
```

629 rows carry a cooking verb `STATEFUL` cannot see. Among them is the single
biggest per-100 g preparation gap the user actually eats: `Egg, whole, raw`
143 kcal against `Egg, whole, cooked, fried` 196 kcal, +37%, 26 g of fat
against 9.5 g. `fried` is not in the tuple.

### 1.7 The confirm gate hides the qualifier precisely when it is the only one

`render.confirm_card` prints the matched USDA row under a component **only
when the label is not a substring of the description**:

```python
if desc and str(label).lower().strip() not in desc.lower():
    lines.append(f"     <i>→ {_esc(desc)}</i>")
```

Measured over the 283 confirmed components: 39 of them (13.8%) resolved to a
state-qualified row *and* had that row suppressed by this rule. All 15 distinct
cases are currently harmless — `banana` → `Banana, raw`, `carrot` → `Carrots,
raw`, `espresso` → `…restaurant-prepared`.

They are harmless by luck of diet, not by construction. The rule is: hide the
row when the user's word is the row's genus. For rice, pasta, potato, oats,
lentils and eggs the user's word *is* the genus and the preparation clause is
the only distinguishing content — `rice` is a substring of both `Rice, white,
long-grain, regular, raw, enriched` (365 kcal) and `Rice, white, long-grain,
regular, enriched, cooked` (130 kcal), and the card would show `rice — 200 g`
in both cases with nothing else.

This is the same failure the rule was written to fix (pickle juice → relish),
inverted. It suppresses the provenance line in exactly the population where
provenance is the whole story.

### 1.8 The audit can see 2% of the problem

`jobs/audit.py` has a `frozenset({"raw", "cooked", "dried"})` family in
`QUALIFIER_SETS`, and the check fires only when a state word appears in **both**
the user's label and the row description and they disagree.

```sql
SELECT count(*) FILTER (WHERE c.label ~* '\m(raw|cooked|dried|dry|fried|boiled|baked|roasted|grilled)\M'),
       count(*)
  FROM log_component c JOIN log_entry e ON e.id=c.entry_id WHERE e.status='confirmed';
```

**6 of 283.** The six are `baked potato`, `boiled egg`, `boiled eggs`, `boiled
potatoes`, `egg whites, fried`, `whole egg, fried` — and all six matched
correctly. The check has 2.1% coverage because people do not say "cooked rice",
they say "rice". The evidence it needs is `parse.items[].state`, which has 100%
coverage on parsed entries and is not stored where the audit can reach it.

### 1.9 Nothing else can catch a state error either

The energy cross-check is the system's one automatic guard, at
`ENERGY_TOLERANCE = 0.12`. It compares a row's own macros to a row's own energy.
A raw/cooked swap replaces one internally consistent row with another
internally consistent row, so the check passes by construction — the same
blindness `FAILURES.md` records for cases 5 and 7, where "the error is
proportional".

There is no coverage metric, no plausibility bound, and no per-food density
check that would notice 200 g of `rice` arriving at 730 kcal.

---

## 2. Measured cost of getting it wrong

### 2.1 Population scale, from the loaded data

767 raw/cooked pairs were recovered from SR Legacy by stripping preparation and
salt clauses from the description and grouping on the remainder, then requiring
both a raw-marked and a cooked-marked member with an energy value.

| statistic | value |
|---|---:|
| matched pairs | 767 |
| median raw/cooked energy ratio | **0.79** |
| pairs within 10% on energy | 114 (14.9%) |
| pairs ≥25% apart on energy | **341 (44.5%)** |
| pairs ≥2× apart on energy | 56 |
| 25th / 75th percentile | 0.72 / 0.92 |
| median raw/cooked **protein** ratio | 0.76 |

Applying the wrong state at the same gram weight is a ≥25% energy error in
**44% of the cases where the choice exists**, and immaterial in 15%.

**Energy is not a sufficient test of materiality.** Of the 114 pairs that agree
on energy within 10%, **70 are ≥20% apart on protein.** Fatty mince is the
canonical case: `Beef, ground, 80% lean / 20% fat` is 254 kcal raw and 258
cooked — a 2% energy difference, because rendered fat offsets lost water — while
protein moves from 18.6 to 25.9 g per 100 g. A protein target is the thing this
user tracks most closely, and the guard the system owns is the one that cannot
see this.

### 2.2 Per food class, from the real rows

Per 100 g, both rows as USDA publishes them. `raw/cooked` is the multiplier you
apply to the truth by picking the wrong row at the same weight.

| food (fdc_id pair) | kcal raw → cooked | ratio | protein raw → cooked | ratio |
|---|---|---:|---|---:|
| Oats, regular/quick (173904 → 173905) | 379 → 71 | **5.34×** | 13.2 → 2.5 | 5.18× |
| Rice, white long-grain (168877 → 168878) | 365 → 130 | **2.81×** | 7.1 → 2.7 | 2.65× |
| Pasta, enriched (169736 → 169737) | 371 → 158 | **2.35×** | 13.0 → 5.8 | 2.25× |
| Pasta, whole-wheat (169738 → 168910) | 352 → 149 | 2.36× | 13.9 → 6.0 | 2.32× |
| Lentils (172420 → 172421) | 352 → 116 | **3.03×** | 24.6 → 9.0 | 2.73× |
| Chicken breast, skinless (171077 → 171477) | 120 → 165 | 0.73× | 22.5 → 31.0 | **0.73×** |
| Beef mince 85/15 (171796 → 174032) | 215 → 250 | 0.86× | 18.6 → 25.9 | **0.72×** |
| Egg, whole (171287 → 173423, fried) | 143 → 196 | 0.73× | 12.6 → 13.6 | 0.92× |
| Egg, whole (171287 → 173424, boiled) | 143 → 155 | 0.92× | 12.6 → 12.6 | 1.00× |
| Potato, flesh (170026 → 170438) | 77 → 87 | 0.89× | 2.1 → 1.9 | 1.10× |
| Carrot (170393 → 170394) | 41 → 35 | 1.17× | 0.9 → 0.8 | 1.22× |
| Broccoli (170379 → 169967) | 34 → 35 | 0.97× | 2.8 → 2.4 | 1.19× |
| **Spinach (168462 → 168463)** | **23 → 23** | **1.00×** | 2.9 → 3.0 | 0.96× |

The most extreme pairs in SR Legacy, by energy ratio: oat bran 6.15×, bulgur
4.12×, buckwheat groats 3.76×, wild rice 3.53×, soba noodles 3.39×, rice
noodles 3.37×, couscous 3.36×, mung beans 3.30×, brown rice 3.23×, millet
3.18×, fava beans 3.10×.

Spinach is the instructive negative. It shrinks visibly in the pan and is
therefore the food people *expect* preparation to matter for, and the per-gram
answer is that it does not move at all: raw spinach is 91.4% water, boiled
spinach is 91.2% water, and both are 23 kcal per 100 g. The mass changed; the
concentration did not. **Machinery here is pure friction.**

### 2.3 What it would have cost this user, in the log as it stands

The user's 283 confirmed components across 96 distinct foods, classified by the
preparation marker on the matched row:

| row carries | components | grams | distinct foods |
|---|---:|---:|---:|
| no preparation token | 194 | 20,702 | 63 |
| raw / dry | 53 | 2,596 | 19 |
| cooked | 36 | 2,979 | 14 |

**Rice, pasta, oats, couscous, bulgur, dry pulses do not appear once.** The
entire class that carries the 2.4×–6.2× exposure is absent from 283 components.
The 19 raw-marked foods are: mixed salad greens, lemon juice, banana, pineapple,
pear (×2 rows), lime juice, avocado, onions, red onion, arugula, cucumber,
lettuce, raspberries, blueberries, carrot, ginger root, garlic, and one
`Beef, ground, raw`.

Eighteen of the nineteen are nutritionally immaterial: fruit, salad, aromatics
and juice, where "raw" is a *nominal* clause distinguishing the row from a
canned or cooked sibling nobody would log, not an actionable one.

The nineteenth is real and it is in the log:

```
entry 24596 · 2026-08-24 · "Pastel de Choclo" · source=repeat
  label "minced beef" · 100 g · grams_source=stated · yield_factor=1.0
  → Beef, ground, raw  (FNDDS 2705853, 213 kcal, 18.4 g protein)
```

Pastel de choclo is a baked corn pie; its mince is browned before assembly. If
the 100 g is a served weight, the row should be `Beef, ground, patty` (272 kcal,
25.4 g protein) — the snapshot is 22% light on energy and 28% light on protein.
If the 100 g is a raw ingredient weight from the recipe, the row is right. **The
system stored no evidence of which,** and that is the point: the state field was
emitted and discarded, so the question is now unanswerable against the record.

### 2.4 Two loaded aliases

`food_alias` holds 135 rows, 0 pinned, 1 verified. Two are armed:

| alias | hits | resolves to | kcal/100 g |
|---|---:|---|---:|
| `eggs` | 5 | `Egg, whole, raw` | 143 |
| `egg yolk` | 5 | `Egg, yolk only, raw` | 328 |
| `whole eggs` | 1 | `Egg, whole, cooked, fried` | 196 |
| `whole egg, fried` | 3 | `Egg, whole, cooked, fried` | 196 |
| `boiled eggs` | 3 | `Egg, whole, cooked, hard-boiled` | 155 |
| `scrambled eggs` | 1 | `Egg, whole, cooked, scrambled` | 149 |
| `minced beef` | 1 | `Beef, ground, 80/20, raw` (Foundation 2514744) | no 1008; 248 via Atwater |
| `pork chop` | 1 | `Pork, chop, center cut, raw` | — |
| `rice` | 1 | `Rice, white, long-grain, enriched, cooked` | 130 |

The same food resolves to six different preparation states depending on the
words used, and the bare, most likely phrasing — `eggs` — lands on **raw**, at
27% under a fried egg on energy and 36% under on fat. No confirmed component
points at either raw egg row today; the alias is loaded and has not yet fired
into a surviving meal. `rice` → the cooked row is correct, and it is correct by
trigram luck, not by any rule.

`minced beef` compounds with `FAILURES.md` case 2: it is a Foundation row, and
Foundation is both the raw-heaviest dataset and the one that routinely omits
nutrient 1008.

### 2.5 The direction of the asymmetry, established

The brief asks which way round this codebase gets it. The answer is: **the
prompt gets it right, the retrieval gets it wrong, and the ranking actively
pushes toward raw.**

- `PARSE_SYSTEM` rule 4 is correct and explicit: *"Default to the food as
  served: a description of a meal refers to what was on the plate unless the
  user says 'dry', 'raw' or 'uncooked'."* The parse output bears this out —
  `as_sold` + `cooked` is 95 of 140 items, `raw` + `dry` is 32.

- The `search_terms` field description contradicts it. Its worked example is
  `'beef, ground, 15% fat, raw'`. The one field whose value is actually used
  for retrieval is illustrated with a raw phrase, while the rule governing the
  field that is *not* used says "as served".

- `food.precedence` ranks `foundation_food` first. Foundation is 42.3% raw
  (174/411) and 2.9% cooked (12/411) — by a factor of fourteen, the dataset most
  likely to be raw is the one ranked highest.

  | data_type | rows | raw | cooked | dry | no prep token |
  |---|---:|---:|---:|---:|---:|
  | foundation_food | 411 | 174 | 12 | 60 | 147 |
  | sr_legacy_food | 7,793 | 1,388 | 1,778 | 503 | 2,842 |
  | survey_fndds_food | 5,432 | 132 | 402 | 92 | 3,954 |

- What has kept this from hurting is FNDDS. It supplies 194 of the user's 283
  components, 72.8% of its rows carry no preparation token, and FNDDS names the
  *eaten* form in the food's name rather than in a qualifier: `Oatmeal, regular
  or quick, made with water, no added fat` is 64 kcal, `Oats, raw` is 379, and
  neither says "cooked". A cooked-weight logger lands on the right basis in
  FNDDS by default.

  That is luck with a mechanism, and it is fragile in exactly one direction: any
  change that raises Foundation or SR Legacy against FNDDS — and precedence
  already wants to — moves the user onto raw-basis rows without a single line of
  the resolver noticing.

Cross-tabulating the model's declared state against the marker on the row it
was matched to, over confirmed entries:

| model said | row marked | n | grams |
|---|---|---:|---:|
| as_sold | unmarked | 55 | 6,413 |
| cooked | unmarked | 19 | 1,951 |
| cooked | cooked | 18 | 1,869 |
| raw | raw/dry | 23 | 1,382 |
| unknown | unmarked | 11 | 1,163 |
| raw | unmarked | 5 | 350 |
| dry | unmarked | 3 | 78 |
| unknown | raw/dry | 2 | 208 |
| as_sold | cooked | 2 | 130 |
| as_sold | raw/dry | 1 | 150 |

No direct `cooked` → `raw/dry` inversion has been confirmed. 1,951 g were
declared cooked and matched to an unmarked row, which is right in FNDDS and
unverifiable in general.

---

## 3. Specification

Five changes. The first two are cheap and recover information the system
already pays for; the rest are gated behind a bounded whitelist.

### 3.1 Store the state that is already produced

Add `state` to the three writes that omit it: `db._write_components`,
`db.add_component_to_entry` (which already takes the parameter), and
`db.upsert_dish_components`. Add `state: str = "as_logged"` to
`core.nutrition.ResolvedComponent` and stop dropping it in the
`dsl.Component` → `ResolvedComponent` conversions at `bot.py:3736` and
`bot.py:3954`.

Values are the parse enum, unchanged: `raw | cooked | dry | as_sold | unknown`,
plus the existing `as_logged` for rows written by paths with no parse (repeat,
template, companion). `as_logged` must mean "this path never had the
information", not "we assumed as served" — a default that silently asserts a
state is worse than one that admits ignorance, and the audit needs to tell them
apart.

`state` is snapshot data, exactly like `grams_source`. It is what the row was
when it was logged, it is never recomputed, and correcting a food's
classification later must not rewrite it. Same reasoning as the NOVA
group decision recorded in `CLAUDE.md`.

Nothing downstream changes arithmetic. This step alone converts the audit's
coverage from 2.1% of components to 100% of parsed ones.

### 3.2 Classify the row, deterministically, in SQL

A view `v_food_prep(fdc_id, prep, prep_source)` where `prep ∈ {raw, cooked,
unmarked}`, derived from `food.description` by **whole-word** match — reuse the
`\m…\M` / `_qualifiers` approach in `audit.py`, never `in`.

- `raw`: word `raw`, `dry`, `dried`, `uncooked`, `unprepared`.
- `cooked`: word `cooked`, `boiled`, `roasted`, `fried`, `baked`, `grilled`,
  `steamed`, `braised`, `stewed`, `broiled`, `toasted`, `sauteed`,
  `microwaved`, `prepared`, `pan-broiled`. The current `STATEFUL` tuple misses
  ten of these across 629 rows.
- `unmarked`: everything else.

Measured over the 13,650 loaded rows, this classifier gives **raw 2,438 /
cooked 3,215 / unmarked 7,997** — so the majority of the database says nothing
about preparation and the view must be able to say so.

`unmarked` is a third value and must never be coerced into either of the others.
For FNDDS it usually means as-eaten; for `Bread, crumbs, dry, grated, plain` the
word `dry` is part of the product identity and not a preparation state at all.
The view records what the description says and nothing more.

Escape hatch: a small explicit override table for descriptions where the
regex is provably wrong, seeded with the handful found during implementation
and never populated by a model.

### 3.3 Use state in retrieval, with a hard exclusion on a bounded whitelist

Preparation becomes a *hard exclusion* only where the two rows are a different
food by the numbers, and only where the food class is enumerated. Everywhere
else it is a ranking hint at most.

**The exclusion set** — a component whose declared state is `cooked` or
`as_sold` may not auto-match a `raw` row when the row is in either class:

- a raw/dry staple: `raw`-marked and description matches rice, pasta, noodle,
  spaghetti, macaroni, oats, barley, couscous, bulgur, quinoa, millet, lentils,
  beans, peas, chickpeas, groats. **174 rows.**
- raw flesh: `raw`-marked and description matches beef, pork, chicken, turkey,
  lamb, veal, fish and named species, shrimp, duck, game. **962 rows.**

1,136 rows, 8.3% of the table. Small enough to eyeball, large enough to cover
every case in §2.2 that moves a number, and it excludes fruit, salad,
aromatics and juice — the 18 immaterial `raw` foods in this user's actual log
— by construction.

Symmetrically, a component declared `raw` or `dry` may not auto-match a
`cooked` row in the same classes. That direction is rarer and cheaper but the
rule should not be one-sided; a recipe stating "100 g dry pasta" matched to
cooked pasta understates by 57% (158 against 371 kcal).

**What "may not auto-match" means:** the candidate is not removed from the list.
It drops out of the tier-2 auto-accept and goes to tier 3 with the state
stated, exactly as `inverts_meaning` already does for meat substitutes
(`parse.py:441`). This reuses a mechanism that exists, costs a fraction of a
penny, and has a precedent in the codebase.

**Retrieval, not just filtering:** when the declared state is `cooked` and the
label names a whitelisted staple, `_candidates` should issue one additional
query with the state word appended, so a cooked row is in the pool at all. The
`search_foods` docstring already records that `rice, white, long-grain,
regular, cooked` scores 0.84 against the cooked row and 0.48 against the raw
one — the query wins when the word is present and loses when it is absent.

### 3.4 Persist the correction

Add `state` and `yield_factor` to `food_alias`, written by `upsert_alias`
whenever tier 3 supplies them.

Without this, §3.3 buys one correct meal per food and the alias re-arms the
error. This is the smallest change in the spec and the one that decides whether
any of the rest compounds.

Pinning must cover it: a pinned alias asserts *(word → row, at this state, with
this factor)*, and re-resolving any of the three is what pinning exists to
prevent.

### 3.5 Prefer a cooked row; derive a factor only as a fallback; never fabricate one

**No yield-factor table is loaded and none is available.** `scripts/load_usda.py`
reads `nutrient.csv`, `food.csv`, `food_nutrient.csv`, `food_category.csv`,
`branded_food.csv`, `measure_unit.csv` and `food_portion.csv`. There is no
retention-factor or yield-factor table in the schema and none in the loader.
The FNDDS yield data that exists upstream is not in the FDC bulk CSV release
this project loads.

There is, however, a derivation from the loaded data. Where nothing but water
moves, dry matter is conserved, so

```
yield = (100 − water_raw) / (100 − water_cooked)
```

Validated against protein conservation, which is independent evidence for the
same quantity:

| pair | yield from dry matter | yield from protein | disagreement |
|---|---:|---:|---:|
| spinach (boiled) | 0.978 | 0.963 | 1.6% |
| carrot (boiled) | 1.191 | 1.224 | 2.7% |
| chicken breast (roast) | 0.751 | 0.725 | 3.6% |
| pasta whole-wheat | 2.403 | 2.316 | 3.8% |
| oats regular/quick | 5.440 | 5.177 | 5.1% |
| rice white long-grain | 2.800 | 2.651 | 5.7% |
| pasta enriched | 2.379 | 2.248 | 5.8% |
| egg (hard-boiled) | 0.940 | 0.998 | 5.9% |
| lentils | 3.022 | 2.731 | 10.7% |
| beef mince 85/15 (broil) | 0.817 | 0.717 | **14.0%** |
| egg (fried) | 0.781 | 0.923 | **15.3%** |
| potato (boiled) | 0.901 | 1.096 | **17.8%** |

Two agreeing estimates within 6% for boiling and roasting; 14–18% apart for
frying (oil enters), rendering (fat leaves) and peeling (solids leave).

**The honest ordering, therefore:**

1. **Prefer a cooked row.** For every food in §2.2 a cooked row exists in the
   loaded data. This is a retrieval problem, not an arithmetic one, and it is
   the only option that introduces no derived quantity.
2. **Derive a yield factor only when no cooked row exists for that food**, both
   rows report water (1051), and the cooking method is not frying. Store it as
   `yield_factor` with a provenance marker distinguishing it from a
   model-supplied one, and surface the derivation on `/why`.
3. **Otherwise abstain.** Send it to tier 3 with the state named, and if tier 3
   declines, leave the mass unconverted and say so on the card. An abstention is
   readable; a wrong factor is not.

Invariant 1 is not breached at step 2. A yield factor is a *mass* ratio computed
in SQL from USDA's own published water content, not a nutrient value and not a
model estimate — the same standing the supplement-label amendment gives a
transcription. But it is weaker than a chosen row, it must be labelled as
derived wherever it appears, and it must never be the first answer when a
cooked row is available. Step 1 exists so that step 2 fires rarely.

### 3.6 Fix the two places that mislead the user

- **`render.confirm_card`**: when the matched row carries a `prep` marker,
  print the `→ row` line unconditionally, overriding the substring suppression.
  The suppression rule is right for `Relish, pickle` and wrong for
  `Rice, …, raw` (§1.7).
- **`parse.validate`**: either wire "dry"/"cooked" as a real DSL operation that
  re-resolves the component and re-parents the alias, or change the wording to
  stop promising it (§1.6). Shipping a prompt that does nothing costs more than
  no prompt — it teaches the user the system handles this.

### 3.7 Where ambiguity reduces confidence — deferred to Agent 7

Preparation ambiguity is a confidence input, and Agent 7 owns confidence. I
specify the *signal*, not the arithmetic, and defer the shape to them:

- `state = 'unknown'` on a whitelisted staple or flesh row is the strongest
  single-component uncertainty signal available. It is not a matter of a wide
  portion — a wrong state on rice is a 180% error with a perfectly weighed
  100 g, and inflating `grams_sigma` would misattribute it.
- Agent 7 should treat it as a *distinct* uncertainty channel from
  `grams_sigma`, not fold it in. `grams_sigma` answers "how well do you know the
  mass"; state answers "of what". `db.day_energy_sigma` combines mass sigmas in
  quadrature and there is a test protecting that; a state term does not belong
  in the same sum.
- The `unmarked` row class is genuine unknown-unknown. It is right ~73% of the
  time by FNDDS convention and unverifiable. Whatever penalty Agent 7 applies
  should be small — it covers 194 of 283 components and a visible warning on
  two-thirds of every meal is a warning nobody reads.

### 3.8 New audit checks

Two, both pure SQL, once §3.1 lands:

- **`state_mismatch`** (error): component `state ∈ {cooked, as_sold}` against a
  row in the §3.3 exclusion set, or the reverse. Coverage goes from the 2.1% of
  components whose *label* carries a state word to 100% of parsed ones.
- **`unconverted_state`** (warn): `state` and row `prep` disagree and
  `yield_factor = 1.0`. This is the state that all 283 confirmed components are
  in today.

Backfill is possible and worth doing once: `log_entry.parse` holds the state
for 65 confirmed entries and it can be read out to populate `log_component.state`
retrospectively. That is a write to a provenance column, not to `log_nutrient`,
so invariant 2 holds — nothing about what any day scored changes.

---

## 4. Which foods justify the machinery, and which do not

| class | ratio | verdict |
|---|---|---|
| dry grains, pasta, rice, dry pulses, couscous, bulgur, oat bran | 2.3× – 6.2× | **Hard exclusion.** A wrong state here is a different meal, not a worse estimate. 174 rows. |
| raw flesh — poultry, lean red meat, fish | 0.72× – 0.86× on energy, ~0.72× on protein | **Hard exclusion.** Protein is the axis and it moves ~28% even where energy barely moves. 962 rows. |
| eggs | 0.73× raw→fried; 0.92× raw→boiled | **Hard exclusion.** Live risk: `eggs` → raw, 5 hits, unpinned. Frying dominates and `fried` is absent from the current `STATEFUL` tuple. |
| starchy vegetables — potato | 0.89× | Ranking hint. Real but under the noise floor of an eyeballed portion. |
| root vegetables — carrot, beetroot | 1.17× / 0.98× | **No machinery.** |
| leafy greens — spinach, broccoli, collards, cabbage | 0.97× – 1.00× | **No machinery.** Spinach is 23 kcal both ways. The mass changes, the concentration does not. |
| fruit, salad leaves, juice, aromatics | n/a — no cooked sibling anyone logs | **No machinery.** "raw" is a nominal clause. This is 18 of the user's 19 raw-marked foods; a naive state rule fires on all of them for zero benefit and teaches the user to dismiss it. |
| milk, cream, yoghurt | Foundation vs SR Legacy differ 1.7% | **No machinery.** `PARSE_SYSTEM` rule 4 already names milk as the case where the question makes the system look stupid. Keep it that way. |
| oil, butter, sugar, honey, spices | n/a | **No machinery.** |

The whitelist is the whole design. The instinct after reading §2.1 — 44% of
pairs ≥25% apart — is to check state everywhere, and that produces a system
that asks whether your cappuccino was weighed before or after cooking.

**Sequencing note.** Rice, pasta, oats and pulses appear zero times in 283
components. The exposure this spec addresses is almost entirely *prospective* —
one live mismatch (`minced beef` in Pastel de Choclo) and two loaded aliases
(`eggs`, `egg yolk`). §3.1 and §3.2 are cheap and should land regardless: they
stop discarding evidence and make the question answerable. §3.3–§3.5 are worth
scoring against the eval set before they are built, and the lead agent should
weigh them against layers whose failures are already in the log.

---

## 5. Challenges to other layers

### To Agent 2 (identity) — preparation is not a qualifier, it is part of the key

`inverts_meaning` and `QUALIFIER_SETS` treat a distinguishing word as a veto on
a candidate. That is right for `meatless` and for `white`/`yolk`, and it is
insufficient here, because **preparation state is only knowable from the item's
declared state, not from the user's words.** 6 of 283 labels carry a state word;
140 of 140 parse items carry a state field. Any identity mechanism that reads
only `label` and `description` is structurally blind to two-thirds of this axis.

Concretely: if you add `raw`/`cooked` to `QUALIFIER_SETS`, you inherit the 2.1%
coverage measured in §1.8. The fix is §3.1, and it is mine, but the identity
layer has to consume `state` rather than infer it.

Second challenge: **`food.precedence` is a preparation bias.** Foundation is
42.3% raw against 2.9% cooked. Whatever you do to precedence — and `FAILURES.md`
case 3 says you will — raising Foundation raises raw. If identity gets a
precedence rework, `prep` must be a term in it, or the identity fix silently
buys a preparation regression.

Third: `_candidates` pools three query strings and ranks by the best score any
achieved. If you add more query strings, add the state-qualified one from §3.3
in the same pass rather than separately.

### To Agent 3 (portions) — `portion_history` pools masses across states

```sql
SELECT c.grams FROM log_component c JOIN log_entry e ON e.id = c.entry_id
 WHERE e.user_id = p_user AND e.status='confirmed' AND c.fdc_id = p_fdc
   AND c.grams_source IN ('scale','stated','package') AND e.source <> 'repeat'
```

Keyed on `fdc_id` alone. A stated 100 g of dry pasta and a weighed 250 g of the
same food cooked are the same food row and become one prior. The median of
those two is a number describing no meal that was ever eaten.

Invariant 7 exists to stop estimates laundering themselves into fact. This is
the same failure with a different laundry: a *measurement* on one basis becomes
evidence about a different basis. **`portion_history` should filter or partition
on `state` once §3.1 stores it.** That is a one-line change to the SQL function
and it is yours to make, not mine.

Related: `db.companions` (`db.py:2019`) takes `percentile_cont(0.5) … ORDER BY
dc.yield_factor` — a *median yield factor* across dishes. Blending yield factors
across preparation states produces a number that is correct for neither. It is
harmless today because every value is 1.0; it stops being harmless the moment
§3.4 lands.

Also: `sigma_for` has no state term, and it should not get one. A wrong state is
not a wide mass — see §3.7. If Agent 3 is tempted to widen sigma to express
preparation doubt, that misattributes a 180% systematic error to a 35% random
one, and it corrupts `day_energy_sigma`, which has a test asserting quadrature.

### To Agent 7 (confidence) — see §3.7

I supply the signal (`state`, row `prep`, whitelist membership); you own the
arithmetic and the presentation. My one request: keep it a separate channel from
`grams_sigma`, and keep the `unmarked` penalty small enough that it does not
attach a caveat to 69% of components.

### To whoever owns the audit and `/why`

Two checks in §3.8, both SQL, both zero-cost, both currently impossible for want
of one column.

---

## 6. What I would defer

- **A general raw↔cooked transformation.** The dry-matter derivation is sound to
  within 6% for boiling and roasting and 14–18% off for frying, rendering and
  peeling. Preferring a cooked row is strictly better and available for every
  food that matters. Build §3.5 step 2 only after the eval set shows step 1
  failing on real foods.

- **Loading FDC yield or retention factors.** Not in the bulk CSV this project
  loads, not in the schema, and the derivation in §3.5 covers the cases where a
  cooked row is missing. Revisit only if a release ships them in a form the
  loader can read.

- **Cooking-method granularity.** `fried` vs `boiled` vs `roasted` matters
  (egg: 196 / 155 / 143), but a three-way `raw | cooked | unmarked` classifier
  captures most of the loss and the extra resolution costs a taxonomy nobody
  maintains. Collapse to three now.

- **Backfilling `dish_component.state`.** Every value is `as_logged` and there
  is no per-dish parse to recover it from. New dishes will carry state from
  §3.1; old ones stay honest at `as_logged`, which correctly says "this was
  never recorded".

- **Retroactively re-scoring the Pastel de Choclo mince.** Invariant 2. The
  snapshot stands. The right action is to correct the alias so the next one is
  right, which §3.4 provides.

- **A `/state` correction command.** `/nova` is already scoped for a comparable
  purpose and `/fix` already re-resolves components. If the resolver is right by
  default a state command is machinery for a case that stops arising; if it is
  wrong by default, a command is not the fix. Decide after the eval set.

- **Anything that surfaces preparation state to the user unprompted.** It is a
  resolution detail, not a diagnosis. The bar in `CLAUDE.md` — the morning note,
  supplement reminders, the Sunday report — is not met by "your rice may have
  been logged on a dry basis". `/audit` and the confirm card are where this
  belongs.
