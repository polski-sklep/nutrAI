# SPEC-7 — confidence, ambiguity and abstention

Agent 7. Investigation and specification only; no code in `nutrai/`, `tests/`,
`sql/` or `scripts/` was changed.

Every number below was measured against the live database on 25 Aug 2026:
user 2, **118 confirmed entries, 283 components, 96 distinct foods, 132
aliases, 10 days of logging** (16–25 Aug), plus 39 discarded and 3 pending
entries. Queries are reproducible; each is stated inline.

**The headline.** The confidence figure on the confirm card does not predict
error (Spearman rho = **−0.015**, permutation p = **0.91**, n = 65). It is
almost entirely a restatement of something the card already prints five lines
higher (R² = 0.65 against the fraction of masses that were stated or weighed),
and it is absent from the 45% of confirmed entries that carry the *highest*
error rate. Everything in this spec follows from that.

---

## 1. What confidence means today

### 1.1 Three quantities, one number, no combination

| # | quantity | produced by | stored | shown | drives |
|---|---|---|---|---|---|
| 1 | model parse confidence | `PARSE_SYSTEM` rule 6 → `ParsedMeal.confidence` | `log_entry.confidence` | `🎯 confidence N%` in `render.confirm_card` | `CONFIDENCE_FLOOR` 0.60, `CONFIDENCE_ESCALATE` 0.45 |
| 2 | candidate similarity | `db.search_foods` → `cands[0]["sim"]` | **nowhere** | only the *labels* of weak matches | `AUTO_MATCH_SIMILARITY` 0.62, `WEAK_MATCH_SIMILARITY` 0.45 |
| 3 | mass sigma | `core/estimate.sigma_for` | `log_component.grams_sigma` | per-component range when σ/g > 8% | `db.day_energy_sigma` (quadrature) |

They are never combined. Nothing in the tree reads two of them together. The
single percentage on the card is **(1) alone**, and (2) — the score that
decides which USDA row you are about to eat the nutrients of — is discarded
the moment resolution finishes. Only `parse->'_weak'` survives, and it holds
labels, not scores.

### 1.2 Quantity (1) is not an independent judgement

```sql
-- overall_confidence vs the mean of its own per-item confidences
corr = 0.988   (n = 65 entries with a parse)
-- overall_confidence vs fraction of masses from scale/stated/package
corr = 0.806,  R² = 0.650,  conf ≈ 0.539 + 0.309 × frac_hard
```

| fraction of masses hard | entries | mean `overall_confidence` |
|---|---:|---:|
| 0.0 | 32 | 0.533 |
| 0.3 | 5 | 0.680 |
| 0.5 | 3 | 0.667 |
| 0.7 | 4 | 0.788 |
| 1.0 | 20 | 0.839 |

So `overall_confidence` is (a) the arithmetic mean of the item confidences,
and (b) two-thirds explained by a fact the database already holds for free and
the card already prints, per component, as ⚖ ✎ ▤ ↺ ≈. **It is a mass-provenance
proxy wearing the name of a global judgement.** The user is shown the same
information twice — once precisely, once aggregated and degraded.

### 1.3 The correlation test

Error labels available: the audit's per-entry checks, plus the duplicate-`fdc_id`
condition FAILURES case 8 says nothing checks (it exists once in the log).
**28 of 118 confirmed entries carry at least one.**

Over the 65 entries that have a confidence at all:

```
Spearman rho = -0.015    permutation p = 0.912  (20,000 resamples)
flagged   n=10  mean 0.640  median 0.625
unflagged n=55  mean 0.669  median 0.650
difference +0.029 on a pooled sd of 0.170   →  Cohen d = +0.17
```

Flag rate by confidence band is not monotone and not even ordered:

| band | n | flagged | rate |
|---|---:|---:|---:|
| 0.30–0.35 | 2 | 2 | 100% |
| 0.40–0.45 | 4 | 0 | 0% |
| 0.50–0.60 | 26 | 3 | 11.5% |
| 0.65–0.70 | 8 | 1 | 12.5% |
| 0.75 | 5 | 1 | 20.0% |
| 0.80–0.88 | 9 | 2 | 22.2% |
| 0.90–0.95 | 11 | 1 | 9.1% |

**The one significant relationship runs backwards.** 53 of 118 confirmed
entries are repeats and carry `confidence = NULL` — every repeat path in
`bot.py` passes `confidence=None`. The system therefore treats them as
needing no warning and no gate, i.e. as confidence 1.0. Scored that way over
all 118: **rho = +0.192, p = 0.038.** Higher assumed confidence, more error.
Directly:

| population | n | flagged | rate |
|---|---:|---:|---:|
| has a confidence (text + photo) | 65 | 10 | **15.4%** |
| `confidence IS NULL` (repeat) | 53 | 18 | **34.0%** |

The highest-risk population is exactly the one the figure does not cover.

### 1.4 `CONFIDENCE_FLOOR = 0.60` as a detector

Sweeping the threshold over the 65 entries that have a confidence:

| threshold | fires | of 65 | catches | precision | recall |
|---|---:|---:|---:|---:|---:|
| < 0.45 | 4 | 6% | 2/10 | 0.50 | 0.20 |
| < 0.55 | 16 | 25% | 2/10 | 0.12 | 0.20 |
| **< 0.60 (current)** | **26** | **40%** | **3/10** | **0.12** | **0.30** |
| < 0.70 | 35 | 54% | 6/10 | 0.17 | 0.60 |
| < 0.80 | 45 | 69% | 7/10 | 0.16 | 0.70 |

At the shipped setting the warning "low overall confidence — check the
masses" appears on **two entries in five** and is right about one in eight.
No setting in the range beats precision 0.17. This is a warning that trains
the reader to skim, which is the failure `bot.py`'s own comment about the
blondie card already names — and the measurement says it is the general case,
not an edge case.

### 1.5 The traced failures, against the confidence they carried

| FAILURES case | entry | source | confidence at the time | outcome |
|---|---:|---|---:|---|
| 1 egg whites → whole egg | 18177 | text | **0.60** | confirmed |
| 1 (photo variants) | 18176, 18178 | photo | 0.75 | discarded |
| 2 butter → no-energy row | 11229 | text | 0.60 | confirmed |
| 3 devolay → cordon bleu | 24101 | text | 0.50 | pending; **repeat 24200 confirmed with no confidence** |
| 5 one drink counted twice | 20198 | photo | **0.85** | discarded |
| 6 pickle juice → relish | 6228, 6229 | text | **0.85** | discarded |
| 7 blondie, inflated panel | 16984 / 17173 / 19279 / 21484 | text | 0.50 / 0.40 / 0.50 / 0.50 | all confirmed |
| — chicken risotto → frozen pot pie | 21482 | text | 0.60 | confirmed |

Two things to read off this table.

**The two cleanest identity failures carried the highest confidences in the
set.** Cases 5 and 6 both scored 0.85 — and the model was *right* to. It read
"pickle juice, 100 ml" perfectly and it read the drink bottle perfectly. Its
confidence is about the parse it produced, and both failures happened after
the parse was over: one in resolution, one in album handling. The number is
honest about a question nobody is asking.

**Where confidence was correctly low, it was ignored.** Every blondie logged
at 0.40–0.55 and every one was confirmed. By then the warning had appeared on
40% of entries.

Two incidental notes. `bot.py` compares `parsed.confidence < CONFIDENCE_FLOOR`,
so entry 18177 at exactly 0.60 — the modal value in the whole log — showed no
warning at all. And 0.60 is where 26 of 65 entries sit; a threshold placed on
the mode is a coin flip by construction.

### 1.6 The error labels themselves are mostly artifacts

This matters for how much weight §1.3 can bear, so it is stated plainly rather
than buried. Of the 39 audit findings in FAILURES.md:

- **`atwater_mismatch`, 18 findings, is 4 distinct dishes.** Every one is on an
  entry under 40 kcal, and the largest absolute discrepancy in the entire set
  is **6 kcal**. Eight are "Lemon lime water" (12 kcal stored, 17 implied),
  four "Ginger tea with honey and lemon", two green salads, one pickle, one
  mineral water. `ENERGY_TOLERANCE` is relative with no absolute floor, so the
  audit's largest category is rounding on lemon juice.
- **`fibre_implausible`, 9 findings, is 4 dishes** and 6 of them are "Chia
  seeds with apple juice": 8.4 g fibre against 15.8 g carbohydrate. Chia
  genuinely exceeds the 40% rule. The check's premise is false for seeds and
  bran.
- **`no_energy_row`, 3 findings, is 2 foods**, one of which is "Muszynianka
  sparkling water", which correctly reports no energy.

So the number of findings that identify a nutritionally material resolution
error is on the order of **three**. I ran the correlation against these labels
anyway because they are the only labels that exist, and I report the result as
what it is: *the stored confidence does not predict the audit's flags*. It does
not follow that confidence predicts nothing. It does follow that **this project
has no error labels**, and that is the thing to fix before any threshold is
tuned by anybody. See the challenge to Agent 8 in §5.

---

## 2. Tuning `AUTO_MATCH_SIMILARITY` honestly

CLAUDE.md says 0.62 "looks arbitrary. It is. Tune it against the eval set."
The measurement says something worse: **it is not tunable at any sample size,
because the score is computed against a string the model wrote to justify its
own choice.**

`parse._candidates` searches the model's `search_terms` alongside the user's
words and ranks by the best score any query achieved. `search_terms` is, by
the schema's own description, "a precise USDA-style phrase". Scoring a
USDA-style phrase against USDA descriptions measures the fluency of the
model's paraphrase, not the fit of the row.

Measured on the 139 items in this log, `sim(description, search_terms)` runs
far above `sim(description, label)`. The consequential rows:

| label | model's `search_terms` | chosen row | sim(label) | **sim(terms)** |
|---|---|---|---:|---:|
| `egg whites, fried` | `egg white, fried, cooked` | Egg, whole, cooked, fried | 0.44 | **0.69** |
| `brownie` | `brownie, chocolate, commercially prepared` | Pie, chocolate creme, commercially prepared | 0.02 | **0.70** |
| `chocolate brownie` | same | same | 0.24 | **0.70** |
| `Cosmic cereal` | `chocolate flavored cereal, Cosmic cereal` | Wheat cereal, chocolate flavored, cooked | 0.20 | **0.63** |
| `butter` | `butter, salted` | Butter, stick, unsalted | 0.32 | 0.57 |

**FAILURES case 1 — the worst identity failure in the record, 397 mg of
cholesterol never eaten — was auto-matched at 0.69, above the threshold, with
no model call**, because the model's paraphrase of the food it had already
misjudged matched the row it had already picked. Case 2's terms say *salted*
and the row says *unsalted*, and trigram scores that pair at 0.57. Raising the
threshold to 0.75 would kill the brownie and the egg white; it would also drop
`baked potato`→`Potatoes, red, flesh and skin, baked` (0.79 survives) but push
the auto-match rate from 57.8% to 38.8% of items, buying a model call for
every fifth component to fix a signal that is contaminated at the source.

**What the 283 components can tell you:**

- the *distributions*. Median similarity of the row actually chosen against
  the user's label is **0.50**; 44 of 121 distinct (label, row) pairs reach
  0.62; **52 of 121 fall below `WEAK_MATCH_SIMILARITY` 0.45** and were matched
  anyway — because the alias path and the disambiguation tier both bypass the
  weak check.
- that **margin-based confidence on raw trigram will not work.** Top-1 minus
  top-2 similarity across the top-5 candidate set has median **0.067**, and
  **46% of labels have a margin under 0.05** — many exactly 0.000, because
  pg_trgm produces exact ties across whole families of rows. `Raspberries` ties
  with two identical descriptions; `egg whites, fried` has `Egg, white, dried`
  at ranks 1 and 2 with the same score. Do not build a confidence axis on this.
- that **one constant governs two different distributions.** `db.resolve_alias`
  compares `similarity(alias, typed_name)` — user vocabulary against user
  vocabulary — and `parse._resolve` compares `similarity(usda_description,
  query)`. Of this user's 132 aliases, exactly **one pair clears 0.62**:
  `lemon juice/wedge (half lemon)` vs `lime juice/wedge (half lime)` at 0.67,
  **two different foods**. n = 1, so that is not a rate; it is a reason to give
  the branch its own constant and its own evidence before it fires again.

**What they cannot tell you:** whether 0.62 is better than 0.58 or 0.66.
96 distinct foods, 49 seen exactly once, 26 seen three or more times. The
effective sample is about 60 distinct resolution decisions with **zero verified
labels** — 132 aliases exist, one is verified, none are pinned. A 0.04 shift
moves roughly eight decisions and there is no ground truth to say which way.

**Therefore: do not move 0.62 or 0.45 in this wave.** Tuning is unblocked by
two things, in order: (a) score the user's words and the model's words
separately and stop taking the max; (b) build the 40-meal labelled set
ARCHITECTURE.md §8 already specifies. Until then a changed constant is a
changed number with no evidence attached, which is the failure this whole
investigation is about.

---

## 3. The proposed model

### 3.1 Four axes, deliberately not combined

A meal can be certain in one and hopeless in another. Collapsing them destroys
the information that decides what to ask.

| axis | question | error shape | persists | remedy | who can answer |
|---|---|---|---|---|---|
| **I** identity | is this the right USDA row? | biased, systematic | **forever**, via the alias | pin / correct | the user, once per food |
| **P** preparation | raw or cooked; what yield? | biased, 2–3× | per entry, and via the alias's yield | say "dry"/"cooked" | the user |
| **M** portion | how much? | random, roughly symmetric | one entry | a scale | nobody, by message |
| **C** completeness | does this row report what I am scoring? | one-sided, understates only | forever, via the row | pin to a fuller row | nobody |

The asymmetry that decides everything: **portion error is random and averages
out over a fortnight; identity error is a constant offset that never averages
out.** Measured here:

- Portion, propagated in quadrature exactly as `db.day_energy_sigma` does:
  mean daily energy sigma **±108 kcal on 1,966 kcal/day = 5.5%**, and
  concentrated — two of ten days sit at 16–17% and the rest at 2–4%.
- Identity, one substitution: "Chicken risotto", 350 g, the **largest single
  component in the entire log at 714 kcal**, resolved to `Chicken pot pie,
  frozen entree, prepared` (204 kcal/100 g, 5.1 g protein/100 g) at label
  similarity **0.18**, on a 2,145 kcal day. Nothing raised it. Confidence 0.60.

Identity is where the attention belongs, and the number currently on the card
is a portion proxy.

### 3.2 Inputs per axis — all SQL and arithmetic, no model call

Invariant 4's spirit holds: none of this calls a model, and none of it lets a
model emit a nutrient value.

**Identity doubt.** Inputs, in descending order of what the evidence supports:

1. **Resolution tier**: user's own `/food` row (precedence 0) → alias hit →
   threshold auto-match → disambiguation model → unresolved. Four different
   epistemic positions currently indistinguishable downstream.
2. **`sim_user`** — similarity of the row against the user's own words only.
3. **`sim_model` − `sim_user`** — the paraphrase gap. A large gap is the
   self-fulfilling signature of §2 and must **raise** doubt, not lower it.
   It fires on **39 of 139 items (28%)** at a gap ≥ 0.25, of which 28 would
   otherwise auto-match, and it is the shared signature of FAILURES cases 1, 2
   and the brownie and Cosmic-cereal rows.
4. **Qualifier-set disagreement** (`audit.QUALIFIER_SETS`) and
   `parse.INVERTING_TERMS`. Exact, cheap, already written, currently only run
   the next morning.
5. **Alias age and verification**: hits, `pinned`, and whether the alias was
   born of a weak match. Today an alias silences the weak-match warning that
   its own creation raised.

**Preparation doubt.** The row carries a state qualifier (`validate`'s
`STATEFUL` list) **and** the item's `state` is `unknown`; or the `yield_factor`
came from the disambiguation model rather than a curated table. 87 of 283
components sit on stateful rows; 13 items came back `state: unknown`, 7 of
them over 80 g.

**Portion doubt.** Already exists and is well-founded. One change: express it
in **kcal, not grams**. ±25 g of olive oil and ±25 g of lettuce are the same
number and not the same problem, and the card prints grams.

**Completeness.** Already exists as `coverage()`; is not on the confirm card
at all.

### 3.3 How they combine

**They do not.** Publish per-axis, or publish nothing. Concretely:

- **Delete `🎯 confidence N%` from `render.confirm_card`.** It is r = 0.81
  correlated with the provenance marks printed five lines above it and
  rho = −0.015 with error. Removing it costs no information and removes a
  number that looks like a summary of everything and summarises nothing.
- Each axis contributes **at most one line**, and only when that axis is the
  one in doubt.
- Nothing is stored as a float and displayed as a percentage until it has been
  checked against labels that exist. Four honest booleans beat one
  calibrated-looking number.

---

## 4. Thresholds, and measured firing rates

### 4.1 Materiality first, doubt second

The gate order is deliberate and is the whole friction argument: **a doubt is
worth surfacing only if resolving it could move a nutrient by an amount that
matters.** Two floors, ordinary config values:

```
ASK_ENERGY_FLOOR   = 100 kcal   # the component carries at least this
ASK_SIGMA_FLOOR    =  75 kcal   # 1σ of mass uncertainty, in kcal
```

Justification for putting energy first: the top 5% of components (14 of 283)
carry **30.6%** of all logged energy; the top 10% carry 45.7%; the top 20%
carry 66.7%. Attention allocated by energy at stake reaches most of the diet
while touching a handful of components.

### 4.2 Measured against the real 118 entries / 283 components / 10 days

| gate | comps | entries | /day | /week | energy under it |
|---|---:|---:|---:|---:|---:|
| every `estimate` mass (no gate today) | 120 | 66 | 6.6 | 46 | 58.1% |
| …AND ≥100 kcal | 52 | 38 | 3.8 | 27 | 51.7% |
| …AND σ ≥ 50 kcal | 7 | 6 | 0.6 | 4 | 15.8% |
| **…AND σ ≥ 75 kcal — proposed M-notice** | **3** | **3** | **0.3** | **2** | 8.2% |
| weak label similarity (<0.45) | 109 | 67 | 6.7 | 47 | 37.5% |
| …AND ≥100 kcal | 28 | 24 | 2.4 | 17 | 30.6% |
| **…AND first sight of the food — proposed I-ask** | **10** | **8** | **0.8** | **5.6** | — |
| first sight of a food, any size | 49 | 26 | 2.6 | 18 | 30.0% |
| stateful row AND ≥150 kcal | 11 | 11 | 1.1 | 8 | 13.4% |
| **current: `CONFIDENCE_FLOOR` < 0.60 line** | 53 | **26** | **2.6** | **18** | 29.9% |

### 4.3 What happens at each state

**Identity.**

- *Refuse to auto-match* (drop to the disambiguation tier — no user contact at
  all): qualifier-set disagreement; an `INVERTING_TERMS` hit; **or a paraphrase
  gap ≥ 0.25**. Rate: 39 items in 10 days, 28 of which currently auto-match.
  Cost: about $0.0008 each, batched per entry — **≈$0.07/month**, and 1–2 s
  only on entries not already making a disambiguation call. Zero friction.
- *Ask* — the one genuinely new interaction in this design: **first sight of a
  food, AND ≥100 kcal, AND weak `sim_user` or a qualifier disagreement.**
  **10 components, 8 entries, 5.6 questions/week.** The question is two
  buttons naming two candidate rows plus "neither — define it", answered in
  one tap, and the answer **pins the alias**.
- *Record* below that: store the doubt, show nothing.

The 10 components this would have asked about, in the real log:

```
714 kcal  Chicken risotto        sim 0.18 → Chicken pot pie, frozen entree
378 kcal  devolay chicken        sim 0.16 → Chicken or turkey cordon bleu   ← FAILURES case 3
322 kcal  ice cream (novelty)    sim 0.23 → Ice cream bar, vanilla
235 kcal  baked potato           sim 0.35 → Potatoes, red, flesh and skin, baked
213 kcal  minced beef            sim 0.22 → Beef, ground, raw
192 kcal  wheat-rye bread…       sim 0.34 → Bread, wheat
156 kcal  boiled potatoes        sim 0.42 → Potatoes, boiled, cooked in skin
144 kcal  corn on the cob        sim 0.09 → Corn, sweet, yellow, cooked, boiled
119 kcal  Hot dog sausage        sim 0.00 → Frankfurter, meat and poultry
102 kcal  pear, skin on          sim 0.29 → Pear, Anjou, green, with skin, raw
```

Note honestly: **four or five of these ten are already correct.** The baked
potato, the pear and the corn are fine. The gate's precision as an error
detector is roughly 0.4, and that is acceptable *because the gate's job is not
error detection* — it is allocating one confirmation per calorie-bearing new
food, whose answer is cached forever. A right answer confirmed costs one tap
and converts an unverified alias into a pinned one. Against 132 aliases of
which **one is verified and none are pinned**, that is the point of the
question, not a side effect.

**Preparation.** Never its own question. Where it fires it overlaps identity
almost entirely — offer the two rows that differ by the state word inside the
identity card. Where it does not overlap, `validate`'s existing "was that
weighed before or after cooking?" line is already correctly phrased and stays.

**Portion.** **Never ask a question, and this is the recommendation I most
want on the record.** In 283 components this user has taken **zero scale
readings**: 54.8% stated, 42.4% model estimate, 2.1% package, 0.7% prior.
Asking "how much was that?" asks him to answer a question he has already
answered as precisely as he intends to. What changes the number is a scale,
and no message produces one.

What fires instead is one line, on the single component that dominates the
entry's uncertainty, when its σ exceeds 75 kcal — **3 entries in 10 days** —
expressed in kcal:

```
≈ meat pierogi 340 g → 660 kcal, could be 430–890
```

The two largest are `meat pierogi` (±232 kcal) and `Basque butter cake`
(±198 kcal). Keep `grams_sigma` and the quadrature exactly as they are; they
are the one part of the current confidence machinery that is well-founded.

**Completeness.** Never a question — it is a property of the row, not the meal,
and the user cannot answer it. `UNUSABLE_ROW` already refuses the worst case
and is right. Showing coverage on the confirm card is correct and is not my
measurement; see §6.

---

## 5. Friction budget, and the argument for it

### 5.1 The ledger

| | today | proposed |
|---|---:|---:|
| unprompted push messages | 0 | **0** |
| card lines that demand a decision | 0 | ~5.6/week (identity, one tap) |
| card lines that are informational | 18/week ("low overall confidence") + provenance marks | ~2/week (portion, in kcal) + provenance marks |
| model calls added | — | ~39/10 days, ≈$0.07/month |
| card lines **deleted** | — | the 18/week low-confidence line, and `🎯 confidence N%` |

**Nothing new arrives unasked.** Every element of this design appears on the
confirm card the user is already reading, before he presses a button he was
already going to press. CLAUDE.md's bar for unprompted messages — the bar that
has already retired three message classes — is untouched, because nothing here
is a message.

**The card gets quieter, not louder.** Today a low-confidence line appears on
26 of 118 entries (2.6/day) with precision 0.12. It is replaced by ~0.8/day of
a specific question with two named answers. Total lines go down; the ones that
remain are actionable.

### 5.2 Why 5.6 questions a week is worth it

Each identity question is asked **once per food, ever**, and its answer is
pinned. 26 of 96 foods supply **67.8% of all components**. Roughly three weeks
at this rate pins the entire repeat core, after which the rate falls to the
genuinely-new-food rate.

The cost of not asking is not one wrong meal. It is that **34% of repeat
entries carry a flag against 15% of parsed ones** — because a resolution is
decided once, cached in an alias, and replayed forever with no confidence
figure attached at all. FAILURES case 3's devolay is the shape: parsed once at
0.50, discarded twice, then confirmed through a *repeat* that carried no
confidence and showed no warning.

### 5.3 The counter-argument, stated

**My new-food rate does not decay over 10 days**: 20, 16, 2, 5, 11, 9, 2, 6,
24, 1 new foods per day. If it does not decay, 5.6 questions a week does not
decay either, and this design costs six taps a week indefinitely. I cannot
rule that out with ten days of data and I am not going to pretend otherwise.

Three things bound the risk. The gate requires ≥100 kcal, so a long-tail diet
raises the rate only in proportion to foods that carry calories. `ASK_ENERGY_FLOOR`
is one config line — at 150 kcal the rate drops to about 4/week, at 200 to
about 3. And **the asks-per-week figure must be logged from day one**; if it
does not fall over a month, the gate is wrong and the evidence to say so will
exist, which is more than can be said for any threshold currently in
`config.py`.

---

## 6. Abstention

**The confirm gate is already the abstention mechanism, it works, and a second
one should not be built.**

Measured: of 160 proposed entries for this user, **39 were discarded (24%)**.
Of those 39, **27 were followed by a confirmed entry within 20 minutes** — the
user read the card, rejected it, and re-logged corrected. That is not
abandonment, that is a review loop being exercised twelve times a week.

It caught real failures the confidence number did not: the doubled drink
(case 5, confidence 0.85) and the original pickle-juice parse (case 6, 0.85)
were both **discarded**. It missed the egg white (0.60), the butter (0.60) and
every blondie (0.40–0.55) — all confirmed.

The pattern in what it caught versus what it missed is exact and is the whole
design principle here: **the gate catches what the card shows.** Pickle juice
was caught because `render.confirm_card` prints `→ Relish, pickle` under the
label. The egg white was missed because the card printed `→ Egg, whole,
cooked, fried` under `egg whites, fried` and the difference is one word deep
inside a long string that a person scanning a card at breakfast will not
isolate.

So the correct investment is **not a veto and not a confidence score**. It is
making the axis that is actually in doubt visible and, where the difference is
one word, naming that word. A refusal-to-log built on a figure with rho = −0.015
would decline correct entries at approximately the base rate and teach the user
to override it.

**One exception, and it is the only blocking rule I propose.** An unmodified
repeat currently logs with **no gate at all** (ARCHITECTURE.md §4, and it is
right to). But a repeat inherits a resolution that may never have been
confirmed. Rule: *an entry may not auto-log as an unmodified repeat while any
of its components is in the identity **ask** state.* Show the card once, get
the tap, pin the alias, and every future repeat of that dish is unblocked
forever. Given the ask gate fires on 8 entries in 10 days and most repeats are
of already-settled foods, this converts a handful of silent logs into a card,
once each.

---

## 7. Explicit challenges to other layers

### To Agent 2 (identity)

1. **Stop taking `max(sim_user, sim_model)`.** `_candidates` scores the model's
   `search_terms` — a string the model wrote to describe the row it already
   wants — against USDA descriptions. This is self-fulfilling and it produced
   **0.69** for `egg white, fried, cooked` against `Egg, whole, cooked, fried`,
   above `AUTO_MATCH_SIMILARITY`, with no model call. Do not hand me a
   similarity for a confidence axis until the two scores are separate. I will
   treat a large **gap** as doubt, not as confidence.
2. **The trigram top-1/top-2 margin is degenerate** — median 0.067, 46% under
   0.05, many exactly 0.000 from ties within a family. If your design leans on
   margin, measure the ties first.
3. **Split `AUTO_MATCH_SIMILARITY`.** `db.resolve_alias` uses it for
   alias-vs-typed-name; `parse._resolve` for description-vs-query. Different
   distributions, one constant. The single alias pair in this user's 132 that
   clears 0.62 is `lemon…(half lemon)` vs `lime…(half lime)` at 0.67 — two
   different foods.
4. **Persist the resolution evidence.** `sim_user`, `sim_model`, the tier
   (own-food / alias / threshold / model / unresolved) and the runner-up
   `fdc_id` belong on `log_component`, as a snapshot, for the same reason
   `grams_source` is there. **No threshold in this system can be tuned by
   anyone while the score that set it is discarded.** This is the single change
   I most want out of this wave.
5. `resolve_alias` bypasses the weak-match check entirely, so a warning raised
   on first sight is permanently silenced by the alias that first sight created.
   43% of committed components (52 of 121 distinct pairs) sit below
   `WEAK_MATCH_SIMILARITY` against the user's own words.

### To Agent 8 (QA / audit)

1. **`atwater_mismatch` needs an absolute floor.** All 18 findings are on
   entries under 40 kcal; the largest absolute discrepancy is 6 kcal; 15 of 18
   are lemon water, ginger tea or a green salad. A 25 kcal absolute floor
   removes all 18 and touches nothing real.
2. **`fibre_implausible` at 40% of carbohydrate is false for seeds.** 6 of 9
   findings are "Chia seeds with apple juice", where 8.4 g fibre against 15.8 g
   carbohydrate is simply what chia is.
3. **`no_energy_row` fires on sparkling water.** Exempt rows whose macros are
   all zero or absent — the check should mean "this food has calories and the
   row does not report them".
4. **Deduplicate by food, not by entry.** 39 findings collapse to about ten
   distinct foods and 18 atwater findings to four dishes. An audit that reports
   eighteen of one thing teaches the reader to skim it.
5. **Rank by materiality.** Nothing in the current output distinguishes 397 mg
   of cholesterol never eaten from 5 kcal of rounding on a pickle. If I get one
   change from you: every finding carries the nutrient delta it implies, and
   the list sorts on that.
6. **FAILURES case 8 still has no check.** Duplicate `fdc_id` within one entry
   occurs once in the current log and is three lines of SQL.
7. **Build the label set.** The correlation in §1.3 was run against labels that
   are largely artifacts because they are the only ones that exist. Without
   ARCHITECTURE.md §8's 40 verified meals, no confidence figure anywhere in
   this system can be calibrated, including mine.

### To whoever holds repeats / provenance

Every repeat path in `bot.py` passes `confidence=None`, and repeats are **34%
flagged against 15%** for parsed entries. A repeat inherits a resolution
decision without inheriting any record of how doubtful it was. Whatever
identity doubt gets stored at first parse must travel with the dish into every
repeat, or the highest-risk population permanently has no signal.

### To whoever holds `render`

Delete `🎯 confidence {confidence:.0%}` from `confirm_card`. r = 0.81 with the
provenance marks already on the card, rho = −0.015 with error.

---

## 8. What I would defer

1. **Any stored per-component confidence *number*, and any calibration curve.**
   Both need Agent 2's persistence change first, then a fortnight of data, then
   labels. Ship booleans and named doubts now; ship floats when they can be
   checked.
2. **Moving `AUTO_MATCH_SIMILARITY` or `WEAK_MATCH_SIMILARITY`.** Not tunable
   today for the reason in §2. Do not touch them in this wave. Changing them
   now would be a changed number with no evidence attached, which is the
   failure this entire investigation is about.
3. **Confidence-based blocking, beyond the one repeat rule in §6.** The confirm
   gate is the abstention mechanism and it is being exercised at 24%.
4. **`CONFIDENCE_ESCALATE` tuning.** It fires on 4 of 65 entries and there are
   **4 photo entries in the entire log**. There is no evidence about photo
   escalation in this database and there will be none until photos are used.
   Leave the constant and its comment exactly as they are.
5. **Nutrient-completeness on the confirm card.** Real and worth doing; it is
   the coverage layer's measurement, not mine, and I have not made it.
6. **A `notes`-derived or model-derived doubt signal.** Everything proposed here
   is SQL and arithmetic. Asking a model how confident it is has now been
   measured once, and the answer is rho = −0.015.

---

## Appendix — reproducing the measurements

All read-only, all against user 2, all as of 25 Aug 2026.

```sql
-- §1.2  overall_confidence is the mean of its items, and a mass-provenance proxy
WITH per AS (
  SELECT e.id, e.confidence::float8 AS conf,
         avg((it->>'confidence')::numeric)::float8 AS avg_item,
         (count(*) FILTER (WHERE it->>'grams_source'
            IN ('scale','stated','package')))::float8/count(*) AS frac_hard
    FROM log_entry e, jsonb_array_elements(e.parse->'items') it
   WHERE e.user_id=2 AND e.status='confirmed'
     AND jsonb_typeof(e.parse->'items')='array' AND jsonb_typeof(it)='object'
   GROUP BY 1,2)
SELECT corr(conf,avg_item) AS r_items, corr(conf,frac_hard) AS r_provenance,
       regr_slope(conf,frac_hard), regr_intercept(conf,frac_hard) FROM per;
-- 0.988 | 0.806 | 0.309 | 0.539

-- §1.6  every atwater finding, with its absolute size
WITH atw AS (
  SELECT e.id, e.name, round(k.amount) kcal,
         round(pr.amount*4+cb.amount*4+ft.amount*9-COALESCE(fb.amount,0)*2) atwater
    FROM log_entry e
    JOIN log_nutrient k  ON k.entry_id=e.id AND k.nutrient_id=1008
    JOIN log_nutrient pr ON pr.entry_id=e.id AND pr.nutrient_id=1003
    JOIN log_nutrient cb ON cb.entry_id=e.id AND cb.nutrient_id=1005
    JOIN log_nutrient ft ON ft.entry_id=e.id AND ft.nutrient_id=1004
    LEFT JOIN log_nutrient fb ON fb.entry_id=e.id AND fb.nutrient_id=1079
   WHERE e.user_id=2 AND e.status='confirmed' AND k.amount>0)
SELECT * FROM atw WHERE abs(atwater-kcal)>kcal*0.12 ORDER BY kcal;
-- 18 rows, all under 40 kcal, |delta| <= 6

-- §2  the paraphrase gap
WITH items AS (
  SELECT e.id eid, it->>'label' label, it->>'search_terms' terms
    FROM log_entry e, jsonb_array_elements(e.parse->'items') it
   WHERE e.user_id=2 AND e.status='confirmed'
     AND jsonb_typeof(e.parse->'items')='array' AND jsonb_typeof(it)='object')
SELECT i.label, i.terms, f.description,
       round(similarity(f.description,i.label)::numeric,2) sim_user,
       round(similarity(f.description,i.terms)::numeric,2) sim_model
  FROM items i JOIN log_component c ON c.entry_id=i.eid AND c.label=i.label
  JOIN food f ON f.fdc_id=c.fdc_id
 WHERE similarity(f.description,i.terms)-similarity(f.description,i.label) >= 0.25
 ORDER BY sim_model DESC;   -- 39 of 139 items

-- §2  the one alias pair over threshold
WITH a AS (SELECT alias, fdc_id FROM food_alias WHERE user_id=2)
SELECT x.alias, y.alias, round(similarity(x.alias,y.alias)::numeric,2), x.fdc_id=y.fdc_id
  FROM a x JOIN a y ON x.alias<y.alias WHERE similarity(x.alias,y.alias)>0.62;
-- lemon juice/wedge (half lemon) | lime juice/wedge (half lime) | 0.67 | f

-- §6  the confirm gate as abstention
SELECT count(*) discarded,
       count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM log_entry e2 WHERE e2.user_id=d.user_id AND e2.status='confirmed'
           AND e2.created_at BETWEEN d.created_at AND d.created_at + interval '20 min'))
       AS followed_by_confirm
  FROM log_entry d WHERE d.user_id=2 AND d.status='discarded';   -- 39 | 27
```

The Spearman correlation, its 20,000-resample permutation p-value, the gate
firing rates and the per-day quadrature sigma were computed in Python over a
CSV export of the 283 components; the export query is the `comp.sql` shape
given in §4.2's table headings (`log_component` joined to `food`, `log_entry`
and `food_nutrient` for per-component kcal). Sample sizes are stated beside
every figure and none of them is large.
