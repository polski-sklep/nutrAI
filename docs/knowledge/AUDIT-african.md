# Knowledge audit — African foods

26 Aug 2026. **912 terms probed** with `scripts/probe_knowledge.py` against the
live database (13,651 food rows). North, West, East, Central and Southern
African dishes, ingredients, aliases, spellings and variants.

Every line below is pasted probe output or pasted SQL. Nothing here is inferred
from what the resolver "would" do.

```
none = 394 (43%)   weak = 278 (30%)   ask = 141 (15%)   auto = 99 (11%)
```

Read `docs/resolution/RECONCILED.md` §1 first. Almost everything here is the
length correlation in a different costume.

---

## 0. Method note — the probe is not the resolver

`probe_knowledge.py` reports `search_foods` ranking only. `resolve_items` then
applies three guards (`state_conflicts`, `unrequested_qualifier`,
`label_absent`). So an `auto` verdict in the probe is not yet a wrong-confident
match. I ran the guards on **every** `auto` in this domain and separated the
ones that survive:

```
$ python -c "... state_conflicts / unrequested_qualifier / label_absent ..."
0.688 partial pepper soup      -> Soup, pepperpot          none=BLOCK cooked=BLOCK raw=BLOCK
0.652 partial spinach cooked   -> Malabar spinach, cooked  none=BLOCK cooked=BLOCK raw=BLOCK
0.667 ALLPASS avocado          -> Oil, avocado             none=PASS  cooked=PASS  raw=PASS
0.727 ALLPASS pumpkin          -> Pie, pumpkin             none=PASS  cooked=PASS  raw=PASS
0.812 ALLPASS sweet potato     -> Pie, sweet potato        none=PASS  cooked=PASS  raw=PASS
0.647 ALLPASS brown rice       -> Flour, rice, brown       none=PASS  cooked=PASS  raw=PASS
0.636 partial couscous         -> Couscous, dry            none=PASS  cooked=BLOCK raw=BLOCK
0.692 ALLPASS red palm oil     -> Oil, palm                none=PASS  cooked=PASS  raw=PASS
0.667 ALLPASS sorghum grain cooked -> Sorghum grain        none=PASS  cooked=PASS  raw=PASS
```

`pepper soup -> Soup, pepperpot` is blocked on `unrequested_qualifier='pepperpot'`
and is therefore **not** a finding. It is the guard working. Said here so it is
not re-filed by the next reader.

---

## 1. Wrong-confident matches (the dangerous class)

These reach `auto` **and** survive all three guards, so no model is consulted
and an alias is cached that is never re-checked.

### 1.1 `couscous` -> `Couscous, dry` — 3.4x, and it is the North African staple

```
--- couscous auto
   0.636 Couscous, dry    (169699)
   0.583 Couscous, cooked (169700)
   0.389 Couscous, plain, cooked (2708441)
```
```
Couscous, dry     376 kcal   12.76 prot   77.43 carb
Couscous, cooked  112 kcal    3.79 prot   23.22 carb
```

The dry row outranks the cooked row by 0.053 for the bare word. Guard result:

```
PASS  'couscous' state=None   -> Couscous, dry  state_conflicts=None unreq=None label_absent=False
BLOCK 'couscous' state=cooked -> Couscous, dry  state_conflicts='dry'
```

So the whole thing rests on the model emitting `state="cooked"` for a word that
in every kitchen on earth means the cooked grain. When it emits `None` or
`as_sold`, 200 g of couscous logs as **752 kcal instead of 224**. Nothing
downstream catches it: the Atwater check is scale-invariant in mass
(RECONCILED §1.2), and the number is plausible.

The same shape, unstated-state, in this domain: `plantain -> Plantain, raw`,
`cassava -> Cassava, raw`, `tapioca pearls -> Tapioca, pearl, dry` (blocked only
when state is stated).

### 1.2 `sorghum grain cooked` -> `Sorghum grain` — state guard cannot fire

```
auto  sorghum grain cooked               0.667  Sorghum grain
PASS 'sorghum grain cooked' state=cooked -> Sorghum grain  state_conflicts=None
```

`Sorghum grain` (169716) is 329 kcal — the dry grain. It says neither "raw" nor
"cooked", so `state_conflicts` has nothing to contradict. The user explicitly
typed "cooked" and the guard still cannot help. Sorghum porridge (ting, mabele,
sour porridge) is eaten across Southern Africa.

### 1.3 `peanut butter soup` -> `Peanut butter` — 6.8x

```
auto  peanut butter soup                 0.737  Peanut butter
PASS 'peanut butter soup' state=cooked -> Peanut butter  reason=False
```
```
Peanut butter  598 kcal  51.4 fat
Soup, peanut    88 kcal   5.3 fat
```

`Soup, peanut` (2707547) exists and is the right row — for `peanut soup` it
auto-matches at 1.000. Adding the word "butter", which is how Ghanaians name
nkate nkwan, swaps a soup for a jar of nut paste. A 400 g bowl logs 2,392 kcal
instead of 352.

### 1.4 `bean cake fried` / `akara bean cake` -> `Bean cake`

```
auto  akara bean cake                    0.625  Bean cake
auto  bean cake fried                    0.625  Bean cake
PASS 'bean cake fried' state=cooked -> Bean cake  reason=False
```
```
 2707409 | Bean cake | 414 kcal | 5.80 prot | 21.41 fat | 49.88 carb
```

5.8 g protein and 49.9 g carbohydrate is a sweet bean-paste pastry, not akara.
Akara is fried cowpea paste: roughly 250 kcal, 7–8 g protein, ~15 g carb. The
name collides exactly and the row is nutritionally the opposite shape.
Bare `akara` gets `Okara` (soy pulp) at 0.333 — weak, so that one escalates.

### 1.5 `red palm oil` -> `Oil, palm` — right calories, asserted-zero vitamin A

```
auto  red palm oil                       0.692  Oil, palm
PASS 'red palm oil' state=as_sold -> Oil, palm  reason=False
```
```
 1104 | Vitamin A, IU                | 0
 1106 | Vitamin A, RAE               | 0
 1107 | Carotene, beta               | 0
 1109 | Vitamin E (alpha-tocopherol) | 15.94
```

`Oil, palm` is the refined product. Unrefined red palm oil is the richest plant
source of provitamin A there is. Invariant 6 says a *missing* nutrient is
skipped rather than zeroed — but this row does not omit beta-carotene, it
**asserts 0**. So a West African diet built largely on red palm oil records a
hard zero for the nutrient that oil is eaten for, at identical energy and fat,
which means no cross-check anywhere can notice. This is the cleanest example in
the domain of a match that is right on macros and wrong on the thing that
matters.

### 1.6 Cross-domain, but eaten daily in this one

Not African-specific; filed because avocado is a daily food in Kenya and
Ethiopia, pumpkin and pumpkin leaves are staples across East and Southern
Africa, and orange-fleshed sweet potato is a public-health crop in Uganda and
Nigeria.

```
--- avocado auto
   0.667 Oil, avocado (173573)      884 kcal
   0.667 Avocado, raw (2709223)     160 kcal
--- pumpkin auto
   0.727 Pie, pumpkin (2708011)     249 kcal   327 RAE
   0.667 Pumpkin, raw (168448)       26 kcal   426 RAE
--- sweet potato auto
   0.812 Pie, sweet potato (2708012) 269 kcal  189 RAE
   0.765 Sweet potato, NFS (2709697) 115 kcal  684 RAE
--- brown rice auto
   0.647 Flour, rice, brown (1104812) 368 kcal
   [Rice, brown, cooked, no added fat (2708414) 123 kcal — not in top 5]
```

`avocado` is a **tie at 0.667** decided by the ordering tail, and the oil wins.
5.5x. `pumpkin -> pie` is 9.6x. `sweet potato -> pie` understates vitamin A by
3.6x while overstating energy by 2.3x — the two errors point opposite ways, so
neither is visible in a day total.

### 1.7 `spinach cooked` — the guard promotes a worse row

```
--- spinach cooked auto
   0.652 Malabar spinach, cooked
   0.652 Spaghetti, spinach, cooked
   0.517 Spinach, cooked, as ingredient
   ...
BLOCK 'spinach cooked' -> Malabar spinach, cooked   unreq='Malabar spinach'
PASS  'spinach cooked' -> Spaghetti, spinach, cooked reason=False
```

`unrequested_qualifier` correctly rejects Malabar spinach (a different species),
and the next survivor is **spinach pasta**. This is the exact failure the
docstring of `unrequested_qualifier` already records for
`Spaghetti, spinach, cooked` vs `Spaghetti squash` — reappearing from the other
direction. Relevant here because every African greens dish (efo riro, morogo,
imifino, sukuma wiki, mchicha) is logged as "spinach cooked" by people who do
not know the local leaf's English name.

---

## 2. Reachability gaps — USDA has the row, the query cannot get there

The most valuable class, and the one the length correlation explains directly.

### 2.1 The row is the *only* candidate and is still called weak

```
weak  injera                             0.304  Injera, Ethiopian bread
weak  teff                               0.417  Teff, cooked
weak  fonio                              0.300  Fonio, grain, dry, raw
weak  ghee                               0.227  Butter, Clarified butter (ghee)

--- injera weak n=1
   0.304 Injera, Ethiopian bread (2707796)
--- ghee weak n=2
   0.227 Butter, Clarified butter (ghee) (171314)
   0.227 Ghee, clarified butter (2710168)
```

`injera` returns exactly one row, that row is named "Injera", and the verdict is
`weak` — which `config.py` documents as "the point past which the database
itself looks like the problem". The database is not the problem. The word is
six letters and the description is 23.

`ghee` scores **0.227** against a row whose first word is "Ghee". These four are
the domain's proof of RECONCILED §1: a query that is an exact prefix of the
description's first segment cannot be a weak match, and the scorer has no way to
express that.

### 2.2 The right row is not in the candidate list at all

```
--- collard greens weak n=10
   0.375 Poke greens, cooked
   0.360 Mustard greens, raw
   0.360 Beet greens, cooked
   0.360 Greens, canned, cooked
   0.333 Collards, raw
   0.308 Chicory greens, raw
   0.300 Dandelion greens, cooked
none  sukuma wiki                        -      (nothing)
none  sukuma                             -      (nothing)
ask   collard cooked greens              0.583  Poke greens, cooked
```

`Collards, cooked, boiled, drained, without salt` (170407) and
`Collards, NS as to form, cooked` (2709579) both exist and appear in **none** of
the ten candidates. Sukuma wiki is the single most-eaten vegetable dish in
Kenya; the model tier cannot rescue it because the right row was never handed
over.

```
--- groundnut weak n=16
   0.429 Groundhog
   0.400 Ham, ground
   0.375 Lamb, ground / Veal, ground / Beef, ground / Pork, ground
   0.316 Emu, ground, raw
weak  groundnut oil                      0.333  Groundhog
weak  groundnut stew                     0.316  Groundhog
weak  groundnut soup                     0.350  Soup, peanut
ask   groundnuts raw                     0.500  Emu, ground, raw
```

Sixteen candidates for `groundnut`, not one of them a peanut. "Groundnut" is the
standard English word for peanut in Nigeria, Ghana, Gambia, Malawi and Zambia —
mafe, domoda, nkate nkwan, tigadegena all name it. `Peanuts, raw` (2515376)
auto-matches at 1.000 for `peanuts raw`. The gap is one word.

```
--- maize weak n=2
   0.078 Corn flour, whole-grain, blue (harina de maiz morado)
   0.300 Mai Tai
none  maize meal                         -      (nothing)
none  maize porridge                     -      (nothing)
weak  maize flour                        0.196  Corn flour, whole-grain, blue (harina de maiz morado)
```

Two candidates for the staple grain of the continent, and one of them is a
cocktail. USDA says "corn"; every English-speaking African market says "maize".

```
--- garden eggs weak n=5
   0.148 Shrimp garden salad, shrimp, lettuce, eggs, vegetables ...
   0.146 Shrimp garden salad, shrimp, lettuce, eggs, tomato ...
   0.138 Seafood garden salad ...
   0.318 Cress, garden, raw
ask   african eggplant raw               0.619  Eggplant, raw
```

No eggplant row anywhere in the list. The tokeniser has split a compound name
and matched both halves against a salad.

### 2.3 The wrong part of the right plant

```
--- cowpeas weak n=21
   0.348 Cowpeas, leafy tips, raw
   0.250 Cowpeas, catjang, mature seeds, raw
   0.216 Cowpeas (blackeyes), immature seeds, raw
   0.145 Cowpeas, common (blackeyes, crowder, southern), mature seeds, raw
weak  cowpeas cooked                     0.277  Cowpeas, leafy tips, cooked, boiled, drained, with salt
```

The leaf row wins because "leafy tips" is short. The seed — the bean in every
ewa, waakye, red-red, akara and moin moin — sits at 0.145. Length again, and the
error is 22 kcal against 336 dry.

```
--- pigeon peas weak n=3
   0.306 Pigeon peas (red gram), mature seeds, raw
   0.204 Pigeon peas (red gram), mature seeds, cooked, boiled, with salt
   0.193 Pigeon peas (red gram), mature seeds, cooked, boiled, without salt
```

Three candidates, all three correct, all three below the weak floor.

### 2.4 Same food, different English

Each of these returns nothing while a perfectly good row sits in the table:

| typed | verdict | USDA row that exists |
|---|---|---|
| `prawns`, `prawn` | none | `Shrimp, NFS` (2706360), `Shrimp, dried` (2706366) |
| `okro` | none | `Okra, cooked, boiled, drained, without salt` (169261) |
| `manioc` | none | `Cassava, cooked` (2709564) |
| `cocoyam` | none | `Taro, cooked` (2709567) |
| `linseed` | none | `Seeds, flaxseed` (169414) |
| `omelette` | none | `Egg, whole, cooked, omelet` (172185); `omelet` itself only reaches it at 0.292 |
| `guinea fowl` | none | `Guinea hen, meat only, raw` (174471) |
| `molokhia`, `mloukhia`, `melokhia`, `mulukhiyah`, `molokheya`, `ewedu` | none | `Jute, potherb, cooked, boiled, drained, without salt` (168420) |

`molokhia` is the strongest of these. `Corchorus olitorius` is the plant; USDA
files it as "Jute, potherb". Egyptian molokhia, Levantine mloukhieh and Yoruba
ewedu are the same leaf, and the query reaches it only if you type the word
"jute" — which nobody does:

```
auto  jute potherb                       0.765  Jute, potherb, raw
none  molokhia                           -      (nothing)
none  mulukhiya                          -      (nothing)
weak  jute mallow                        0.304  Candy, marshmallow
```

`jute mallow` — the standard English common name — lands on a **marshmallow**.

### 2.5 Offal, and the length penalty at its worst

Offal is central to nkwobi, isi ewu, mutura, kamounia and dulet.

```
weak  lung                               0.091  Lamb, variety meats and by-products, lungs, raw
weak  suet                               0.119  Beef, variety meats and by-products, suet, raw
weak  spleen                             0.159  Veal, variety meats and by-products, spleen, raw
weak  kidney beef                        0.239  Beef, variety meats and by-products, kidneys, raw
weak  snails                             0.238  Mollusks, snail, raw
weak  oxtail                             0.429  Beef, oxtails
none  cow foot                           -      (nothing)
none  cow leg                            -      (nothing)
none  beef intestine                     -      (nothing)
```

`lung` at **0.091** against the row that is literally lungs. USDA's
"variety meats and by-products" prefix is 34 characters of pure length penalty
applied to every organ meat in the database.

### 2.6 Game

```
weak  antelope                           0.391  Game meat, antelope, raw
none  springbok / kudu / impala / warthog / crocodile meat  -  (nothing)
auto  ostrich                            1.000  Ostrich
```

`Game meat, antelope, raw` (175292) exists and is a defensible row for springbok,
kudu and impala. Ostrich is very well covered (18 rows).

---

## 3. Entity gaps — searched by ingredient and by category, nothing there

Each was searched by name, by ingredient and by category before filing.

**Stiff maize porridge.** `ugali`, `posho`, `sadza`, `nsima`, `nshima`, `pap`,
`mieliepap`, `putu pap`, `phutu`, `umphokoqo`, `isitshwala`, `mealie pap`,
`maize porridge`, `stiff maize porridge`, `cornmeal porridge` — every one of them
`none` or `weak` on a non-porridge row. Search:

```
=== porridge   (no rows)
=== polenta    (no rows)
Cornmeal mush, NS as to fat / fat added / no added fat   (2708373/5/4)
```
`Cornmeal mush, no added fat` is 58 kcal/100 g — a thin American breakfast mush
at roughly 13% dry matter. Ugali is made at 1:2 to 1:3 meal-to-water and runs
110–130 kcal/100 g. **The nearest USDA row understates the most-eaten dish in
East and Southern Africa by about half.** This is the largest single gap in the
domain and it is not fixable by an alias; it needs decomposition to the dry meal
(see §4) or a `user_product` row.

**Fermented locust bean** (iru, dawadawa, soumbala, netetou, ogiri). All `none`.
Nearest by name is `Gums, seed gums (includes locust bean, guar)` at 0.353 —
carob galactomannan from *Ceratonia siliqua*, a thickener from a different
continent and a different plant from *Parkia biglobosa*. Deliberately not mapped;
see §5.

**Edible insects.** `mopane worms`, `termites`, `grasshopper`, `caterpillar
edible`, `locusts` — all `none`. Category searches `insect`, `cricket` return
**zero rows**. USDA holds no entomophagy data at all. Genuine.

**Others with no row and no near neighbour:** moringa, rooibos, honeybush,
camel milk, camel meat, tigernut/chufa, kola nut, bitter kola, bambara
groundnut, niger seed/noug, safou/African pear, bush mango (ogbono/*Irvingia*),
enset/kocho, African nightshade, cleome, teff `injera` starter cultures.

**Spice blends.** berbere, ras el hanout, harissa, dukkah, chermoula, suya
spice/yaji, mitmita, awaze, tabil, shito, peri-peri, chakalaka — none. USDA
carries single spices, not blends; `berbere seasoning` returns
`Spices, poultry seasoning` at 0.323.

**Every North African dish name.** tagine, harira, pastilla, msemen, baghrir,
rfissa, mechoui, zaalouk, briouat, seffa, sellou, maakouda, harcha, mrouzia,
loubia, chakchouka, brik, lablabi, ojja, bazin, asida, sfenj, makroudh, koshari,
ful medames, ta'ameya, hawawshi, feteer, umm ali, konafa — all `none` except
`Basbousa` (2708045), which USDA does carry, at 1.000.

---

## 4. Dishes worth decomposing rather than matching

`Fufu` (2709568, 166 kcal) is the precedent: USDA does carry a few African
composites. Where it does not, the honest route is `dish_ingredient`, not a
one-row analogue.

- **ugali / pap / sadza / nsima** = white maize meal + water.
  `Cornmeal, degermed, enriched, white` (168922) at 25–33 g dry per 100 g served.
- **jollof rice** = `Rice, white, long-grain, regular, enriched, cooked` (168878)
  + `Tomato, paste, canned, without salt added` (2685580) + vegetable or red
  palm oil + stock.
- **waakye** = cooked rice + cooked cowpeas. `Beans and brown rice` (2709033)
  exists and is close in shape.
- **egusi soup** = `Seeds, watermelon seed kernels, dried` (169407) + red palm
  oil + leafy greens + meat/fish.
- **suya** = `Beef, steak, NFS` (2705824) grilled + a peanut-flour spice crust.
- **doro wat** = chicken + `Butter, Clarified butter (ghee)` (171314) + onion +
  berbere; the butter is the calorie term and is the part currently unreachable
  (`niter kibbeh` -> none; `ghee` -> 0.227).

---

## 5. Deliberately NOT encoded

Recorded so nobody re-proposes them.

- **iru / dawadawa / locust bean -> `Gums, seed gums (includes locust bean, guar)`.**
  Wrong plant, wrong continent, wrong food class. A fermented seed condiment used
  a tablespoon at a time is not a galactomannan thickener. Currently 0.353, and
  it should stay unreachable rather than become reachable and wrong.
- **masa -> `Masa harina, cooked`** (currently 0.263). Nigerian masa is a
  fermented *rice* cake; masa harina is nixtamalised *maize* flour. Identical
  word, different grain.
- **ogbono -> egusi / watermelon seed.** Both are soup-thickening seeds and they
  are not interchangeable: *Irvingia* kernels are ~67% fat and near 700 kcal,
  melon seed ~47% fat and 557. Conflating them because both are "African seed
  thickeners" is the over-broad failure.
- **rooibos -> any tea row.** Rooibos is *Aspalathus linearis*, not
  *Camellia sinensis*, and carries no caffeine. Zero-energy either way, so the
  mapping buys nothing and imports a wrong identity into a cached alias.
- **berbere / ras el hanout / suya spice -> any single spice row.** A blend is
  not a spice. `Spices, poultry seasoning` is not berbere in any sense.
- **biltong -> `Beef, cured, dried` (170604).** 153 kcal and 1.9 g fat is
  air-dried *lean* sliced beef; biltong is a whole muscle dried with its fat cap
  and runs 250–350 kcal. Too lean by half. `Beef jerky` is closer on energy but
  carries 9 g sugar per 100 g against biltong's ~0, so it is a *fallback with a
  stated caveat*, not a synonym.
- **morogo / imifino -> any one leaf row.** These are collective nouns covering
  amaranth, cowpea leaf, pumpkin leaf and blackjack, chosen by season. Picking
  one species and caching it is an invented fact.
- **mopane worm -> any meat row.** Chitin is counted as fibre in some methods and
  not others, and the amino profile is not that of muscle. No defensible row
  exists; leave it as a `user_product`.
- **`pap` is ambiguous across regions** and should never be auto-aliased: in
  South Africa it is stiff maize porridge (~110 kcal), in Nigeria it is ogi/akamu,
  a thin fermented maize gruel (~40 kcal). Same word, 3x apart.

---

## 6. What actually works

Worth recording so the fixes do not break it.

```
auto  fufu                               1.000  Fufu
auto  basbousa                           1.000  Basbousa
auto  palm oil                           1.000  Oil, palm
auto  cassava flour                      1.000  Flour, cassava
auto  plantain chips                     1.000  Plantain chips
auto  dried shrimp                       1.000  Shrimp, dried
auto  chicken feet                       1.000  Chicken feet
auto  ostrich                            1.000  Ostrich
auto  goat                               1.000  Goat
auto  sorghum flour                      1.000  Flour, sorghum
auto  millet                             1.000  Millet
auto  baobab powder                      1.000  Baobab powder
auto  peanut soup                        1.000  Soup, peanut
auto  tahini                             1.000  Tahini
auto  amaranth leaves                    0.800  Amaranth leaves, raw
auto  sweet potato leaves                0.833  Sweet potato leaves, raw
auto  pumpkin leaves                     0.789  Pumpkin leaves, raw
auto  hibiscus tea                       0.812  Tea, hot, hibiscus
auto  roselle                            0.727  Roselle, raw
ask   fluted pumpkin leaves              0.577  Pumpkin leaves, raw
auto  boiled plantain                    0.625  Plantains, green, boiled
ask   fried plantain                     0.609  Plantains, green, fried
```

FNDDS carries more African food than one expects — Fufu, Injera, Basbousa,
Baobab powder, Fonio, Teff, Roselle, Goat, Chicken feet, Shrimp dried,
Jute potherb, Sweet potato leaves, Pumpkin leaves, Amaranth leaves. Most of the
damage in this domain is not that the data is missing. **It is that the data is
there and the name does not reach it.**

---

## 7. The one structural recommendation

Four separate findings above — `injera` 0.304, `ghee` 0.227, `teff` 0.417,
`fonio` 0.300 — are the same fact: **the query is an exact prefix of the
description's first segment and the score is below the weak floor.** No
threshold move fixes this without wrecking everything else, and RECONCILED §3.3
(stop max-pooling, length-normalise) is the right instrument. A cheap interim
that costs nothing elsewhere: when the query equals or prefixes the first
comma-segment of a candidate, that candidate cannot be scored `weak`.

The second structural fact is §2.5: USDA's `variety meats and by-products,`
prefix is 34 characters of length penalty on every organ meat. Stripping known
USDA boilerplate segments before scoring (`variety meats and by-products`,
`mature seeds`, `Game meat`, `Crustaceans`, `Mollusks`) is the brand-stripping
argument of RECONCILED §3.2 applied to the national rows instead of the
branded ones.
