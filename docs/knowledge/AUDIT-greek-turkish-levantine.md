# Knowledge audit — Greek / Turkish / Levantine / Caucasian

26 Aug 2026. Domain: Greek, Turkish, Lebanese, Syrian, Palestinian, Jordanian,
Israeli, Armenian, Georgian.

Instrument: `scripts/probe_knowledge.py` only, which calls `db.search_foods`
with `limit=5` — the same call and the same limit `_candidates` uses. No alias
tier, no model tier. Every number below is pasted from a probe run; nothing is
inferred about what the resolver "would" do except where the real guard
functions (`inverts_meaning`, `state_conflicts`, `unrequested_qualifier`,
`label_absent`) were imported and called directly, which is marked as such.

**659 distinct terms probed.**

```
ask=113 (17%)  auto=110 (17%)  none=247 (37%)  weak=189 (29%)
```

Read `docs/resolution/RECONCILED.md` §1 first. Almost everything here is that
one fact — trigram similarity falls with description length — in local costume.

---

## 0. Summary of what matters

Three things, in order of damage:

1. **`cracked wheat` auto-matches a bread roll**, and no guard blocks it. This
   is the base grain of tabbouleh, kısır, kibbeh and pilav. Measured, not
   assumed. Same class: `walnut` → `Oil, walnut`, `almond` → `Oil, almond`,
   `whole chicken roasted` → `Chicken, chicken roll, roasted`.
2. **A large group of dishes USDA genuinely holds are unreachable by their own
   name.** `molokhia` returns nothing while `Jute, potherb, cooked` sits in the
   table. `baba ganoush` returns nothing while `Eggplant dip` sits in the
   table. `dolmades` returns nothing while three stuffed-grape-leaf rows sit in
   the table. `moussaka` returns `Mousse` while `Eggplant and meat casserole`
   sits in the table. These are reachability gaps, not entity gaps, and they
   are cheap to close.
3. **Defining ingredients score worse than the dishes that contain them.**
   `mint`, `dill`, `egg`, `lemon`, `zucchini`, `walnuts` all return candidate
   lists made of confections and baked goods with the plain food absent or
   last. This is the carbonara/guanciale shape at ingredient level and it
   affects every cuisine, not only this one.

---

## 1. Wrong-confident matches (`auto` onto a semantically wrong row)

The dangerous class: no model is consulted and `upsert_alias` caches the answer
forever, with no command that repoints one.

For each, the guard functions were imported from `nutrai.llm.parse` and called
with the real arguments. Output pasted verbatim.

```
'cracked wheat'         state=None -> 'Roll, wheat or cracked wheat'   blocked_by=NOTHING (auto-match stands)
'cracked wheat'         state=raw  -> 'Roll, wheat or cracked wheat'   blocked_by=NOTHING (auto-match stands)
'walnut'                state=None -> 'Oil, walnut'                    blocked_by=NOTHING (auto-match stands)
'almond'                state=None -> 'Oil, almond'                    blocked_by=NOTHING (auto-match stands)
'whole chicken roasted'            -> 'Chicken, chicken roll, roasted' blocked_by=NOTHING
'orange blossom water'  state=None -> 'Orange Blossom'                 blocked_by=NOTHING (auto-match stands)
'bulgur'                state=None -> 'Bulgur, dry'                    blocked_by=NOTHING (auto-match stands)
'bulgur'                state=cooked -> 'Bulgur, dry'                  blocked_by=['state']
'bulgur'                state=unknown -> 'Bulgur, dry'                 blocked_by=NOTHING (auto-match stands)
```

### 1.1 `cracked wheat` → `Roll, wheat or cracked wheat` (0.636, auto)

```
auto  cracked wheat                      0.636  Roll, wheat or cracked wheat
### cracked wheat  [auto]
    0.636  Roll, wheat or cracked wheat
    0.700  Bread, cracked-wheat
    0.609  Bread, wheat or cracked wheat
    0.500  Bread, pita, wheat or cracked wheat
    0.467  Bread, wheat or cracked wheat, toasted
```

**Every one of the top five is bread.** `Bulgur, dry` (170688, 342 kcal) and
`Bulgur, cooked` (170287, 83 kcal) are in the database and neither appears.
`Roll, wheat or cracked wheat` is 273 kcal/100 g with 6.3 g fat — a bread roll
where the user meant a grain. `label_absent` cannot fire because both of the
user's words are in the description; `unrequested_qualifier` cannot fire for
the same reason. Nothing stops it and the alias is permanent.

This is the single worst finding in the domain, because "cracked wheat" is what
an English-speaking cook calls the bulgur in tabbouleh, kısır, kibbeh and
mercimek köftesi.

### 1.2 `walnut` → `Oil, walnut` (0.636) and `almond` → `Oil, almond` (0.636)

```
auto  walnut                             0.636  Oil, walnut
auto  almond                             0.636  Oil, almond
### walnuts  [ask]
    0.471  Nuts, walnuts, glazed
    0.462  Oil, walnut
    0.462  Walnut oil
    0.444  Nuts, walnuts, english
    0.364  Nuts, walnuts, black, dried
```

| row | kcal/100 g | fat |
|---|---|---|
| `Oil, walnut` | 884 | 100.0 |
| `Nuts, walnuts, english` | 654 | 69.7 (`Walnuts, excluding honey roasted`) |
| `Oil, almond` | 884 | 100.0 |
| `Almonds, NFS` | 598 | 52.5 |

Walnut is a defining ingredient of muhammara, satsivi, pkhali, churchkhela,
baklava and every Levantine nut-filled pastry; almond of Greek amygdalota and
Turkish şekerpare. Singular → oil, plural → glazed (sugared) walnuts at 500
kcal and 32.1 g sugar. The plain nut is reachable only as `walnuts english`
(auto 0.889).

### 1.3 `whole chicken roasted` → `Chicken, chicken roll, roasted` (0.640)

```
### whole chicken roasted  [auto]
    0.640  Chicken, chicken roll, roasted
    0.390  Chicken, roasting, meat only, cooked, roasted
    0.457  Chicken breast, roll, oven-roasted
    0.356  Chicken, roasting, meat and skin, cooked, roasted
    0.348  Chicken, roasting, dark meat, meat only, cooked, roasted
```

`Chicken, chicken roll, roasted` is 164 kcal — a pressed deli loaf.
`Chicken, roasting, meat and skin, cooked, roasted` is 223 kcal and is the
right row; it is in the same candidate list at 0.356, ranked below the wrong
one. The word "roll" is inside a segment that also contains "chicken", which is
why `unrequested_qualifier` does not fire.

### 1.4 `bulgur` → `Bulgur, dry` when the model omits `state`

`Bulgur, dry` is 342 kcal/100 g; `Bulgur, cooked` is 83. A bulgur pilav or a
tabbouleh is eaten cooked, and 200 g of it scored dry is 684 kcal against 166 —
the largest single-item energy error available in this cuisine. `state_conflicts`
does block it, but only when the parse actually emits `state="cooked"`; with
`state` absent or `unknown` the match stands (measured above). Related:
`coarse bulgur` → ask 0.474 `Bulgur, cooked`, `fine bulgur` → weak 0.438
`Bulgur, dry`, `bulgur pilav` → weak 0.412 `Bulgur, dry`.

### 1.5 Minor, but caching

```
auto  orange blossom water               0.714  Orange Blossom
```
`Orange Blossom` (2710647) is 98 kcal/100 g — it is not the flowerwater used by
the tablespoon in maamoul, kanafeh syrup and sahlab. Small absolute error,
permanent alias.

```
auto  fried onion                        0.667  Fried onion rings   (352 kcal, battered)
auto  rice with lentils                  0.640  Lentil curry with rice (118 kcal)
auto  tomato sauce                       0.684  Tomato chili sauce   (92 kcal)
auto  sour cream                         0.647  Sour cream, light
auto  toasted bread                      0.778  Bread, rye, toasted
```
The last four are caught by `unrequested_qualifier` (verified by direct call)
and escalate — that is the guard working. `fried onion` → `Fried onion rings`
and `rice with lentils` → `Lentil curry with rice` are **not** blocked. Fried
onion is the defining garnish of mujadara; `Onions, raw` is 40 kcal and battered
onion rings are 352.

### 1.6 Auto-matches that are correct, for contrast

`spanakopita` 1.000, `baklava` 1.000, `tabbouleh` 1.000, `falafel` 1.000,
`tahini` 1.000, `tzatziki` 0.692, `pita bread` 1.000, `kefir` 1.000,
`turkish coffee` 1.000, `stuffed grape leaves` 0.677, `olive oil` 1.000.
USDA/FNDDS carries a surprising amount of this cuisine correctly named. The
problem is almost never absence; it is the name used to ask.

`garlic sauce` → auto 1.000 `Garlic sauce` deserves a note: that row is
683 kcal/100 g and 74 g fat, which is exactly what toum is. It is right, and it
is right by accident — `toum` itself returns nothing.

---

## 2. Reachability gaps — USDA has the row, the name cannot reach it

The most valuable class. In each case the "found by" line is a probe of the
USDA-shaped phrase, proving the row is present and reachable by *some* query.

### 2.1 `molokhia` / `mulukhiyah` / `jew's mallow` → nothing

```
none  molokhia                           -      (nothing)
none  mulukhiyah                         -      (nothing)
none  jew's mallow                       -      (nothing)
```
Ingredient search on the plant, not the name:
```
169354 | sr_legacy_food | Jute, potherb, cooked, boiled, drained, with salt
168420 | sr_legacy_food | Jute, potherb, cooked, boiled, drained, without salt
168419 | sr_legacy_food | Jute, potherb, raw
2709641 | survey_fndds_food | Bitter melon, horseradish, jute, or radish leaves, cooked
```
Found by:
```
auto  jute potherb                       0.765  Jute, potherb, raw
weak  jute leaves                        0.245  Bitter melon, horseradish, jute, or radish leaves, cooked
```
Molokhia *is* jute (Corchorus olitorius). `Jute, potherb, cooked` is 37 kcal,
3.7 g protein. The row is exact and USDA files it under a botanical name no cook
has ever typed. **High confidence synonym.** Note the ingredient/dish ambiguity:
molokhia as a *dish* is a stew with chicken or rabbit over rice; only the leaf
maps here.

### 2.2 `baba ganoush` / `mutabbal` / `melitzanosalata` → nothing

```
none  baba ganoush                       -      (nothing)
none  baba ghanoush                      -      (nothing)
none  mutabbal                           -      (nothing)
none  melitzanosalata                    -      (nothing)
```
```
2710049 | survey_fndds_food | Eggplant dip
```
Found by:
```
auto  eggplant dip                       1.000  Eggplant dip
ask   roasted eggplant dip               0.619  Eggplant dip
```
One FNDDS row covers all four names. **High confidence** for baba ganoush /
baba ghanoush / mutabbal; melitzanosalata is the Greek cousin (olive oil rather
than tahini) — **medium**.

### 2.3 `dolmades` / `dolma` / `warak enab` / `yaprak sarma` → nothing

```
none  dolmades                           -      (nothing)
none  dolma                              -      (nothing)
none  warak enab                         -      (nothing)
none  yaprak sarma                       -      (nothing)
weak  stuffed vine leaves                0.417  Grape leaves stuffed with rice
```
```
2709064 | survey_fndds_food | Grape leaves stuffed with rice          (168 kcal)
2706621 | survey_fndds_food | Stuffed grape leaves with beef and rice (228 kcal)
2706659 | survey_fndds_food | Stuffed grape leaves with lamb and rice (271 kcal)
```
Found by `auto grape leaves stuffed with rice 1.000`. Three rows, three
fillings, and the four names people actually use reach none of them. **High.**

### 2.4 `vine leaves` ranks a different plant first

```
### vine leaves  [weak]
    0.333  Taro leaves, raw
    0.318  Grape leaves, raw
```
`vine leaves` is the standard British term for grape leaves. The top hit is
taro. `grape leaves` → auto 0.765 `Grape leaves, raw`. **High confidence
synonym**, and the same defect shape as `pork jowl` → `Pork jerky`.

### 2.5 `moussaka` → a single candidate, `Mousse`

```
### moussaka  [ask]
    0.455  Mousse
weak  mousaka                            0.364  Mousse
```
```
2710144 | survey_fndds_food | Eggplant and meat casserole  (96 kcal, 7.1 P, 5.5 F)
```
Found by `auto eggplant and meat casserole 1.000` and `auto eggplant casserole 0.679`.
The candidate list handed to the model tier contains exactly one option and it
is a chocolate dessert. **Medium** on the mapping — 96 kcal is low for a
béchamel-topped moussaka (a restaurant portion is nearer 130–180) — but it is a
different food from `Mousse` in the way that matters.

### 2.6 `shish kebab` → nothing; `shish kabob` → the right rows, called weak

```
none  shish kebab                        -      (nothing)
none  sis kebab                          -      (nothing)
### shish kabob  [weak]
    0.245  Pork shish kabob with vegetables, excluding potatoes
    0.245  Fish shish kabob with vegetables, excluding potatoes
    0.235  Beef shish kabob with vegetables, excluding potatoes
    0.235  Lamb shish kabob with vegetables, excluding potatoes
    0.235  Shrimp shish kabob with vegetables, excluding potatoes
```
Five correct rows, at 0.235–0.245, judged "probably absent". The `kebab`
spelling — the one used everywhere outside American English — reaches none of
them. `lamb kebab` → weak 0.312 `Lamb, chop`; `chicken kebab` → ask 0.500
`Chicken kiev`; `beef kebab` → weak 0.333 `Beef, NFS`. **High confidence
spelling synonym** `kebab ≡ kabob`.

### 2.7 `kibbeh` → nothing; `Kibby, Puerto Rican style` exists

```
none  kibbeh                             -      (nothing)
none  kibbe                              -      (nothing)
none  kubba                              -      (nothing)
### kibby  [weak]
    0.240  Kibby, Puerto Rican style
```
```
2708716 | survey_fndds_food | Kibby, Puerto Rican style  (168 kcal, 8.8 P, 7.2 F, 18.0 C)
```
Puerto Rican kibby arrived with Lebanese migration and is the same construction
— bulgur shell, spiced minced beef, fried. Macros are in the right family.
**Medium**, because kibbeh spans fried, baked (bil sanieh) and raw forms with
very different fat. `kibbeh nayyeh` must **not** map here: raw kibbeh is not a
fried one and the row is a fried one.

### 2.8 `gyro` and `gyros` — the right row, ranked first, called weak

```
weak  gyro                               0.357  Gyro sandwich
weak  gyros                              0.250  Gyro sandwich
weak  gyro meat                          0.357  Meat, NFS
```
`Gyro sandwich` (2706962, 184 kcal) is the only candidate and is correct.
Adding one word destroys it entirely:
```
### lamb gyro  [weak]
    0.375  Lamb, ground
    0.333  Lamb, chop
    0.333  Stew, lamb
    0.300  Lamb, ground, raw
    0.300  Lamb, ground, raw
### chicken gyro  [ask]
    0.474  Chicken, ground
    0.471  Fat, chicken
    0.444  Chicken, tail
    0.444  Chicken, back
    0.444  Chicken skin
```
`Gyro sandwich` is not in either list. `chicken gyro` offers the model chicken
skin and chicken fat. Related: `doner` / `doner kebab` / `donair` / `iskender`
all return nothing, and `Gyro sandwich` is the nearest thing USDA holds to any
of them.

### 2.9 `courgette` / `aubergine` → nothing; and `zucchini` returns cake

```
none  courgette                          -      (nothing)
none  aubergine                          -      (nothing)
weak  grilled aubergine                  0.320  Shrimp, grilled
### zucchini  [ask]
    0.600  Bread, zucchini
    0.562  Muffin, zucchini
    0.529  Zucchini, pickled
    0.429  Cake or cupcake, zucchini
    0.360  Squash, zucchini, baby, raw
```
The vegetable is absent from its own top five. `Squash, summer, zucchini,
includes skin, raw` (169291, 17 kcal) and the cooked rows exist; reachable only
as `squash summer zucchini` (ask 0.564). Zucchini and aubergine are the two
defining vegetables of imam bayıldı, karnıyarık, briam, gemista, kousa mahshi
and musakka. **High confidence** on the British synonyms.

### 2.10 `mint`, `dill`, `egg`, `lemon` — defining ingredients, nonsense lists

```
### mint  [ask]
    0.455  Candy, mint
    0.455  Mint julep
    0.118  Candies, NESTLE, AFTER EIGHT Mints
    0.093  Ice creams, BREYERS, All Natural Light Mint Chocolate Chip
### dill  [weak]
    0.385  Pickles, dill
    0.312  Dill weed, fresh
    0.312  Spices, dill seed
    0.238  Spices, dill weed, dried
    0.161  Pickles, cucumber, dill or kosher dill
### egg  [weak]
    0.400  Bread, egg
    0.364  Bagels, egg
    0.333  Egg, deviled
    0.333  Egg, creamed
    0.333  Egg burrito
### lemon  [ask]
    0.600  Pie, lemon
    0.600  Lemon, raw
    0.400  Lemon peel, raw
    0.375  Lemon juice, raw
    0.353  Cookie, lemon bar
```
`Spearmint, fresh` (173475), `Peppermint, fresh` (173474) and `Spearmint, dried`
(172239) exist — none is reachable from `mint`. `Egg, whole, raw` exists
(`auto egg whole raw 1.000`) and is not in `egg`'s list at all. Mint is the
defining herb of tabbouleh, cacık, ayran and kısır; egg of menemen, shakshuka,
avgolemono and sabich; lemon of avgolemono, fattoush and tabbouleh. Every one of
these lists is led by a confection.

### 2.11 Short words against long right rows — the §1 mechanism, undiluted

```
weak  ghee                               0.227  Butter, Clarified butter (ghee)
weak  scallion                           0.160  Onions, spring or scallions (includes tops and bulb), raw
weak  spring onion                       0.240  Onions, spring or scallions (includes tops and bulb), raw
weak  squid                              0.194  Mollusks, squid, mixed species, raw
weak  lamb ribs                          0.140  Lamb, rib, separable lean and fat, trimmed to 1/8" fat, choice, raw
weak  lamb leg roast                     0.176  Lamb, leg, shank half, separable lean only, trimmed to 1/4" fat, choice, cooked, roasted
weak  lamb shank                         0.190  Lamb, New Zealand, imported, hind-shank, separable lean only, raw
weak  lamb shoulder                      0.222  Lamb, shoulder, arm, separable lean and fat, trimmed to 1/4" fat, choice, raw
weak  feta                               0.417  Cheese, feta
```
`ghee` scores 0.227 against a row that contains the literal string "(ghee)".
Every lamb cut — the meat of kleftiko, mansaf, tandır, mtsvadi and every kebab
in the domain — is `weak` with the correct row at rank 1. `feta` alone is weak
while `feta cheese` is auto 1.000. Nothing needs adding to the database for any
of these; they are pure ranking.

### 2.12 `yoghurt` returns nothing at all

```
none  yoghurt drink                      -      (nothing)
weak  yogurt drink                       0.412  Yogurt, NFS
weak  greek yoghurt                      0.423  Yogurt, Greek, with oats
```
The British spelling falls below the trigram `%` cut-off entirely for the
two-word query. `ayran`, `matsoni`, `tan drink` (→ ask 0.500 `Tamarind drink`)
and `doogh` all depend on this word.

### 2.13 `pomegranate molasses` — right family present, wrong head

```
### pomegranate molasses  [ask]
    0.480  Pomegranate, raw
    0.462  Pomegranates, raw
    0.429  Molasses
    0.429  Molasses
    0.387  Pomegranate juice, 100%
```
`Molasses` (168820) is 290 kcal / 74.7 g carbohydrate — pomegranate molasses is
~290 / ~69. `Pomegranate, raw` is 83 kcal of watery fruit. The correct family
is on the list, ranked below a 3.5× energy error. Same for `pekmez` (none),
`grape molasses` (ask 0.600 `Molasses`), `carob molasses` (ask 0.600), `nar
eksisi` (none). **High** for the molasses mapping.

### 2.14 Other confirmed reachability gaps, in brief

| typed | probe | USDA row that exists |
|---|---|---|
| `tabouli` | weak 0.385 `Tabbouleh` | `Tabbouleh` (rank 1, called probably-absent) |
| `hommos` | none | `Hummus, plain`, `Hummus, home prepared` |
| `filo` | none | `Phyllo dough` (172791) |
| `sultanas` | none | `Raisins` |
| `sesame paste` | ask 0.542 `Seeds, sesame butter, paste` | fine, but `tahina` → ask 0.556 and `hommos`→none |
| `kalamata olives` | weak 0.350 `Olives, NFS` | `Olives, black` (auto 1.000) |
| `bechamel` | none | `White sauce or gravy` (ask 0.571 via `white sauce`) |
| `orzo`, `kritharaki`, `risoni` | none | `Pasta, cooked` (2708357), `Pasta, dry, enriched` |
| `basmati rice` | weak 0.333 `Bread, rice` | `Rice, white, cooked, NS as to fat` |
| `menemen`, `shakshuka` | none | `Egg omelet or scrambled egg, with tomatoes, NS as to fat` (via `scrambled eggs with tomato`, ask 0.500) |
| `mercimek corbasi`, `ezogelin` | none | `Soup, lentil` (auto 1.000 via `lentil soup`) |
| `sutlac` | none | `Pudding, rice` (auto 1.000 via `rice pudding`) |
| `cacik` | none | `Tzatziki dip` (auto 0.692) — same dish |
| `tolma` (Armenian) | none | the three stuffed grape-leaf rows |
| `lahmacun`, `lahmajun` | none | nothing near; see §3 |

---

## 3. Entity gaps — USDA genuinely has nothing

Each of these was searched by ingredient and by category as well as by name.

### 3.1 Halloumi — real gap, with a defensible fallback

```
none  halloumi                           -      (nothing)
none  haloumi                            -      (nothing)
none  hellim                             -      (nothing)
weak  halloumi cheese                    0.400  Cheese ball
weak  grilling cheese                    0.375  Grilled cheese sandwich, NFS
weak  squeaky cheese                     0.400  Cheese, swiss
weak  cyprus cheese                      0.412  Cheese, NFS
```
Category search (`%halloum%`) returns nothing. Every cheese in the table:

| row | kcal | P | F | Na |
|---|---|---|---|---|
| `Cheese, white, queso blanco` | 310 | 20.4 | 24.3 | 704 |
| `Cheese, feta` | 265 | 14.2 | 21.5 | 1139 |
| `Cheese, Feta` (FNDDS) | 273 | 19.7 | 19.1 | 1034 |
| `Cheese, goat, semisoft type` | 364 | 21.6 | 29.8 | 415 |
| `Cheese, ricotta, whole milk` | 150 | 7.5 | 10.2 | 110 |

Halloumi is ~321 kcal, ~25 g fat, ~22 g protein. `Cheese, white, queso blanco`
is the closest on every macro *and* is the same kind of cheese — a fresh,
pressed, non-ripened curd that holds its shape under heat. That is not a
coincidence; it is why both fry. **Medium** (sodium is understated).

I explicitly reject `halloumi → cheese` (§5) and `halloumi → mozzarella`.

### 3.2 Labneh

```
none  labneh                             -      (nothing)
none  labaneh                            -      (nothing)
weak  strained yoghurt cheese            0.302  Babyfood, dinner, macaroni and cheese, strained
weak  yogurt cheese                      0.389  Cheese dip
weak  strained yogurt                    0.444  Babyfood, dessert, banana yogurt, strained
```
`Yogurt, Greek, plain, whole milk` exists (auto 1.000 via
`yogurt greek whole milk plain`). Labneh is Greek yogurt strained further —
roughly 1.5× the concentration. **Medium** as a nutritional fallback, with the
concentration named rather than hidden. Note the "strained" queries all collide
with USDA's babyfood texture vocabulary, which is a separate normalisation bug.

### 3.3 Freekeh / firik

```
none  freekeh                            -      (nothing)
none  firik                              -      (nothing)
weak  green wheat                        0.438  Wheat germ
weak  freekeh soup                       0.412  Soup, fruit
```
`Bulgur, dry` 342 kcal / 12.3 P / 75.9 C; freekeh dry is ~325–350 / 12–14 /
~72, with more fibre. Both are cracked durum wheat. **Medium** — the roasting
and the higher fibre are real differences, and a fallback should say so.

### 3.4 Genuinely absent, and no honest neighbour

`sumac`, `sumak`, `za'atar` (all three spellings), `mahleb` / `mahlab` /
`mahlepi`, `urfa biber`, `pul biber`, `mastic` / `mastiha`, `nigella seed`,
`baharat`, `dukkah`, `bottarga`, `sheep tail fat`, `verjuice`, `yufka`,
`kadayif`, `sahlab`, `jameed`, `kashk` / `kishk`, `shanklish`, `akkawi`,
`nabulsi`, `sulguni`, `matsoni`, `churchkhela`, `tkemali`, `ajika`, `boza`,
`salep`, `arak`, `ouzo`, `retsina`, `tsipouro` — all `none`, all searched by
category, all genuinely absent.

Most are used in gram quantities and are not worth encoding. The two that carry
real mass and deserve a decision are `kashk`/`kishk` (a fermented dried-yogurt
paste, used by the spoonful) and `jameed` (the dried yogurt that mansaf is
built on). Neither has a neighbour I would defend, so neither is proposed.

`aleppo pepper` / `urfa pepper` / `pul biber` are the one spice group where a
fallback is defensible: `Spices, pepper, red or cayenne` exists, and the
quantities are a teaspoon. **Low value, medium correctness** — proposed at
medium only because it prevents a `weak` and costs nothing at those masses.

### 3.5 Georgian and Armenian — a near-total gap

Every Georgian dish probed returns `none`: `khachapuri` (both regional forms),
`khinkali`, `satsivi`, `lobio`, `badrijani`, `pkhali`, `elarji`, `chakhokhbili`,
`chashushuli`, `mtsvadi`, `kharcho`. Armenian: `lahmajun`, `ghapama`,
`matnakash`, `gata`, `soorj`, `tolma` — all `none`.

`Bread, cheese` (408 kcal) exists and is reachable (`georgian cheese bread` →
ask 0.591), which is the only near-neighbour in the whole group. I am **not**
proposing `khachapuri → Bread, cheese`: adjaruli khachapuri is a bread boat
holding sulguni, butter and a raw egg yolk and is nearer 300 kcal/100 g of a
very different composition. Proposing it would be the "overly broad mapping"
failure this audit is supposed to refuse. Recorded as an entity gap.

---

## 4. Findings that are the system working

Reported so they are not re-filed by the next agent:

- `hummus` → ask 0.538 with five hummus rows. Correct list, model decides.
- `brined cheese` → 0.625 but blocked by `unrequested_qualifier` (verified) →
  escalates. `cheese pie` → same. `tomato sauce` → `Tomato chili sauce` blocked.
  `sour cream` → `Sour cream, light` blocked. `toasted bread` → `Bread, rye,
  toasted` blocked. The qualifier guard is earning its place in this cuisine.
- `stuffed grape leaves` → auto 0.677 `Grape leaves stuffed with rice`. Correct:
  rice-only (yalancı / yalantzi) is the default dolma.
- `spanakopita`, `baklava`, `falafel`, `tabbouleh`, `tahini`, `tzatziki`,
  `pita bread`, `kefir`, `turkish coffee`, `olive oil` — all auto and all right.

---

## 5. Deliberately rejected

- **`halloumi → cheese`** (or → `Cheese, NFS`). An over-broad parent. USDA's
  generic cheese row is a cheddar-weighted average; halloumi's distinguishing
  facts are its protein (22 g) and its salt, and the parent carries neither.
  Nutritionally useless, and it would auto-match and cache.
- **`halloumi → mozzarella`.** Both are pasta-filata-adjacent, but low-moisture
  part-skim mozzarella is ~280 kcal with a fifth of halloumi's sodium. The
  resemblance is textural, not nutritional.
- **`pastirma → Beef, cured, pastrami`.** The names share an etymology and that
  is the trap. Pastırma is air-dried, çemen-coated and about 30 g protein per
  100 g; `Beef, cured, pastrami` (147 kcal, 21.8 P, 5.8 F, 1078 Na) is a
  wet-brined smoked navel cut. `Beef, cured, dried` (153 kcal, 31.1 P, 1.9 F,
  2790 Na) is the honest analogue and is what I propose instead.
- **`feta → Cheese, white, queso blanco`** or any "white cheese" generic. Feta
  has its own three rows; the fix is reachability, not a substitute. Probing
  `white cheese` → ask 0.500 `Cheese, white, queso blanco` and `white brined
  cheese` → weak 0.366 `Cheese sandwich, cheddar cheese, on white bread` shows
  how badly a generic route behaves here.
- **`khachapuri → Bread, cheese`.** See §3.5.
- **`tyropita → Spanakopita`.** Tempting — same phyllo, same feta, one
  ingredient different — but spanakopita is 212 kcal with the spinach diluting
  it and tyropita is cheese-dense. `Cheese pastry puffs` and `Danish pastry,
  cheese` are no better. Left as an entity gap.
- **`mansaf → Lamb, ...` anything.** Mansaf is lamb, jameed yogurt sauce and
  rice in proportions nothing in USDA approximates, and jameed itself is absent.
  A component-level parse is the right answer, not a dish mapping.
- **`molokhia (the dish) → Jute, potherb`.** The leaf maps; the stew does not.
  Encoding the dish name onto the leaf row would log a chicken-and-rice meal as
  37 kcal of greens.
- **`sumac → Spices, ...` anything.** No neighbour. A tart dried drupe with no
  analogue in the table; guessing one is the fabrication this system exists to
  avoid.
- **`kibbeh nayyeh → Kibby, Puerto Rican style`.** Raw onto fried.
- **`asure / noah pudding → Noodle pudding`** (currently ask 0.556). A wheat-
  berry, pulse and dried-fruit pudding is not a noodle kugel.

---

## 6. Cross-cutting notes for whoever implements

1. **Transliteration is a first-class axis in this domain and is not modelled
   anywhere.** `kebab`/`kabob`, `borek`/`burek`, `kofte`/`kofta`/`kufte`,
   `zaatar`/`za'atar`/`zatar`, `knafeh`/`kanafeh`/`kunefe`, `tabouli`/
   `tabbouleh`, `hommos`/`hummus`, `yoghurt`/`yogurt`, `sultanas`/`raisins`,
   `courgette`/`zucchini`, `aubergine`/`eggplant`, `vine leaves`/`grape leaves`,
   `filo`/`phyllo`. Trigram handles none of them reliably: `tabouli` → 0.385
   against `Tabbouleh`, `yoghurt drink` → nothing at all.
2. **The single highest-value structural change for this cuisine is not a
   synonym table.** It is §3.3 of RECONCILED — stop max-pooling and
   length-normalise. `feta` 0.417, `ghee` 0.227, `scallion` 0.160, `gyros`
   0.250, `shish kabob` 0.245, `squid` 0.194 all have the correct row at rank 1
   and are graded "probably absent" purely on description length. A synonym
   table papers over each of them one at a time; normalisation fixes the class.
3. **`data_type` matters here.** Nearly every correct dish row in this domain is
   FNDDS (`Spanakopita`, `Tabbouleh`, `Falafel`, `Baklava`, `Gyro sandwich`,
   `Eggplant dip`, `Eggplant and meat casserole`, `Grape leaves stuffed with
   rice`, `Kibby, Puerto Rican style`). RECONCILED D1 is right that precedence
   ranking Foundation first is a bias toward the uneaten form; in this cuisine
   it is a bias toward there being no dish at all.
4. **`_candidates` searching the model's `search_terms` will paper over most of
   §2 and hide it.** A model asked to parse "dolmades" will write
   `search_terms: "grape leaves stuffed with rice"` and the pooled max will
   auto-match at 1.000 with no model consulted at the resolve step — the exact
   shape of the brownie failure in CLAUDE.md. The probe deliberately does not
   pool, which is why these gaps are visible here and invisible in production
   logs. Closing them with real synonyms is what makes that path checkable.
