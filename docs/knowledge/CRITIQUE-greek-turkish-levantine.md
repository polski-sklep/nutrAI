# Critique — AUDIT-greek-turkish-levantine.md

28 Aug 2026. Adversarial review. I did not write the audit.

Method: every claim re-probed with `scripts/probe_knowledge.py`; every
nutritional claim checked with a read-only SELECT against the live
`food` / `food_nutrient` tables; every claimed dangerous auto-match run
through the three real guards in `nutrai/llm/parse.py`.

Status: complete.

---

## A. The instrument was read wrong, and it changes the headline finding

`probe_knowledge.py` prints `db.search_foods` in **`search_foods` order**, which
is `covers` first, then `similarity + ts_rank`. It is *not* ordered by `sim`.
`_candidates` then **re-sorts the pooled set strictly by `sim`** before
`resolve_items` walks it. So the row the probe prints first is not the row
production would auto-match, and the audit read them as the same thing.

The audit's own §1.1 paste shows the tell and does not notice it:

```
    0.636  Roll, wheat or cracked wheat     <- printed first
    0.700  Bread, cracked-wheat             <- higher sim, printed second
```

Run through the real `_candidates` + the three real guards:

```
=== 'cracked wheat'
   0.700 Bread, cracked-wheat          AUTO
   0.636 Roll, wheat or cracked wheat  AUTO
   0.500 Bread, pita, wheat or cracked wheat  BLOCK:qual:pita
  -> RESULT: AUTO Bread, cracked-wheat
```

**Production auto-matches `Bread, cracked-wheat` (172672), not the roll.**
Measured: 260 kcal, 8.7 P, 3.9 F, 49.5 C, 538 Na, 5.5 fibre per 100 g — against
the audit's quoted 273 kcal / 6.3 g fat, which belongs to `Roll, wheat or
cracked wheat` (2707746). The finding survives in direction (a bread where a
grain was meant) and the audit's own damage arithmetic is off: the honest
comparison for tabbouleh/kısır is `Bulgur, cooked` at **83 kcal**, so the error
is 260 vs 83 = 3.1x, not the roll's figures.

This is a general caveat on the whole document, not one entry: any "top" line
the audit quotes may not be the head `_candidates` hands the guards, and any
`weak`/`ask` verdict is computed from the *printed* head's `sim`, so a
higher-`sim` row further down could still auto-match in production.

## B. Two claimed unguarded auto-matches are already blocked — the audit is wrong

§1.5 states: "`fried onion` → `Fried onion rings` and `rice with lentils` →
`Lentil curry with rice` are **not** blocked." Both are. Called directly:

```
unrequested_qualifier('fried onion ', 'Fried onion rings')      -> 'Fried onion rings'
unrequested_qualifier('rice with lentils ', 'Lentil curry with rice') -> 'Lentil curry with rice'
```

Full guard walk over the real candidate list:

```
=== 'fried onion'
   0.667 Fried onion rings                          BLOCK:qual:Fried onion rings
   0.316 Fast foods, onion rings, breaded and fried below
   0.279 Onion rings, breaded, par fried, frozen…   BLOCK:qual:Onion rings
  -> RESULT: ESCALATE to model
=== 'rice with lentils'
   0.640 Lentil curry with rice                     BLOCK:qual:Lentil curry with rice
   0.545 Rice, white, with lentils, fat added       BLOCK:qual:white
   0.500 Rice, white, with lentils, NS as to fat    BLOCK:qual:white
  -> RESULT: ESCALATE to model
```

Both first-segment names echo a query word and add one, which is exactly the
`i == 0` branch of `unrequested_qualifier`. The audit asserts the opposite for
both, in the section whose entire premise is that the guards were "imported and
called directly". They were not called for these two.

**And the damage claim for `fried onion` is wrong even if it fired.** The audit
writes "`Onions, raw` is 40 kcal and battered onion rings are 352", implying the
correct answer is 40. The fried onion garnish on mujadara is onion cooked in a
depth of oil; it is not raw onion and 40 kcal/100 g would understate it
severely. `Fried onion rings` (352) is wrong on composition — batter, wheat
flour — but is not the 8x energy error the framing implies.

Note also `rice with lentils`: three literal `Rice, white, with lentils, …` rows
exist and are on the list. Mujadara is reachable; the audit files this under
wrong-confident matching and never says so.

## C. Confirmed dangerous auto-matches (guards do NOT save these)

Re-run and upheld:

| label | production auto-match | kcal/100 g | what was meant |
|---|---|---|---|
| `walnut` | `Oil, walnut` (171030) | 884, 100 g fat | `Nuts, walnuts, english` 654, 65.2 F |
| `almond` | `Oil, almond` (171031) | 884, 100 g fat | `Almonds, NFS` 598, 52.5 F |
| `whole chicken roasted` | `Chicken, chicken roll, roasted` (2706087) | 164, 6.33 F | `Chicken, roasting, meat and skin, roasted` 223, 13.4 F |
| `orange blossom water` | `Orange Blossom` (2710647) | 98 | a flowerwater, ~0 |
| `bulgur` (no state / `unknown`) | `Bulgur, dry` (170688) | 342 | `Bulgur, cooked` 83 |
| `cracked wheat` | `Bread, cracked-wheat` (172672) | 260 | `Bulgur, cooked` 83 |

Mechanism worth recording, because the audit does not: the sibling rows *are*
blocked. `Walnut oil` and `Almond oil` are caught by `unrequested_qualifier`
(first segment echoes the query and adds a word) while `Oil, walnut` and
`Oil, almond` sail through, because their first segment is "Oil" — which shares
nothing with the query, so the `i == 0` branch declines to judge it. The guard
blocks the harmless duplicate and passes the dangerous original. That is a
guard defect the audit had the data to see and did not report.

Correction to the audit's own table: it lists `Nuts, walnuts, english` as
"654 | 69.7 (`Walnuts, excluding honey roasted`)". 654 kcal and 69.7 g fat are
from two different rows spliced into one line. `Nuts, walnuts, english` (170187)
is 654 kcal / **65.21** g fat.

## D. Two claimed *correct* auto-matches also do not happen

The mirror of §B. The audit's §1.6 / §4 list of "auto and all right" includes
two that the guards escalate:

```
=== 'tzatziki'
   0.692 Tzatziki dip   BLOCK:qual:Tzatziki dip
  -> RESULT: ESCALATE to model
=== 'stuffed grape leaves'
   0.677 Grape leaves stuffed with rice          BLOCK:qual:…
   0.538 Stuffed grape leaves with lamb and rice BLOCK:qual:…
   0.525 Stuffed grape leaves with beef and rice BLOCK:qual:…
   0.520 Grape leaves, raw                       below
  -> RESULT: ESCALATE to model
```

The mechanism is the same one that saves `fried onion`, and it is worth naming
because it runs through the whole domain: `unrequested_qualifier`'s `i == 0`
branch fires on FNDDS's pervasive **`<dish name> <form>`** pattern — `Tzatziki
dip`, `Eggplant dip` (only when the query omits "dip"), `Fried onion rings`,
`Falafel sandwich`, `Gyro sandwich` against `gyro`. Any single-word dish label
whose FNDDS row appends a form word escalates rather than auto-matching.

This is the correct behaviour and it is also the reason a large part of §1 and
§4 of the audit is mis-scored in both directions. The audit's headline
`auto=110 (17%)` is a count of probe verdicts, not of production auto-matches,
and the real figure is lower by an unmeasured amount.

Verified as genuinely auto and correct (guards walked): `spanakopita`,
`baklava`, `tabbouleh`, `falafel`, `tahini`, `pita bread` → `Bread, pita`,
`kefir`, `turkish coffee`, `olive oil`, `garlic sauce`, `eggplant dip`,
`grape leaves`, `feta cheese`, `lentil soup`, `rice pudding`,
`walnuts english`, `jute potherb`, `eggplant and meat casserole`,
`grape leaves stuffed with rice`.

## E. Culinary errors in the proposed mappings

### E.1 `dolma` → a grape-leaf row is wrong, and USDA holds the right rows

§2.3 puts `dolmades`, **`dolma`**, `warak enab` and `yaprak sarma` in one
bucket and rates the mapping to `Grape leaves stuffed with rice` **High**.
In Turkish the two words are not synonyms and the distinction is the whole
point of them:

- **dolma** = *filled* — a hollow vegetable stuffed: biber dolması (pepper),
  domates dolması (tomato), kabak dolması (courgette), karnıyarık's cousin.
- **sarma** = *wrapped* — a leaf rolled around a filling: yaprak sarma
  (vine leaf), lahana sarma (cabbage).

Bare `dolma` most commonly means the stuffed vegetable. USDA holds those rows
and the audit never searched for them:

| fdc_id | row | kcal | P | F | C |
|---|---|---|---|---|---|
| 2709073 | `Stuffed pepper, with rice and meat` | 178 | 7.8 | 11.7 | 9.9 |
| 2709074 | `Stuffed pepper, with rice, meatless` | 166 | 3.8 | 11.3 | 12.0 |
| 2709072 | `Stuffed pepper, with meat` | 198 | 9.2 | 15.9 | 4.2 |
| 2709075 | `Stuffed tomato, with rice and meat` | 99 | 4.8 | 4.5 | 9.9 |
| 2709076 | `Stuffed tomato, with rice, meatless` | 77 | 1.6 | 2.1 | 13.1 |
| 2706620 | `Stuffed cabbage rolls with beef and rice` | 114 | 8.3 | 5.1 | 8.8 |
| 2709064 | `Grape leaves stuffed with rice` | 168 | **2.3** | 11.9 | 13.9 |

A stuffed tomato logged as a vine leaf is 168 vs 77 kcal — 2.2x — and the
protein is 2.3 vs 1.6/4.8, so the direction differs by filling too. The vine
leaf row is also strikingly low in protein for a "stuffed" dish, which is a
signal the audit should have read: it is nearly all rice and oil.

`malfouf` / `lahana sarması` / `sarma` / `mahshi` / `kousa mahshi` /
`biber dolması` all probe `none`, and `stuffed cabbage` is the §2.11 shape —
correct row at rank 1, graded weak:

```
weak  stuffed cabbage      0.400  Stuffed cabbage rolls with beef and rice
none  malfouf / sarma / yaprak sarma / mahshi / kousa mahshi / biber dolmasi
ask   stuffed peppers      0.538  Stuffed jalapeno pepper
auto  stuffed pepper       0.625  Stuffed jalapeno pepper   (guards: ESCALATE)
```

`dolma` should map to the stuffed-vegetable rows, or — the honest answer —
should not be a single mapping at all. `dolmades`, `warak enab` and
`yaprak sarma` to the grape-leaf rows: **High**, unchanged. Bare `dolma`:
**overturned**.

### E.2 `cacik` ≡ `Tzatziki dip` overstates by roughly 2x

§2.14 records `cacik | none | Tzatziki dip (auto 0.692) — same dish`. They are
close relatives, not the same dish: cacık is thinned with water and served as a
cold soup or a spoonable side, tzatziki is a thick strained-yogurt dip.
`Tzatziki dip` (2705448) is **91 kcal, 5.2 P, 6.0 F, 307 Na**; cacık as poured
from a jug is nearer 40–55. At the masses cacık is eaten in — a bowl, 200–250 g,
against a tablespoon of tzatziki — the error is larger than the per-100 g gap
suggests. Downgrade to **medium**, and it belongs with the mass, not only the
row.

### E.3 `kalamata olives → Olives, black` is the cured-vs-cured trap

§2.14 offers `Olives, black` (auto 1.000) as the row for kalamata. Measured:

| row | kcal | fat | Na |
|---|---|---|---|
| `Olives, black` / `Olives, ripe, canned (small-extra large)` | 116 | 10.9 | 735 |
| `Olives, green` / `Olives, pickled, canned or bottled` | 145 | 15.3 | 1556 |

USDA's "black olives" are California-style **lye-treated, canned ripe** olives —
a mild, low-sodium, low-fat product. Kalamata are naturally brine-cured and run
roughly 15–25 g fat and 1,300–2,300 mg sodium. On both axes that is the green
row's neighbourhood, not the black one, despite the colour. Choosing by colour
here is the same error class as bresaola/pork: the visible attribute is not the
one that carries the nutrition. Either propose `Olives, green` with the colour
mismatch stated, or leave it and let the model tier pick. **Overturned as
written.**

### E.4 The halloumi rejection rests on figures that are wrong

§5 rejects `halloumi → mozzarella` because "low-moisture part-skim mozzarella is
~280 kcal with **a fifth** of halloumi's sodium". Measured:

| row | kcal | P | F | Na |
|---|---|---|---|---|
| `Cheese, mozzarella, low moisture, part-skim` (329370) | 298 | 23.7 | 20.4 | 699 |
| `Cheese, mozzarella, whole milk, low moisture` (170846) | 318 | 21.6 | 24.6 | 710 |
| `Cheese, white, queso blanco` (172224) | 310 | 20.4 | 24.3 | 704 |

Halloumi is ~320 kcal / 22–25 P / 25 F / 1,100–1,800 Na. Mozzarella's sodium is
**not** a fifth of halloumi's — 699 against ~1,200 is over half, and it is the
*same* 700 mg understatement the audit accepts in queso blanco. `Cheese,
mozzarella, whole milk, low moisture` at 318/21.6/24.6/710 is nutritionally
indistinguishable from the proposed queso blanco at 310/20.4/24.3/704.

The conclusion (queso blanco) survives; the argument for it does not. And the
mechanism claim is wrong too: queso blanco is **acid**-coagulated, halloumi is
rennet-set and scalded in whey. They both hold shape under heat for different
reasons, and halloumi is not "pasta-filata-adjacent" — it is not stretched.
Keep the mapping at **medium**; drop the reasoning.

### E.5 `pastırma → Beef, cured, dried` swaps one wrong energy figure for another

§5 rejects `Beef, cured, pastrami` (147 kcal, 21.8 P, 5.8 F) and proposes
`Beef, cured, dried` (153 kcal, 31.1 P, 1.9 F, 2790 Na) as "the honest
analogue". Pastırma is roughly 240–280 kcal with 9–15 g fat. The proposal fixes
protein (31 vs ~35) and is *worse* on fat (1.9 g against ~12) while leaving
energy essentially where it was — 153 against 147, both ~40% low. The audit
picked the one macro that agreed and called the mapping honest. Downgrade to
**low/medium with the energy gap stated**, or leave pastırma an entity gap;
either is defensible, "the honest analogue" is not.

### E.6 `baba ganoush ≡ mutabbal` is variant-dependent, not High

`Eggplant dip` (2710049) measures 183 kcal, 4.8 P, 15.0 F, 209 Na — an
oil-heavy row. In much of the Levant *mutabbal* is the tahini-and-yogurt
version and *baba ghanouj* is the tahini-free eggplant salad with tomato,
pepper and pomegranate molasses; in Egypt and in most English-language usage
the two names are used interchangeably for the tahini one. The mapping is
nutritionally survivable either way (both are eggplant plus fat), but the
audit's **High** is a claim about naming that a competent Levantine cook would
dispute. **Medium.**

## F. What the audit missed — probed, with the row it should have found

659 terms and it did not test the four staples below. All are re-probed here.

### F.1 `lentils` auto-matches the dry row — the bulgur finding, unreported

```
=== 'lentils'  (state absent, as the parse usually leaves it)
   0.667 Lentils, dry   AUTO      <- 360 kcal/100 g
   0.667 Lentils, raw   AUTO
   0.667 Lentils, NFS   AUTO
  -> RESULT: AUTO Lentils, dry
```
`Lentils, cooked` is ~116 kcal. **3.1x**, identical in shape to §1.4's bulgur
finding, in a cuisine whose staples are mercimek çorbası, ezogelin, adas,
mujadara, imjadra and koshari. The audit built a whole subsection on bulgur and
never ran the same query for lentils. `state="cooked"` does rescue it, onto
`Lentils, NFS`.

### F.2 `couscous` — same again

```
=== 'couscous'
   0.636 Couscous, dry     AUTO   <- 376 kcal
   0.583 Couscous, cooked  below  <- 112 kcal
  -> RESULT: AUTO Couscous, dry
```
**3.4x.** With `state="cooked"` it escalates correctly.

### F.3 `halva` returns nothing while `Candies, halavah, plain` sits in the table

```
none  halva                -      (nothing)
none  halvah               -      (nothing)
weak  sesame halva         0.412  Sesame seeds
auto  candies halavah      0.727  Candies, halavah, plain   (guards: AUTO, correct)
```
`Candies, halavah, plain` (167996) — **469 kcal, 12.5 P, 21.5 F, 60.5 C**. This
is exactly the §2 reachability shape the audit calls "the most valuable class",
for a sweet eaten across the whole domain (tahin helvası, halawa, χαλβάς) and
dense enough that a 60 g piece is 280 kcal. Untested. **High confidence
synonym**, and cheaper than any of the mappings the audit did propose.

### F.4 `lamb kebab` — the right row exists and is not the one the audit proposed

§2.6 proposes `kebab ≡ kabob` and points at the FNDDS `… shish kabob with
vegetables` rows. Those rows are a *plate*, not the meat:

| row | kcal | P | F |
|---|---|---|---|
| `Lamb shish kabob with vegetables, excluding potatoes` (2706780) | 162 | 12.0 | 10.3 |
| `Lamb, cubed for stew or kabob (leg and shoulder), lean, cooked, broiled` (172510) | 186 | **28.1** | 7.3 |
| `Lamb, cubed for stew or kabob …, cooked, braised` (172509) | 223 | 33.7 | 8.8 |

Protein differs by **2.3x**. `Lamb, cubed for stew or kabob …, broiled` is
literally the şiş kebap row, it contains the word "kabob", and the audit never
surfaced it — it reported `lamb kebab → weak 0.312 Lamb, chop` as an unsolved
failure. Also missed: `Chicken or turkey shish kabob with vegetables` (2706783),
a sixth row the audit's five-row paste omits.

And the synonym itself is over-broad. In British and German usage an
unqualified **"kebab" means döner** — shaved meat in bread — not skewered cubes.
Routing bare `kebab` to a shish-kabob-with-vegetables row would be wrong for the
most common sense of the word. Split it: `shish kebab ≡ shish kabob` **high**;
bare `kebab` → leave to the model, or `Gyro sandwich` (184 kcal) with the
reasoning stated. **Downgraded from High.**

### F.5 `eggplant` auto-matches raw, in the cuisine of imam bayıldı

```
=== 'eggplant'
   0.692 Eggplant, raw  AUTO
  -> RESULT: AUTO Eggplant, raw     (25 kcal, 0.2 g fat)
```
`Eggplant, cooked, fat added` (2709930) is 51 kcal / 2.9 F and exists.
Imam bayıldı, karnıyarık, musakka and papoutsakia are eggplant cooked in a
depth of olive oil; a real fried slice is several times either figure. §2.9
discusses `zucchini`/`aubergine`/`courgette` reachability at length and never
probes the word `eggplant` itself, which is the one that auto-matches.

### F.6 The honest target for mujadara's fried onion, which §1.5 also missed

`Onions, cooked, fat added` (2709951) = **73 kcal**. The audit's framing offers
only `Onions, raw` (40) and `Fried onion rings` (352). The right row was in the
table the whole time.

### F.7 Untested and materially absent

`shawarma` → **none**; `chicken shawarma` → weak 0.429 **`Chicken skin`**.
Arguably the most-eaten Levantine dish outside the Levant and it appears
nowhere in a 659-term audit of the Levant. Nearest holding is `Gyro sandwich`.

Also untested, all `none`: `souvlaki`, `pastitsio`, `saganaki`, `avgolemono`,
`taramasalata`, `skordalia`, `horta`, `gigantes`, `loukaniko`, `graviera`,
`kefalotyri`, `mizithra`, `kasseri`, `bougatsa`, `galaktoboureko`,
`loukoumades`, `koulouri`, `trahana`, `fasolada`, `stifado`, `youvetsi`,
`briam`, `gemista`, `keftedes`, `sucuk`, `kaymak`, `simit`, `pide`, `manti`,
`cig kofte`, `kofte`, `kofta`, `shish taouk`, `muhammara`, `fattoush`,
`manakish`, `kanafeh`/`knafeh`/`kunefe`, `maamoul`, `mujadara`, `makloubeh`,
`bamia`, `lokum`, `piyaz`, `kuru fasulye`, `ezme`, `haydari`, `ful medames`,
`ayran`, `laban`, `jibneh`, `yufka`, `borek`/`burek`. Most are genuine entity
gaps, consistent with §3 — but `greek salad` → ask 0.500 `Greek Salad, no
dressing` (2709830) is a reachable row the audit never found, and `horiatiki`,
its Greek name, returns nothing.

Minor factual slip in §2.9: "The vegetable is absent from its own top five" is
contradicted by the audit's own paste — `Squash, zucchini, baby, raw` and
`Zucchini, pickled` are both in it. The complaint (the plain cooked/raw row is
not) stands; the sentence does not.

## G. Guard tally

Of the 14 auto verdicts the audit puts through the guards in §1:

- **8 survive** and are genuine wrong-confident matches that will cache an
  alias: `cracked wheat` (×2 states), `walnut`, `almond`,
  `whole chicken roasted`, `orange blossom water`, `bulgur` (state absent),
  `bulgur` (state `unknown`).
- **6 are blocked** and escalate to the model tier — the system working.
  Four the audit correctly identified (`bulgur` cooked, `tomato sauce`,
  `sour cream`, `toasted bread`) and **two it asserted were not blocked and
  are** (`fried onion`, `rice with lentils`).
- Two further rows it listed as working auto-matches (`tzatziki`,
  `stuffed grape leaves`) are also blocked, so its §4 count is wrong in the
  other direction.

New guard survivors found here: `lentils` → `Lentils, dry`, `couscous` →
`Couscous, dry`, `eggplant` → `Eggplant, raw` (all state-absent).

Blocked, and worth recording so nobody re-files them: `olive` → `Olive oil`
(blocked by `unrequested_qualifier`, escalates — the walnut/almond class does
**not** extend to olive), `meatballs` → `Meatballs, meatless` (blocked by
`inverts_meaning`), `stuffed pepper` → `Stuffed jalapeno pepper` (blocked).

A guard defect the audit had the data to see: `Walnut oil` and `Almond oil` are
blocked while `Oil, walnut` and `Oil, almond` pass, because
`unrequested_qualifier` only judges the first segment when that segment echoes a
query word — and "Oil" echoes nothing in "walnut". The guard blocks the
duplicate and passes the original.

## H. Where the audit is right and should not be re-litigated

Every §2 and §3 reachability claim re-probed clean: `molokhia`, `baba ganoush`,
`dolmades`, `kibbeh`, `halloumi`, `labneh`, `freekeh`, `courgette`, `aubergine`,
`toum`, `sumac`, `orzo`, `hommos`, `filo`, `shish kebab`, `yoghurt drink` all
return nothing; `moussaka` → `Mousse` 0.455; `vine leaves` → `Taro leaves, raw`;
`gyro` → `Gyro sandwich` 0.357 weak; `feta` 0.417; `ghee` 0.227; `tabouli`
0.385. The molokhia = jute (*Corchorus olitorius*) identification is correct;
`Jute, potherb, cooked` measures 37 kcal / 3.68 P as claimed. `Garlic sauce` at
683 kcal / 74.0 g fat is right for toum. The refusals in §5 — `halloumi →
cheese`, `khachapuri → Bread, cheese`, `sumac → Spices, …`, `mansaf`,
`kibbeh nayyeh`, `molokhia the dish`, `asure` — are all correctly reasoned and
should stand.

The §6 structural argument (length-normalise rather than max-pool) is the
strongest thing in the document and nothing here weakens it.
