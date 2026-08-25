# SPEC-2 — Food identity resolution

Agent 2 of nine. Scope: how a user's words become an `fdc_id`. Cases 1, 2, 3
and 6 of `FAILURES.md`.

Investigation only. Nothing under `nutrai/`, `tests/`, `sql/` or `scripts/`
was modified. Every number below was measured against the live database on
25 Aug 2026 (13,650 food rows, user 2, 132 aliases, 283 confirmed components).

---

## 1. How resolution works today

### 1.1 The path

`resolve_items` (`nutrai/llm/parse.py:356`) runs four gates per parsed item,
in order:

| gate | code | cost | writes an alias? |
|---|---|---|---|
| 0. non-food label | `is_non_food` | free | — |
| 1. alias cache | `db.resolve_alias` | free | no (bumps `hits`) |
| 2a. own-product | `precedence == 0 AND sim >= 0.62` | free | **yes** |
| 2b. auto-match | `cands[0].sim >= 0.62` | free | **yes** |
| 3. model | `DISAMBIGUATE`, Haiku 4.5, top-5 | ~$0.0008 | **yes** |

Gates 2a, 2b and 3 all call `db.upsert_alias`, unconditionally and without a
human ever confirming the *row* (the confirm button confirms the meal). Gate 3
writes an alias even when its own returned `confidence` is 0.3 — that field is
required by `DISAMBIGUATE_TOOL`, returned by the model, and **read by nothing**
(`grep -n confidence nutrai/llm/parse.py` — only `yield_factor` and `fdc_id`
are consumed at line 494).

### 1.2 The ranking function, exactly

`db.search_foods` (`nutrai/db.py:169`). Retrieval:

```
WHERE (to_tsvector('english', description) @@ plainto_tsquery('english', $1)
       OR description % $1)          -- pg_trgm default threshold 0.3
  AND (owner_user_id IS NULL OR owner_user_id = $3)
  AND retired_at IS NULL
  AND NOT UNUSABLE_ROW               -- macros present, no 1008/2047/2048
```

Order:

```
1. similarity(description, q) + ts_rank(tsvector, tsquery)   DESC
2. has_energy                                                DESC
3. precedence                                                ASC
LIMIT 5
```

Two observations that matter for everything below.

**The sort key is a sum of two incommensurable quantities.** `similarity` is a
trigram Jaccard in [0,1]; `ts_rank` is an unnormalised lexeme-density score
that in practice lands between 0.00 and 0.61 on this corpus. They are added.
But the *thresholds* — `AUTO_MATCH_SIMILARITY`, `WEAK_MATCH_SIMILARITY`, the
`own` gate — all read `sim` alone. So the row that is selected and the score
that decides whether to trust it are computed by two different functions.
Measured instance, query `unsalted butter`:

```
fdc_id  description                          sim    ts_rank  order key
789828  Butter, stick, unsalted              0.727  0.0985   0.826   (excluded: no energy)
173410  Butter, salted                       0.667  0.0000   0.667   <- chosen, auto-matched
173430  Butter, without salt                 0.333  0.0000   0.333
```

**Positions 2 and 3 of the sort are nearly dead.** They only fire on an exact
tie of a float sum. Ties do occur (identical descriptions across datasets:
`Egg, white, dried` exists as both 323793 Foundation and 172204 SR Legacy), but
across 132 aliases replayed, precedence decided the winner in a handful of
cases only. `docs/ARCHITECTURE.md` §0.3 describes precedence as "the resolver
orders by it". It does not; it breaks float ties.

### 1.3 Pooling in `_candidates`

`_candidates` (`nutrai/llm/parse.py:267`) runs `search_foods` up to three times
— on the model's `search_terms`, on the user's label, and (single-item meals
only) on the dish name — takes `limit=5` from each, pools by `fdc_id` keeping
**the best `sim` any query achieved**, re-sorts by that max, truncates to 5.

### 1.4 Exclusions and guards in force

- `NON_FOOD_LABELS` — 33 stopwords, checked before the alias cache.
- `UNUSABLE_ROW` — 48 rows of 13,650, all Foundation. Applied in
  `search_foods` **and** in `resolve_alias`.
- `INVERTING_TERMS` — 9 terms, 164 rows. Applied in gates 2a and 2b only:
  it *defers to the model*, it does not exclude. **Not applied in
  `resolve_alias`.**

---

## 2. Failure taxonomy for identity

Measured over the live alias table and the 283 confirmed components. Each
class carries a real example and the reason the wrong candidate won.

### T1 — Attribute inversion: the row asserts the opposite of what was asked

**Live, uncorrected, created 23 Aug 2026:** alias `unsalted butter` → 173410
`Butter, salted`.

```
Butter, salted        sim 0.667   717 kcal   643 mg sodium/100 g
Butter, without salt  sim 0.333   717 kcal    11 mg sodium/100 g
```

The correct row scores **half** the wrong one, because USDA spells one
attribute two ways — `unsalted` (Foundation) and `without salt` (SR Legacy) —
and trigram similarity has no synonymy. `unsalted butter` is 0.667 ≥ 0.62, so
it auto-matches at gate 2b with no model call and no candidate list ever shown.

This class is systematic, not incidental. Across the corpus:

| axis pair | rows with A | of which an exact twin with B exists |
|---|---:|---:|
| `separable lean only` / `separable lean and fat` | 673 | 560 |
| `with salt` / `without salt` | 237 | 193 |
| `bone-in` / `boneless` | 160 | 51 |
| `enriched` / `unenriched` | 77 | 32 |
| `raw` / `cooked` | 1,612 | 103 |
| `salted` / `unsalted` | 35 | 19 |
| `drained solids` / `solids and liquids` | 44 | 14 |

For the 194 `with salt` / `without salt` twin pairs, mean trigram similarity
**between the twins** is 0.902 (min 0.808) and the mean sodium difference is
**254 mg per 100 g**. That is the shape of the whole problem in one line: the
rows that string similarity is least able to separate are exactly the rows
whose nutrient difference on the contested axis is largest.

### T2 — Attribute assertion: the row asserts an attribute the query left open

`boiled potatoes` → 170519 `Potatoes, boiled, cooked in skin, **skin**, with
salt` — the potato-skin row, not the potato. `Potato, boiled, NFS` was rank 1
at sim 0.619; the model (gate 3) chose rank 3 at 0.421.

Scale of the class: **65 of 283 confirmed components (23%)** sit on a row that
asserts a preparation state (raw / cooked / fried / canned / dried / …) the
user's label never mentioned. Over aliases: 38 of 132 for thermal state, 13 for
part (white/yolk/skin/flesh), 9 for fat level, 3 for salt.

`jobs/audit.py`'s `qualifier_mismatch` check cannot see any of these. It
requires `in_label and in_desc` — both sides must name a member of the family —
so it fires only when the user *stated* the attribute and the row disagreed.
It found 1. The asymmetric case, where the row silently adds an attribute, is
the larger one and is unmonitored.

### T3 — Category drift: the row is a different food that contains the word

Live and currently auto-matchable:

```
query "avocado"      Oil, avocado   sim 0.667  884 kcal/100 g   <- would auto-match today
                     Avocado, raw   sim 0.667  160 kcal/100 g
```

Both at 0.667; the tie is broken by `has_energy` (equal) then `precedence`
(SR Legacy 2 beats FNDDS 3) — so `Oil, avocado` wins on a tie-break that was
introduced to prefer better-measured data. A 5.5× energy error decided by
dataset precedence.

Others found by replaying the 132 aliases through today's `search_foods`:
`onion` → `Bread, onion`; `corn on the cob` → `Corn oil`; `butter/oil for
eggs` → `Oil, cocoa butter`; `eggs` → `Eggnog`; `juice` → `Beet juice`;
`brownie` → `Cookie, butterscotch, brownie` (cached as `Pie, chocolate creme`).

The generator is what fails here, not the model: `Oil, avocado` reaching rank 1
means the model is never consulted.

### T4 — Pooling: the model's own paraphrase outranks the user's own product

Case 3, and it recurred **today, 25 Aug 2026**:

```
alias "cosmic cereal"        -> 2708443 Wheat cereal, chocolate flavored, cooked
alias "lubella cosmic cereal" -> -565   Lubella Cosmic Cereal   (created same day)
```

The arithmetic:

```
similarity('Lubella Cosmic Cereal', 'cosmic cereal')            = 0.61904764
AUTO_MATCH_SIMILARITY                                            = 0.62
similarity('Wheat cereal, chocolate flavored, cooked',
           'wheat cereal, chocolate flavored')                   = 0.8611111
```

The `own` guard at `parse.py:440` requires `precedence == 0 AND sim >= 0.62`.
It missed by **0.00095**. The model's paraphrase then won the pool at 0.861 and
auto-matched.

The `own` guard does not generalise, and the reason is structural: users refer
to their own products without the brand word. Of the 9 user products whose
description begins with a brand, only 3 still clear 0.62 when the brand word is
dropped:

```
Ginger-turmeric-lemon juice   0.214       Nestle Corn Flakes           0.632
Kaktus lody                   0.417       Devolay chicken (…)          0.742
Monster Munch                 0.462       Olimp Whey Protein Powder    0.760
Nesquik cereal                0.467
Muszynisnka Sparkling Water   0.571
Lubella Cosmic Cereal         0.619
Vemondo Coconut Milk          0.619
```

**Is max-score pooling defensible at all? No.** Two arguments, both measured.

*(a) The scores are not on a common scale.* Trigram similarity is
`|shared trigrams| / |union|`, so the attainable maximum depends on the query's
own length and vocabulary. The best score *any row in the entire database* can
achieve:

```
query "cereal"                            best possible 0.538  (Cereal, crunch)
query "cosmic cereal"                     best possible 0.619
query "wheat cereal, chocolate flavored"  best possible 0.861
```

A one-word query can never reach 0.62. Taking a max across queries with
different ceilings does not rank candidates; it ranks *queries*, and it always
picks whichever query most resembles a USDA description.

*(b) That query is the model's, and it is circular.* `search_terms` is the
model's belief about what the food is, formed without ever seeing the database.
Searching it retrieves the row named after that belief and scores it highly,
and the high score is then read as evidence for the belief. The same row for
the same food swings a third of the scale on phrasing alone:

```
                                              vs "Salami, Italian, pork"
"salami"                                              0.350
"italian salami"                                      0.750
"italian salami slices"                               0.577
"salami, Italian, organic, sliced"                    0.441
```

The docstring at `_candidates` uses exactly this instability to justify pooling.
It is real, but pooling treats a measurement artefact as evidence rather than
correcting for it.

### T5 — Missing entity: nothing in the database is the food

Case 6. `100 ml of pickle juice` → `Relish, pickle` (130 kcal, 35 g carb).
`/food` fixed the instance — `Pickle juice` now exists at `fdc_id -3` and wins
at 1.000 — but nothing detects the class. `WEAK_MATCH_SIMILARITY = 0.45` is the
only signal and it is measuring the wrong thing: the query `juice` (the label
the parse actually produced) returns `Beet juice` at 0.545, above the weak
threshold, and is not the food. A short query scores *higher* on a wrong row
than a long query does on the right one.

### T6 — Label hygiene: the label was never a food

Cached in the live table: `and` → `Seven and Seven` (a whisky cocktail),
`x` → `Spaghetti, protein-fortified, dry, enriched (n x 6.25)`,
`chilli,` / `jalapeños,` / `yoghurt,` / `fillets,` (trailing commas from a bad
split), `devolay chicken (breaded stuffed chicken` (unbalanced, truncated).
`is_non_food` now blocks new ones at parse time but the rows survive, and
`fillets,` → `Vegetarian fillets` is an **inverted alias that no gate re-checks**
— `resolve_alias` applies `UNUSABLE_ROW` and nothing else.

### T7 — The confirm gate cannot see the row

`render.confirm_card` prints the matched USDA description only when
`str(label).lower().strip() not in desc.lower()` (`core/render.py:196`). So the
row is shown exactly when the label and the description are *lexically
different* — and hidden when the row merely *adds* an attribute, which is T1
and T2, the largest classes.

**120 of 283 confirmed components (42%)** had their USDA row hidden from the
card by that rule. Including, precisely, case 2:

```
label "butter"  ->  Butter, stick, unsalted    (81.5 g fat, no energy)   hidden
label "avocado" ->  Oil, avocado                                         would be hidden
```

The one fact that would have caught the failure was suppressed by a rule whose
stated purpose was to show it "when that is not obvious from the name".

### T8 — Candidate recall ceiling

`limit=5` per query. Replaying each of the 132 aliases as its own query against
today's `search_foods`:

| the row eventually chosen is… | count | share |
|---|---:|---:|
| rank 1 | 75 | 57% |
| in top 5 (what the model sees) | 97 | 73% |
| in top 25 | 105 | 80% |
| not in top 25 at all | 27 | 20% |

Tier 3 cannot outperform its candidate list. In roughly a quarter of cases the
list handed to the model does not contain the answer, and the model's only
honest response — `fdc_id 0` — is discouraged by `DISAMBIGUATE_SYSTEM`
("Choosing nothing is not the safe option").

This is also why hard exclusions alone make things *worse*. Prototyped against
the live database: adding a salt-axis contradiction rule to query
`unsalted butter` correctly excludes `Butter, salted` — and then returns
`Pecans, unsalted`, because `Butter, without salt` is at rank 8 and the correct
row was never competitive. **Attribute normalisation has to happen on the
retrieval side, not only in scoring.**

---

## 3. Proposed candidate scoring

### 3.0 Shape of the change

Today: one score, `sim + ts_rank`, decides everything, and `precedence` and
`has_energy` break ties.

Proposed: **a gate, then a score, then a tie-break** — and lexical similarity
demoted to the tie-break.

```
stage A  retrieval        attribute-normalised, recall-oriented, wider than 5
stage B  hard exclusions  boolean; an excluded row is not a candidate at all
stage C  dimensions       named, bounded, summed with stated weights
stage D  decision         auto-accept / ask the model / ask the user
```

### 3.1 Stage A — retrieval with attribute normalisation

The 13,636 non-user descriptions are comma-delimited and highly regular in
*shape*: 91.9% carry at least one comma (SR Legacy 98.6%, Foundation 100%,
FNDDS 81.9%), mean 4.62 / 3.64 / 2.62 segments respectively, max 13.

They are much less regular in *vocabulary*. 38,132 tail segments (position ≥ 2)
across 5,244 distinct strings; the top 100 cover 50.2%, the top 300 66.0%, the
top 1,000 82.5%, and 2,805 are singletons.

**Measured feasibility of structured parsing.** A hand-written lexicon of ~75
segment forms covering the axes below matches:

```
36.4%  of all tail segments
55.4%  of rows carry at least one recognised attribute segment
 8.9%  of rows have their entire tail parsed
```

**Conclusion: attribute *detection* is feasible; full structured parsing is
not, and should not be attempted.** The 8.9% figure is the honest ceiling on
"parse the description into a record". The 55.4% figure is the useful one:
half the corpus can be tagged on at least one axis, and the axes that matter
are concentrated in exactly the foods that get confused.

Per-axis segment incidence over 13,636 rows:

```
thermal   5,514  40.4%     bone       670   4.9%
trim      1,450  10.6%     NFS/NS     505   3.7%
part      1,178   8.6%     liquid     461   3.4%
fat level 1,164   8.5%     enrich     234   1.7%
salt        780   5.7%     sugar      204   1.5%
                           inverting  164   1.2%
```

Retrieval changes, in order of expected value:

1. **A materialised `food_attribute(fdc_id, axis, value)` table**, populated by
   a deterministic segment matcher at load time, with synonym folding
   (`unsalted` ≡ `without salt` ≡ `no salt added`; `skimmed` ≡ `skim` ≡
   `nonfat` ≡ `fat free`). 13,636 rows, one pass, rebuilt by `load_usda.py`.
   This is what makes `Butter, without salt` reachable from `unsalted butter`.
2. **Query attribute extraction with the same matcher**, over the user's label
   and the model's `search_terms` *separately*, unioned as a set — not scored.
3. **Retrieval on identity terms, not on the whole string.** Strip recognised
   attribute words from the query; what remains is the identity term set
   (`unsalted butter` → `{butter}`; `egg whites, fried` → `{egg}`;
   `cosmic cereal` → `{cosmic, cereal}`). Require a stemmed match on at least
   the highest-IDF identity term. Prototyped, this removes `Pecans, unsalted`,
   `Almonds, unsalted` and `Cashews, unsalted` from the `unsalted butter`
   candidate set and lifts `Butter, without salt` from rank 8 into the list.
4. **Negation-aware segment reading.** A segment of the form `no X`,
   `without X`, `X free` *removes* X. Necessary: with rule 3 alone,
   `Pretzels, soft, ready-to-eat, unsalted, no butter` satisfies the identity
   gate for `unsalted butter` and outranks the right answer.
5. **Raise `limit` from 5 to ~25 for the candidate pool** and let stage B/C do
   the cutting. The current 5 is a recall ceiling (T8), not a cost control:
   candidate rows cost nothing until they enter a prompt.

### 3.2 Stage B — hard exclusions

A hard exclusion is warranted when there is **no query for which the row is the
correct answer**, given what the query said. Each below is stated with its
evidence.

| # | exclusion | evidence | verdict |
|---|---|---|---|
| B1 | **Row has macros and no energy** (`UNUSABLE_ROW`) | 48 rows, all Foundation; 46 have a same-head replacement carrying energy; the 2 that do not are `Beans, Dry, … (0% moisture)` research rows | **Generalises.** Keep. It is a *usability* predicate, query-independent, and the row can only ever understate (invariant 6). |
| B2 | **Explicit axis contradiction** — query asserts value X on axis A, row asserts Y ≠ X | 194 with-salt/without-salt twins at mean trigram 0.902 with a 254 mg sodium gap; a penalty small enough not to break neighbouring cases is an order of magnitude smaller than the lexical noise it must overcome | **Hard exclusion, not a penalty.** The whole lesson of case 2 is that "demotion only breaks ties, and relevance leads". |
| B3 | **Inverting term in the row, absent from the query** | 164 rows; already detected but only *deferred to the model*, and not checked on the alias path at all — `fillets,` → `Vegetarian fillets` is cached and live | **Promote to hard exclusion**, and apply it in `resolve_alias`. Paying Haiku to read the word "vegetarian" is a deterministic rule wearing a model's clothes. |
| B4 | **Unrequested transforming form** — row's head asserts `oil`, `juice`, `flour`, `powder`, `relish`, `dressing`, `sauce` and the query does not | `avocado`→`Oil, avocado` (884 vs 160 kcal, would auto-match today at 0.667); `corn on the cob`→`Corn oil`; `pickle juice`→`Relish, pickle` | **Hard exclusion.** A transform of a food is a different food, and the energy ratios are 3–6×, not percentages. |
| B5 | **Identity-term miss** — no stemmed identity term of the query appears in the description | removes `Pecans, unsalted` from `unsalted butter`; removes `Eggnog` from `eggs`, `Bread, onion` from `onion` | **Hard exclusion**, with negation-awareness (B4/rule 4). |
| B6 | Head-segment ("genus") mismatch | **Rejected.** Tested: rejects 30 of 132 live aliases, most of them correct — USDA heads are often category words. 2,428 distinct heads; the top 25 cover 35% and include `Beverages` (278), `Spices`, `Candies`, `Fish` (351), `Snacks`, `Fast foods`. `black pepper` → `Spices, pepper, black` and `canned tuna` → `Fish, tuna, canned` both fail it. | **Do not build.** Recorded so the next person does not try it. |

**Axes must be scoped to a food family, not global.** Found by prototyping: a
global `white/yolk/whole` axis makes `white chocolate candy` "agree" with
`white` in the egg sense. `white` is egg-part for eggs, colour for chocolate
and rice, and meaningless for bread flour. The `food_attribute` table must
therefore carry `(fdc_id, axis, value)` where the axis is assigned from the
row's own family, and the query matcher must resolve the query's axis from the
candidate under consideration — not from the query in isolation.

### 3.3 Stage C — scoring dimensions

Named, bounded, and each one traceable to a failure it prevents.

| dimension | range | source | prevents |
|---|---|---|---|
| `lexical` | 0–1 | `similarity` on the *identity terms only*, attribute words stripped from both sides | the phrasing instability in T4 (salami 0.35→0.75 on the same row) |
| `attribute_agreement` | 0–1 | matched axes / axes asserted by the query | T1 |
| `attribute_silence` | −0.3–0 | axes the row asserts that the query left open, discounted where an `NFS`/`NS as to` sibling does not exist | T2 |
| `ownership` | 0 or +0.25 | `precedence = 0` **and** the row is owned by this user | T4 |
| `dataset` | 0–0.1 | `precedence` as a real term, not a tie-break | ARCHITECTURE §0.3's stated intent |
| `coverage` | 0–0.1 | count of the 20 core nutrients the row reports | ARCHITECTURE's pinning rule ("its nulls are catastrophic") |

`ownership` replaces the `own` gate and its 0.62 cliff. **A user product must
never be gated on a raw trigram threshold** — the evidence is 0.61904764 vs
0.62, and 6 of 9 branded user rows failing once the brand word is dropped. It
is an additive term that participates in the same ranking as everything else,
so a genuinely different food (`alpro coconut milk` against a stored *Vemondo*
coconut milk at 0.481) can still lose, which is correct.

`attribute_silence` needs the NFS check to avoid a perverse incentive: FNDDS
carries 505 `NFS` / `NS as to …` rows that assert nothing. Where one exists,
silence in the query should prefer it; where it does not, every candidate
asserts something and penalising them all is noise.

**Pooling is replaced, not reweighted.** Run retrieval per query as now, but
carry `(fdc_id, which query retrieved it)` and score **once**, against the
user's label plus the union of extracted attributes — never against the model's
paraphrase. `search_terms` earns its keep as a *recall* device (it finds rows
the user's words never would) and must not be allowed to supply a *score*.
That single change removes T4 without any threshold moving.

### 3.4 Stage D — the decision, and what needs a model

| does | deterministic today | needs a model |
|---|---|---|
| detect `meatless` / `vegetarian` in a description | **yes** — it is a substring test currently costing a Haiku call | no |
| detect salted vs unsalted, raw vs cooked, white vs yolk | **yes**, once `food_attribute` exists | no |
| decide `Oil, avocado` is not `avocado` | **yes** (B4) | no |
| decide `Butter, without salt` ≡ `unsalted butter` | **yes** — synonym folding is a fixed list of ~40 pairs | no |
| decide whether `Chicken breast, roll, oven-roasted` is what "chicken breast" meant | no | **yes** — this is a judgement about a processed product, and it is currently cached as an alias with 2 hits |
| decide `pastel de choclo` is a dish, not a food | no | **yes** |
| `yield_factor` for a state mismatch | no | **yes** — keep it in tier 3 |
| decide **no row is this food** | no | **yes**, and `DISAMBIGUATE_SYSTEM` currently argues against it |

The model is doing three things a rule does better (inversion terms, attribute
contradictions, transformed forms) and one thing badly that only it can do
(refusing). Move the first three out; then fix the fourth by giving tier 3 the
hard-exclusion results as *context* ("the following candidates were excluded
because …"), so that an empty candidate list is a legible signal rather than a
prompt to pick the least-bad row.

---

## 4. Alias lifecycle

Today: 132 aliases, **1 verified, 0 pinned**, 265 total hits. An alias is
written at gates 2a/2b/3 with no human confirming the row, read forever, and
re-checked never. `upsert_alias` guards on `pinned`, which is false everywhere.
The one verified alias (`egg whites, fried`, verified 20 Aug) has
`pinned = false`, so *the single row the user corrected is not protected by the
one mechanism that exists.*

The measured case for revisiting: replaying all 132 aliases as queries against
today's `search_foods`, **56 (42%) no longer agree with what search returns**,
and only 50 (38%) would clear `AUTO_MATCH_SIMILARITY` at all. The cache is not
reproducible from the words that created it, and 62% of it rests on evidence
the deterministic path would itself refuse.

### 4.1 An alias needs a state, not a boolean

`pinned` conflates "the user chose this" with "do not overwrite". Proposed
`food_alias.trust`:

| state | set by | read by | overwritable |
|---|---|---|---|
| `provisional` | gates 2a / 2b / 3 | resolution, **with the row named on the card** | yes |
| `confirmed` | the user pressing confirm on a card that *named the row* | resolution, silently | only by the user |
| `pinned` | `/pin`, `scripts/pin_foods.py` | resolution, silently | never automatically |
| `rejected` | the user correcting a match | nothing — it is a negative constraint that excludes that `fdc_id` for that alias | — |

`rejected` is the missing one. Today a corrected match can be re-made
identically tomorrow, because nothing records that it was wrong.

### 4.2 When an alias should be trusted

Never on first use. An alias becomes `confirmed` only when the human confirm
gate showed the row and the user pressed confirm — which means **T7 must be
fixed first**: 42% of components had the row hidden, so today's confirm button
cannot carry that meaning. This is the load-bearing dependency in this section.
A trust state derived from a confirmation the user could not see is worse than
no trust state, because it launders a guess into a record.

### 4.3 When an alias should be re-checked

Cheap, deterministic, no model:

- **On write, always** — replay the alias text through stage A/B and record the
  rank the chosen row would have had. A row that is not in the top 5 for its own
  alias (20% of the current table) is a resolution that cannot be re-derived and
  should be marked for review, not silently kept.
- **On the corpus changing** — a USDA reload, a new `/food` row, or an edit to
  the attribute lexicon invalidates every `provisional` alias whose stage-B
  verdict changes. `Lubella Cosmic Cereal` being created should have
  invalidated `cosmic cereal` the same day. It did not.
- **On `hits` crossing a threshold** — `audit.py` already suggests pinning at
  5 hits (`PIN_SUGGEST_HITS`). Keep it; wire it to a `/pin` command that exists
  in the bot rather than to a CLI script that has never been run to completion.

### 4.4 When an alias must be invalidated immediately

- Stage-B hard exclusion now fires for the cached row (`fillets,` →
  `Vegetarian fillets`). `resolve_alias` currently checks `UNUSABLE_ROW` only;
  every hard exclusion belongs there, for the reason already written into
  `db.py:100` — an exclusion that does not hold on every path into the food
  table is not an exclusion.
- The row is retired (`food.retired_at`) — already handled.
- The alias text is a non-food label (`and`, `x`) — `is_non_food` blocks new
  writes but does not clean existing rows.

### 4.5 What must not happen

Alias writing must move **out of `resolve_items` and into the confirm handler.**
Today gate 3 writes an alias for a meal the user then discards. `upsert_dish`
was fixed for exactly this (`replace_components=False`, "a parse is a proposal,
and this runs before anybody has accepted it"); the alias table never got the
same fix. This is the single highest-value change in section 4 and it is three
lines.

---

## 5. Challenges to other layers

**Agent 1 (USDA semantics).** Three, and the first is a blocker for me:

1. `precedence` ranks Foundation first, and Foundation is where 48 of 48
   energy-less rows live and where the `unsalted` spelling lives while
   SR Legacy uses `without salt`. I need a ruling on whether `precedence`
   should be a *quality* ordering (Foundation's analytical panels) or a
   *usability* ordering (SR Legacy and FNDDS are complete enough to log
   against). My stage-C `dataset` term needs it to mean one thing.
2. Cross-dataset synonymy is your table, not mine. `unsalted` ≡ `without salt`
   is the same *kind* of fact as `1063 → 2000` in `nutrient.canonical_id`: a
   vocabulary difference between datasets that silently splits a concept.
   I propose it lives beside that mapping, not in `parse.py`.
3. FNDDS `NFS` / `NS as to …` rows (505 of them) are the correct answer when a
   user asserts nothing, and my `attribute_silence` dimension depends on being
   able to identify them and their non-NFS siblings. If you are building a
   dataset-semantics table, that relation belongs in it.

**Agent 7 (confidence).** Four:

1. `DISAMBIGUATE_TOOL` requires a `confidence` field, the model returns it, and
   `resolve_items` never reads it. Either consume it or drop it from the schema
   — a required field nothing reads is a claim the system does not make.
2. There is no *identity* confidence anywhere. `ParsedMeal.confidence` is the
   model's confidence in the parse; `MassEstimate.sigma` is mass uncertainty.
   The confirm card marks provenance for mass (⚖ ✎ ▤ ↺ ≈) and marks nothing at
   all for identity, which is the step `render.py:186` itself calls "the most
   error-prone step in the pipeline".
3. **`render.confirm_card`'s substring rule hides the row in 42% of confirmed
   components** (120/283), including case 2 itself. I am specifying an alias
   trust state that depends on the user having *seen* the row. Whoever owns the
   card: the rule must invert — always show the row, and suppress only on exact
   equality.
4. `llm_call` stores no request or response. The `search_terms` that produced
   every one of these matches is unrecoverable, so "why did this resolve here"
   is unanswerable after the fact. I could not reconstruct case 3's actual
   query; I had to infer it. Resolution provenance is one column.

**Agent 5 / whoever owns `WEAK_MATCH_SIMILARITY`.** It is being asked to detect
a missing entity (T5) using a score whose ceiling depends on query length. The
query `juice` scores 0.545 on `Beet juice` — above the weak threshold, wrong
food. A missing-entity signal has to be *margin*- and *attribute*-based, not a
second absolute threshold on the same broken scale.

**Agent 8 (entry-level validation).** Two components resolving to the same
`fdc_id` in one entry (case 8) and my T4 are the same defect seen twice: nothing
compares a component against the entry it sits in. If you build an entry-level
check, the user-product one is cheap — a meal containing both a user product
and a generic row for the same food is almost always the pooling failure.

---

## 6. What I would defer

- **Embeddings / pgvector.** The failures here are not semantic-similarity
  failures; two of the largest classes are cases where the wrong row is
  *lexically nearer* and the deciding difference is one word. An embedding
  would smooth exactly the distinction that has to be sharpened. ARCHITECTURE
  puts pgvector at stage 5 and that is right for the wrong reason — it is not
  merely later, it is the wrong instrument for T1 and T2.
- **Tuning `AUTO_MATCH_SIMILARITY` or `WEAK_MATCH_SIMILARITY`.** CLAUDE.md is
  right that these are eval-set work. The stronger point: at 0.62, `unsalted
  butter` → `Butter, salted` (0.667) is *above* the threshold and `Lubella
  Cosmic Cereal` (0.619) is below it. No value of one number separates those.
  The threshold is not mis-set; it is being asked to carry a decision that
  needs more than one dimension.
- **Backfilling `food_attribute` over Branded.** Not loaded, and 3.1 GB of
  near-duplicate label rows would swamp every rule above.
- **Retiring the 5 malformed aliases by hand.** Real, but one `DELETE` once the
  lifecycle rules exist; not worth a migration of its own.
- **A `/nova`-style correction verb for identity.** `/pin` covers it if wired
  into the bot; a second correction surface is the "second version of something
  that already exists" that CLAUDE.md warns about.

---

## Appendix — reproducing the measurements

All read-only. `docker compose exec -T db psql -U nutrai -d nutrai -c "…"`.

```sql
-- T1: with-salt / without-salt twins and the cost of confusing them
WITH t AS (
 SELECT f.fdc_id ai, f.description ad, g.fdc_id bi, g.description bd
   FROM food f JOIN food g
     ON btrim(regexp_replace(lower(g.description),'(^|, )without salt(,|$)','\1','g'),' ,')
      = btrim(regexp_replace(lower(f.description),'(^|, )with salt(,|$)','\1','g'),' ,')
  WHERE lower(f.description) ~ '(^|, )with salt(,|$)'
    AND lower(g.description) ~ '(^|, )without salt(,|$)')
SELECT count(*), avg(similarity(ad,bd)), min(similarity(ad,bd)) FROM t;
-- 194 | 0.902 | 0.808

-- T4: the 0.00095 that decided case 3's recurrence
SELECT similarity('Lubella Cosmic Cereal','cosmic cereal');   -- 0.61904764

-- T7: how often the confirm card hides the matched row
SELECT count(*) FILTER (WHERE position(lower(btrim(c.label)) in lower(f.description))>0),
       count(*)
  FROM log_component c JOIN food f ON f.fdc_id=c.fdc_id
  JOIN log_entry e ON e.id=c.entry_id
 WHERE e.user_id=2 AND e.status='confirmed';                  -- 120 | 283

-- section 3.1: how far descriptions parse
SELECT count(*) FILTER (WHERE description LIKE '%, %')::numeric/count(*) FROM food; -- 0.919
```

The alias replay (section 4, "56 of 132 disagree") and the attribute-lexicon
coverage figures were produced by wrapping `db.search_foods`'s SQL in a
`LATERAL` over `food_alias`; the query is long and is reproduced in full in the
investigation transcript rather than here.
