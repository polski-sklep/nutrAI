# Reconciliation of the nine resolution specs

25 Aug 2026. Inputs: `SPEC-1` … `SPEC-9` and `golden.yaml` (7,558 lines),
plus independent verification of every load-bearing claim against the live
database. Disagreements are resolved on source semantics, reproducible
evidence and observed behaviour — not by counting agents.

This document supersedes the individual specs where they conflict. It does not
replace them: each remains the record of its own evidence.

---

## 1. The root cause

Nine agents traced nine different symptoms. They reduce to one measurable fact.

**Trigram similarity between a short query and a USDA description is dominated
by the length of the description, not by whether it names the right food.**

Among the 66 rows in this database whose description contains `salmon`, the
correlation between description length and similarity to the query `salmon` is
**r = −0.874**. For `chicken breast` across its 66 rows: **r = −0.936**.

USDA descriptions get longer *as they get more specific*.
`Fish, salmon, Atlantic, farmed, cooked, dry heat` is long precisely because it
is precise. So the ranking function systematically penalises specificity: the
more exactly a row describes what was eaten, the lower it scores.

Every traced failure is that one fact in a different costume.

| Costume | Case | Mechanism |
|---|---|---|
| Short wrong row beats long right row | `salmon` → `Salmon salad` (0.700 vs 0.167) | length |
| Model's paraphrase beats the user's own words | `cosmic cereal` → FNDDS porridge | length, via max-pooling |
| Brand+product name is longer than what a person types | `coconut milk` → generic FNDDS | length |
| One word decides the food and carries no weight | `egg whites` → whole egg; `unsalted` vs `salted` | content, not length |

The first three are one defect. The fourth is a genuinely separate one and
needs a separate mechanism.

### 1.1 What this overturns

**The cosmic cereal failure was not a threshold failure.** Agents 5 and 9 both
reported that the user's own row lost by 0.00095 against
`AUTO_MATCH_SIMILARITY`. Measured against the user's *own words*:

```
'cosmic cereal' -> Lubella Cosmic Cereal          0.619   (his own row)
                -> Wheat cereal, chocolate, cooked 0.195   (what was logged)
```

A margin of **0.42 in favour of the correct row**. It lost only because
`_candidates` pools by `max()` across the user's label and the *model's*
`search_terms`, and the model's USDA-shaped paraphrase scored 0.861 against the
wrong row. **The threshold never had to decide this.** Agents 7 and 8 are
right that pooling is the primary defect; Agents 5 and 9 misattributed it to
the gate. The 0.00095 is real and is a coincidence.

**My own earlier report to the user inherited that error** and should be read
with this correction.

### 1.2 The two validators are proved inert

- **Atwater cross-check.** Entry error decomposes to `Σ mass × (atwater − stored)`,
  residual 3.6e-15. Scale-invariant in mass: reading every gram as an ounce on
  a real 817 kcal meal yields 23,158 kcal at −1.3% delta, `ok=True`. It cannot
  catch a mass error at any tolerance. All 18 live `atwater_mismatch` findings
  are false positives; the largest true Atwater error in the corpus is 5.3 kcal.
- **Confidence figure.** Spearman rho **−0.015**, permutation p = **0.91**
  (n = 65, 20,000 resamples) against error. It correlates with mass provenance
  at r = 0.806 — information the card already prints per component.

So: one overloaded signal, and no working check on it. That is why fixing
these one at a time has never converged — every patch adjusts the same scalar,
and nothing in the system can tell whether the patch helped.

---

## 2. Adjudicated disagreements

### D1 — Is `precedence` the ranking key? **No. Retire it as a ranking concept.**

Three agents attacked it independently and from different directions:

- **Completeness (Agent 1):** Foundation ranks first and is the *thinnest*
  dataset — mean 11.30 of 22 core nutrients, against SR Legacy 19.83 and FNDDS
  21.00. 276 of 411 rows lack nutrient 1008; 58 have no energy under any id.
- **Preparation (Agent 4):** Foundation is 42.3% raw against 2.9% cooked, so
  precedence is a silent bias toward the uneaten form.
- **Inertness (Agents 1, 2):** it only breaks exact float ties, which do not
  occur. FNDDS, ranked third of four, supplies 45% of components and 57% of mass.

**Agent 5's objection is upheld:** precedence-first ordering regresses case 2
and must not be adopted. But the reason a user's own row must win is not
precedence — it is **authority**, which is a different kind of fact and needs
its own rule (§3.2). Replace the ranking use of precedence with a per-row
**completeness** column (Agent 1's proposal) used only as a tie-break.

### D2 — Tune, split, or replace the threshold? **Replace the instrument; retune nothing yet.**

Five agents converge and none asks for a new number. Sequenced:

1. **Nothing is tunable while the deciding score is discarded** (Agents 7, 9).
   `sim_user`, `sim_model`, tier and runner-up are not stored anywhere.
   This is a hard precondition, and it is also the cheapest change in the wave.
2. **The structural defects need no new evidence** — they are provably wrong
   today (§3).
3. **Threshold work happens after a fortnight of stored scores**, not before.

Agent 7's proposal to *split* the constant is upheld on evidence:
`db.resolve_alias` and `parse._resolve` compare different distributions through
one constant.

### D3 — Can arithmetic backstop mass? **No. Settled by proof, not preference.**

Agent 6's decomposition is a proof, not an opinion. Every guard on mass must
come from a portion prior, from `food_portion`, or from the user. Agent 3's
spec is amended accordingly. Atwater gets a **25 kcal absolute floor**, which
removes all 18 false positives and touches nothing real.

### D4 — `yield_factor` or a different `fdc_id`? **A different `fdc_id`, with yield as fallback.**

Agent 3 posed the question; Agent 4 answers it and the answer holds:
**prefer a correctly-stated cooked row over a derived factor.** An identity is
checkable at the confirm gate; a derived factor is checkable against nothing.
Agent 4's own validation supports the ordering — dry-matter derivation is
within 6% for boiling and roasting but 14–18% off for frying and rendering.

Agent 3's R11 stands: one factor, one multiplication, in `scale_profile`.
**Agent 6's sequencing constraint is binding:** three definitions of "the day's
mass" currently agree *only* because yield is 1.0 everywhere. They must be
unified **before** any yield factor is populated, or `v_day_mass_confidence`
and `day_nutrient_coverage` begin dividing by different denominators.

### D5 — Delete the confidence figure or fix it? **Delete the merged scalar; add identity as its own axis.**

Agents 7 and 2 agree and are not in conflict. The displayed number is deleted;
four unmerged axes replace it (identity / preparation / portion / completeness),
all SQL, no model. Agent 7's measured firing rates make the card **quieter**,
not noisier: identity-ask 5.6/week against today's 18/week low-confidence line
at precision 0.12.

**Agent 7's repeat finding is escalated.** Every repeat path passes
`confidence=None`, read as 1.0, and repeats are 34% flagged against 15%. Doubt
must travel with a dish into every repeat, or the highest-risk population
permanently has no signal.

### D6 — Golden set now, or the fortnight first? **Both. The user decides the emphasis.**

CLAUDE.md stage 3 says collect for two weeks and build nothing else. Agent 8
substituted construction for collection and delivered 76 cases today. This is
a real deviation from the documented order of work and is flagged as such
rather than absorbed. Agent 8's own recommendation is sound: run the set now
as a regression gate, **and still collect the fortnight** — spent extending and
weighting a set that exists rather than starting from nothing.

---

## 3. The reconciled design

**Identity is decided by a tuple, not a scalar.** In order:

### 3.1 Partition before you score

A named set of **partitioning qualifiers** — presence in the query and absence
in the candidate, or the reverse, **disqualifies an auto-match**:
`white/whole/yolk`, `salted/unsalted`, `raw/cooked/dry`, `drained/rinsed`,
`skinless/skin-on`, `boneless/bone-in`. This is the treatment `INVERTING_TERMS`
already receives.

**Agent 2's constraint is upheld and is the reason this is not sufficient
alone:** exclusion applied only at scoring returns `Pecans, unsalted` for
`unsalted butter`, because the right row sits at rank 8. **Attribute handling
must reach retrieval.** `limit=5` is a recall ceiling — the eventually-chosen
row is in the top 5 for only 73% of aliases and absent from the top 25 for 20%.

Cross-dataset synonymy (`unsalted` ≡ `without salt`) is the same kind of fact
as `1063 → 2000` and belongs beside `nutrient.canonical_id`, not in `parse.py`.

### 3.2 Authority is not a score

A row the user transcribed from a packet in their hand is not a candidate to be
weighed against a national average. The comparison is **own row versus the
pooled head**, never own row versus a constant. The query must also be scored
against the **brand-stripped** description — brand tokens are pure length
penalty under trigram.

### 3.3 Stop pooling by max over heterogeneous queries

Rank by the `search_terms` score with the label score used only for
*inclusion*, or length-normalise. A score from a query with fewer tokens than
the candidate description is weaker evidence, not equal evidence. This is the
single change that fixes the cosmic cereal class.

### 3.4 Record the decision

`sim_user`, `sim_model`, tier and runner-up `fdc_id` on `log_component` as a
snapshot, for the same reason `grams_source` is there; the candidate list in a
`resolution_event` table, because `replace_components` DELETEs component rows
and `/fix` would otherwise destroy the record of what it was fixing.

### 3.5 Store what is already produced

`state` is emitted by the model on 140 of 140 parse items, rendered on the card,
and absent from the INSERT. One line. Forward-only — invariant 2 is untouched.

---

## 4. Order of work

Sequencing constraints are binding, not stylistic.

**Phase 0 — record (nothing is tunable without it).**
Resolution evidence on `log_component`; `resolution_event`; `state` in
`_write_components`; `request_id`. Cheapest phase and a precondition for
Phase 3.

**Phase 1 — provably wrong today, needs no new evidence.**
Stop max-pooling (§3.3) · partitioning qualifiers reaching retrieval (§3.1) ·
authority rule (§3.2) · unit conversion on the label path
(`parse.per_100g` reads its own required field) · canonical fold in
`nutrient_attribution` and `day_energy_sigma` · Atwater 25 kcal floor ·
duplicate-`fdc_id` **pre-confirm** check · `/why calories` returning kJ ·
invert `confirm_card`'s substring rule (hides the row on 42% of components) ·
extend `UNUSABLE_ROW` to the 12 rows with neither macros nor energy.

**Phase 2 — loader, needs a reload.**
FNDDS `portion_description` (one truthy-check line, 22,046 rows) · record the
data version (one table) · **check whether FNDDS added sugars are being
dropped the same way** — nutrient 1235 has exactly one row in this database and
it is the user's own Nesquik transcription.

**Phase 3 — after a fortnight of stored scores.**
Thresholds · yield-factor population (only after the three mass definitions are
unified) · confidence axes calibrated against real labels.

---

## 5. Not doing, and why

- **pgvector / embeddings.** Agent 2: the failures are cases where the wrong
  row is *lexically nearer* and one word decides. An embedding smooths exactly
  the distinction that must be sharpened. Wrong instrument, not merely early.
- **Precedence-first ordering.** Regresses case 2 (Agent 5, upheld).
- **Backfilling history.** Invariant 2. The 1 g onion stays 1 g. What is
  repaired is *derived* state that feeds future decisions — the seven poisoned
  `food_alias.default_grams` rows.
- **Prometheus / dashboards / SLOs.** Agent 9: no fleet, no on-call, no traffic.
  `llm_call` already stores latency and cost.
- **Loading Branded.** 3.1 GB of near-duplicate label rows would swamp every
  rule above. Remove the dead `branded_food` precedence arm instead.
- **Repairing the 12 `user_product` panels in code.** Human-in-the-loop data
  repair with a packet in a cupboard. Separate task, `food.retired_at` exists.

---

## 6. Open for the user

1. **Data repairs** — this morning's cereal entry, the `unsalted butter` alias,
   the seven 1 g aliases, entry 18177's duplicated egg. Separable from all of
   the above and doable now.
2. **The fortnight** (D6) — run the golden set as a gate now and still collect,
   or hold to CLAUDE.md's stage 3 as written.
3. **Added sugars** — whether to pursue the free-versus-intrinsic distinction
   once Phase 2 establishes if it is a loader gap.
