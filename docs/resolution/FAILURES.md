# Traced resolution failures

Every case below was found in production use, traced to a root cause, and
fixed individually. They are recorded together because the pattern across them
matters more than any one of them: each was a *plausible* answer that no check
rejected, and several were cached permanently on first occurrence.

Measured baseline, all history (283 confirmed components, 96 distinct foods,
118 entries, user 2):

| audit finding | count |
|---|---:|
| `atwater_mismatch` — energy disagrees with macros | 18 |
| `fibre_implausible` — fibre vs carbohydrate ratio | 9 |
| `unpinned_alias` — resolved ≥5× and never confirmed | 5 |
| `no_energy_row` — component contributes mass and no kcal | 3 |
| `inverted_match` / `inverted_alias` — meat-substitute rows | 2 |
| `qualifier_mismatch` — white/whole/yolk etc. | 1 |
| `low_mass_confidence` | 1 |

**132 aliases exist for this user. One is verified. None are pinned.**

Datasets in use simultaneously: FNDDS 126 components, SR Legacy 100,
`user_product` 35, Foundation 22.

---

## 1. Egg whites resolved to whole egg  (identity / qualifier)

`egg whites, fried` → `Egg, whole, cooked, fried` (401 mg cholesterol/100 g).
Egg white contains none. 99 g carried 397 mg of cholesterol never eaten; the
day read 249% of its ceiling and the morning note advised eating fewer yolks
on a day containing one yolk.

Cached as an alias and reused three times. Trigram similarity cannot see it:
the two descriptions share every token that matters and differ by the single
word that decides what the food is.

## 2. Butter resolved to a row with no energy  (dataset semantics)

`butter` → `Butter, stick, unsalted`, a Foundation row carrying 81.5 g of fat
per 100 g and **no energy value at all**. 276 of 411 Foundation rows have no
1008 and no Atwater fallback. `total_nutrients` skips a missing nutrient
rather than zeroing it (invariant 6), so the fat counted and the calories did
not — a food that can only ever understate.

Ranking was the wrong instrument: demotion only breaks ties, and relevance
leads. "unsalted butter" scored 0.73 against the energy-less row and 0.67
against `Butter, salted`, so the wrong row won on merit.

## 3. A user's own food lost to a generic row  (precedence)

A Devolay defined from its own ingredients an hour earlier was logged as
`Chicken or turkey cordon bleu`. `_candidates` searches the model's
`search_terms` alongside the user's words and ranks by the best score any
query achieved — the model's phrase describes what it believes the food to be,
so it matches a generic row almost exactly, while the user's product can only
match the words the user typed. The user food scored 0.84 and came second.

## 4. Sugar counted under one of two USDA ids  (nutrient mapping)

FNDDS reports sugar as 1063, SR Legacy as 2000, Foundation as either. The
target sat on 2000, so every FNDDS food's sugar went uncounted. A day totalling
53.8 g displayed 11 g, at 19% of a 57 g ceiling. Nothing raised anything; the
number was a correct total of the wrong half.

## 5. One meal photographed twice became two foods  (input handling)

Album photos were parsed separately and their item lists concatenated. A 330 ml
bottle photographed from both sides became two components, 660 g, 61 g of sugar
— more than a day's ceiling from one drink. Both items plausible, both masses
plausible, and the energy cross-check passes because a doubled food is
internally consistent with itself.

## 6. Pickle juice resolved to pickle relish  (missing entity)

USDA has no row for pickle brine. `100 ml of pickle juice` matched
`Relish, pickle` at 130 kcal and 35 g of carbohydrate. The correct answer was
that the database does not contain this food, which is what `/food` now exists
to record.

## 7. A recipe divided by a stated yield that was impossible  (portion)

A blondie's ingredients totalled 1,587 g and were declared as an 850 g tray,
giving 105.6 g of carbohydrate, 46.8 g of fat and 8.1 g of protein per 100 g —
160 g of macronutrients inside 100 g of food, saved without complaint. Every
figure inflated in exact proportion and stayed internally consistent.

## 8. Not a resolution failure, recorded to prevent a false lead

`80g turkey breast` correcting a 400 g estimate **appended** a second turkey
rather than replacing the first. The USDA row was correct throughout. The bug
was `_label_match`: a multi-word phrase matched neither by prefix nor as a
single word, so `apply` converted an unplaceable `SetComponent` into an
`AddComponent`. Both components resolved to the same `fdc_id` and the entry
logged 907 kcal of a bird eaten once.

Relevance: no check anywhere noticed one entry containing the same `fdc_id`
twice.

---

## What the pattern is

1. **Every failure produced a plausible number.** None raised an error. The
   only ones caught early were caught by the Atwater cross-check, and it passes
   whenever the error is proportional (cases 5 and 7).
2. **Resolution is cached on first use and never revisited.** 131 unverified
   aliases. A wrong match is not one wrong meal, it is every future meal
   containing that food.
3. **Similarity is scored against text, and the deciding attribute is often a
   single word** — white/whole, salted/unsalted, raw/cooked, drained/rinsed.
4. **Dataset semantics differ and are mixed freely.** Foundation rows lack
   energy; FNDDS and SR Legacy disagree on nutrient ids; precedence is applied
   only as a tie-break.
5. **Nothing validates a component against the entry it sits in** — duplicate
   `fdc_id`, mass sums, or a component contributing zero energy to a meal that
   plainly has some.
