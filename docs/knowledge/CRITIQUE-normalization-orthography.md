# CRITIQUE-normalization-orthography

Critic pass over `docs/knowledge/AUDIT-normalization-orthography.md`.
Started 28 Aug 2026. Appended after every batch; nothing held in memory only.

Arbiter: `scripts/probe_knowledge.py` (re-run, not trusted from the audit) plus
read-only SQL for every nutrient figure quoted, plus the three resolver guards
read from `nutrai/llm/parse.py`.

STATUS: in progress.

## Headline correction: the audit did not run the guards, and it shows

The audit's `Proposals` and `Deliberately rejected` sections are **empty
headings**, and F6 cross-references "see Deliberately rejected" for its central
claim. The document has no proposals in it at all.

More seriously: eleven of its findings are stated as `wrong_confident_match`,
and the guards were checked in only one of them (F5, correctly). I replayed all
three guards over `db.search_foods(term, limit=5)` — the same call production
makes at `nutrai/llm/parse.py:733` — with the same "best candidate that
survives every guard" loop. Results below. `state` was varied where it could
matter; it changed nothing in any case tested.

### The mechanism the audit missed, and it decides half its findings

`unrequested_qualifier` has an `i == 0` branch: a *first* segment that echoes a
query word and **adds** one is a narrowing and is blocked. So the guard's reach
depends entirely on which way round USDA wrote the name:

| description form | example | guard |
|---|---|---|
| plain-English `Adjective Noun` (one segment, shares a word, adds one) | `Olive oil`, `Cranberry sauce`, `Palak Paneer`, `Blueberry juice` | **blocked** |
| USDA-inverted `Noun, adjective` (segment 0 shares nothing → skipped; segment 1 shares → passes) | `Oil, almond`, `Pie, strawberry`, `Pie, oatmeal` | **survives** |

F17 claims the four oil cases are "one repeating mechanism, not four
coincidences". They are not one mechanism in production: `olive` is blocked and
escalates, `almond`, `walnut` and `avocado` survive. The audit could not see
this because it never ran the guards.

### Claimed dangerous auto-matches, adjudicated

CONFIRMED — survives all three guards, auto-matches with no model consulted:

```
avocado           0.667 AUTO Oil, avocado        (Avocado, raw TIES at 0.667 — see below)
oatmeal           0.667 AUTO Pie, oatmeal        (Oatmeal, NFS ties at 0.667)
almond            0.636 AUTO Oil, almond
walnut            0.636 AUTO Oil, walnut
strawberry        0.733 AUTO Pie, strawberry
blueberry         0.714 AUTO Pie, blueberry
biscuit           0.667 AUTO KFC, biscuit        (Biscuit, NFS ties at 0.667)
```

OVERTURNED — the guards already block it; the case escalates to the model tier,
which is the system working:

```
olive              0.667  Olive oil              BLOCKED qual:"Olive oil"      -> escalates
cranberry          0.625  Cranberry sauce        BLOCKED qual:"Cranberry sauce"-> escalates
paneer             0.636  Palak Paneer           BLOCKED qual:"Palak Paneer"   -> escalates
beet soup          0.667  Soup, beef             BLOCKED qual:"beef"           -> escalates
chicken with rice  0.783  Chicken curry with rice BLOCKED qual                 -> but see below
chicken liver pate 0.760  Pate, chicken liver, canned BLOCKED qual:"canned"    -> but see below
tomato puree       0.650  Tomato, puree, canned  BLOCKED qual:"canned"         -> escalates
sauteed onions     0.682  Onions, yellow, sauteed BLOCKED qual:"yellow"        -> escalates
cheese souffle(é)  0.765  Cheese souffle         BLOCKED qual                  -> escalates
jalapeno pepper    0.700  Peppers, jalapenos     BLOCKED qual -> falls to Peppers, jalapeno, raw (0.682), the BETTER row
```

Ten claimed dangerous autos do not happen. Seven do.

### The two overturns that turn into a *different* wrong auto-match

**F2 is not a diacritics finding at all.** The audit's claim is that the
accented spelling promotes a different row past the gate. In production both
spellings resolve to the same wrong row:

```
chicken liver pate   0.760  Pate, chicken liver, canned   BLOCKED qual:"canned"
                     0.737  Liver, chicken                --> AUTO
chicken liver pâté   0.737  Liver, chicken                --> AUTO
```

The accent changes nothing. The real defect is that `chicken liver pate` —
spelled the *American* way, with no accent, which F2 presents as the correct
control — already logs 189 kcal / 8.69 g fat (`Liver, chicken`, 2706154)
instead of 201 / 13.10 (`Pate, chicken liver, canned`, 172928). F2 belongs in
whichever audit owns `unrequested_qualifier` demoting the only correctly-named
row on the list because USDA appended "canned" to it. Filed under diacritics it
is simply mis-attributed.

**F18's stated mechanism is a misreading of the guard, and the real auto-match
is a worse row than the one it names.** The audit says the guard "cannot see"
the curry "because that guard splits on commas and inspects segments after the
first, and this description has no comma at all". Read `unrequested_qualifier`
again: with no comma the whole description **is** segment 0, and the `i == 0`
branch fires exactly when the segment echoes a query word and adds one —
`{chicken, with, rice}` overlaps, `curry` is extra. The guard fires. What
actually happens:

```
chicken with rice  0.783  Chicken curry with rice        BLOCKED qual
                   0.750  Rice, fried, with chicken      --> AUTO
```

173 kcal / 3.66 g fat, against 149 / 5.84 for `Chicken or turkey and rice, no
sauce` — and it reads back to the user as fried rice, which he also did not
eat. The finding survives; every sentence of its explanation does not.

### The confirmed cases, with the figures re-pulled

```
 description                 | kcal |  fat  | sugar     vs the right row
 Oil, avocado        173573  |  884 | 100.0 |   -       Avocado, raw     160 / 14.66
 Pie, oatmeal       2708016  |  396 |  16.0 | 32.1      Oatmeal, NFS      76 /  2.63 / 0.17
 Oil, almond         171031  |  884 | 100.0 |  0.0      Almonds, NFS     598 / 52.54
 Oil, walnut         171030  |  884 | 100.0 |  0.0      Nuts, walnuts, english  654 / 65.21
 Pie, strawberry    2708003  |  289 |  11.6 | 22.6      Strawberries, raw 36 /  0.22
 Pie, blueberry     2707998  |  300 |  15.5 | 15.5      Blueberries, raw  64 /  0.31
 KFC, biscuit        170339  |  358 |  17.1 |  4.0      Biscuit, NFS     370 / 18.92 / 3.88
```

Two corrections inside the confirmed set:

- **F17's "single worst ratio measured" is not the worst ratio, because the
  audit stopped enumerating after four oils.** See the new autos below;
  `pumpkin -> Pie, pumpkin` is 249 against 26, a factor of 9.6, against
  avocado's 5.5.
- **F6 blames the wrong half of the `biscuit` failure.** `Biscuit, NFS`
  (370 kcal, 18.9 g fat, 3.9 g sugar) ties `KFC, biscuit` (358 / 17.1 / 4.0) at
  0.667 and is nutritionally the same food. Which of the two wins is
  immaterial; the audit's "auto-matches a *branded restaurant row*" framing
  points at the harmless half. The damage is the BR/US sense split — 370 vs
  `Cookie, NFS` 492 kcal and 3.9 vs 32.9 g sugar — which is a vocabulary
  failure, not an orthographic one, and the audit files it here anyway.
  Downgrade the framing, keep the finding.
- **F5's LIMIT-dependent coin toss is real and generalises further than the
  audit says.** `avocado` (Oil, avocado / Avocado, raw) and `biscuit`
  (KFC, biscuit / Biscuit, NFS) are ties at exactly 0.667 too. The audit
  checked the tie for `oatmeal` only.

## What the audit missed

### M1 — `extra virgin olive oil` auto-matches a row with NO ENERGY AND NO FAT

The audit's own showcase. F19 lists `auto extra virgin olive oil 1.000 Oil,
olive, extra virgin` in the block demonstrating that expansions work. It is the
worst row in this critique.

```
 fdc_id | description               | data_type       | kcal | fat
 748608 | Oil, olive, extra virgin  | foundation_food | NULL | NULL
1750351 | Oil, olive, extra light   | foundation_food | NULL | NULL
 171413 | Oil, olive, salad or cooking | sr_legacy_food |  884 | 100
2710186 | Olive oil                 | survey_fndds_food | 900 | 100
```

748608 is the only row carrying that phrase, it wins at similarity 1.000, it
survives all three guards, and it carries **no energy, no fat, no protein and
no carbohydrate at all** — 90 nutrient rows, none of them macros. Invariant 6
skips a missing nutrient rather than zeroing it, so 30 g of olive oil logs as
**0 kcal**, and an alias is written that is never re-checked.

`db.UNUSABLE_ROW` was built to catch exactly this and does not fire: it excludes
a row with macros and no energy, and this row has neither. Twelve rows in the
table are in that hole, and eight of them are cooking oils:

```
Oil, canola / corn / olive extra light / olive extra virgin / peanut /
safflower / soybean / sunflower   (all foundation_food, all NULL)
Juice, pomegranate, from concentrate, shelf-stable
Milk, human   Salt, table, iodized   (+ one user_product sparkling water)
```

`peanut` and `sunflower` both auto-match one of them (below). This is out of
this audit's declared scope and squarely inside its evidence, and it went
unnoticed because the probe prints a description and a score and never a
nutrient.

kind: wrong_confident_match | category: other_semantic_failure | confidence: high

### M2 — twelve more bare-singular autos of exactly the F9/F17 shape

The audit stops at `olive / almond / walnut / avocado` and calls it "one
repeating mechanism". I scanned 50 bare ingredient singulars through the full
guard stack. `olive` is blocked; these are not:

```
coconut     AUTO 0.667  Oil, coconut      892 kcal / 99.1 fat   vs Nuts, coconut meat, raw 354 / 33.5
pumpkin     AUTO 0.727  Pie, pumpkin      249 / 9.8 / 24.6 sug  vs Pumpkin, raw   26 / 0.1 / 2.8   <- 9.6x
peanut      AUTO 0.636  Oil, peanut       NO ENERGY, NO FAT      vs Peanuts, NFS 587 / 49.7        <- M1 row
sunflower   AUTO 0.714  Oil, sunflower    NO ENERGY, NO FAT      vs Seeds, sunflower kernels 584 / 51.5
ginger      AUTO 0.636  Tea, ginger         1 kcal / 0.0 fat     vs Ginger root, raw 80, Spices, ginger, ground 335
pecan       AUTO 0.667  Pie, pecan        449 / 25.3 / 31.0      vs pecans (nut row)
cherry      AUTO 0.636  Pie, cherry       311 / 15.3 / 19.5      vs Cherries, raw 71 / 0.2 / 13.9
peach       AUTO 0.667  Pie, peach        296 / 15.3 / 15.7      vs Peaches, raw
hazelnut    AUTO 0.727  Hazelnuts         628 / 60.8            (correct)
```

`ginger` is the one with no analogue anywhere in the audit: a spice
auto-matching a **beverage at 1 kcal per 100 g**. A teaspoon of ground ginger
logs as nothing, permanently. `pumpkin -> Pie, pumpkin` displaces F17's "single
worst ratio" claim.

Safe by comparison, and worth recording as the control: `apple`, `pear`, `fig`,
`plum`, `prune`, `mango`, `grape`, `corn`, `rice`, `carrot`, `onion`,
`mushroom`, `pea`, `bean`, `lentil`, `pepper`, `leek`, `parsnip`, `sesame`,
`lemon`, `lime` all escalate.

kind: wrong_confident_match | category: ingredient_vs_dish_ambiguity | confidence: high

### M3 — `jelly` auto-matches at 1.000, and BR/US jelly are different desserts

Not probed by the audit despite `biscuit`, `chips` and `crisps` being in scope.

```
jelly   1.000 AUTO  Jelly  (2710300)   266 kcal, 0.0 fat, 51.2 g sugar
```

British "jelly" is the gelatin dessert (~60 kcal, ~14 g sugar made up); USDA
`Jelly` is the fruit preserve. Same trap as `biscuit`, higher score, no guard
touches it. The audit tested `chips` (escalates — safe), `squash` (escalates),
`pudding` (escalates) — I re-probed all three — and missed the one that fires.

kind: wrong_confident_match | category: culturally_incorrect_mapping | confidence: high

### M4 — the compound-word / hyphen / ampersand class was never tested

Five sweeps (diacritics, BR/US, plurals, transliteration, abbreviations) and no
sweep for the one thing a phone keyboard actually varies. Probed:

```
sun-dried tomatoes  1.000 AUTO Tomatoes, sun-dried     sundried tomatoes  0.762 BLOCKED -> escalates
ice-cream           0.714 AUTO Ice cream, NFS          icecream           0.438 -> escalates
peanutbutter        0.688 AUTO Peanut butter           corn flour         0.407 -> escalates
chickpea            0.533 -> escalates                 chick pea          0.345 -> escalates (top hit a branded soup)
garbanzo            0.237 -> escalates                 cornflour          0.333 -> escalates (only hit: Flour, coconut)
mac & cheese / mac and cheese / fish & chips / stir fry / half and half   all -> escalate
```

The class fails safely everywhere I could reach it, which is a result worth
having and is not in the audit. Two mechanical notes it also does not have:

- **`label_absent` is doing more of the BR/US blocking than the audit credits.**
  `yoghurt` does not merely score 0.357 against `Yogurt, NFS` — it is *blocked*,
  because neither string is a prefix of the other, so `label_absent` fires on
  every yogurt row. F4's "recall is 0, so no ranking function can reach it" is
  right about `prawn` and `courgette`; for `yoghurt` recall is 4 rows and the
  guard removes them anyway.
- F21's "single-character typos degrade one band and still point at the right
  row" describes the probe, not production. `brocoli` and `brocolli` are both
  blocked by `label_absent` on every `Broccoli` row (prefix matching does not
  survive an interior edit). Harmless — they escalate, and the model tier still
  sees the right list — but the sentence as written is not true of the resolver.

### M5 — `mayo -> mayonnaise` does not resolve, and F19 implies it does

F19 lists `auto mayonnaise 0.647 Mayonnaise, light` in the block of working
expansions. In production `Mayonnaise, light` is blocked (`qual:light`), and
the next survivor, `Mayonnaise, regular` at 0.579, is below the gate:
**`mayonnaise` escalates**. Which is the right outcome — `Mayonnaise, light` is
not mayonnaise — but the audit presents a probe artefact as a success, and the
one line in F19 that would have been a real finding is the one it got wrong.

### M6 — CULINARY: `kebab -> kabob` is the trap in this domain, and F13 walks into it

F13 says "`kebab` is the near-universal spelling outside US government datasets.
Nine usable rows are invisible to it." With no Proposals section written, that
sentence is the proposal, and it is wrong for the commonest sense of the word.

An unqualified British/European "kebab" is a **doner** — shaved fatty
lamb/beef off a vertical spit, roughly 215-280 kcal/100 g of meat. USDA's nine
rows are **shish** kabobs: skewered meat *with vegetables*.

```
 Lamb shish kabob with vegetables       162 kcal | 10.3 fat
 Beef shish kabob with vegetables       122 kcal |  4.9 fat
 Chicken or turkey shish kabob          104 kcal |  3.7 fat
```

Mapping the word to these understates a doner by 40-60% and silently swaps in
vegetables the eater did not have. `shish kebab -> shish kabob` is the safe
rewrite; the bare word is not. The audit does note separately that "doner
kebab" returns nothing — it simply does not connect that to its own proposal.

kind: culturally_incorrect_mapping | confidence: high

### M7 — CULINARY: `coriander` must not be folded to `cilantro`

F4's reachability table puts `cilantro` (2 rows) beside `coriander` (4 rows)
and draws no conclusion, which invites the BR/US fold by analogy with
`rocket -> arugula`. It is not the same shape. British "coriander" means the
**leaf** in a recipe and the **ground seed** in a spice jar, and USDA leads with
the seed:

```
coriander  0.476  Spices, coriander seed              298 kcal | 17.8 fat
           0.345  Coriander (cilantro) leaves, raw     23 kcal |  0.5 fat
```

A 13x energy gap decided by which sense the writer meant. Both spellings
escalate today (0.476 is under the gate) and must be left to escalate; a
synonym rule here would be the galangal/ginger error of this domain. Same
caution the audit correctly applied to `chilli/chili` in F7, not applied here.

## What I checked and upheld

Re-probed, reproduces exactly, keep as written:

- **F0** — 13,651 rows, two non-ASCII characters, both U+00A0; `unaccent` not
  installed. Confirmed. The best-founded finding in the document.
- **F1** — `crème brûlée`, `purée`, `gruyère`, `açaí`, `kiełbasa`, `houmous` all
  return **nothing**; their unaccented twins reach the right row (`creme
  brulee` at 1.000). Confirmed verbatim.
- **F4** — `prawn`, `courgette`, `aubergine`, `rocket`, `beetroot`, `porridge`
  all `none`. Confirmed. Recall is genuinely 0; no ranking change can fix it.
- **F5** — the `oatmeal` / `Pie, oatmeal` tie at 0.667 and its survival of all
  three guards. The one place the audit did the guard check, and it did it
  correctly.
- **F7** — the chilli/chili/chile three-way and the conclusion **do not fold**.
  Right answer, and the sense split (73% of "chili" rows are the stew) is the
  right evidence for it. One overstatement: "a British user typing `chilli`
  means the pepper roughly always" is not true — `chilli con carne` is the
  standard British spelling of the dish and is in the audit's own probe list.
  The conclusion does not depend on it; the confidence should be medium and the
  argument should rest on where the score sits relative to the gate, which is
  the part that is measured.
- **F12, F13 (the measurement), F19, F20, F21** — reproduce. F21's headline
  ("possessives need no work") holds and extends: I tested the case the audit
  did not, a **curly apostrophe** U+2019 as a phone keyboard emits it, and
  `shepherd’s pie` auto-matches `Shepherd's pie` at 1.000 identically.
- **F10, F11** — irregular plurals and plural-worse-than-singular. Correct, and
  correctly self-marked as low impact.

## Method objection

**The verdict-count table overstates production risk and carries no caveat.**
`probe_knowledge.py` measures `db.search_foods` alone; `auto` in that table
means "would clear 0.62", not "would be taken". Of the seventeen claimed
dangerous auto-matches I adjudicated, **ten are already blocked** by
`unrequested_qualifier` and escalate to the model tier — the system working.
The audit ran the guard check in one finding out of eleven and generalised from
the probe everywhere else. Every one of the ten overturns is a case where the
audit reports damage that does not occur.

The compensating error runs the other way and is larger: because the probe
prints a description and a score and never a nutrient, the audit's own showcase
success (`extra virgin olive oil`, M1) logs zero calories, and twelve
bare-singular autos of its own F9 shape (M2) were never enumerated.

## Confidence

Eighteen of the twenty findings are marked `confidence: high`, including F2 and
F18, whose stated mechanisms are both wrong. F6's `confidence: high` covers a
claim that points at the harmless half of its own failure. High should mean
"beyond dispute by a competent cook **and** checked against the code path", and
in this document it means "the probe printed it".

## Structural

`## Proposals` and `## Deliberately rejected` are **empty headings**. F6 says
"see Deliberately rejected" for the load-bearing claim that its failure is not
fixable by a synonym, and there is nothing there. The document is a measurement
log with no recommendations in it, and the one recommendation it makes in prose
(F13's `kebab`) is the one I would reject.

STATUS: complete.
