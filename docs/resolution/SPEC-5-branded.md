# SPEC-5 — Branded and user-supplied composition

Agent 5. Cases 3 (*a user's own food lost to a generic row*) and 6 (*pickle
juice resolved to pickle relish*).

Everything below was measured against the live database on 25 Aug 2026, user 2,
283 confirmed components. Read-only throughout; nothing was written.

---

## 0. The scoping note, verified

**The USDA Branded dataset is not loaded and `food.precedence` reserves a rank
for it anyway.**

```
     data_type     | count |   min   |   max
-------------------+-------+---------+---------
 sr_legacy_food    |  7793 |  167512 |  175304
 survey_fndds_food |  5432 | 2705383 | 2710814
 foundation_food   |   411 |  321358 | 2727589
 user_product      |    14 |    -565 |      -3
```

`sql/014_user_foods.sql` still generates `precedence` with a
`WHEN 'branded_food' THEN 4` arm that can never fire. Harmless today, and a
trap the moment anyone loads Branded expecting rank 4 to mean something — see
§5, challenge to Agent 1.

14 `user_product` rows exist; 13 are live, `-249 Blondie` is retired. 35 of 283
confirmed components (12.4%) point at a user product, spread over 9 distinct
foods.

---

## 1. Source inventory

Four sources can supply a nutrient profile. Only one of them is a laboratory
assay.

| # | source | rank | rows | how it gets in | marker |
|---|---|---:|---:|---|---|
| 1 | user product — **ingredient sum** | 0 | 7 | `/food` → `_consume_food_recipe` → `total_nutrients` over USDA rows | `category LIKE 'made from:%'` |
| 2 | user product — **transcribed panel** | 0 | 4 | `/food` → photo → `FOOD_LABEL_TOOL` → `llm.per_100g` | `category = 'transcribed from the printed panel'` |
| 3 | user product — **OpenFoodFacts** | 0 | 2 | `/food` → barcode or `off.search` → `off._panel` | `category LIKE 'OpenFoodFacts%'` |
| 4 | USDA Foundation / SR Legacy / FNDDS | 1 / 2 / 3 | 13,636 | `scripts/load_usda.py` | `data_type` |

A fifth exists de facto: `-74 Nesquik cereal`, category
`"Nestlé Nesquik cereal, printed panel, per 100 g. 30 g serving."`, which
matches none of the three formats above and was created outside the three
`create_user_food` call sites (`bot.py:2402`, `2642`, `2747`). Whatever made it,
route detection by string prefix already has a row it cannot classify.

### 1.1 The three routes are not distinguishable after the fact

`food` carries `data_type`, `description`, `category`, `brand`, `gtin_upc`,
`owner_user_id`, `precedence`, `yield_grams`, `retired_at`, `retired_reason`.
`food_nutrient` carries `(fdc_id, nutrient_id, amount)` and nothing else.

`db.create_user_food(user_id, name, per_100g, *, category, note)` writes
`category or note` into `food.category` — one free-text column doing duty as
both a taxonomy field and a provenance log. Live contents:

```
   -3 | Pickle juice          | made from: 98 g Water, 1.5 g Garlic, ...
 -296 | Nestle Corn Flakes    | transcribed from the printed panel
 -360 | Monster Munch         | OpenFoodFacts 5000328206738 · Monster Munch
  -74 | Nesquik cereal        | Nestlé Nesquik cereal, printed panel, per 100 g. 30 g serving.
```

Consequences, all live:

- **`brand` is NULL on every one of the 14.** The OFF brand is inside the note
  string; the label route never captures a brand at all.
- **`gtin_upc` is NULL on every one of the 14**, including the two that came in
  by barcode. `off.py`'s docstring claims "every product keeps the barcode it
  came from" — it does not. The barcode survives only as digits inside prose,
  recoverable by regex and by nothing else. There is therefore no way to ask
  "has this barcode changed on OFF since I saved it", which is §1.4.
- **There is no `created_at` on `food`.** A user product has no timestamp of any
  kind. Staleness is not merely un-checked, it is unmeasurable.
- **No unit is stored.** `food_nutrient.amount` is a bare number whose unit is
  implied by `nutrient.unit`. A transcription, an arithmetic sum and a
  crowd-sourced figure are byte-identical at the row level.

### 1.2 Precedence is a tie-break, and the case-3 patch does not close it

`db.search_foods` orders by `(similarity + ts_rank) DESC`, then `has_energy
DESC`, then `precedence ASC`. Precedence is third. That is deliberate and, as
the comment there argues at length, correct — precedence-first regresses case 2.

`llm.parse.resolve_items` adds the case-3 patch: a candidate with
`precedence == 0` **and** `sim >= AUTO_MATCH_SIMILARITY (0.62)` wins outright.
The guarantee it provides is real but narrower than the failure it was written
for. Measured against the live tables, the short natural names for the user's
own foods:

| typed | own product | sim | best generic | sim |
|---|---|---:|---|---:|
| `pickle juice` | Pickle juice | **1.000** | Relish, pickle | 0.350 |
| `blondie` | Blondie | **1.000** | — | — |
| `monster munch` | Monster Munch | **1.000** | Energy drink (Monster) | 0.308 |
| `corn flakes` | Nestle Corn Flakes | **0.632** | Cereal, corn flakes, plain | 0.500 |
| `coconut milk` | Vemondo Coconut Milk | **0.619** ✗ | **Coconut milk** (FNDDS) | **1.000** |
| `sparkling water` | Muszynisnka Sparkling Water | **0.571** ✗ | Wine, sparkling | 0.550 |
| `nesquik` | Nesquik cereal | **0.533** ✗ | Chocolate milk, Nesquik | 0.211 |
| `devolay chicken` | Devolay chicken (breaded…) | **0.516** ✗ | Fat, chicken | 0.400 |
| `devolay` | Devolay chicken (breaded…) | **0.258** ✗ | — | — |

Five of the nine user products that have actually been logged are unreachable
by their own short name through the precedence-0 rule. `coconut milk` misses the
threshold by 0.001 and loses to an FNDDS row scoring 1.000 — the same shape as
case 3, in the same database, today.

The mechanism is an inversion: a user product's description is
*brand + product* ("Vemondo Coconut Milk"), which is **longer** than the phrase
a person types, so trigram similarity is penalised in exactly the place where
the user's authority is highest. The USDA row, being a bare category name, wins
the string comparison by being less specific.

Aliases mask this. `pickle juice → -3`, `coconut milk`-ish → `-464` etc. exist,
so the failure does not fire on the well-worn path. But an alias is a cache of a
past resolution, not a rule: a new phrasing ("that coconut drink", "coconut milk
carton") re-enters search and gets the generic. The existing regression test
`test_your_own_food_beats_a_generic_row` queries the user food by its **verbatim
full description** (sim 1.0), so it cannot see this.

### 1.3 Nutrient coverage by route — the reliability is inverted

```
 fdc_id | food                        | route          | nutrients | minerals | vitamins
--------+-----------------------------+----------------+----------:+---------:+---------:
   -527 | Devolay chicken             | ingredient_sum |       141 |       10 |       13
   -409 | Ginger-turmeric-lemon juice | ingredient_sum |       125 |       10 |       13
   -289 | Blondie                     | ingredient_sum |       118 |       10 |       13
   -108 | Mixed meat                  | ingredient_sum |        89 |       10 |       11
     -3 | Pickle juice                | ingredient_sum |        84 |       10 |       12
    -73 | Olimp Whey Protein Powder   | ingredient_sum |        71 |        9 |       13
    -74 | Nesquik cereal              | unknown        |        20 |        3 |        7
   -565 | Lubella Cosmic Cereal       | label_photo    |        15 |        4 |        4
   -296 | Nestle Corn Flakes          | label_photo    |        13 |        1 |        5
   -464 | Vemondo Coconut Milk        | label_photo    |         8 |        1 |        0
   -465 | Muszynisnka Sparkling Water | label_photo    |         4 |        4 |        0
   -360 | Monster Munch               | off            |         8 |        1 |        0
   -466 | Kaktus lody                 | off            |         8 |        1 |        0
```

**Panels and OFF are macros-only.** 8 nutrients is energy + P/C/F + fibre +
sugar + saturated fat + sodium. `off.FIELDS` maps 19 keys and 2 of them
populated on the products actually saved. For micronutrients, routes 2 and 3
supply essentially nothing, and that is a property of nutrition labelling law,
not of this code — a European panel is legally required to carry eight lines.

**Composites are micronutrient-rich and that richness is partly manufactured.**
See §2.1.

---

## 2. Defects, ranked by materiality

### D1 — the ingredient-sum path launders missing data into a definite figure (invariant 6, at one remove)

`_consume_food_recipe` calls `total_nutrients(components, profiles)`, which
skips a nutrient absent from a component's profile — correct, per invariant 6.
It then divides by yield and hands the result to `create_user_food`, which
writes it as `food_nutrient` rows. **At that moment the skip becomes a zero.**
Downstream, `day_nutrient_coverage` computes coverage from *presence of a
`food_nutrient` row for the fdc_id*, so the composite reports **100% coverage**
on every nutrient any one of its ingredients happened to carry.

Quantified, Blondie `-289` (8 ingredients, 1,586 g, canonical ids folded):

- 117 nutrients present; 54 of them (46%) are summed over less than the full
  ingredient mass.
- **Pantothenic acid: 46% of the mass carries a figure.** 857 g of the 1,586 g
  is FNDDS (brown sugar, chocolate chips, eggs, yolk) and **0 of 5,432 FNDDS
  rows in this database carry nutrient 1170**. The stored B5 figure is the
  flour-and-butter contribution presented as the whole tray's, and every slice
  ever logged inherits it at claimed full coverage.
- Choline: 99%. Vitamin A (IU, 1104): 46%.

Devolay `-527`: vitamin D over 43% of mass, choline over 48%, pantothenic acid
over 82%.

This is the phantom-deficiency bug the codebase rejects everywhere else,
arriving through composition. It is worse than the plain version because
coverage — the one instrument that would show it — reports 100%.

Materiality: **highest.** It affects the route the user trusts most, it is
invisible, it is permanent, and it grows with recipe complexity.

### D2 — the panel and OFF routes have no plausibility gate at all

`_consume_food_recipe` refuses to save when

- macronutrients exceed 100 g per 100 g (the case-7 fix), or
- `energy_cross_check` fails, or 1008 is absent (the case-2 fix).

`cb_food_panel_save` (bot.py:2740) and `cb_off_save` (bot.py:2636) call
`db.create_user_food` **directly**, with neither check. The two routes whose
numbers came from a model reading a photograph or from a database anyone may
edit are the two with no arithmetic guard, and the route that is pure
arithmetic over USDA rows has both.

Live consequence: `-565 Lubella Cosmic Cereal` stores 376 kcal against macros
implying 348 — a 7.5% Atwater gap, under `ENERGY_TOLERANCE` (0.12) but never
actually tested. Nothing establishes that the saved panels are self-consistent
because nothing ever asked.

### D3 — the transcribed `unit` is required by the tool schema and then thrown away

`FOOD_LABEL_TOOL` requires `{"nutrient_id", "amount", "unit", "as_printed"}`.
`llm.per_100g` reads `nutrient_id` and `amount` and **never touches `unit`**.
The prompt tells the model the expected unit via `_nutrient_menu()` ("Sodium
(mg)") and then trusts it to have converted.

Contrast `core/supplements.py`, which exists solely to do this properly:
`convert(nutrient_id, amount, unit, target_unit)` returns `(None, reason)`
rather than guessing, and refuses vitamin A IU as ambiguous while accepting
vitamin D IU as exact. CLAUDE.md's supplements section names unit conversion in
Python as one of three enforcement legs. **Food labels get one leg of the
three:** the id allowlist. They get neither Python-side conversion nor the
refusal.

Live evidence: `-464 Vemondo Coconut Milk`, route `label_photo`, stores
**sodium 0.080 mg per 100 g**. A packaged coconut drink is 40–50 mg/100 g. The
panel almost certainly printed `0.08 g` (of salt or of sodium) and 0.08 was
banked as milligrams — a 1,000× understatement, saved silently, on a food logged
5 times.

European panels print salt in grams and sodium, where given at all, in grams.
`_nutrient_menu()` asks for mg. This is not an edge case; it is the default
shape of the input.

### D4 — `off.py` prefers the field OpenFoodFacts is worst at, and never cross-checks it

`_panel()` reads `sodium_100g × 1000` and falls back to `salt_100g / 2.5 × 1000`
**only when sodium is absent**. When both are present and disagree, the sodium
field wins unexamined.

Fetched live from OFF, 25 Aug 2026:

```
5900130039640  Lody kaktus (Nestlé)   sodium_100g 1e-05   salt_100g 0.01
5000328206738  Monster Munch          sodium_100g 0.692   salt_100g 1.73
```

Monster Munch is internally consistent (1.73 / 2.5 = 0.692) and stored correctly
at 692 mg. Kaktus lody is not: 0.01 g salt implies 4 mg sodium, OFF's own sodium
field says 0.00001 g, and nutrai stored **0.010 mg** — off by 400× from OFF's own
salt line and by ~5,000× from reality. Both figures were on the page. One line
of arithmetic would have caught it. `-466` is live and unretired.

### D5 — duplicate-entry detection is exact-string and within-page only

`render.off_choices_card` flags same-product/different-kcal pairs by grouping on
`lower(name)|lower(brand)` and flagging a >5% energy gap. The intent is right
and the implementation catches almost nothing: OFF duplicates differ precisely
in the name string ("Monster Munch" vs "Monster Munch Pickled Onion 40g"), which
is why they are duplicates rather than one row. It also only compares the ≤5 hits
on one page, and never fires on the barcode path, which returns a single product
with no sibling to compare against.

`off.search` returns OFF's relevance order untouched and `completeness` is shown
but never used as a filter or a sort key. A 0.3-complete entry can be hit 1.

The 556-vs-492 pair recorded in the investigation brief is exactly this shape,
and the current detector would only have caught it if the two entries carried
byte-identical names.

### D6 — a redefinition mutates history's explanation

`create_user_food` looks up an existing row by
`owner_user_id = $1 AND lower(description) = lower($2)`, then
`DELETE FROM food_nutrient WHERE fdc_id = $1` and reinserts. The cards say so
out loud: *"Correct it any time by defining it again — same name, same row."*

`log_nutrient` is a snapshot, so invariant 2 holds and past totals are safe.
But three things read `food_nutrient` **as it is now** for a day that is past:

- `day_nutrient_coverage` — a past day's coverage figures change,
- `jobs/audit.py` `no_energy_row` — joins `food_nutrient` for old components,
- `/why` and the confirm-card `matched` map — join `food.description`.

So a correction silently rewrites what the system says about days it does not
rewrite the totals of. This is the argument CLAUDE.md already accepted for NOVA
("the group is snapshotted onto `log_component`, not read from `food`"), applied
to the nutrient source rather than to a classification. `log_component` snapshots
`grams_source`, `yield_factor` and `grams_sigma`; it snapshots nothing about
where the nutrients came from.

The lookup also ignores `retired_at`. Redefining a food under a retired name
updates the retired row, and the new definition inherits `retired_at` — invisible
to `user_foods`, `search_foods` and `resolve_alias` — while `upsert_alias`
happily points the name at it. The user sees "saved" and the food does not
exist. `-249`/`-289` show a same-name redefinition has already occurred once.

### D7 — no user-facing retirement path

CLAUDE.md documents `food.retired_at` as the way to withdraw a wrong panel.
There is no `/retire` command, no `db.retire_user_food`, and the only row that
carries a `retired_at` had it set by hand in `sql/027_retired_foods.sql`.
`db.delete_user_food` exists, is unwired, and refuses once anything is logged —
which is the only case that matters. The documented remedy for D3/D4 is
currently a psql session.

### D8 — nothing tells the user which source a number came from

`nutrai/core/render.py` and `nutrai/jobs/audit.py` contain **zero** references to
`data_type`, `precedence`, `user_product` or `owner_user_id`. The confirm card
appends `→ <description>` only when the label is not a substring of it, and never
says whether that description is a Foundation assay, a national survey average,
a photograph of a packet, or a stranger's edit on a website. `/why` names the
entry and the component and stops there.

The audit's `no_energy_row` finding says *"reports no energy in USDA"* for any
component whose food lacks 1008/2047/2048 — which for `-465 Muszynisnka
Sparkling Water` (4 nutrients, no energy, no macros, logged twice) is both a
false positive and a false statement about the source.

### D9 — staleness is unmeasurable

No `created_at` on `food`, no stored barcode, no stored fetch date. OFF's own
`last_modified_t` for the two saved products is 2026-07-01 and 2026-03-27; the
system holds no date to compare against and no key to re-fetch by. There is no
query that can answer "which of my products are old" or "has the source changed".

---

## 3. Precedence rules, stated testably

Replacing "precedence 0 wins if `sim >= 0.62`" with a rule that distinguishes
*which food this is* from *how good the numbers are*. These are two questions and
one number is currently answering both.

**R1 — identity beats authority.** Source rank never decides *which food this
is*; it decides only *whose figures to use for the food already identified*. A
user product must not win because it is a user product; it wins because it is
the product. Testable: a user product named `Vemondo Coconut Milk` must not be
returned for the query `chicken breast` at any similarity.

**R2 — an exact product beats a generic row for a query that names the product.**
A query is *product-naming* when it contains the brand token, or when the user
product's description contains every content word of the query. Testable
against the live table:

- `coconut milk` → `-464 Vemondo Coconut Milk` **must** outrank FNDDS
  `Coconut milk` (2705413), which currently scores 1.000 against the user's
  0.619.
- `sparkling water` → `-465` must outrank `Wine, sparkling` (2710687).
- `devolay`, `devolay chicken`, `nesquik` must each reach their own product.
- `chicken breast` must **not** reach `-527 Devolay chicken (breaded stuffed
  chicken)` ahead of `Chicken, breast, meat only` — R1's guard, and the reason
  R2 is stated as containment rather than as "precedence 0 always wins".

The mechanism is a matter for Agent 2; the *requirement* is that
brand-plus-product descriptions stop being penalised for carrying the brand.
Trigram similarity over the full description cannot satisfy R2 and should not be
patched to try — score the query against the description **and** against the
description with brand tokens stripped, take the better, exactly as
`_candidates` already does for the model's `search_terms` versus the user's
words.

**R3 — order among the three user-food routes, when two describe the same
product.** `transcribed_panel` > `openfoodfacts` > `ingredient_sum` **for the
nutrients each actually reports.** A panel you photographed is checkable against
the packet in your hand at the moment it is transcribed; OFF is a lookup by
someone else; an ingredient sum is a model's resolution of your words onto USDA
rows and is therefore the most inferential of the three, notwithstanding that it
returns the most numbers. Testable: two user products with the same
`gtin_upc`, one from each route, must resolve to the panel row.

**R4 — a user-supplied panel is authoritative for the nutrients it reports and
silent for the rest; USDA is never merged in to fill the gaps.** No blending,
ever, across rows. A composite is the one legitimate blend and it must carry its
own coverage (§4, P4). Testable: logging 100 g of `-464` yields no vitamin figure
of any kind, not a coconut-milk-shaped one borrowed from FNDDS 2705413.

Rationale, against the temptation to fill: CLAUDE.md's supplements section draws
the line at *transcription vs estimation*. Filling a label's missing zinc from a
USDA row for a nominally similar food is neither — it is an estimate wearing a
measurement's clothes, and it is precisely the failure invariant 6 exists to
prevent. **The same line is currently drawn for foods in the prompt
(`FOOD_LABEL_SYSTEM` rules 1, 5, 6, 7, 8) and not in the code** (D2, D3). Close
that, and do not open a new hole beside it.

**R5 — USDA overrides a user panel in exactly one case: never automatically.**
A wrong transcription is corrected by re-photographing or by retiring the row
(D7), both of which are human acts. There is no defensible automatic rule —
"USDA disagrees by more than X%" cannot distinguish a mis-transcribed digit from
a genuinely unusual product, which is the entire reason branded data exists.
What the system may do is **raise it**: an audit finding when a user product's
energy disagrees with the best-matching USDA row by more than 2×, or when its
Atwater cross-check fails. Flag, never overwrite.

**R6 — a route with no plausibility gate may not be saved.** Every route into
`create_user_food` runs the same two checks the ingredient path already runs:
macro sum ≤ 100 g/100 g, and `energy_cross_check` where energy and macros are
both present. Testable: a panel transcribed as 5,560 kcal/100 g is refused on
every route.

---

## 4. Provenance requirements

The test each of these must pass: *given one nutrient figure on one past day,
can the system name the source, the route, the fetch or transcription date, and
the fraction of the food's mass that figure actually covers — without consulting
anything that has changed since?*

**P1 — a `source` enum on `food`**, not a prose note. Values:
`usda_foundation`, `usda_sr_legacy`, `usda_fndds`, `user_panel`, `user_off`,
`user_recipe`. `data_type` stays as the FDC-facing column; `source` is the one
the resolver, the audit and the cards read. Prose stays in `category`/`note` for
humans. Backfill the 13 live rows from the `category` prefixes above; `-74` goes
to a nullable `unknown` rather than being guessed at.

**P2 — structured identity for the branded routes.** `food.brand` and
`food.gtin_upc` populated on every OFF and panel row (both columns already
exist and are NULL on all 14). Plus `source_ref` (the OFF URL or product id),
`source_fetched_at`, and `created_at` — the last of which `food` lacks entirely
and every other table has.

**P3 — the transcription is kept.** For `user_panel`, store the model's
`as_printed` line and the `unit` it reported alongside each amount. This is
what makes a transcription checkable a month later rather than only at the
confirm gate, and it is what makes D3 detectable retrospectively — a stored
`"Sól 0,08 g"` against a stored `0.080 mg` names the bug without a photograph.
It also gives `/food` something to show when the user asks why a figure looks
wrong.

**P4 — composites carry their own coverage.** For a `user_recipe` row, store per
nutrient the fraction of constituent mass that reported it, and have
`day_nutrient_coverage` multiply through it rather than treating a
`food_nutrient` row's existence as 100%. This is the fix for D1 and it is
structural: no plausibility heuristic can recover the information, because by
the time the composite exists the ingredient list is prose in a `category`
column. Store the constituent `(fdc_id, grams)` pairs as rows while you have
them.

**P5 — `log_component` snapshots the source.** One column, `nutrient_source`,
written at confirm time from `food.source`, the same treatment `grams_source`
gets and the same argument CLAUDE.md accepted for NOVA. Without it, D6 stands:
`/why`, the audit and coverage describe a past day using a panel that may have
been rewritten since. `log_nutrient` remains untouched.

**P6 — the cards say it.** The confirm card marks each component with its
source, always, not only when the description surprises. Four marks, since the
distinction that matters to a reader is *how sure is this*, not which USDA
release it came from: your own packet / looked up / national average /
laboratory. `/why` names the source per contributing entry. A number whose
provenance is invisible is a number that cannot be doubted at the one moment
doubting it is cheap.

---

## 5. Challenges to other layers

**To Agent 1 (dataset semantics).** Three, in order of consequence.

1. **0 of 5,432 FNDDS rows carry nutrient 1170 (pantothenic acid).** I found
   this from the composite side; it is yours. Establish the full matrix of
   *which nutrient ids each loaded dataset systematically omits* — FNDDS is
   uniformly 65 nutrients, SR Legacy averages 82.7 (range 8–138), Foundation
   averages 46.8 (range 12–159). A nutrient that no FNDDS row reports produces a
   day-level deficiency signal driven entirely by which dataset the resolver
   happened to pick, and `day_nutrient_coverage` is the only thing standing
   between that and `/improve`. My D1 is that composition destroys even that.

2. **`branded_food` is in the `precedence` generated column and not in the
   database.** Either remove the arm or document that loading Branded would put
   13,000 manufacturer self-reports at rank 4 — *below* FNDDS national averages,
   which is defensible for a generic query and indefensible for a barcode.
   My R2/R3 assume Branded stays out. If Agent 1 recommends loading it, the
   ordering in §3 needs a fifth row and I would want to revisit it.

3. **Foundation's 411 rows average fewer nutrients than FNDDS's 5,432** (46.8 vs
   65.0) while ranking above them. Precedence encodes assay quality; it says
   nothing about completeness, and the two point opposite ways here.

**To Agent 2 (ranking).** The case-3 patch in `resolve_items` is a similarity
threshold wearing a precedence rule's clothes, and §1.2 shows it failing live on
five of nine logged user products. Specifically:

- `sim >= AUTO_MATCH_SIMILARITY` on the precedence-0 branch reuses a threshold
  tuned for *is this the right generic row* to answer *is this my own product*.
  Those need different numbers, or better, different comparisons. `coconut milk`
  missing by 0.001 is not a tuning problem.
- Brand tokens in a user product's description are pure penalty under trigram
  similarity. R2 needs the query scored against the brand-stripped description
  too. `_candidates` already pools multiple queries per item; this is the
  mirror — multiple representations per candidate.
- I am **not** asking for precedence-first ordering in `search_foods`. The
  comment there is right and case 2 regresses if you do it.
- CLAUDE.md records that "ask every time" was overtaken by "a saved product wins
  on similarity and precedence". It does not, for five of nine. That claim
  should be corrected in CLAUDE.md whatever else changes.

**To whoever owns the audit.** `jobs/audit.py` has no check that reads
`data_type`, and `no_energy_row` tells the user a food "reports no energy in
USDA" when the food is one the user defined — see `-465`, a mineral water with a
legitimately absent energy figure, logged twice. Findings the audit should carry
once P1–P5 exist: a user panel failing Atwater; a user product whose energy
differs >2× from the closest USDA row (R5); an OFF row whose `sodium_100g` and
`salt_100g` disagree by >20% (D4); a composite whose worst-covered targeted
nutrient falls below ~70% (D1); a user product older than a year with no
recheck (D9).

**To whoever owns `/food`'s UX.** D7 — the retirement path documented in
CLAUDE.md does not exist as a command. D3 and D4 both produce rows the user must
be able to withdraw, and "define it again with the same name" (D6) currently
mutates history's explanation rather than superseding a row.

---

## 6. What I would defer

- **Loading USDA Branded.** It would multiply `food` by ~30×, and every ranking
  problem in §5 gets harder before it gets easier. It is also the wrong shape
  for the actual need: this user's branded foods are Polish and German
  supermarket products that FDC does not carry. Revisit after the eval
  fortnight, if at all.
- **Re-fetching OFF on a schedule.** P2 makes it *possible* (barcode +
  fetched-at). Doing it is stage 5. An unprompted "this product's figures
  changed" message would also fail CLAUDE.md's bar for unbidden messages; it
  belongs in `/audit`.
- **Backfilling P3 (`as_printed`) for the 4 existing panel rows.** The
  photographs are gone. Leave them NULL and let the column start honest —
  the same reasoning as "do not backfill the NOVA table".
- **Nutrient-level source mixing within one food.** Filling a panel's missing
  micronutrients from a USDA row is tempting and R4 forbids it. Do not build a
  merge layer "for later"; the absence is the correct answer and coverage is how
  it gets shown.
- **Any change to `AUTO_MATCH_SIMILARITY` itself.** Eval-set work, per
  CLAUDE.md. R2 must be satisfiable without moving it.
- **`-74 Nesquik cereal`'s unknown provenance.** One row, created by something
  no longer in the tree. Mark it `unknown` under P1 and move on rather than
  reverse-engineering it.
