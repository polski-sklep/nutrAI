# AUDIT-taxonomy-fallback

28 Aug 2026. Cross-cutting domain: **when the exact food is unavailable, is the
fallback semantically and nutritionally reasonable?**

Method: every term below went through `scripts/probe_knowledge.py` against the
live `food` table, read-only. Where a fallback is proposed, the candidate row's
nutrients were pulled with a read-only SELECT and are quoted per 100 g, because
a taxonomy link that is not checked against numbers is a guess wearing a
category label.

Verdicts: `none` (nothing returned) | `weak` (< 0.45) | `ask` (0.45–0.62, goes
to the model tier — the system working) | `auto` (>= 0.62, taken with no model
consulted — the dangerous one when wrong, because it caches an alias forever).

## Verdict counts

413 terms in ten batches, plus a systematic scan of 893 `Dish, ingredient` rows.

| batch | terms | none | weak | ask | auto |
|---|---|---|---|---|---|
| 1 cured/salted pork | 35 | 10 | 6 | 10 | 9 |
| 2 fresh cheeses | 33 | 17 | 2 | 8 | 6 |
| 3 fermented soy, nut/seed pastes | 30 | 5 | 8 | 8 | 9 |
| 4 animal fats, offal | 40 | 4 | 11 | 7 | 18 |
| 5 chilli products | 36 | 12 | 16 | 6 | 2 |
| 6 tubers, starches, grains | 55 | 9 | 12 | 14 | 20 |
| 7 whole fish | 39 | 3 | 18 | 14 | 4 |
| 8 leafy greens | 43 | 9 | 14 | 4 | 16 |
| 9 aged cheeses, dairy grades | 50 | 16 | 15 | 8 | 11 |
| 10 dishes vs defining ingredients | 52 | 18 | 14 | 8 | 12 |
| **total** | **413** | **103 (25%)** | **116 (28%)** | **87 (21%)** | **107 (26%)** |

Findings, proposals and rejections are at the end of the file, after the ten
batch sections.

---

## Batch 1 — cured and salted pork (34 terms)

```
none  guanciale                          -      (nothing)
none  pancetta                           -      (nothing)
ask   lardo                              0.571  Lard
none  speck                              -      (nothing)
ask   salt pork                          0.500  Pork, cured, salt pork, raw
weak  streaky bacon                      0.346  Bacon strip, meatless
weak  pork jowl                          0.400  Pork jerky
none  coppa                              -      (nothing)
none  capocollo                          -      (nothing)
none  bresaola                           -      (nothing)
auto  prosciutto                         0.733  Ham, prosciutto
ask   prosciutto crudo                   0.524  Ham, prosciutto
weak  jamon serrano                      0.308  Peppers, serrano, raw
none  culatello                          -      (nothing)
none  lonza                              -      (nothing)
ask   pork cheek                         0.450  Liver cheese, pork
weak  cured pork jowl                    0.440  Pork, cured, salt pork, raw
auto  cured pork belly                   0.647  Pork, belly
auto  pork belly                         1.000  Pork, belly
auto  pork belly raw                     0.714  Pork, fresh, belly, raw
ask   smoked pork belly                  0.611  Pork, belly
ask   bacon                              0.600  Bacon bits
weak  bacon raw                          0.429  Basil, raw
auto  salami                             0.636  Salami, NFS
auto  chorizo                            1.000  Chorizo
ask   cured pork                         0.550  Pork, cured, salt pork, raw
auto  cured beef                         0.688  Beef, cured, dried
ask   air dried beef                     0.550  Beef, cured, dried
auto  dried beef                         0.688  Beef, cured, dried
ask   smoked ham                         0.550  Ham, honey, smoked, cooked
auto  ham                                1.000  Ham
weak  pork fatback                       0.333  Pork, fresh, backfat, raw
ask   back fat                           0.562  Fat back, cooked
none  salo                               -      (nothing)
none  slanina                            -      (nothing)

ask=10 (29%)  auto=9 (26%)  none=10 (29%)  weak=6 (17%)
```

The rows that exist, with numbers per 100 g (read-only SELECT):

```
168269 sr_legacy  Pork, fresh, variety meats and by-products, jowl, raw
    kcal=655  fat=69.61  prot=6.38  satfat=25.26  Na=25     chol=90
168287 sr_legacy  Pork, cured, salt pork, raw
    kcal=748  fat=80.50  prot=5.05  satfat=29.38  Na=2684   chol=86
167811 sr_legacy  Pork, fresh, backfat, raw
    kcal=812  fat=88.69  prot=2.92  satfat=32.21  Na=11     chol=57
2705892 fndds     Fat back, cooked
    kcal=750  fat=81.93  prot=2.68  satfat=31.34  Na=2039   chol=84
168277 sr_legacy  Pork, cured, bacon, unprepared
    kcal=393  fat=37.13  prot=13.66 satfat=12.62  Na=751    chol=66
2705879 fndds     Ham, prosciutto
    kcal=195  fat=8.32   prot=27.80 satfat=2.78   Na=2695   chol=70
```

### The cured-pork axis USDA does not encode: cut vs cure

The whole family splits on two independent axes and USDA's descriptions carry
only one of them cleanly.

* **Fat fraction is set by the cut**: jowl 69.6 g, belly ~53 g, backfat 88.7 g,
  loin (lonza/coppa/bresaola territory) under 10 g.
* **Sodium is set by the cure**: fresh jowl 25 mg, salt pork 2684 mg,
  prosciutto 2695 mg, fresh backfat 11 mg against cooked fat back 2039 mg.

A fallback that gets the cut right and the cure wrong is off by **two orders of
magnitude on sodium**. A fallback that gets the cure right and the cut wrong is
off by a factor of 8 on fat and 3.4 on energy. There is no row that is right on
both for guanciale, and the file should say so rather than pick one.

**Measured on a real portion.** 30 g of guanciale in a carbonara (true ≈ 200
kcal, 21 g fat, ≈450 mg Na):

| fallback | kcal | fat | Na |
|---|---|---|---|
| `Pork, fresh, ... jowl, raw` | 197 | 20.9 g | **7 mg** |
| `Pork, cured, salt pork, raw` | 224 | 24.2 g | **805 mg** |
| `Pork, cured, bacon, unprepared` | **118** | **11.1 g** | 225 mg |

Bacon — the fallback a person would reach for first, and the one the
`bacon cured pork` phrasing in CLAUDE.md already lands on — is the **worst** of
the three on energy, understating a fatty cured pork by 40%.


---

## Batch 2 — fresh cheeses by make (33 terms)

```
auto  paneer                             0.636  Palak Paneer
auto  queso fresco                       1.000  Queso Fresco
none  halloumi                           -      (nothing)
weak  feta                               0.417  Cheese, feta
ask   ricotta                            0.533  Cheese, Ricotta
auto  cottage cheese                     0.778  Cheese, cottage, NFS
none  twarog                             -      (nothing)
none  twaróg                             -      (nothing)
none  chhena                             -      (nothing)
none  labneh                             -      (nothing)
none  labaneh                            -      (nothing)
none  quark                              -      (nothing)
none  fromage blanc                      -      (nothing)
none  mascarpone                         -      (nothing)
none  burrata                            -      (nothing)
ask   mozzarella                         0.500  Cheese, Mozzarella, NFS
weak  fresh mozzarella                   0.394  T.G.I. FRIDAY'S, fried mozzarella
none  bocconcini                         -      (nothing)
auto  cream cheese                       1.000  Cheese, cream
ask   farmer cheese                      0.609  Cottage cheese, farmer's
ask   curd cheese                        0.579  Soybean, curd cheese
ask   white cheese                       0.500  Cheese, white, queso blanco
auto  brined cheese                      0.625  Cheese, brie
none  mizithra                           -      (nothing)
none  anari                              -      (nothing)
none  akawi                              -      (nothing)
none  nabulsi                            -      (nothing)
ask   queso blanco                       0.500  Cheese, white, queso blanco
none  requeson                           -      (nothing)
auto  panela cheese                      0.647  Cheese, paneer
none  skyr                               -      (nothing)
ask   fresh cheese                       0.591  Cheese, fresh, queso fresco
ask   soft cheese                        0.545  Cheese, goat, soft type

ask=8 (24%)  auto=6 (18%)  none=17 (52%)  weak=2 (6%)
```

### First correction to my own method: the raw `auto` verdict overstates the danger

`probe_knowledge.py` reports the head of the candidate list. `resolve_items`
takes the best candidate **that survives four guards**. I reproduced that step
(scratchpad `eff.py`, calling the shipped `inverts_meaning`, `state_conflicts`,
`unrequested_qualifier`, `label_absent` directly) and the three alarming autos
in this batch all escalate instead:

```
'paneer': effective=escalates   (head 0.636 Palak Paneer)
    0.636 Palak Paneer -> BLOCKED:qualifier
'brined cheese': effective=escalates   (head 0.625 Cheese, brie)
    0.625 Cheese, brie -> BLOCKED:qualifier
    0.625 Cheese, Brie -> BLOCKED:qualifier
'panela cheese': effective=escalates   (head 0.647 Cheese, paneer)
    0.647 Cheese, paneer -> BLOCKED:qualifier
'salami': effective=AUTO -> Salami, NFS
'chorizo': effective=AUTO -> Chorizo
'prosciutto': effective=AUTO -> Ham, prosciutto
'cured beef': effective=AUTO -> Beef, cured, dried
'dried beef': effective=escalates   (head 0.688 Beef, cured, dried)
    0.688 Beef, cured, dried -> BLOCKED:qualifier
```

So `paneer` → `Palak Paneer` — an ingredient resolving to the *dish it appears
in* — is caught. Every `auto` I report from here on has been through this
harness; unqualified "auto" below means it survived the guards.

### FINDING — the paneer row itself is not paneer

`Cheese, paneer` exists and is the row a taxonomy would point at:

```
2705740 [survey_fndds_food] Cheese, paneer
    kcal=299  prot=15.86  fat=15.52  carb=22.46  sugar=23.33  Na=185  Ca=597
```

**22.5 g of carbohydrate and 23 g of sugar per 100 g.** Paneer is an acid-set
curd drained of whey; the lactose leaves with the whey. Real paneer is ~1–2 g
carb. Whole milk itself is 4.8 g/100 g, so no drained curd can reach 22 g —
that is a milk-solids (khoya) profile wearing a paneer label. The
carb/sugar figures are also internally inconsistent (sugar > total carb).

This matters more than a missing synonym. Every proposal of the form
`X -> Cheese, paneer` inherits a 20 g/100 g phantom sugar load. On a 150 g
saag paneer portion that is **34 g of sugar** attributed to a food containing
almost none — against a daily ceiling. **Do not use this row as any fallback
target, including for paneer itself.** The honest fallback for paneer is
`Cheese, queso fresco` / `Cheese, white, queso blanco`, which are the same
make (acid- or acid+rennet-set, unaged, unripened, pressed):

```
172223 Cheese, fresh, queso fresco     kcal=299 prot=18.09 fat=23.82 carb=2.98  Na=751
172224 Cheese, white, queso blanco     kcal=310 prot=20.38 fat=24.31 carb=2.53  Na=704
```

Right on make, right on macros, **wrong on sodium**: paneer is unsalted (~20 mg)
and both Mexican fresh cheeses are salted to ~700 mg. Same shape as the
guanciale problem — the fallback preserves the *make* and loses the *cure*.

### The fresh-cheese family splits three ways, and no single parent survives

All figures below are measured from `food_nutrient`, per 100 g. Rows marked
"no row" returned `none` from the probe — USDA has no entry at all.

| word | set by | finish | USDA row | kcal | prot | fat | Na |
|---|---|---|---|---|---|---|---|
| queso fresco | acid+rennet | pressed, salted | `Cheese, fresh, queso fresco` 172223 | 299 | 18.09 | 23.82 | 751 |
| queso blanco | acid | pressed, salted | `Cheese, white, queso blanco` 172224 | 310 | 20.38 | 24.31 | 704 |
| paneer, chhena | acid | pressed, **unsalted** | `Cheese, paneer` 2705740 — unusable, see above | 299 | 15.86 | 15.52 | 185 |
| feta | rennet | **brined** | `Cheese, feta` 173420 | 265 | 14.21 | 21.49 | **1139** |
| halloumi, akawi, nabulsi | rennet | brined, then grilled | no row | | | | |
| cottage | acid | drained curd, salted | `Cheese, cottage, lowfat, 1% milkfat` 173417 | **72** | 12.39 | **1.02** | 406 |
| ricotta, mizithra, anari, requesón | whey, heat | unpressed | `Cheese, ricotta, whole milk` 170851 | 150 | 7.54 | 10.18 | **110** |
| ricotta (part skim) | | | 171248 | 138 | 11.39 | 7.91 | 99 |
| twaróg, quark, fromage blanc, skyr, labneh | acid | drained, unsalted | **no row** | | | | |
| mozzarella (for contrast) | rennet, pasta filata | | 171244 | 295 | 23.75 | 19.78 | 666 |

A `fresh cheese` parent spans **72 to 310 kcal, 1.0 to 24.3 g fat and 110 to
1139 mg sodium** across rows that actually exist. It
is nutritionally empty and must not be encoded. The rows in this batch that
`fresh cheese` (0.591) and `soft cheese` (0.545) reach —
`Cheese, fresh, queso fresco` and `Cheese, goat, soft type` — are both in the
wrong sub-family for most of the words a person would type.


---

## Batch 3 — fermented soy, and nut/seed pastes (30 terms)

```
auto  miso                               1.000  Miso
ask   miso paste                         0.455  Miso
ask   red miso                           0.556  Miso
ask   white miso                         0.455  Miso
none  doenjang                           -      (nothing)
none  gochujang                          -      (nothing)
auto  tempeh                             1.000  Tempeh
auto  natto                              1.000  Natto
none  douchi                             -      (nothing)
weak  fermented black beans              0.440  Black beans, NFS
none  furu                               -      (nothing)
weak  fermented bean curd                0.320  Soybean curd
weak  soybean paste                      0.444  Soybean oil
weak  fermented soybean paste            0.324  Bean paste, sweetened
ask   tofu                               0.455  Tofu, fried
auto  tahini                             1.000  Tahini
ask   sesame paste                       0.542  Seeds, sesame butter, paste
weak  Chinese sesame paste               0.406  Seeds, sesame butter, paste
weak  toasted sesame paste               0.433  Seeds, sesame butter, paste
auto  sesame seeds                       1.000  Sesame seeds
auto  sesame butter                      0.667  Sesame butter, creamy
auto  peanut butter                      1.000  Peanut butter
weak  peanut paste                       0.438  Peanut oil
auto  almond butter                      1.000  Almond butter
auto  cashew butter                      1.000  Cashew butter
ask   sunflower seed butter              0.588  Seeds, sunflower seed butter, without salt
ask   hazelnut butter                    0.450  Oil, hazelnut
weak  pistachio paste                    0.435  Pistachio nuts, NFS
none  halva                              -      (nothing)
ask   tahina                             0.556  Tahini

ask=8 (27%)  auto=9 (30%)  none=5 (17%)  weak=8 (27%)
```

### FINDING (b, reachability) — `tahini` in one probe, illustrating §1 of RECONCILED

Full candidate list for `tahini`, verbatim:

```
1.000  2707587  Tahini                                                        [fndds]
0.135   168604  Seeds, sesame butter, tahini, type of kernels unspecified      [sr_legacy]
0.123   169410  Seeds, sesame butter, tahini, from raw and stone ground kernels
0.103   170189  Seeds, sesame butter, tahini, from roasted and toasted kernels (most common type)
0.095   169406  Seeds, sesame butter, tahini, from unroasted kernels (non-chemically removed seed coat)
```

Four rows containing the exact word `tahini` score under 0.14. The only reason
this term works at all is that FNDDS happens to hold a two-syllable row.
**Every proposal in this file that names an SR Legacy row as a fallback target
is therefore unreachable by similarity and must be carried by an explicit
mapping, not by a threshold change.**

### FINDING (b/c) — the tahini / Chinese sesame paste conflation is real and is a mineral error

Measured, per 100 g:

```
170191 Seeds, sesame butter, paste                          <- unhulled whole seed
    kcal=586 prot=18.08 fat=50.87 carb=24.05 Ca=960  Fe=19.20 Mg=362 Na=12
170189 ...tahini, from roasted and toasted kernels (most common type)
    kcal=595 prot=17.00 fat=53.76 carb=21.19 Ca=426  Fe=8.95  Mg=95  Na=115
169410 ...tahini, from raw and stone ground kernels
    kcal=570 prot=17.81 fat=48.00 carb=26.19 Ca=420  Fe=2.51  Mg=96  Na=74
169406 ...tahini, from unroasted kernels (non-chemically removed seed coat)
    kcal=607 prot=17.95 fat=56.44 carb=17.89 Ca=141  Fe=6.35  Mg=353 Na=1
168604 ...tahini, type of kernels unspecified
    kcal=592 prot=17.40 fat=53.01 carb=21.50 Ca=141  Fe=4.42  Mg=95  Na=35
2262073 Sesame butter, creamy [foundation]
         prot=19.71 fat=62.40 carb=14.18 Ca=116  Fe=7.00  Mg=357 Na=64
```

**Energy and macros agree to within 6%. Calcium spans 116 to 960 mg — a factor
of 8.3 — and iron 2.51 to 19.2, a factor of 7.6.** The split is hulling: Chinese
`zhima jiang` is ground from whole unhulled toasted seed and keeps the seed
coat, which is where sesame's calcium lives; Levantine tahini is made from
hulled kernels and does not.

So the conflation is **safe on energy and actively misleading on calcium**, and
which direction it misleads in depends on which row you land on. Note also that
USDA's own five tahini rows disagree with each other by 3x on calcium and 3.6x
on iron, so a fallback pointing at "tahini" without saying which row is not a
well-defined statement.

`Chinese sesame paste` currently reaches 170191 — the *correct* unhulled row —
at 0.406, which is below the weak floor. It survives only because the model
tier is consulted.

### FINDING (a, entity) — the fermented-soy pastes are absent, and no near neighbour exists

Neighbour search by ingredient and category, not by name:

```
$ q.py find "Miso"
  173433 | sr_legacy_food | Cheese, goat, semisoft type      <- trigram noise
  172442 | sr_legacy_food | Miso
 2707439 | survey_fndds_food | Miso
 2707438 | survey_fndds_food | Miso sauce
 2707455 | survey_fndds_food | Soup, miso or tofu
```

That is the entire fermented-soy-seasoning inventory. `doenjang`, `gochujang`,
`douchi` and `furu` return nothing, and the searches that should find a
neighbour by category also fail: `fermented soybean paste` → 0.324
`Bean paste, sweetened` (a *sweet* red-bean confection, not soy);
`soybean paste` → 0.444 `Soybean oil`; `fermented bean curd` → 0.320
`Soybean curd`.

`Miso` measured: `kcal=198 prot=12.79 fat=6.01 carb=25.37 Na=3728 K=210`.

Doenjang is a defensible fallback onto miso — same organism family, same
substrate, same order of magnitude on every macro and on sodium. **Gochujang is
not**: it is a chilli-and-glutinous-rice paste, roughly 220–240 kcal with
**~45 g carbohydrate and ~25 g sugar**, against miso's 25 g carb / 6.2 g sugar.
Mapping gochujang to miso would understate sugar by ~19 g per 100 g while
looking entirely plausible. Gochujang is a case where **no fallback should be
offered**.

### FINDING (b) — nut paste falls back to nut *oil*, which is pure fat

```
weak  peanut paste                       0.438  Peanut oil
ask   hazelnut butter                    0.450  Oil, hazelnut
weak  soybean paste                      0.444  Soybean oil
weak  pistachio paste                    0.435  Pistachio nuts, NFS
```

A nut butter is ~50–60% fat with 17–25 g protein and 5–10 g fibre; a nut oil is
100% fat with none of either. `hazelnut butter` at 0.450 is *above* the weak
floor, so it is presented to the model tier as a serious candidate. The
`unrequested_qualifier` guard cannot help — `Oil, hazelnut` is only two
segments and "hazelnut" was asked for. **Any `X butter`/`X paste` → `Oil, X`
resolution is a 1.8x energy error and a total loss of protein and fibre**, and
`pistachio nuts, NFS` (whole nuts) is the *better* of these fallbacks despite
scoring lowest.


---

## Batch 4 — animal fats and offal (40 terms)

```
auto  lard                               1.000  Lard
weak  tallow                             0.438  Fat, beef tallow
auto  beef tallow                        0.750  Fat, beef tallow
weak  ghee                               0.227  Butter, Clarified butter (ghee)
auto  clarified butter                   0.773  Butter, Clarified butter (ghee)
none  schmaltz                           -      (nothing)
auto  chicken fat                        1.000  Fat, chicken
weak  duck fat                           0.333  Duck sauce
auto  goose fat                          1.000  Fat, goose
none  dende                              -      (nothing)
auto  red palm oil                       0.692  Oil, palm
auto  palm oil                           1.000  Oil, palm
weak  suet                               0.119  Beef, variety meats and by-products, suet, raw
weak  beef suet                          0.429  Soup, beef
weak  bacon fat                          0.417  Animal fat, bacon grease
weak  dripping                           0.320  Animal fat or drippings
weak  beef dripping                      0.364  Beef, cured, dried
auto  butter                             0.636  Butter, tub
none  smen                               -      (nothing)
none  niter kibbeh                       -      (nothing)
ask   liver                              0.545  Liver, beef
auto  chicken liver                      1.000  Liver, chicken
auto  beef liver                         1.000  Liver, beef
ask   pork liver                         0.611  Liver cheese, pork
weak  lamb liver                         0.286  Lamb, New Zealand, imported, liver, raw
weak  foie gras                          0.238  Pate de foie gras, canned (goose liver pate), smoked
auto  kidney                             1.000  Kidney
ask   beef kidney                        0.583  Kidney
auto  heart                              1.000  Heart
ask   beef heart                         0.545  Heart
ask   chicken heart                      0.483  Chicken, heart, all classes, raw
auto  tripe                              1.000  Tripe
auto  sweetbreads                        1.000  Sweetbreads
auto  tongue                             1.000  Tongue
ask   beef tongue                        0.583  Tongue
auto  brain                              0.625  Brains
auto  gizzard                            1.000  Gizzard
ask   chicken gizzard                    0.516  Chicken, gizzard, all classes, raw
weak  bone marrow                        0.316  Caribou, bone marrow, raw (Alaska Native)
auto  blood sausage                      1.000  Blood sausage

ask=7 (18%)  auto=18 (45%)  none=4 (10%)  weak=11 (28%)
```

All 18 autos were run through the guard harness; every one survives, so these
are real auto-matches that write an alias with no model consulted.

### Animal fats: energy is a safe parent, saturated fat is not

Measured per 100 g:

```
171401 Lard                          kcal=902 fat=100  satfat=39.2 mufa=45.1 pufa=11.2 chol=95  vitD=2.5
171400 Fat, beef tallow              kcal=902 fat=100  satfat=49.8 mufa=41.8 pufa=4.0  chol=109 vitD=0.7
173564 Fat, chicken                  kcal=900 fat=99.8 satfat=29.8 mufa=44.7 pufa=20.9 chol=85  vitD=4.8
173572 Fat, goose                    kcal=900 fat=99.8 satfat=27.7 mufa=56.7 pufa=11.0 chol=100
171314 Butter, Clarified butter(ghee)kcal=900 fat=100  satfat=60.0 pufa=4.0  chol=300  vitA=4000 IU
171015 Oil, palm                     kcal=884 fat=100  satfat=49.3 mufa=37.0 pufa=9.3  chol=0
```

**Energy varies by 2%. Saturated fat spans 27.7 to 60.0 g — a factor of 2.2 —
and cholesterol 0 to 300 mg.** So an `animal fat` parent is defensible for
energy and total fat and *actively misleading* for the two things a person
using a cholesterol ceiling is watching. Any fallback here must be to a
specific fat, not to a category.

The one clean high-confidence pair falls out of the same table:
**duck fat → `Fat, goose`**. Both are waterfowl fats, both MUFA-dominant, and
the two published duck-fat analyses sit between goose and chicken on every
line. USDA has **no duck fat row at all** — neighbour search by category
confirms it:

```
$ q.py find "duck"
 2707176 Duck egg, cooked          2710298 Duck sauce           2706141 Duck, Peking
 2706137 Duck, cooked, skin eaten  2706138 Duck, cooked, skin not eaten
  174467 Duck, domesticated, liver, raw
  172408/9/10/11 Duck, domesticated, meat and skin / meat only, raw / roasted
```

— twelve duck rows, not one of them a rendered fat. Today `duck fat` reaches
`Duck sauce` (0.333), a sweet apricot condiment, and `rendered duck fat`
reaches `Pork, bacon, rendered fat, cooked` (0.371).

`schmaltz` is simpler still: it **is** rendered chicken fat, `Fat, chicken`
exists, and `schmaltz` returns nothing. A pure synonym, high confidence.

### FINDING (c-adjacent) — `red palm oil` auto-matches refined palm oil and zeroes the carotene

```
auto  red palm oil                       0.692  Oil, palm     [survives all four guards]
171015 Oil, palm    kcal=884 fat=100 satfat=49.3 vitA_RAE=0 vitK=8
```

Macros are right. Unrefined red palm oil / dendê is one of the densest dietary
sources of provitamin A carotenoids; `Oil, palm` reports `vitA_RAE = 0`, a
*measured* zero for the refined oil. This is not the "missing nutrients are
skipped, never zeroed" case — invariant 6 does not protect here, because the
value is present and it is zero. The match is silent, it is an `auto`, and it
caches. Macro-defensible, micronutrient-wrong.

### Offal: the FNDDS single-word rows are species-unspecified and they auto-match

```
2706157 Kidney       kcal=157 prot=27.05 fat=4.61  chol=710  Se=166.7 B12=24.70
2706156 Heart        kcal=164 prot=28.25 fat=4.69  chol=210
2706160 Tongue       kcal=282 prot=19.14 fat=22.12 chol=131
2706162 Tripe        kcal=89  prot=12.60 fat=3.85  chol=127
2706165 Gizzard      kcal=153 prot=30.15 fat=2.66  chol=367
2706159 Brains       kcal=150 prot=11.58 fat=10.45 chol=3075
2706158 Sweetbreads  kcal=124 prot=22.49 fat=3.08  chol=347
```

**`offal` is not a usable parent.** Energy 89 to 282, fat 2.66 to 22.12,
cholesterol 127 to 3075 — a factor of 24. Organ identity is the whole
nutritional content of the word; nothing above the organ carries information.

**The liver sub-family is the sharpest case in this audit for refusing a
fallback.** Measured:

```
2706153 Liver, beef     vitA_RAE=7683  Cu=14.472  B12=82.47  folate=258
2706154 Liver, chicken  vitA_RAE=2808  Cu=0.570   B12=15.07  folate=575
```

Same organ, same species genus of use, and **copper differs 25-fold, vitamin A
2.7-fold, B12 5.5-fold**. `liver` alone resolves to `Liver, beef` (0.545).
A 150 g portion of what the user actually ate as chicken liver would be booked
at 11,525 µg RAE and 21.7 mg copper — against a copper RDA of 0.9 mg, so
**2,400% of a day's copper from one unspecified word.** `liver` must ask, never
fall back.

### FINDING (b/c) — `pork liver` reaches a sausage

```
ask   pork liver                         0.611  Liver cheese, pork
```

`Liver cheese, pork` (173869) is liverwurst — a comminuted, fatty, cured
sausage — not an organ. It is 0.009 below the auto gate. Real pork liver is
~134 kcal / 21 g protein / 3.7 g fat; the numbers for the sausage row are in
the appended measurement below. USDA holds
`Pork, fresh, variety meats and by-products, liver, raw` and the query cannot
reach it — the same long-description reachability failure as `pork jowl`.

Measured:

```
173869 Liver cheese, pork   kcal=304 prot=15.20 fat=25.60 Na=1225 chol=174 vitA_RAE=5252
```

against real pork liver at ~134 kcal / 21 g protein / 3.7 g fat / ~87 mg Na.
**2.3x the energy, 7x the fat, 14x the sodium**, and it is plausible enough that
nothing downstream would raise anything.


---

## Batch 5 — chilli products: fresh vs dried vs powder vs paste (36 terms)

```
weak  chilli                             0.417  Chili, NFS
ask   chili pepper                       0.481  Cheese dip with chili pepper
weak  fresh chilli                       0.350  Coconut, fresh
weak  green chilli                       0.393  Peppers, chili, green, canned
weak  red chilli                         0.333  Peppers, hot chili, red, raw
none  bird's eye chilli                  -      (nothing)
weak  jalapeno                           0.429  Peppers, jalapeno, raw
auto  serrano pepper                     0.667  Peppers, serrano, raw
none  habanero                           -      (nothing)
ask   scotch bonnet                      0.500  Scotch
ask   cayenne pepper                     0.517  Spices, pepper, red or cayenne
weak  dried chilli                       0.429  Seeds, chia seeds, dried
weak  chilli flakes                      0.308  Cereal, wheat flakes
weak  red pepper flakes                  0.385  Peppers, red, cooked
ask   chilli powder                      0.545  Spices, chili powder
ask   paprika                            0.533  Spices, paprika
weak  smoked paprika                     0.429  Spices, paprika
weak  pimenton                           0.412  Pimento, canned
none  gochugaru                          -      (nothing)
none  ancho chilli                       -      (nothing)
ask   chipotle                           0.474  Chipotle dip, light
none  guajillo                           -      (nothing)
weak  chilli paste                       0.316  Chili, white
none  sambal                             -      (nothing)
none  sambal oelek                       -      (nothing)
none  harissa                            -      (nothing)
weak  harissa paste                      0.300  Guava paste
weak  chilli oil                         0.333  Corn oil
weak  sriracha                           0.375  Sauce, hot chile, sriracha
auto  hot sauce                          0.667  Hot Thai sauce
none  doubanjiang                        -      (nothing)
weak  chilli bean paste                  0.393  Bean paste, sweetened
none  aji amarillo                       -      (nothing)
none  piri piri                          -      (nothing)
none  berbere                            -      (nothing)
weak  cayenne                            0.276  Spices, pepper, red or cayenne

ask=6 (17%)  auto=2 (6%)  none=12 (33%)  weak=16 (44%)
```

### The chilli family is the clearest case that **form, not species, is the axis**

Measured per 100 g:

```
170106 Peppers, hot chili, red, raw    kcal=40  carb=8.81  fib=1.5  Na=9    vitC=143.7 vitA_RAE=48
170497 Peppers, hot chili, green, raw  kcal=40  carb=9.46  fib=1.5  Na=7    vitC=242.5 vitA_RAE=59
171319 Spices, chili powder            kcal=282 carb=49.7  fib=34.8 Na=2867 vitC=0.7   vitA_RAE=1483
171329 Spices, paprika                 kcal=282 carb=53.99 fib=34.9 Na=68   vitC=0.9   vitA_RAE=2463
171186 Sauce, hot chile, sriracha      kcal=93  carb=19.16 fib=2.2  Na=2124 vitC=26.9  vitA_RAE=129
2706373 Chili, NFS  (the stew)         kcal=118 prot=9.8   fat=4.33 Na=340  chol=22
```

**Fresh to dried is 7x on energy, 23x on fibre, and vitamin C collapses from
143.7 mg to 0.7.** Species (jalapeño vs serrano vs habanero) moves energy by
less than 10 kcal. So the correct parent chain runs
`ancho / guajillo / gochugaru / bird's eye, dried → Spices, chili powder` and
`habanero / scotch bonnet / bird's eye, fresh → Peppers, hot chili, red, raw`,
and **crossing between them is the error worth preventing**, not getting the
cultivar wrong.

Note also `Spices, chili powder` carries **2867 mg sodium** (it is a blend with
salt) against paprika's 68 mg. A pure ground chilli mapped onto `chili powder`
picks up 2.9 g of sodium per 100 g that is not in the food. For pure ground
chillies the honest target is `Spices, paprika` or
`Spices, pepper, red or cayenne`, not `Spices, chili powder`.

### FINDING (b, spelling) — the British double-l blocks the whole family

```
weak  chilli                             0.417  Chili, NFS      <- the STEW
weak  red chilli                         0.333  Peppers, hot chili, red, raw
weak  green chilli                       0.393  Peppers, chili, green, canned
weak  dried chilli                       0.429  Seeds, chia seeds, dried
weak  chilli flakes                      0.308  Cereal, wheat flakes
weak  chilli paste                       0.316  Chili, white
weak  chilli oil                         0.333  Corn oil
```

Every `chilli` query is below the weak floor, and the best of them lands on
`Chili, NFS` — the American bean-and-beef stew, 118 kcal and 9.8 g protein per
100 g. `chilli oil` reaches `Corn oil` (100% fat), `chilli flakes` reaches
`Cereal, wheat flakes`, `dried chilli` reaches `chia seeds`. This is one
character of orthography taking out an entire ingredient family, and it is not
a taxonomy problem — it belongs to the normalisation layer.

### FINDING (b) — `sriracha` cannot reach `Sauce, hot chile, sriracha`

```
weak  sriracha                           0.375  Sauce, hot chile, sriracha
```

The exact word is in the description and the score is 0.375, below the weak
floor. Same shape as the `tahini` list in batch 3: SR Legacy's comma-prefixed
descriptions are systematically unreachable by the short name.

### Where NO fallback should be offered in this family

`harissa`, `sambal oelek`, `doubanjiang` and `gochujang` (batch 3) all return
nothing, and each is a *compound* — chilli plus oil, or chilli plus fermented
bean, or chilli plus sugar and rice. Their energy is set by the non-chilli
component: harissa is oil-bound (~180–250 kcal), sambal oelek is not (~30),
doubanjiang is salt-dominated (~5 g Na/100 g). There is no chilli row that
predicts any of them, and `Sauce, hot chile, sriracha` — the only paste-like
row available — is a *sugar* sauce at 15.1 g sugar per 100 g. Offering it as a
generic "chilli paste" fallback would import 15 g of sugar into a food that has
none. **Ask.**


---

## Batch 6 — tubers, starches and grains (55 terms)

```
ask   yam                                0.500  Yam, raw
auto  sweet potato                       0.812  Pie, sweet potato
auto  yam raw                            1.000  Yam, raw
weak  true yam                           0.308  Yam, raw
weak  white yam                          0.429  Wine, white
none  purple yam                         -      (nothing)
none  ube                                -      (nothing)
ask   taro                               0.556  Taro, raw
auto  cassava                            0.667  Cassava, raw
none  manioc                             -      (nothing)
ask   yuca                               0.455  Yuca fries
weak  tapioca                            0.444  Tapioca, pearl, dry
weak  tapioca starch                     0.203  Rolls, gluten-free, white, made with brown rice flour, tapioca starch, and potato starch
auto  cassava flour                      1.000  Flour, cassava
none  gari                               -      (nothing)
auto  fufu                               1.000  Fufu
auto  plantain                           0.692  Plantain, raw
auto  green plantain                     0.667  Plantains, green, raw
auto  potato                             0.636  Potato, NFS
auto  sweet potato raw                   0.708  Sweet potato leaves, raw
ask   Japanese sweet potato              0.520  Pie, sweet potato
auto  jicama                             0.636  Jicama, raw
auto  lotus root                         0.786  Lotus root, raw
auto  water chestnut                     0.706  Water Chesnut
auto  arrowroot                          0.714  Arrowroot, raw
none  sago                               -      (nothing)
none  malanga                            -      (nothing)
weak  yautia                             0.368  Yautia (tannier), raw
none  eddoe                              -      (nothing)
auto  poi                                1.000  Poi
none  kasza gryczana                     -      (nothing)
auto  buckwheat groats                   1.000  Buckwheat groats
auto  bulgur                             0.636  Bulgur, dry
none  freekeh                            -      (nothing)
weak  farro                              0.273  Farro, pearled, dry, raw
ask   spelt                              0.462  Spelt, cooked
ask   pearl barley                       0.611  Barley, pearled, raw
ask   whole barley                       0.538  Barley
auto  brown rice                         0.647  Flour, rice, brown
ask   white rice                         0.524  Beans and white rice
weak  wholemeal flour                    0.407  Flour, oat, whole grain
ask   wholewheat flour                   0.517  Flour, whole wheat, unenriched
weak  white flour                        0.444  Rice flour, white, unenriched
weak  plain flour                        0.207  Snacks, pretzels, hard, plain, made with unenriched flour, salted
ask   semolina                           0.500  Semolina, enriched
auto  durum wheat                        1.000  Wheat, durum
weak  oat groats                         0.421  Buckwheat groats
ask   steel cut oats                     0.556  Oats, whole grain, steel cut
weak  rolled oats                        0.333  Oats, whole grain, rolled, old fashioned
auto  millet                             1.000  Millet
weak  teff                               0.417  Teff, cooked
ask   sorghum                            0.571  Flour, sorghum
ask   amaranth                           0.600  Flour, amaranth
ask   quinoa                             0.538  Flour, quinoa
auto  rye flour                          1.000  Flour, rye

ask=14 (25%)  auto=20 (36%)  none=9 (16%)  weak=12 (22%)
```

### FINDING (c) — `sweet potato` auto-matches a **pie**, and survives every guard

This is the worst result in the audit and it is not an exotic word.

```
$ eff.py '' 'sweet potato'
'sweet potato': effective=AUTO -> Pie, sweet potato   (head 0.812 Pie, sweet potato)
    0.812 Pie, sweet potato -> SURVIVES

$ eff.py cooked 'sweet potato'          # state does not help
'sweet potato': effective=AUTO -> Pie, sweet potato   (head 0.812 Pie, sweet potato)
    0.812 Pie, sweet potato -> SURVIVES
```

Measured:

```
2708012 Pie, sweet potato                kcal=269 prot=4.96 fat=9.75 carb=41.08 sugar=25.16 Na=269 chol=47
168482  Sweet potato, raw, unprepared    kcal=86  prot=1.57 fat=0.05 carb=20.12 sugar=4.18  Na=55  chol=0
```

A 200 g sweet potato is booked as **538 kcal instead of 172, 19.5 g of fat
instead of 0.1, and 50 g of sugar instead of 8.4.** No confirm-card line names
the matched row when the label is a substring of the description (SPEC-2 §5),
and `sweet potato` *is* a substring of `Pie, sweet potato` — so the card is
silent, the alias is written, and every sweet potato after it is a slice of pie.

**Why the guards miss it, and this generalises.** `unrequested_qualifier`
deliberately checks only the segments *after* the first, because "the first is
the food's name, and a different name is a weak match rather than a narrowed
one". FNDDS writes a large family of rows as `Dish, ingredient` —
`Pie, sweet potato`, `Soup, miso or tofu`, `Salad, egg` — which puts the
**food in the qualifier position and the dish in the head position**, exactly
inverting the assumption. For that shape the guard is structurally blind.

I checked how wide the shape is: `Pie, ` alone, and `sweet potato` is not a rare
word. `Japanese sweet potato` heads to the same pie row at 0.520.

Related, same batch, same shape but caught: `sweet potato raw` →
`Sweet potato leaves, raw` at 0.708 (leaves, not tuber; 42 kcal, 4.0 g protein)
is blocked by `unrequested_qualifier` because "leaves" sits after the first
segment. The guard works exactly when the dish word comes second and fails
exactly when it comes first.

### FINDING (c) — `brown rice` auto-matches brown rice **flour**

```
'brown rice': effective=AUTO -> Flour, rice, brown   (head 0.647 Flour, rice, brown)
    0.647 Flour, rice, brown -> SURVIVES        [also with state='cooked']

1104812 Flour, rice, brown      kcal=365.25 prot=7.19 fat=3.85 carb=75.5
2708409 Rice, brown, cooked, NS as to fat  (measured below)
```

Dry flour against cooked grain is roughly a **3x energy error per gram**, in the
direction that matters: a person types "brown rice" meaning the cooked grain on
the plate. `state_conflicts` does not fire because "flour" is not a preparation
word, and `unrequested_qualifier` does not fire because the head segment is
`Flour`. Same structural blindness as the pie.

The same shape without the auto: `sorghum` → `Flour, sorghum` (0.571),
`amaranth` → `Flour, amaranth` (0.600), `quinoa` → `Flour, quinoa` (0.538),
`white flour` → `Rice flour, white, unenriched` (0.444). Four more grains whose
best candidate is their own flour. These escalate, so the model tier can save
them — but they are all one similarity point away from the `brown rice` case.

### The tuber family: `yam` and `sweet potato` are genuinely different foods

Measured per 100 g raw:

```
170071 Yam, raw          kcal=118 carb=27.88 fib=4.1 K=816 vitA_RAE=7    vitC=17.1
168482 Sweet potato, raw kcal=86  carb=20.12 fib=3.0 K=337 vitA_RAE=709  vitC=2.4
169985 Cassava, raw      kcal=160 carb=38.06 fib=1.8 K=271 vitA_RAE=1    vitC=20.6
169308 Taro, raw         kcal=112 carb=26.46 fib=4.1 K=591 vitA_RAE=4    vitC=4.5
169250 Lotus root, raw   kcal=74  carb=17.23 fib=4.9 K=556 vitA_RAE=0    vitC=44.0
168490 Arrowroot, raw    kcal=65  carb=13.39 fib=1.3 K=454 folate=338
170431 Poi               kcal=112 carb=27.23 fib=0.4 K=183
2709560 Plantain, raw    kcal=122 carb=31.89 sugar=17.51 K=487
```

**The US labelling error is worth an order of magnitude on one nutrient.**
`Dioscorea` yam has `vitA_RAE = 7`; sweet potato has **709**, a hundredfold
difference, and it is the single thing sweet potato is nutritionally known for.
Conflating them in either direction either invents or destroys a full day's
vitamin A per 130 g portion. Energy also differs by 37%.

Encouragingly the resolver does **not** make this mistake — `yam` reaches
`Yam, raw` and nothing sweet-potato-shaped appears in its list. The risk is in
the other direction: an American user typing "yam" meaning a sweet potato. That
is a genuine ambiguity in the *word*, not in the data, and it is a case where
the honest response is to **ask**, not to encode either mapping.

`gari`, `sago`, `eddoe`, `malanga`, `manioc`, `ube` and `purple yam` return
nothing. `manioc` = cassava and `ube` = purple yam are pure synonyms of rows
that exist; `gari` (toasted fermented cassava granules, ~360 kcal dry) is a
processed derivative that `Cassava, raw` at 160 kcal would understate by more
than half, so gari is **not** a cassava fallback.


---

## Batch 7 — whole fish, oily vs white (39 terms)

```
ask   fish                               0.556  Fish, raw
ask   white fish                         0.500  Fish, sucker, white, raw
weak  oily fish                          0.444  Fish oil, salmon
auto  salmon                             0.700  Salmon salad
ask   mackerel                           0.500  Fish, mackerel, NFS
weak  sardines                           0.429  Fish, sardines, canned
ask   sardine                            0.533  Sardine sandwich
weak  anchovies                          0.353  Fish, anchovy
ask   herring                            0.615  Fish, herring
weak  kipper                             0.188  Fish, herring, Atlantic, kippered
weak  trout                              0.400  Fish, trout, NFS
weak  sea bass                           0.290  Fish, sea bass, mixed species, raw
ask   cod                                0.500  Cape Cod
ask   haddock                            0.471  Fish, haddock, raw
ask   pollock                            0.471  Fish, pollock, raw
none  hake                               -      (nothing)
ask   tilapia                            0.471  Fish, tilapia, raw
weak  sole                               0.308  Soup, pozole
none  plaice                             -      (nothing)
ask   halibut                            0.615  Fish, halibut
weak  turbot                             0.280  Fish, turbot, european, raw
ask   monkfish                           0.600  Fish, monkfish, raw
weak  tuna                               0.357  Fish, tuna, NFS
auto  canned tuna                        0.706  Fish, tuna, canned
weak  tuna steak                         0.412  Steak tartare
auto  swordfish                          0.833  Fish, swordfish
ask   snapper                            0.615  Fish, snapper
weak  bream                              0.333  Bread, egg
ask   carp                               0.500  Fish, carp
ask   pike                               0.500  Fish, pike
weak  perch                              0.400  Fish, perch, NFS
weak  eel                                0.444  Fish, eel
auto  smoked salmon                      0.722  Fish, salmon, smoked
weak  smoked mackerel                    0.423  Fish, mackerel, salted
weak  salt cod                           0.235  Fish, cod, Atlantic, dried and salted
weak  bacalao                            0.353  Bacalaitos fritos
weak  kippers                            0.182  Fish, herring, Atlantic, kippered
weak  whitebait                          0.333  Wine, white
none  sprats                             -      (nothing)

ask=14 (36%)  auto=4 (10%)  none=3 (8%)  weak=18 (46%)
```

### FINDING (c) — `salmon` auto-matches `Salmon salad`

```
'salmon': effective=AUTO -> Salmon salad   (head 0.700 Salmon salad)
    0.700 Salmon salad -> SURVIVES
```

Third instance of the same structural hole as `Pie, sweet potato` — except here
the dish word is *appended*, so it is not even the `Dish, ingredient` shape;
`Salmon salad` is a single unpunctuated segment, so `unrequested_qualifier` has
nothing after a comma to inspect at all. Measured:

```
2706826 Salmon salad                    kcal=213 prot=10.82 fat=17.36 Na=507 pufa=9.527 DHA=0.358 EPA=0.172
175167  Fish, salmon, Atlantic, farmed, raw  kcal=208 prot=20.42 fat=13.42 Na=59  DHA=1.104 EPA=0.862
```

Energy happens to agree within 2%, which is exactly why nothing downstream
raises anything. **Protein is halved, sodium is 8.6x, and EPA+DHA falls from
1.97 g to 0.53 g** — a 73% loss of the one thing salmon is eaten for. The
`pufa` figure *rises* (9.5 g against 3.9) because it is mayonnaise.

Note the top three candidates for `salmon` are all wrong:

```
2706826 Salmon salad
2706850 Lomi salmon
 172343 Fish oil, salmon
```

### The omega-3 gap, measured, is the reason `fish` must not have a parent

Per 100 g raw:

```
                                    kcal  fat    prot   DHA    EPA    vitD    Se
171955 Fish, cod, Atlantic, raw       82   0.67  17.81  0.120  0.064   0.9µg  33.1
171964 Fish, haddock, raw             74   0.45  16.32  0.089  0.042   0.5µg  25.9
175150 Fish, sucker, white, raw       92   2.32  16.76  0.289  0.190          12.6
175167 Fish, salmon, Atlantic, farmed 208  13.42 20.42  1.104  0.862  11.0µg  24.0
175119 Fish, mackerel, Atlantic, raw  205  13.89 18.60  1.401  0.898  16.1µg  44.1
175139 Fish, sardine, canned in oil   208  11.45 24.62  0.509  0.473   4.8µg  52.7  Ca=382
2706224 Fish, NFS  (the generic row) 238  14.52 19.32  0.409  0.286   5.3µg  26.4
```

**EPA+DHA spans 0.131 g (haddock) to 2.299 g (mackerel) — a factor of 17.5 —
and vitamin D spans 0.5 to 16.1 µg, a factor of 32.** Energy spans 2.8x. There
is no defensible `fish` parent; `Fish, NFS` at 238 kcal is closer to fried fish
than to any whole fish and would triple a cod portion.

The distinction that carries all of it is **oily vs white**, and it is not a
word the resolver has:

```
ask   white fish                         0.500  Fish, sucker, white, raw
weak  oily fish                          0.444  Fish oil, salmon
```

`white fish` reaches a *specific* North American freshwater sucker — not a
category — and `oily fish` reaches a **fish oil supplement**, which is 100% fat
at ~900 kcal. Both are cases where the word is a category and USDA answers with
a species or a product.

Sardine deserves a separate note: canned-with-bones is the only row and its
`Ca=382` is 25x any other fish here. A sardine fallback to any other oily fish
destroys that, and a boneless-sardine dish mapped onto it invents it.

### Reachability again, and it is now clearly systemic

```
weak  kippers    0.182  Fish, herring, Atlantic, kippered
weak  salt cod   0.235  Fish, cod, Atlantic, dried and salted
weak  turbot     0.280  Fish, turbot, european, raw
weak  sea bass   0.290  Fish, sea bass, mixed species, raw
```

Four correct rows, all containing the queried word verbatim, all scoring below
0.30. `cod` alone reaches `Cape Cod` (0.500) ahead of `Fish, cod, NFS`.


---

## Batch 8 — leafy greens (43 terms)

```
auto  spinach                            0.667  Spinach, raw
ask   kale                               0.556  Kale, raw
ask   chard                              0.600  Chard, raw
auto  swiss chard                        0.750  Chard, swiss, raw
none  silverbeet                         -      (nothing)
weak  collard greens                     0.375  Poke greens, cooked
auto  mustard greens                     0.789  Mustard greens, raw
auto  turnip greens                      0.778  Turnip greens, raw
auto  beet greens                        0.750  Beet greens, raw
weak  sorrel                             0.333  Squirrel
auto  purslane                           0.692  Purslane, raw
auto  watercress                         0.733  Watercress, raw
none  rocket                             -      (nothing)
auto  arugula                            0.667  Arugula, raw
weak  lamb's lettuce                     0.444  Lettuce, raw
none  mache                              -      (nothing)
weak  romaine                            0.421  Romaine lettuce, raw
auto  iceberg lettuce                    0.800  Lettuce, iceberg, raw
ask   cos lettuce                        0.462  Lettuce, cos or romaine, raw
weak  pak choi                           0.346  Cabbage, chinese (pak-choi), raw
ask   bok choy                           0.450  Cabbage, bok choy, raw
none  choy sum                           -      (nothing)
none  gai lan                            -      (nothing)
auto  Chinese broccoli                   0.810  Broccoli, chinese, raw
none  morning glory                      -      (nothing)
weak  water spinach                      0.444  Spinach, raw
auto  amaranth leaves                    0.800  Amaranth leaves, raw
none  callaloo                           -      (nothing)
none  molokhia                           -      (nothing)
weak  jute leaves                        0.245  Bitter melon, horseradish, jute, or radish leaves, cooked
weak  fenugreek leaves                   0.407  Spices, fenugreek seed
none  methi                              -      (nothing)
weak  curry leaves                       0.444  Lentil curry
auto  grape leaves                       0.765  Grape leaves, raw
weak  vine leaves                        0.333  Taro leaves, raw
weak  nettles                            0.170  Stinging Nettles, blanched (Northern Plains Indians)
auto  dandelion greens                   0.810  Dandelion greens, raw
auto  cabbage                            0.667  Cabbage, raw
auto  savoy cabbage                      0.778  Cabbage, savoy, raw
auto  napa cabbage                       0.684  Cabbage, napa, cooked
weak  greens                             0.438  Beet greens, raw
weak  leafy greens                       0.391  Tea, hot, leaf, green
weak  salad leaves                       0.353  Salmon salad

ask=4 (9%)  auto=16 (37%)  none=9 (21%)  weak=14 (33%)
```

This is the **best-served family in the audit** — 16 clean autos onto the right
raw-vegetable row. USDA covers greens densely and the FNDDS short names
(`Spinach, raw`, `Kale, raw`) are reachable. The findings here are synonyms and
one part-of-plant error, not fallback quality.

### Energy is uniform, so the *only* thing a greens fallback can get wrong is micronutrients — and it does

Per 100 g raw:

```
                          kcal  Ca    Fe    Mg   vitK    vitA_RAE  vitC   folate
168462  Spinach, raw       23    99   2.71  79   482.9    469      28.1   194
2709574 Chard, raw         19    51   1.80  81   830.0    306      30.0    14
323505  Kale, raw          35   254   1.60  33   390.0    241      93.4    62
2685574 Collards, raw      —    276   0.75  50     —        —      89.4   168
169387  Arugula, raw       25   160   1.46  47   108.6    119      15.0    97
2709590 Romaine lettuce    21    28   0.27  12    83.4     436      4.6     50
169975  Cabbage, raw       25    40   0.47  12    76.0       5     36.6     43
```

**Energy spans 19 to 35 kcal — under 16 kcal absolute — while vitamin K spans
76 to 830 µg, a factor of 10.9, and calcium 28 to 276, a factor of 9.9.**

So a `leafy green` parent is harmless on the energy target and useless-to-
harmful on everything the user would consult a greens entry *for*. For anyone
on warfarin the vitamin K spread is the only number that matters, and
`chard → spinach` (which the words nearly do already) is a 1.7x understatement
while `romaine → chard` is 10x the other way. **A generic greens parent should
not be encoded.** Species-to-species synonyms are fine; the category is not.

Note in passing that spinach's `Fe=2.71` and `Ca=99` are the classic
bioavailability trap — spinach's oxalate binds most of both, and USDA reports
total, not available. Nothing in nutrAI models that and nothing should pretend
to; it is a reason to prefer the *correct species row* rather than a plausible
neighbour, since at least the error is then USDA's and not ours.

### FINDING (b) — leaf resolves to seed

```
weak  fenugreek leaves                   0.407  Spices, fenugreek seed
171324 Spices, fenugreek seed   kcal=323  prot=23.0  carb=58.35  fib=24.6  Fe=33.53
```

Fresh methi leaf is ~49 kcal / 4.4 g protein. The seed row is **6.6x the
energy and 12x the iron**, and 0.407 is close enough to the weak floor that the
model tier sees it as a serious candidate with nothing better beside it.
`methi` returns nothing at all, so the Hindi name has no route in either.

Same shape, less extreme: `curry leaves` → `Lentil curry` (0.444), a dish.

### Pure synonym gaps, all onto rows that exist and already auto-match

```
none  rocket        -> arugula      (Arugula, raw auto-matches at 0.667)
none  silverbeet    -> chard        (Chard, raw at 0.600)
weak  vine leaves   0.333 Taro leaves, raw   -> grape leaves (Grape leaves, raw auto at 0.765)
weak  romaine       0.421 Romaine lettuce, raw     (its own row, below the floor)
weak  pak choi      0.346 Cabbage, chinese (pak-choi), raw   (its own row, verbatim)
```

`vine leaves` is the one that would do damage rather than merely fail: it lands
on **taro leaves**, a different plant that must be cooked before eating and is
nutritionally unlike a brined grape leaf.


---

## Batch 9 — aged/hard cheeses and dairy grades (50 terms)

```
weak  parmesan                           0.429  Cheese, parmesan, hard
weak  parmigiano reggiano                0.391  Veal parmigiana
none  pecorino                           -      (nothing)
weak  pecorino romano                    0.318  Cheese, romano
none  grana padano                       -      (nothing)
none  manchego                           -      (nothing)
none  comte                              -      (nothing)
ask   gruyere                            0.533  Cheese, gruyere
none  emmental                           -      (nothing)
auto  cheddar                            0.667  Cheese, cheddar
weak  mature cheddar                     0.421  Cheese, cheddar
ask   gouda                              0.462  Cheese, gouda
weak  edam                               0.417  Cheese, edam
ask   provolone                          0.588  Cheese, provolone
none  asiago                             -      (nothing)
ask   cotija                             0.538  Queso cotija
none  kefalotyri                         -      (nothing)
none  kashkaval                          -      (nothing)
weak  pepper jack                        0.391  Spices, pepper, black
none  red leicester                      -      (nothing)
none  wensleydale                        -      (nothing)
none  double gloucester                  -      (nothing)
ask   hard cheese                        0.571  Cheese, parmesan, hard
weak  aged cheese                        0.387  Queso Anejo, aged Mexican cheese
weak  grating cheese                     0.407  Cheese, parmesan, grated
auto  blue cheese                        1.000  Cheese, blue
none  gorgonzola                         -      (nothing)
ask   roquefort                          0.588  Cheese, roquefort
none  stilton                            -      (nothing)
weak  brie                               0.417  Cheese, brie
auto  camembert                          0.625  Cheese, camembert
none  raclette                           -      (nothing)
none  taleggio                           -      (nothing)
ask   fontina                            0.533  Cheese, fontina
ask   greek yogurt                       0.565  Yogurt, Greek, with oats
auto  plain yogurt                       0.650  Yogurt, plain, nonfat
weak  natural yogurt                     0.444  Yogurt, NFS
weak  full fat yogurt                    0.440  Yogurt, plain, low fat
auto  kefir                              1.000  Kefir
auto  buttermilk                         1.000  Buttermilk
weak  double cream                       0.353  Cake, cream
auto  heavy cream                        1.000  Cream, heavy
weak  single cream                       0.353  Cake, cream
none  creme fraiche                      -      (nothing)
auto  soured cream                       0.684  Cream, sour, cultured
auto  condensed milk                     0.625  Milk, condensed, sweetened
auto  evaporated milk                    0.727  Milk, evaporated, whole
auto  whole milk                         1.000  Milk, whole
weak  semi skimmed milk                  0.346  Milk, fat free (skim)
weak  skimmed milk                       0.409  Milk, fat free (skim)

ask=8 (16%)  auto=11 (22%)  none=16 (32%)  weak=15 (30%)
```

### Aged/hard cheese is the ONE family where a parent is defensible

Measured per 100 g:

```
                             kcal  prot   fat    satfat  Ca     Na     chol
170848 Cheese, parmesan, hard 392  35.75  25.00  14.85   1184   1175    68
171249 Cheese, romano         387  31.80  26.94  17.12   1064   1433   104
171242 Cheese, gruyere        413  29.81  32.34  18.91   1011    714   110
328637 Cheese, cheddar        408  23.30  34.00  19.20    707    654   100
170850 Cheese, provolone      351  25.58  26.62  17.08    756    727    69
171241 Cheese, gouda          356  24.94  27.44  17.61    700    819   114
172175 Cheese, blue           353  21.40  28.74  18.67    528   1146    75
172177 Cheese, brie           334  20.75  27.68  17.41    184    629   100
```

Excluding parmesan/romano (which are drier and higher-protein by make) and brie
(a soft-ripened outlier on calcium), **energy is 351–413 (±8%), fat 26.6–34.0,
saturated fat 17.1–19.2 (±6%), sodium 629–1146.** For once a category holds.

That gives real, defensible mappings for the sixteen `none` results:

* `grana padano`, `pecorino`, `pecorino romano` → `Cheese, romano` — same
  make (hard, grating, sheep or long-aged cow), same 387 kcal / 1064 Ca band.
  `parmigiano reggiano` → `Cheese, parmesan, hard`, which today reaches
  **`Veal parmigiana`** at 0.391.
* `comté`, `emmental`, `raclette` → `Cheese, gruyere` — Alpine cooked-curd,
  the closest make and within 5% on every line.
* `manchego`, `asiago`, `kashkaval`, `kefalotyri` → `Cheese, gouda` or
  `Cheese, provolone`; all semi-hard pressed, 351–356 kcal.
* `red leicester`, `double gloucester`, `wensleydale` → `Cheese, cheddar` —
  literally the same make with different colour and moisture.
* `gorgonzola`, `stilton` → `Cheese, blue` (which auto-matches at 1.000).

These are the highest-confidence proposals in this audit and the reason is that
**hard cheese is defined by its make and its make fixes its composition** — the
opposite of the fresh-cheese family in batch 2, where make is exactly what
splits them.

### FINDING (b/c) — the British dairy grades have no route at all

```
weak  double cream                       0.353  Cake, cream
weak  single cream                       0.353  Cake, cream
weak  semi skimmed milk                  0.346  Milk, fat free (skim)
weak  skimmed milk                       0.409  Milk, fat free (skim)
none  creme fraiche                      -      (nothing)
```

`Cake, cream` for both cream grades is not a near miss, it is a cake. And
`semi skimmed milk` → `Milk, fat free (skim)` is the wrong end of the grade
scale:

```
2705386 Milk, reduced fat (2%)   kcal=50  fat=1.90   <- what semi-skimmed is
        Milk, fat free (skim)    kcal=34  fat=0.2    <- what it resolves to
2346386 Cream, heavy             fat=35.56 satfat=20.45  <- what double cream is nearest
2705593 Cream, light             kcal=195 fat=19.10 satfat=10.18  <- single cream
```

A litre of semi-skimmed logged as skim loses 160 kcal and 17 g of fat. This is
a **synonym problem with a measurable price**, and it is entirely a British-vs-
American vocabulary gap: every target row exists and auto-matches under its
American name.

`double cream` is the one to be careful with: UK double cream is ~48% fat
against `Cream, heavy` at 35.6%. That is a 35% understatement, so the mapping is
**medium** confidence — better than `Cake, cream` by a wide margin, but not a
synonym.

### FINDING — `greek yogurt` reaches a sweetened breakfast product

```
ask   greek yogurt                       0.565  Yogurt, Greek, with oats
```

`Yogurt, Greek, plain, whole milk` (2259794) exists. The head candidate is the
oat-and-sugar version. Below the auto gate, so the model tier sees it, but the
list it is handed is dominated by CHOBANI flavour SKUs — a search for
`Yogurt, Greek` returns eight rows and every one is a fruit blend:

```
170864 Yogurt, Greek, 2% fat, apricot, CHOBANI
173434 Yogurt, Greek, 2% fat, key lime blend, CHOBANI
172199 Yogurt, Greek, 2% fat, mango, CHOBANI
...
```


---

## Batch 10 — the carbonara test: every dish beside its defining ingredient (52 terms)

```
none  carbonara                          -      (nothing)
weak  spaghetti carbonara                0.400  Spaghetti sauce
weak  saag paneer                        0.438  Palak Paneer
auto  palak paneer                       1.000  Palak Paneer
weak  mapo tofu                          0.312  Tofu, fried
none  doubanjiang paste                  -      (nothing)
ask   kimchi jjigae                      0.500  Kimchi
auto  kimchi                             1.000  Kimchi
ask   bibimbap                           0.562  Bibimbap, Korean
weak  gochujang paste                    0.333  Guava paste
auto  pad thai                           0.692  Pad Thai, NFS
ask   tamarind paste                     0.600  Tamarind
auto  fish sauce                         1.000  Fish sauce
auto  dried shrimp                       1.000  Shrimp, dried
weak  pho                                0.235  Soup, pho, no meat
weak  star anise                         0.333  Spices, anise seed
auto  rice noodles                       0.765  Rice noodles, dry
none  laksa                              -      (nothing)
auto  coconut milk                       1.000  Coconut milk
ask   shrimp paste                       0.450  Kung Pao shrimp
none  belacan                            -      (nothing)
ask   hummus                             0.538  Hummus, plain
auto  chickpeas                          0.714  Chickpeas, NFS
auto  falafel                            1.000  Falafel
none  baba ganoush                       -      (nothing)
ask   tahini sauce                       0.538  Tahini
none  shakshuka                          -      (nothing)
none  harissa spice                      -      (nothing)
ask   moussaka                           0.455  Mousse
none  bechamel                           -      (nothing)
auto  pierogi                            1.000  Pierogi
none  bigos                              -      (nothing)
auto  sauerkraut                         1.000  Sauerkraut
none  zurek                              -      (nothing)
weak  sour rye starter                   0.300  Flour, rye
none  kotlet schabowy                    -      (nothing)
weak  pork loin                          0.435  Pork, loin, boneless, raw
weak  feijoada                           0.429  Feijoa, raw
auto  black beans                        0.733  Black beans, NFS
weak  jollof rice                        0.300  Cream of rice
weak  scotch bonnet pepper               0.333  Scotch
none  tagine                             -      (nothing)
weak  preserved lemon                    0.368  Pie, lemon
none  ras el hanout                      -      (nothing)
weak  ramen                              0.400  Ramen bowl, NFS
none  chashu                             -      (nothing)
none  nori                               -      (nothing)
ask   miso soup                          0.556  Soup, miso or tofu
none  dashi                              -      (nothing)
none  katsuobushi                        -      (nothing)
weak  kombu                              0.357  Tea, kombucha
none  bonito flakes                      -      (nothing)
```
```
ask=8 (15%)  auto=12 (23%)  none=18 (35%)  weak=14 (27%)
```

### The carbonara pattern is general: the dish resolves, its signature does not

| dish | verdict | signature ingredient | verdict |
|---|---|---|---|
| `palak paneer` | **auto 1.000** | `paneer` | escalates; and its row's macros are wrong (batch 2) |
| `pierogi` | **auto 1.000** | `twaróg` | **none** (batch 2) |
| `miso soup` | ask 0.556 | `dashi` / `katsuobushi` / `kombu` / `nori` | **none / none / weak 0.357 / none** |
| `kimchi jjigae` | ask 0.500 | `gochujang` | **none** (batch 3) |
| `mapo tofu` | weak 0.312 | `doubanjiang` | **none** (batch 3) |
| `laksa` | **none** | `belacan` / `shrimp paste` | **none** / ask 0.450 `Kung Pao shrimp` |
| `bigos` | **none** | `sauerkraut` auto 1.000, `kielbasa` — but `slanina` **none** (batch 1) |
| `tagine` | **none** | `preserved lemon` weak 0.368 `Pie, lemon`, `ras el hanout` **none** |
| `spaghetti carbonara` | weak 0.400 `Spaghetti sauce` | `guanciale` | **none** (batch 1) |

When the dish resolves and the ingredient does not, the model's item list is
the only thing standing between the user and a plausible wrong number — and
the model is being asked to name an ingredient it knows the database cannot
hold. That is precisely the position that produced the fabricated "deli"
qualifier recorded in CLAUDE.md.

### FINDING (b) — `nori` returns nothing while `Seaweed, laver, raw` sits in the table

```
none  nori                               -      (nothing)
weak  kombu                              0.357  Tea, kombucha

$ q.py find "Seaweed"
  168458 | sr_legacy_food | Seaweed, laver, raw          <- nori
  168457 | sr_legacy_food | Seaweed, kelp, raw           <- kombu
  170090 | sr_legacy_food | Seaweed, agar, dried
 2709988 | survey_fndds_food | Seaweed, dried
 2709805 | survey_fndds_food | Seaweed, raw
  ... 12 rows
```

`laver` **is** nori and `kelp` **is** kombu; both are exact botanical
identities, not fallbacks. `kombu` currently reaches `Tea, kombucha` — a
fermented sweet tea drink, which is a different substance that merely starts
with the same four letters.

### FINDING (b) — `star anise` resolves to a different plant

```
weak  star anise                         0.333  Spices, anise seed
$ q.py find "anise"   ->  only "Spices, anise seed" and "Anisette toast"
```

Star anise is *Illicium verum*, a fruit; anise seed is *Pimpinella anisum*, an
umbellifer seed. They share a flavour compound and nothing else. USDA has no
star anise row — this is a genuine **entity gap**, and because the quantities
used are 1–2 g the honest answer is that neither row matters nutritionally.
Recorded here as an entity gap that deliberately gets **no** proposal.

### `Dish, ingredient` inversion, third and fourth sightings

```
weak  preserved lemon                    0.368  Pie, lemon
weak  feijoada                           0.429  Feijoa, raw
weak  jollof rice                        0.300  Cream of rice
```

`Pie, lemon` for a preserved lemon completes the set with `Pie, sweet potato`
and `Salmon salad`. All three put a dish word where the guard does not look.
Only the `sweet potato` one clears 0.62 and auto-matches today; the others are
saved by their low scores, not by any check.


---

## Batch 11 — how wide is the `Dish, ingredient` blind spot? (systematic scan)

The `Pie, sweet potato` result in batch 6 is not a one-off, so I measured its
extent instead of guessing. Scratchpad `dishscan.py` (read-only) takes every
`food` row whose description is `<DishWord>, <tail>` for 24 dish words, feeds
the **tail alone** to `db.search_foods` as if a person had typed it, and applies
all four shipped guards:

```
scanned 893 `Head, tail` rows; 95 distinct tails auto-match their own dish row
```

Filtered to tails that are ordinary ingredient or food words rather than
recipe names, verified independently through `probe_knowledge.py`:

```
auto  strawberry                         0.733  Pie, strawberry
auto  pumpkin                            0.727  Pie, pumpkin
auto  blueberry                          0.714  Pie, blueberry
auto  peach                              0.667  Pie, peach
auto  pecan                              0.667  Pie, pecan
auto  cherry                             0.636  Pie, cherry
auto  seaweed                            0.667  Soup, seaweed
auto  vegetable                          0.667  Soup, vegetable
auto  sweet potato                       0.812  Pie, sweet potato

auto=9 (100%)
```

and passing `state="raw"` does not change any of them:

```
'strawberry': effective=AUTO -> Pie, strawberry   (head 0.733 Pie, strawberry)
'pumpkin':    effective=AUTO -> Pie, pumpkin
'pecan':      effective=AUTO -> Pie, pecan
```

Measured cost per 100 g:

```
                        kcal   fat    carb   sugar   Na
Pie, strawberry         289    11.60  44.22  22.59  189
Strawberries, raw        31     0.22   7.63   5.34   10     <- 9.3x energy, 53x fat
Pie, pumpkin            249     9.78  36.34  24.55  252
Pumpkin, raw             26     0.10   6.50   2.76    1     <- 9.6x energy, 98x fat
Pie, blueberry          300    15.52  37.95  15.49  217
Blueberries, raw          —     0.31  14.57   9.36    0     <- 51x fat
Pie, pecan              449    25.25  49.46  31.01  299
Pecans, NFS             750    73.28  12.70   3.97    0     <- energy the OTHER way, -40%
```

**`strawberry` is not an exotic word.** A 150 g bowl of strawberries is logged
as 434 kcal, 17 g of fat and 34 g of sugar instead of 47 kcal, 0.3 g and 8 g —
and because the label is a substring of the description, SPEC-2 §5 suppresses
the line on the confirm card that would name the matched row. The user sees
"strawberry, 150 g" and presses confirm. The alias is then cached and never
re-checked (`upsert_alias` has no repointing command), so **every strawberry
after it is pie**.

This is the highest-value finding in the audit and it needs no knowledge layer
to fix — it is a fifth guard, or an extension of `unrequested_qualifier` to the
head segment when the head segment is a preparation/dish noun. The existing
comment is explicit that the first segment is skipped because "a different name
is a weak match rather than a narrowed one"; that reasoning holds for
`Broccoli, raw` vs `Spinach, raw` and fails for `Pie, strawberry`, because a
dish word in the head is not a competing *name*, it is a transformation.

The same reasoning covers `Flour, rice, brown` (batch 6) and `Salmon salad`
(batch 7) — a form word and a dish word in the position the guard does not
inspect.

