# AUDIT-japanese-korean

28 Aug 2026. Probe: `scripts/probe_knowledge.py` (read-only, `SELECT` only).
Domain: Japanese and Korean dishes, defining ingredients, and romanisation
variants. Every dish tested is accompanied by its signature ingredient tested
separately — a dish that resolves while its defining ingredient returns nothing
is the carbonara/guanciale failure this audit exists for.

Verdicts: `none` (nothing returned) | `weak` (below the weak floor) | `ask`
(escalates to the model tier — the system working) | `auto` (taken with no
model consulted — the dangerous one when wrong, because it caches an alias).

## Verdict counts

| batch | terms | none | weak | ask | auto |
|---|---|---|---|---|---|
| 1 Japanese dishes + ingredients | 90 | 53 (59%) | 22 (24%) | 10 (11%) | 5 (6%) |
| 2 Japanese ingredients + condiments | 134 | 61 (46%) | 32 (24%) | 28 (21%) | 13 (10%) |
| 3 Korean dishes + ingredients | 136 | 72 (53%) | 36 (26%) | 20 (15%) | 8 (6%) |
| 4 orthography, yoshoku, cuts, stocks | 117 | 63 (54%) | 29 (25%) | 17 (15%) | 8 (7%) |
| **total** | **477** | **249 (52%)** | **119 (25%)** | **75 (16%)** | **34 (7%)** |

Plus 39 targeted neighbour/verification probes reported inline under the
findings they belong to.

## Findings

### Batch 1 — Japanese noodles, donburi, fried, grilled, hot pot (90 terms)

Verbatim probe output, `scripts/probe_knowledge.py --file` (90 lines):

```
weak  ramen                              0.400  Ramen bowl, NFS
none  shoyu ramen                        -      (nothing)
ask   miso ramen                         0.455  Miso
none  tonkotsu ramen                     -      (nothing)
weak  shio ramen                         0.300  Ramen bowl, NFS
none  tantanmen                          -      (nothing)
none  tsukemen                           -      (nothing)
none  instant ramen                      -      (nothing)
ask   ramen noodles                      0.452  Soup, ramen noodles, water added
none  chashu                             -      (nothing)
ask   chashu pork                        0.467  Pork hash
none  menma                              -      (nothing)
auto  bamboo shoots                      0.778  Bamboo shoots, raw
none  ajitama                            -      (nothing)
none  marinated soft boiled egg          -      (nothing)
none  narutomaki                         -      (nothing)
ask   fish cake                          0.526  Fish, cake or patty
none  udon                               -      (nothing)
weak  udon noodles                       0.400  Noodles, cooked
none  kake udon                          -      (nothing)
none  kitsune udon                       -      (nothing)
weak  tempura udon                       0.348  Vegetable tempura
none  yaki udon                          -      (nothing)
weak  soba                               0.192  Noodles, japanese, soba, dry
ask   soba noodles                       0.500  Noodles, japanese, soba, dry
ask   buckwheat noodles                  0.556  Buckwheat
none  zaru soba                          -      (nothing)
none  kake soba                          -      (nothing)
weak  somen                              0.222  Noodles, japanese, somen, dry
ask   somen noodles                      0.519  Noodles, japanese, somen, dry
none  hiyamugi                           -      (nothing)
none  yakisoba                           -      (nothing)
weak  yakisoba noodles                   0.344  Noodles, japanese, soba, dry
none  donburi                            -      (nothing)
none  gyudon                             -      (nothing)
none  katsudon                           -      (nothing)
none  oyakodon                           -      (nothing)
none  unadon                             -      (nothing)
none  unagi                              -      (nothing)
weak  grilled eel                        0.421  Shrimp, grilled
none  tendon                             -      (nothing)
none  chirashi don                       -      (nothing)
none  tonkatsu                           -      (nothing)
weak  pork cutlet                        0.312  Pork, NFS
none  panko                              -      (nothing)
none  panko breadcrumbs                  -      (nothing)
weak  breadcrumbs                        0.312  Bread, crumbs, dry, grated, plain
none  karaage                            -      (nothing)
weak  japanese fried chicken             0.424  Rice, fried, with chicken
weak  potato starch                      0.189  Rolls, gluten-free, white, ... potato starch
none  katakuriko                         -      (nothing)
weak  tempura                            0.444  Vegetable tempura
weak  tempura batter                     0.320  Vegetable tempura
weak  tempura prawn                      0.333  Vegetable tempura
none  kakiage                            -      (nothing)
none  okonomiyaki                        -      (nothing)
weak  okonomiyaki sauce                  0.435  Teriyaki sauce
none  takoyaki                           -      (nothing)
auto  octopus                            1.000  Octopus
ask   takoyaki sauce                     0.500  Teriyaki sauce
none  bonito flakes                      -      (nothing)
none  katsuobushi                        -      (nothing)
none  aonori                             -      (nothing)
none  yakitori                           -      (nothing)
none  momo yakitori                      -      (nothing)
none  negima                             -      (nothing)
none  tsukune                            -      (nothing)
none  kawa yakitori                      -      (nothing)
auto  chicken skin                       1.000  Chicken skin
ask   chicken thigh                      0.467  Chicken thigh, stewed, skin eaten
ask   chicken meatball                   0.545  Chicken, meatless
auto  tare sauce                         0.643  Tartar sauce
none  sukiyaki                           -      (nothing)
none  shabu shabu                        -      (nothing)
none  nabe                               -      (nothing)
none  hot pot                            -      (nothing)
none  chanko nabe                        -      (nothing)
none  oden                               -      (nothing)
none  chawanmushi                        -      (nothing)
weak  savory egg custard                 0.429  Egg custards, dry mix
none  onigiri                            -      (nothing)
weak  rice ball                          0.400  Bread, rice
auto  natto                              1.000  Natto
weak  fermented soybeans                 0.400  Soybeans, cooked
none  tamagoyaki                         -      (nothing)
none  japanese rolled omelette           -      (nothing)
none  gyoza                              -      (nothing)
weak  japanese curry                     0.400  Cookie, tea, Japanese
weak  katsu curry                        0.353  Beef curry
weak  curry roux                         0.375  Beef curry

ask=10 (11%)  auto=5 (6%)  none=53 (59%)  weak=22 (24%)
```

#### F1. `tare sauce` -> `Tartar sauce` (auto)

kind: **wrong_confident_match** | category: `bad_fuzzy_matching`

```
== tare sauce  auto
    0.643 Tartar sauce | survey_fndds_food
    0.571 Taco sauce | survey_fndds_food
    0.429 Soy sauce | survey_fndds_food
    0.400 Sauce, NFS | survey_fndds_food
    0.400 Fry sauce | survey_fndds_food
    0.375 Miso sauce | survey_fndds_food
```

Expected: `Soy sauce` (or a teriyaki/mirin glaze row). Tare is the soy-mirin-sugar
glaze brushed on yakitori and brushed into ramen. `Tartar sauce` is a
mayonnaise emulsion: it is fat where tare is sugar and sodium. One vowel of
edit distance decides it, and the alias is then cached for every yakitori
logged after. This is the single most damaging `auto` in the batch.

#### F2. `soba` -> 0.192, `somen` -> 0.222 (both weak, correct row is rank 1)

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```
== soba  weak
    0.192 Noodles, japanese, soba, dry | sr_legacy_food
    0.172 Noodles, japanese, soba, cooked | sr_legacy_food

== somen  weak
    0.222 Noodles, japanese, somen, dry | sr_legacy_food
    0.200 Noodles, japanese, somen, cooked | sr_legacy_food
```

USDA holds the exactly-right rows and the query returns them *at rank 1* — and
still falls under the weak floor, so nothing is offered. This is the length
effect of RESUME.md in its purest form: a 4-letter query against a 27-character
description. Note the perverse gradient: `soba noodles` reaches 0.500 (`ask`)
and `noodles japanese` reaches 0.654 (`auto`) — the *less* Japanese the phrasing,
the better it scores. Also note `soba` picks `dry` over `cooked`, a 3.5x energy
difference per 100 g, purely on description length.

#### F3. `udon` -> nothing, and USDA has no udon row

kind: **entity_gap** | category: `missing_food_entity`

```
== udon  none
    (nothing)
== noodles japanese  auto
    0.654 Noodles, japanese, soba, dry | sr_legacy_food
    0.630 Noodles, japanese, somen, dry | sr_legacy_food
    0.586 Noodles, japanese, soba, cooked | sr_legacy_food
    0.567 Noodles, japanese, somen, cooked | sr_legacy_food
    0.367 Noodles, chinese, chow mein | sr_legacy_food
    0.333 Noodles, cooked | survey_fndds_food
== wheat noodles  weak
    0.381 Noodles, cooked | survey_fndds_food
    0.375 Adobo, with noodles | survey_fndds_food
    0.348 Rice noodles, dry | sr_legacy_food
```

Neighbour search by category (`noodles japanese`) enumerates the whole Japanese
noodle family in USDA: soba and somen, dry and cooked. There is no udon row.
Searching by ingredient (`wheat noodles`) reaches only the generic
`Noodles, cooked`. So this is a genuine entity gap with a defensible fallback:
udon is a thick wheat-flour noodle, and `Noodles, cooked` (FNDDS, egg-free
generic) or `Noodles, japanese, somen, cooked` (wheat, salted, no egg) are the
two candidates. Somen is the better nutritional match — same flour, same salt
tradition — and is already in the database.

#### F4. `yakisoba noodles` -> `Noodles, japanese, soba, dry` (weak, and wrong food)

kind: **wrong_confident_match** (near-miss; escalates today only because the
score is low) | category: `bad_fuzzy_matching`

```
== yakisoba noodles  weak
    0.344 Noodles, japanese, soba, dry | sr_legacy_food
    0.333 Noodles, cooked | survey_fndds_food
    0.314 Noodles, japanese, soba, cooked | sr_legacy_food
    0.308 Rice noodles, dry | sr_legacy_food
```

Yakisoba contains no buckwheat: it is a *wheat* ramen-style noodle, and the
"soba" in the name means "noodle", not "buckwheat". The substring drags it onto
the buckwheat row. The fibre and the gluten story are both wrong. Today it lands
weak so nothing is logged silently; any ranking change that lifts it 0.28
converts a naming coincidence into a cached alias.

#### F5. `japanese curry` -> `Cookie, tea, Japanese` (weak)

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```
== japanese curry  weak
    0.400 Cookie, tea, Japanese | survey_fndds_food
    0.333 Nuts, chestnuts, japanese, raw | sr_legacy_food
    0.323 Noodles, japanese, soba, dry | sr_legacy_food
```

The word "japanese" is doing all the work and the word "curry" none of it —
every candidate is a Japanese *something* and not one is a curry. `katsu curry`
(0.353) and `curry roux` (0.375) both reach `Beef curry`, which is the right
neighbourhood; the more specific query is the worse one.

#### F6. `eel` -> 0.444 weak, while `Fish, eel` exists

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```
== eel  weak
    0.444 Fish, eel | survey_fndds_food
    0.267 Sushi roll, eel | survey_fndds_food
    0.182 Sushi, topped with eel | survey_fndds_food
    0.148 Fish, eel, mixed species, raw | sr_legacy_food
    0.105 Fish, eel, mixed species, cooked, dry heat | sr_legacy_food
```

`unagi` and `unadon` return nothing; the English word reaches the right row at
rank 1 and still sits under the floor. Unagi is glazed and grilled, so the
cooked SR row (rank 5, 0.105) is the honest one and is effectively unreachable.

#### F7. Whole-dish `none` block — Japanese

kind: **entity_gap**, but not one worth a food row | category: `missing_dish_ingredient`

53 of 90 returned *nothing*. The pattern is that USDA has no composite row for
almost any named Japanese dish: `tonkatsu`, `karaage`, `okonomiyaki`,
`takoyaki`, `yakitori`, `sukiyaki`, `shabu shabu`, `oden`, `chawanmushi`,
`onigiri`, `tamagoyaki`, `gyoza`, `donburi` and every `-don` compound. That is
the correct state of affairs — these are dishes, and the parse tier is supposed
to break them into components. The failure is not the missing dish row, it is
that the *components* are also unreachable: `panko` (nothing), `katsuobushi`
(nothing), `bonito flakes` (nothing), `menma` (nothing), `chashu` (nothing),
`tare sauce` (wrong). A dish that decomposes into unreachable ingredients is the
carbonara/guanciale failure, one level down.

### Batch 2 — Japanese ingredients, seasonings, seaweeds, sushi (134 terms)

```
auto  miso                               1.000  Miso
ask   miso paste                         0.455  Miso
ask   shiro miso                         0.455  Miso
ask   white miso                         0.455  Miso
ask   aka miso                           0.556  Miso
ask   red miso                           0.556  Miso
ask   awase miso                         0.455  Miso
weak  hatcho miso                        0.417  Miso
ask   miso soup                          0.556  Soup, miso or tofu
none  dashi                              -      (nothing)
none  dashi stock                        -      (nothing)
none  bonito stock                       -      (nothing)
weak  kombu                              0.357  Tea, kombucha
none  kombu dashi                        -      (nothing)
weak  kelp                               0.294  Seaweed, kelp, raw
none  konbu                              -      (nothing)
none  nori                               -      (nothing)
none  nori sheet                         -      (nothing)
ask   seaweed nori                       0.471  Seaweed, raw
weak  laver                              0.333  Seaweed, laver, raw
weak  wakame                             0.368  Seaweed, wakame, raw
none  hijiki                             -      (nothing)
none  arame                              -      (nothing)
none  dulse                              -      (nothing)
weak  agar agar                          0.294  Seaweed, agar, raw
none  kanten                             -      (nothing)
weak  sake                               0.172  Alcoholic beverage, rice (sake)
weak  cooking sake                       0.357  Oil, olive, salad or cooking
none  ryorishu                           -      (nothing)
auto  rice wine                          1.000  Wine, rice
none  mirin                              -      (nothing)
none  hon mirin                          -      (nothing)
none  aji mirin                          -      (nothing)
none  ponzu                              -      (nothing)
weak  ponzu sauce                        0.412  Pesto sauce
none  yuzu                               -      (nothing)
weak  yuzu juice                         0.375  Beet juice
none  sudachi                            -      (nothing)
none  shiso                              -      (nothing)
none  perilla leaf                       -      (nothing)
none  perilla                            -      (nothing)
weak  green perilla                      0.381  Peas, green, raw
auto  wasabi                             1.000  Wasabi
ask   real wasabi                        0.583  Wasabi
auto  wasabi paste                       1.000  Wasabi paste
auto  horseradish                        1.000  Horseradish
ask   japanese horseradish               0.571  Horseradish
none  daikon                             -      (nothing)
ask   daikon radish                      0.500  Radish
none  takuan                             -      (nothing)
weak  pickled daikon                     0.400  Fish, pickled
none  tsukemono                          -      (nothing)
weak  japanese pickles                   0.385  Cabbage, japanese style, fresh, pickled
none  umeboshi                           -      (nothing)
ask   pickled plum                       0.471  Okra, pickled
weak  ume plum                           0.385  Plum, raw
none  koji                               -      (nothing)
weak  rice koji                          0.333  Rice milk
weak  sushi rice                         0.400  Sushi, NFS
weak  japanese rice                      0.360  Cookie, tea, Japanese
ask   short grain rice                   0.472  Rice, white, short-grain, raw, unenriched
ask   sushi                              0.600  Sushi, NFS
none  nigiri                             -      (nothing)
weak  maki roll                          0.385  Roll, rye
auto  california roll                    0.727  Sushi roll, California
none  sashimi                            -      (nothing)
ask   salmon sashimi                     0.471  Lomi salmon
weak  tuna sashimi                       0.318  Fish, tuna salad
none  maguro                             -      (nothing)
ask   sake salmon                        0.538  Salmon salad
weak  hamachi                            0.333  Ham
weak  yellowtail                         0.324  Fish, yellowtail, mixed species, raw
none  ikura                              -      (nothing)
ask   salmon roe                         0.500  Salmon salad
none  tobiko                             -      (nothing)
weak  flying fish roe                    0.381  Fish, ling, raw
none  uni                                -      (nothing)
none  sea urchin                         -      (nothing)
ask   edamame                            0.533  Edamame, cooked
weak  soybeans in pod                    0.407  Beans, fava, in pod, raw
ask   tofu                               0.455  Tofu, fried
ask   silken tofu                        0.500  MORI-NU, Tofu, silken, soft
weak  firm tofu                          0.400  MORI-NU, Tofu, silken, firm
none  atsuage                            -      (nothing)
none  aburaage                           -      (nothing)
auto  fried tofu                         1.000  Tofu, fried
none  yuba                               -      (nothing)
weak  tofu skin                          0.312  Tofu, fried
ask   shiitake                           0.474  Mushrooms, shiitake
auto  shiitake mushroom                  0.850  Mushrooms, shiitake
weak  enoki                              0.400  Mushroom, enoki
none  shimeji                            -      (nothing)
ask   maitake                            0.500  Mushroom, maitake
none  nameko                             -      (nothing)
none  renkon                             -      (nothing)
auto  lotus root                         0.786  Lotus root, raw
none  gobo                               -      (nothing)
auto  burdock root                       0.812  Burdock root, raw
none  mitsuba                            -      (nothing)
none  negi                               -      (nothing)
weak  japanese leek                      0.360  Cookie, tea, Japanese
none  mizuna                             -      (nothing)
none  komatsuna                          -      (nothing)
none  shungiku                           -      (nothing)
none  satsumaimo                         -      (nothing)
ask   japanese sweet potato              0.520  Pie, sweet potato
none  kabocha                            -      (nothing)
weak  japanese pumpkin                   0.400  Pie, pumpkin
none  goma                               -      (nothing)
auto  sesame seeds                       1.000  Sesame seeds
auto  sesame oil                         1.000  Sesame oil
ask   toasted sesame oil                 0.579  Sesame oil
ask   rice vinegar                       0.615  Vinegar
none  su                                 -      (nothing)
none  sansho                             -      (nothing)
none  shichimi togarashi                 -      (nothing)
weak  seven spice                        0.400  Seven and Seven
none  karashi                            -      (nothing)
ask   japanese mustard                   0.471  Mustard
ask   kewpie mayonnaise                  0.458  Vegan mayonnaise
weak  japanese mayonnaise                0.440  Vegan mayonnaise
weak  tonkatsu sauce                     0.368  Taco sauce
auto  worcestershire sauce               1.000  Sauce, worcestershire
none  furikake                           -      (nothing)
none  matcha                             -      (nothing)
weak  green tea powder                   0.385  Tea, hot, leaf, green
none  sencha                             -      (nothing)
none  hojicha                            -      (nothing)
none  mochi                              -      (nothing)
none  daifuku                            -      (nothing)
none  anko                               -      (nothing)
ask   red bean paste                     0.500  Bean paste, sweetened
none  dorayaki                           -      (nothing)
none  taiyaki                            -      (nothing)

ask=28 (21%)  auto=13 (10%)  none=61 (46%)  weak=32 (24%)
```

#### F8. The three seaweeds are distinct foods, and none is reachable by its own name

kind: **reachability_gap** | category: `missing_synonym`

USDA holds each of them, under English or Latin-derived names a cook will never
type. Full seaweed family in the database
(`SELECT fdc_id, description FROM food WHERE description ILIKE '%seaweed%'`):

```
 167602 | Seaweed, Canadian Cultivated EMI-TSUNOMATA, dry
 167603 | Seaweed, Canadian Cultivated EMI-TSUNOMATA, rehydrated
 170090 | Seaweed, agar, dried
 169280 | Seaweed, agar, raw
2709990 | Seaweed, cooked, fat added
2709989 | Seaweed, cooked, no added fat
2709988 | Seaweed, dried
 168456 | Seaweed, irishmoss, raw
 168457 | Seaweed, kelp, raw            <- kombu
 168458 | Seaweed, laver, raw           <- nori
2710100 | Seaweed, pickled
2709805 | Seaweed, raw
 170495 | Seaweed, spirulina, dried
 170091 | Seaweed, spirulina, raw
 170496 | Seaweed, wakame, raw
2710110 | Soup, seaweed
```

They are not interchangeable, measured:

```
 168458 | Seaweed, laver, raw   (nori)   |  35 kcal |   48 mg sodium
 168457 | Seaweed, kelp, raw    (kombu)  |  43 kcal |  233 mg sodium
 170496 | Seaweed, wakame, raw          |  45 kcal |  872 mg sodium
```

18x sodium between nori and wakame; iodine — not carried in this database —
differs by two orders of magnitude between nori and kombu. Yet:

```
none  nori                               -      (nothing)
ask   nori seaweed                       0.471  Seaweed, raw      <- generic, laver not in top 6
weak  kombu                              0.357  Tea, kombucha
none  konbu                              -      (nothing)
weak  kombu seaweed                      0.444  Seaweed, raw      (kelp 4th at 0.409)
weak  wakame                             0.368  Seaweed, wakame, raw
weak  kelp                               0.294  Seaweed, kelp, raw
weak  laver                              0.333  Seaweed, laver, raw
```

```
== nori seaweed  ask
    0.471 Seaweed, raw | survey_fndds_food
    0.471 Soup, seaweed | survey_fndds_food
    0.444 Seaweed, dried | survey_fndds_food
    0.400 Seaweed, pickled | survey_fndds_food
    0.364 Seaweed, kelp, raw | sr_legacy_food
    0.364 Seaweed, agar, raw | sr_legacy_food

== kombu seaweed  weak
    0.444 Seaweed, raw | survey_fndds_food
    0.444 Soup, seaweed | survey_fndds_food
    0.421 Seaweed, dried | survey_fndds_food
    0.409 Seaweed, kelp, raw | sr_legacy_food
    0.381 Seaweed, pickled | survey_fndds_food
    0.348 Seaweed, agar, raw | sr_legacy_food
```

Three exact rows, none reachable by the word a cook uses, and `kombu` lands on
a fermented tea. This is the highest-value block in the domain: the rows exist,
the mapping is not disputable, and the current behaviour is either nothing or
wrong.

`hijiki`, `arame` and `dulse` return nothing and have **no** row — checked by
category, not just by name:

```
== hijiki seaweed  weak
    0.421 Seaweed, raw | survey_fndds_food
    0.421 Soup, seaweed | survey_fndds_food
    0.400 Seaweed, dried | survey_fndds_food
    0.364 Seaweed, pickled | survey_fndds_food
    0.333 Seaweed, kelp, raw | sr_legacy_food
== brown seaweed  weak
    0.444 Seaweed, raw | survey_fndds_food
    0.421 Seaweed, dried | survey_fndds_food
    0.368 Sugar, brown | survey_fndds_food
```

Genuine entity gaps. They are *not* proposed as fallbacks onto kelp — see
Deliberately rejected.

#### F9. `wasabi` resolves to the horseradish substitute, and asking for the real thing does not change that

kind: **wrong_confident_match** | category: `culturally_incorrect_mapping` / `preparation_state_mismatch`

```
== wasabi  auto
    1.000 Wasabi | sr_legacy_food
    0.583 Wasabi peas | survey_fndds_food
    0.538 Wasabi paste | survey_fndds_food
    0.467 Wasabi, root, raw | sr_legacy_food
    0.200 Snacks, peas, roasted, wasabi-flavored | sr_legacy_food

ask   real wasabi                        0.583  Wasabi
ask   japanese horseradish               0.571  Horseradish
```

Measured:

```
 171831 | Wasabi            | 292 kcal | 3390 mg sodium
2710103 | Wasabi paste      | 292 kcal | 3390 mg sodium
 168583 | Wasabi, root, raw | 109 kcal |   17 mg sodium
2710083 | Horseradish       |  48 kcal |  420 mg sodium
```

The bare row called `Wasabi` **is** the tube paste — horseradish, sorbitol, oil
— at 199x the sodium of the root. For restaurant sushi the paste is the honest
answer, so the `auto` is defensible. What is not defensible is that `real
wasabi` and `fresh wasabi` cannot reach `Wasabi, root, raw`: the disambiguating
word is the one the ranker discards. `japanese horseradish` lands on a third
distinct food.

#### F10. `tofu` cannot reach a plain tofu row; `firm tofu` reaches a *silken brand* row

kind: **reachability_gap** | category: `preparation_state_mismatch`

```
== tofu  ask
    0.455 Tofu, fried | sr_legacy_food
    0.417 Tofu yogurt | sr_legacy_food
    0.278 Soup, miso or tofu | survey_fndds_food
    0.208 Mayonnaise, made with tofu | sr_legacy_food
    0.208 MORI-NU, Tofu, silken, soft | sr_legacy_food
    0.200 Tofu, dried-frozen (koyadofu) | sr_legacy_food

weak  firm tofu                          0.400  MORI-NU, Tofu, silken, firm
weak  firm tofu block                    0.323  MORI-NU, Tofu, silken, firm
auto  fried tofu                         1.000  Tofu, fried
```

The correct rows exist and are absent from the candidate list
(`SELECT ... ILIKE '%tofu%'`):

```
 172476 | Tofu, raw, regular, prepared with calcium sulfate
 172475 | Tofu, raw, firm, prepared with calcium sulfate
 172448 | Tofu, firm, prepared with calcium sulfate and magnesium chloride (nigari)
 174290 | Tofu, extra firm, prepared with nigari
 172450 | Tofu, dried-frozen (koyadofu)
 174280 | Tofu, salted and fermented (fuyu)
```

Measured:

```
 172451 | Tofu, fried                                       | 270 kcal
 172476 | Tofu, raw, regular, prepared with calcium sulfate |  76 kcal
```

**3.6x.** The plain word for the food takes the deep-fried form, because the
correct row's description carries eight words the query does not. `firm tofu`
takes a *brand* row that is silken where the query said firm. Both land below
`auto` today so the model tier sees them — but the list handed to the model does
not contain the right row, which is exactly what `label_absent` was written to
notice.

Aside: `Tofu, dried-frozen (koyadofu)` and `Tofu, salted and fermented (fuyu)`
carry their Japanese names in parentheses and are the two USDA rows that would
answer a Japanese query — and `atsuage`, `aburaage`, `yuba` all return nothing.

#### F11. `sake` -> 0.172 against a row containing the word "sake"

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```
== sake  weak
    0.172 Alcoholic beverage, rice (sake) | sr_legacy_food
```

One candidate, exactly right, containing the query as a whole word, at 0.172 —
the lowest score in this audit for a correct rank-1 row. Four characters against
thirty-two. Nothing in the domain illustrates the length effect so cleanly.

Separately: `cooking sake` -> 0.357 `Oil, olive, salad or cooking`, and `sake
salmon` (a real menu phrasing, sake = salmon in sushi context) -> 0.538
`Salmon salad`. The word is triply overloaded and the ranker has no way to see it.

#### F12. `mirin` -> nothing, and `rice wine` is not a substitute for it

kind: **entity_gap** | category: `missing_food_entity`

```
none  mirin | none  hon mirin | none  aji mirin
== sweet rice wine  auto
    0.625 Wine, rice | survey_fndds_food
    0.458 Wine, dessert, sweet | survey_fndds_food
    0.406 Rice, sweet, cooked with honey | survey_fndds_food
    0.406 Sweet and sour pork with rice | survey_fndds_food
== rice wine japanese  ask
    0.526 Wine, rice | survey_fndds_food
    0.318 Wine, rose | survey_fndds_food
```

Searched by category (rice wine, sweet wine) and by ingredient (sweet rice).
USDA has `Wine, rice` and nothing sweeter. Mirin is roughly 40 g sugar per 100 g
against a dry rice wine's near-zero, so the one available neighbour is wrong in
the only nutrient that matters. Entity gap with **no** proposed fallback — see
Deliberately rejected.

#### F13. `dashi` -> nothing, and neither does either of its two ingredients

kind: **entity_gap** cascading into a dish-ingredient gap | category: `missing_dish_ingredient`

```
none  dashi | none  dashi stock | none  bonito stock | none  kombu dashi
none  katsuobushi | none  bonito flakes            (batch 1)
weak  kombu                              0.357  Tea, kombucha
```

Dashi is the base of miso soup, every nabe, chawanmushi, oden, tamagoyaki, and
the dipping sauce of both soba and tempura — the most-used liquid in the cuisine
— and neither the stock nor either ingredient is reachable. Nutritionally dashi
is close to salted water, so the stock gap is cheap; `katsuobushi` is not,
because it is eaten dry by the handful on okonomiyaki and takoyaki at roughly
350 kcal and 77 g protein per 100 g.

#### F14. Miso is one row, and the variants the brief asks about do not exist

kind: **entity_gap** (bounded, and correctly handled) | category: `missing_food_entity`

```
== miso  auto
    1.000 Miso | sr_legacy_food
    1.000 Miso | survey_fndds_food
    0.455 Miso sauce | survey_fndds_food
    0.278 Soup, miso or tofu | survey_fndds_food
```

`Miso` = 198 kcal, 3728 mg sodium. USDA has no shiro/aka/hatcho split, so
`shiro miso` (0.455), `white miso` (0.455), `aka miso` (0.556), `awase miso`
(0.455) and `hatcho miso` (0.417) all escalate to the model, which has exactly
one row to choose. The answer is right and the route is expensive: five model
calls for a mapping nobody disputes. Note that the real sodium spread — shiro
around 3200 mg, hatcho around 4300 mg per 100 g — is not representable here at
all, so no proposal can recover it and none is made.

#### F15. `shimeji` -> nothing while `Mushroom, beech` is in the database

kind: **reachability_gap** | category: `missing_synonym`

```
== enoki mushroom  auto
    1.000 Mushroom, enoki | foundation_food
    0.667 Mushrooms, enoki, raw | sr_legacy_food
    0.429 Mushroom, beech | foundation_food       <- this is shimeji
    0.409 Mushroom, maitake | foundation_food
    0.409 Mushroom, oyster | foundation_food

none  shimeji                            -      (nothing)
weak  enoki                              0.400  Mushroom, enoki
```

Bunashimeji is sold in English as beech mushroom; the Foundation row exists and
the Japanese name reaches nothing. `enoki` alone is 0.400 against its own exact
row, while `enoki mushroom` is 1.000 — the bare-word length effect once more.
`nameko` returns nothing and has no row.

#### F16. `hamachi` -> `Ham`

kind: **wrong_confident_match** (weak today, so it escalates) | category: `spelling_transliteration_failure`

```
weak  hamachi                            0.333  Ham
weak  yellowtail                         0.324  Fish, yellowtail, mixed species, raw
== yellowtail fish  ask
    0.471 Fish, yellowtail, mixed species, raw | sr_legacy_food
    0.356 Fish, yellowtail, mixed species, cooked, dry heat | sr_legacy_food
    0.333 Fish, tuna, fresh, yellowfin, raw | sr_legacy_food
```

A romanised fish name whose first three letters are a cured pork product. Both
the Japanese name and the English name fail; the row exists. `maguro`, `ikura`,
`tobiko`, `uni` and `sea urchin` all return nothing.

#### F17. "japanese" is an active liability as a query word

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```
weak  japanese curry                     0.400  Cookie, tea, Japanese
weak  japanese leek                      0.360  Cookie, tea, Japanese
weak  japanese rice                      0.360  Cookie, tea, Japanese
ask   japanese sweet potato              0.520  Pie, sweet potato
weak  japanese pumpkin                   0.400  Pie, pumpkin
weak  japanese fried chicken             0.424  Rice, fried, with chicken
weak  japanese mayonnaise                0.440  Vegan mayonnaise
ask   japanese horseradish               0.571  Horseradish
```

Three separate queries land on `Cookie, tea, Japanese`. Qualifying a food with
its cuisine makes it *less* reachable, not more, because the cuisine word
matches a small set of unrelated rows strongly while the food word matches a
large set weakly. The Chinese audit filed `sweet potato -> Pie, sweet potato` at
`auto` 0.812; adding "japanese" does not rescue it, it only lowers the score.

### Batch 3 — Korean dishes, ingredients, romanisation variants (136 terms)

```
auto  kimchi                             1.000  Kimchi
ask   baechu kimchi                      0.500  Kimchi
auto  napa cabbage kimchi                0.750  Cabbage, kimchi
auto  cabbage kimchi                     1.000  Cabbage, kimchi
none  kkakdugi                           -      (nothing)
ask   radish kimchi                      0.500  Radish
none  oi sobagi                          -      (nothing)
ask   cucumber kimchi                    0.450  Cucumber, raw
ask   white kimchi                       0.538  Kimchi
ask   baek kimchi                        0.583  Kimchi
ask   kimchee                            0.500  Kimchi
weak  gimchi                             0.400  Kimchi
ask   bibimbap                           0.562  Bibimbap, Korean
weak  bibimbop                           0.316  Bibimbap, Korean
weak  dolsot bibimbap                    0.391  Bibimbap, Korean
none  bulgogi                            -      (nothing)
none  pulgogi                            -      (nothing)
weak  beef bulgogi                       0.316  Beef burgundy
none  galbi                              -      (nothing)
none  kalbi                              -      (nothing)
weak  short ribs                         0.444  Beef, shortribs
none  la galbi                           -      (nothing)
none  samgyeopsal                        -      (nothing)
ask   pork belly grilled                 0.579  Pork, belly
weak  tteokbokki                         0.423  Dukboki or Tteokbokki, Korean
none  ddeokbokki                         -      (nothing)
none  topokki                            -      (nothing)
auto  rice cake                          1.000  Rice cake
none  tteok                              -      (nothing)
none  garaetteok                         -      (nothing)
ask   rice cakes korean                  0.474  Rice cake
none  japchae                            -      (nothing)
none  chapchae                           -      (nothing)
weak  glass noodles                      0.381  Noodles, cooked
none  dangmyeon                          -      (nothing)
ask   sweet potato noodles               0.583  Sweet potato, NFS
weak  cellophane noodles                 0.317  Noodles, chinese, cellophane or long rice (mung beans), dehydrated
none  sundubu jjigae                     -      (nothing)
weak  soft tofu stew                     0.357  MORI-NU, Tofu, silken, soft
ask   kimchi jjigae                      0.500  Kimchi
ask   kimchi stew                        0.583  Kimchi
none  doenjang jjigae                    -      (nothing)
weak  soybean paste stew                 0.381  Soybean oil
none  budae jjigae                       -      (nothing)
weak  army stew                          0.357  Stew, NFS
none  samgyetang                         -      (nothing)
ask   ginseng chicken soup               0.619  Soup, chicken
weak  ginseng                            0.333  Gin
none  naengmyeon                         -      (nothing)
ask   cold noodles                       0.556  Noodles, cooked
none  mul naengmyeon                     -      (nothing)
none  bibim naengmyeon                   -      (nothing)
none  jeon                               -      (nothing)
none  pajeon                             -      (nothing)
none  haemul pajeon                      -      (nothing)
ask   kimchijeon                         0.500  Kimchi
none  bindaetteok                        -      (nothing)
weak  mung bean pancake                  0.333  Mung beans, cooked
none  banchan                            -      (nothing)
none  side dishes                        -      (nothing)
none  gochujang                          -      (nothing)
none  kochujang                          -      (nothing)
weak  red pepper paste                   0.417  Peppers, red, cooked
none  gochugaru                          -      (nothing)
weak  korean chili flakes                0.324  Cereal, bran flakes, flavored
weak  red pepper powder                  0.417  Peppers, red, cooked
none  doenjang                           -      (nothing)
weak  soybean paste                      0.444  Soybean oil
weak  fermented soybean paste            0.324  Bean paste, sweetened
none  ssamjang                           -      (nothing)
none  jajangmyeon                        -      (nothing)
none  chunjang                           -      (nothing)
ask   black bean paste                   0.455  Black bean sauce
none  myeolchi                           -      (nothing)
weak  dried anchovies                    0.440  Peppers, ancho, dried
ask   anchovy                            0.615  Fish, anchovy
none  myeolchi bokkeum                   -      (nothing)
none  kimbap                             -      (nothing)
none  gimbap                             -      (nothing)
weak  korean seaweed rice roll           0.333  Seaweed, raw
weak  gim                                0.375  Gimlet
weak  korean seaweed                     0.421  Seaweed, raw
none  miyeok                             -      (nothing)
none  miyeok guk                         -      (nothing)
auto  seaweed soup                       1.000  Soup, seaweed
none  guk                                -      (nothing)
none  tang                               -      (nothing)
none  jjigae                             -      (nothing)
none  bokkeum                            -      (nothing)
weak  korean bbq                         0.421  Bibimbap, Korean
weak  sundae                             0.333  Ice cream sundae cone
none  soondae                            -      (nothing)
auto  blood sausage                      1.000  Blood sausage
none  dakgalbi                           -      (nothing)
none  jokbal                             -      (nothing)
none  pig trotters                       -      (nothing)
none  bossam                             -      (nothing)
none  kongnamul                          -      (nothing)
weak  soybean sprouts                    0.333  Soybeans, mature seeds, sprouted, raw
none  sukju namul                        -      (nothing)
weak  mung bean sprouts                  0.395  Mung beans, mature seeds, sprouted, raw
none  namul                              -      (nothing)
weak  spinach namul                      0.444  Spinach, raw
none  sigeumchi                          -      (nothing)
none  gyeranjjim                         -      (nothing)
weak  korean egg custard                 0.379  Egg custards, dry mix
none  mandu                              -      (nothing)
weak  korean dumpling                    0.375  Dumpling, no meat
none  tteokguk                           -      (nothing)
none  juk                                -      (nothing)
none  korean porridge                    -      (nothing)
none  patbingsu                          -      (nothing)
none  hotteok                            -      (nothing)
ask   korean fried chicken               0.452  Rice, fried, with chicken
weak  yangnyeom chicken                  0.375  Orange chicken
none  dakkochi                           -      (nothing)
none  soju                               -      (nothing)
none  makgeolli                          -      (nothing)
ask   korean rice wine                   0.588  Wine, rice
none  bori cha                           -      (nothing)
auto  barley tea                         0.636  Barley
none  maesil                             -      (nothing)
weak  green plum syrup                   0.308  Syrups, grenadine
none  jocheong                           -      (nothing)
ask   rice syrup                         0.500  Soup, rice
weak  korean pear                        0.333  Bibimbap, Korean
auto  asian pear                         0.733  Pear, Asian, raw
weak  nashi pear                         0.375  Pear nectar
weak  perilla oil                        0.353  Peanut oil
none  deulgireum                         -      (nothing)
weak  sesame leaf                        0.438  Sesame seeds
none  kkaennip                           -      (nothing)
none  chwinamul                          -      (nothing)
none  gochu                              -      (nothing)
weak  korean chili pepper                0.382  Cheese dip with chili pepper
none  cheongyang pepper                  -      (nothing)

ask=20 (15%)  auto=8 (6%)  none=72 (53%)  weak=36 (26%)
```

#### F18. USDA holds exactly five Korean-named rows, and four of them are unreachable by their own names

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```sql
SELECT fdc_id, description, data_type FROM food
WHERE description ILIKE '%korea%' OR description ILIKE '%kimchi%'
   OR description ILIKE '%bulgogi%' OR description ILIKE '%tteok%'
   OR description ILIKE '%bibimbap%' ORDER BY description;
```
```
 2708950 | Bibimbap, Korean              | survey_fndds_food
  170392 | Cabbage, kimchi               | sr_legacy_food
 2708957 | Dukboki or Tteokbokki, Korean | survey_fndds_food
 2710077 | Kimchi                        | survey_fndds_food
 2710228 | Korean dressing or marinade   | survey_fndds_food
```

That is the entire Korean representation in 8,204 loaded foods. Only `Kimchi`
is reachable by its own name. The other four:

```
weak  tteokbokki      0.423  Dukboki or Tteokbokki, Korean   <- the word is IN the row
ask   bibimbap        0.562  Bibimbap, Korean
weak  bibimbop        0.316  Bibimbap, Korean
none  bulgogi         -      (nothing)                       <- marinade row unreached
== korean marinade  ask
    0.571 Korean dressing or marinade | survey_fndds_food
== tteokbokki korean  auto
    0.692 Dukboki or Tteokbokki, Korean
== bibimbap korean  auto
    1.000 Bibimbap, Korean
```

`tteokbokki` scores **0.423 against a row whose description literally contains
the string "Tteokbokki"** — below the weak floor, so the resolver treats it as
"the right answer was probably never on the list" when the right answer is rank
1. Appending the word "korean" doubles the score to 0.692 and turns it into an
`auto`. The dish name alone is the worst possible query for the row named after
it, which is F2/F11's length effect at its most absurd.

#### F19. `gochujang` -> nothing, and there is no honest substitute in the database

kind: **entity_gap** | category: `missing_food_entity`

```
none  gochujang | none  kochujang | none  gochu | none  ssamjang
weak  red pepper paste                   0.417  Peppers, red, cooked
== chili paste  weak
    0.412 Chili, white | survey_fndds_food
    0.375 Chili, NFS | survey_fndds_food
    0.333 Guava paste | survey_fndds_food
    0.316 Almond paste | survey_fndds_food
    0.316 Wasabi paste | survey_fndds_food
== hot chili sauce  weak
    0.538 Sauce, hot chile, sriracha | sr_legacy_food
    0.522 Tomato chili sauce | survey_fndds_food
    0.476 Hot Thai sauce | survey_fndds_food
    0.435 Hot pepper sauce | survey_fndds_food
    0.400 Sauce, peppers, hot, chili, mature red, canned | sr_legacy_food
```

Searched by ingredient (chili paste, red pepper paste) and by category (hot
chili sauce, pepper sauce); the closest thing in the database is sriracha, and
it is a different food:

```
 Sauce, hot chile, sriracha |  93 kcal | 2124 mg sodium | 15.1 g sugar
```

Gochujang is a fermented rice-and-soy paste around 230-250 kcal with about
30 g carbohydrate per 100 g. Sriracha is a thin vinegar-garlic emulsion at
93 kcal. Mapping one onto the other is the plausible-number-from-the-wrong-row
failure. **Entity gap, no fallback proposed** — see Deliberately rejected.

This is the RESUME.md headline case (`gochujang` returns nothing, recall 0)
confirmed at HEAD, and now with the neighbour search that was missing.

#### F20. `doenjang` -> nothing while `Miso` sits in the database

kind: **reachability_gap** dressed as an entity gap | category: `missing_related_food`

```
none  doenjang | none  doenjang jjigae
weak  soybean paste                      0.444  Soybean oil
weak  fermented soybean paste            0.324  Bean paste, sweetened
== soybean paste fermented  weak
    0.324 Bean paste, sweetened | survey_fndds_food
```

`Bean paste, sweetened` is red-bean confectionery: 226 kcal, **124 mg** sodium,
33.9 g sugar. Doenjang is a salt-fermented soybean paste; the food in the
database that matches it is `Miso` (198 kcal, 3728 mg sodium, 6.2 g sugar).
Every route from the Korean word lands on the sweet dessert paste or on soybean
*oil* — a 900 kcal pure fat — while a nutritionally near-identical row is
present and unreferenced. Doenjang is chunkier and slightly saltier than shiro
miso but sits inside the miso range; this is the one Korean fermented paste with
a defensible fallback.

#### F21. `rice cake` auto-matches the puffed snack disc; Korean tteok has no route at all

kind: **wrong_confident_match** | category: `ingredient_vs_dish_ambiguity`

```
auto  rice cake                          1.000  Rice cake
ask   rice cakes korean                  0.474  Rice cake
none  tteok | none  garaetteok | none  tteokguk
```

```
 Rice cake                     | 392 kcal |  71 mg sodium
 Dukboki or Tteokbokki, Korean | 131 kcal | 198 mg sodium
```

`Rice cake` at 392 kcal is the dry puffed crispbread disc, at roughly 4% water.
Korean garaetteok is boiled rice dough at roughly 45% water, near 230 kcal per
100 g. A `tteokbokki` portion logged as "rice cake" would be counted at about
1.7x its energy, and this is an `auto` — cached, silent, forever. The English
phrase genuinely does mean the snack, so the row is not wrong for the phrase;
what is wrong is that there is no route from any Korean spelling to the right
row, and the near-miss lands confidently on the wrong one.

#### F22. `sweet potato noodles` -> `Sweet potato, NFS`; `dangmyeon` -> nothing

kind: **wrong_confident_match** (`ask`, but the candidate list is wrong) | category: `ingredient_vs_dish_ambiguity`

```
none  japchae | none  chapchae | none  dangmyeon
ask   sweet potato noodles               0.583  Sweet potato, NFS
weak  glass noodles                      0.381  Noodles, cooked
weak  cellophane noodles                 0.317  Noodles, chinese, cellophane or long rice (mung beans), dehydrated
== starch noodles  weak
    0.364 Noodles, cooked | survey_fndds_food
    0.333 Rice noodles, dry | sr_legacy_food
    0.320 Noodles, chow mein | survey_fndds_food
```

The signature ingredient of japchae is a dried sweet-potato-starch noodle at
roughly 350 kcal per 100 g dry. `Sweet potato, NFS` is a boiled root vegetable
at roughly 90 kcal. The query names a noodle and the resolver returns a
vegetable, at the highest score in the group — the word "noodles" is discarded
in favour of the two-word ingredient name. The nearest genuine row,
`Noodles, chinese, cellophane or long rice (mung beans), dehydrated`, is
reachable only from the English term `cellophane noodles` and then at 0.317,
below the floor.

#### F23. Korean romanisation is not handled at all

kind: **reachability_gap** | category: `spelling_transliteration_failure`

Every pair below is two accepted romanisations of one word. In each case one
spelling reaches something and the other reaches nothing, or both fail:

```
ask   kimchee     0.500  Kimchi        |  weak  gimchi      0.400  Kimchi
ask   bibimbap    0.562  Bibimbap      |  weak  bibimbop    0.316  Bibimbap
weak  tteokbokki  0.423  Tteokbokki    |  none  ddeokbokki  -      (nothing)
                                       |  none  topokki     -      (nothing)
none  bulgogi     -                    |  none  pulgogi     -
none  galbi       -                    |  none  kalbi       -
none  japchae     -                    |  none  chapchae    -
none  kimbap      -                    |  none  gimbap      -
none  gochujang   -                    |  none  kochujang   -
none  sundae/soondae                    (and `sundae` -> `Ice cream sundae cone`)
```

The Revised Romanisation / McCune-Reischauer split (g/k, d/t, b/p, j/ch) is
systematic and mechanical, and nothing in the pipeline knows about it. Note the
asymmetry: `kimchee` at 0.500 escalates and `gimchi` at 0.400 does not, for the
same food, on a single letter.

#### F24. Short Korean words collide with English drinks

kind: **wrong_confident_match** (weak) | category: `spelling_transliteration_failure`

```
weak  ginseng                            0.333  Gin
weak  gim                                0.375  Gimlet          (gim = Korean nori)
weak  sundae                             0.333  Ice cream sundae cone   (sundae = blood sausage)
weak  kombu                              0.357  Tea, kombucha           (batch 2)
weak  hamachi                            0.333  Ham                     (batch 2)
```

Five distinct cases of a short romanised food name being absorbed by an English
word that is a prefix of it. All land `weak` today, so none is logged silently —
but `sundae` is instructive: the correct answer, `Blood sausage`, is an `auto`
at 1.000 from the English name, and the Korean name reaches an ice cream cone.

#### F25. "korean" is a liability as a query word, exactly as "japanese" is

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```
weak  korean pear                        0.333  Bibimbap, Korean
weak  korean bbq                         0.421  Bibimbap, Korean
weak  korean chili flakes                0.324  Cereal, bran flakes, flavored
weak  korean chili pepper                0.382  Cheese dip with chili pepper
weak  korean egg custard                 0.379  Egg custards, dry mix
weak  korean dumpling                    0.375  Dumpling, no meat
ask   korean fried chicken               0.452  Rice, fried, with chicken
auto  asian pear                         0.733  Pear, Asian, raw
```

`korean pear` reaches a rice-and-vegetable dish; drop the cuisine word and say
`asian pear` and the correct row auto-matches at 0.733. Same pattern as F17: the
cuisine adjective matches a tiny set of unrelated rows strongly and the food
noun matches a large set weakly, so adding it moves the query away from its
answer. This is the single most reproducible structural effect in the domain —
it fired in both cuisines, on eight distinct foods, in the same direction.

#### F26. `myeolchi` (dried anchovy) -> nothing; `dried anchovies` -> `Peppers, ancho, dried`

kind: **wrong_confident_match** (weak) | category: `bad_fuzzy_matching`

```
none  myeolchi | none  myeolchi bokkeum
weak  dried anchovies                    0.440  Peppers, ancho, dried
ask   anchovy                            0.615  Fish, anchovy
== anchovies dried small  weak
    0.355 Peppers, ancho, dried | sr_legacy_food
== fish anchovy  auto
    1.000 Fish, anchovy | survey_fndds_food
    0.500 Fish, anchovy, european, raw | sr_legacy_food
```

"ancho" is a substring of "anchovies" and it wins. Myeolchi is the base stock of
half of Korean home cooking and is also eaten whole as banchan; the plural
English form reaches a dried chilli, and the only route to the fish is the
singular, or the phrase `fish anchovy` that nobody types.

#### F27. Korean whole-dish `none` block, and the ingredients under it

kind: **entity_gap** | category: `missing_dish_ingredient`

72 of 136 returned nothing. As in F7, the missing *dishes* are correct
behaviour — but the defining ingredients under them are also missing, and that
is not:

| dish | verdict | signature ingredient | verdict |
|---|---|---|---|
| tteokbokki | weak 0.423 | tteok | **none** |
| | | gochujang | **none** |
| japchae | none | dangmyeon | **none** |
| bibimbap | ask 0.562 | gochujang | **none** |
| | | namul / kongnamul | **none** |
| doenjang jjigae | none | doenjang | **none** |
| sundubu jjigae | none | sundubu (soft tofu) | weak 0.357 -> a brand row |
| kimbap | none | gim | weak 0.375 -> `Gimlet` |
| miyeok guk | none | miyeok | **none** |
| samgyetang | none | ginseng | weak 0.333 -> `Gin` |
| bossam / jokbal | none | pork trotters | **none** |
| bindaetteok | none | mung bean (ground) | weak 0.333 |

Every row of that table is a carbonara/guanciale: the dish escalates to a model
that is then handed a component list with nothing in it. Kimchi is the sole
exception in the cuisine — it resolves, and so does its own defining ingredient
(`napa cabbage kimchi` 0.750, `cabbage kimchi` 1.000).

### Batch 4 — orthography, yoshoku, cuts, sauces, stocks (117 terms)

```
none  rāmen                              -      (nothing)
none  shōyu                              -      (nothing)
weak  shoyu                              0.176  Soy sauce made from soy and wheat (shoyu)
none  tōfu                               -      (nothing)
none  gyōza                              -      (nothing)
weak  daikon radish raw                  0.421  Radishes, raw
weak  tonkatsu pork                      0.300  Tamale, pork
none  katsu                              -      (nothing)
none  menchi katsu                       -      (nothing)
none  ebi fry                            -      (nothing)
none  korokke                            -      (nothing)
weak  japanese croquette                 0.435  Ham croquette
weak  hamburg steak                      0.364  Hamburger slider
weak  hambagu                            0.333  Ham
none  omurice                            -      (nothing)
weak  omelette rice                      0.381  Rice croquette
none  napolitan                          -      (nothing)
none  kare raisu                         -      (nothing)
none  yoshoku                            -      (nothing)
none  teppanyaki                         -      (nothing)
ask   teriyaki                           0.600  Teriyaki sauce
ask   teriyaki chicken                   0.548  Chicken or turkey with teriyaki
auto  teriyaki sauce                     1.000  Teriyaki sauce
weak  sukiyaki beef                      0.333  Stew, beef
weak  thinly sliced beef                 0.328  Beef, sandwich steaks, flaked, chopped, formed and thinly sliced, raw
ask   beef short plate                   0.455  Beef, shortribs
weak  shabu meat                         0.333  Meat, NFS
ask   nabe vegetables                    0.458  Vegetables, pickled
auto  chinese cabbage                    0.789  Cabbage, Chinese, raw
auto  napa cabbage                       0.684  Cabbage, napa, cooked
none  hakusai                            -      (nothing)
none  shirataki                          -      (nothing)
none  konjac                             -      (nothing)
none  konnyaku                           -      (nothing)
none  harusame                           -      (nothing)
weak  kanpyo                             0.269  Kanpyo, (dried gourd strips)
none  takenoko                           -      (nothing)
none  yamaimo                            -      (nothing)
none  nagaimo                            -      (nothing)
ask   mountain yam                       0.542  Mountain yam, hawaii, raw
weak  japanese yam                       0.375  Cookie, tea, Japanese
none  umeshu                             -      (nothing)
weak  plum wine                          0.357  Plum, raw
none  amazake                            -      (nothing)
none  shochu                             -      (nothing)
none  awamori                            -      (nothing)
none  chuhai                             -      (nothing)
none  calpis                             -      (nothing)
none  ramune                             -      (nothing)
weak  melon pan                          0.353  Melon, frozen
none  anpan                              -      (nothing)
none  castella                           -      (nothing)
none  karinto                            -      (nothing)
none  senbei                             -      (nothing)
auto  rice cracker                       0.800  Rice crackers
none  arare                              -      (nothing)
auto  wasabi peas                        1.000  Wasabi peas
weak  edamame pods                       0.400  Edamame, cooked
ask   natto beans                        0.500  Natto
none  onsen tamago                       -      (nothing)
none  ikura don                          -      (nothing)
none  tekka maki                         -      (nothing)
none  inari                              -      (nothing)
none  inarizushi                         -      (nothing)
none  oshinko                            -      (nothing)
none  gari                               -      (nothing)
auto  pickled ginger                     0.750  Ginger root, pickled
weak  sushi ginger                       0.412  Tea, ginger
none  tsuyu                              -      (nothing)
none  mentsuyu                           -      (nothing)
ask   noodle soup base                   0.600  Soup, noodle, NFS
none  soba tsuyu                         -      (nothing)
weak  japanese soup stock                0.324  Noodles, japanese, soba, dry
weak  instant dashi                      0.321  Gravy, instant beef, dry
none  hondashi                           -      (nothing)
none  bonito                             -      (nothing)
ask   skipjack tuna                      0.519  Fish, tuna, fresh, skipjack, raw
weak  dried bonito                       0.353  Fig, dried
weak  umami seasoning                    0.333  Spices, poultry seasoning
none  msg                                -      (nothing)
none  monosodium glutamate               -      (nothing)
ask   korean soy sauce                   0.562  Soy sauce
none  guk ganjang                        -      (nothing)
none  ganjang                            -      (nothing)
none  jeotgal                            -      (nothing)
none  saeujeot                           -      (nothing)
auto  fish sauce                         1.000  Fish sauce
ask   salted shrimp                      0.562  Shrimp salad
ask   fermented fish sauce               0.550  Fish sauce
none  aekjeot                            -      (nothing)
ask   kimchi radish                      0.500  Radish
ask   korean radish                      0.500  Radish
none  mu                                 -      (nothing)
none  danmuji                            -      (nothing)
ask   yellow pickled radish              0.560  Radishes, pickled
none  chojang                            -      (nothing)
weak  mustard sauce korean               0.381  Mustard
weak  sesame salt                        0.286  Snacks, sesame sticks, wheat-based, salted
none  kkaesogeum                         -      (nothing)
weak  korean pancake                     0.381  Pancake syrup
weak  seafood pancake                    0.429  Pancake syrup
weak  scallion pancake                   0.409  Pancake syrup
ask   green onion                        0.611  Onions, green, raw
weak  scallion                           0.160  Onions, spring or scallions (includes tops and bulb), raw
weak  spring onion                       0.240  Onions, spring or scallions (includes tops and bulb), raw
none  dropwort                           -      (nothing)
none  minari                             -      (nothing)
none  crown daisy                        -      (nothing)
weak  korean beef                        0.400  Bibimbap, Korean
none  hanwoo                             -      (nothing)
auto  brisket                            0.667  Beef, brisket
ask   beef tongue                        0.583  Tongue
none  gyutan                             -      (nothing)
weak  pork jowl                          0.400  Pork jerky
ask   pork neck                          0.462  Pork, NFS
none  moksal                             -      (nothing)
none  chadolbagi                         -      (nothing)
```

#### F28. Macrons destroy the query outright

kind: **reachability_gap** | category: `bad_normalization`

```
none  rāmen   -   (nothing)     |  weak  ramen   0.400  Ramen bowl, NFS
none  shōyu   -   (nothing)     |  weak  shoyu   0.176  Soy sauce ... (shoyu)
none  tōfu    -   (nothing)     |  ask   tofu    0.455  Tofu, fried
none  gyōza   -   (nothing)     |  none  gyoza   -      (nothing)
```

Hepburn with macrons is the standard romanisation and is what a phone's Japanese
keyboard and most menus produce. Every macronised form returns **zero
candidates** — not a weak match, nothing — while the ASCII form at least reaches
the list. Unicode folding (NFKD, strip combining marks) is a mechanical
transformation with no judgement in it, and it is not happening anywhere in the
pipeline. This is the cheapest fix in the audit and it costs no accuracy at all,
because the folded form is strictly more permissive.

#### F29. `tamari` -> `Tamarind`, with the correct row at rank 2 and less than half the score

kind: **wrong_confident_match** (`ask`) | category: `bad_fuzzy_matching`

```
== tamari  ask
    0.600 Tamarind | survey_fndds_food
    0.269 Soy sauce made from soy (tamari) | sr_legacy_food
    0.400 Tamarinds, raw | sr_legacy_food
    0.400 Tamarind drink | survey_fndds_food
    0.333 Candies, Tamarind | sr_legacy_food
== soy sauce tamari  ask
    0.615 Soy sauce made from soy (tamari) | sr_legacy_food
    0.562 Soy sauce | survey_fndds_food
```

A wheat-free soy sauce (roughly 5500 mg sodium per 100 g) reaching a sour
tropical fruit, with three further tamarind products ranked above the row that
contains the word "tamari" in parentheses. Four of the five candidates handed to
the model are the wrong food. `shoyu` has the same shape at 0.176.

#### F30. `scallion` -> 0.160, the lowest correct-rank-1 score in the audit

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```
== scallion  weak
    0.160 Onions, spring or scallions (includes tops and bulb), raw | sr_legacy_food
weak  spring onion   0.240  Onions, spring or scallions (includes tops and bulb), raw
ask   green onion    0.611  Onions, green, raw
```

Three English names for one vegetable; two of them are unreachable and one is
fine. The row that carries *both* failing names in its description is the one
they cannot reach, because it is 56 characters long. Relevant to this domain
because negi, pa and scallion are in essentially every dish in it — `negi`
returns nothing, `pajeon`/`scallion pancake` return nothing useful, and the
generic route depends on the user happening to type "green" rather than
"spring".

#### F31. `konnyaku` / `shirataki` -> nothing, and the only neighbour is 14x wrong

kind: **entity_gap** | category: `missing_food_entity`

```
none  konnyaku | none  shirataki | none  konjac
== konjac noodles  weak
    0.364 Noodles, cooked | survey_fndds_food
    0.333 Rice noodles, dry | sr_legacy_food
    0.320 Noodles, chow mein | survey_fndds_food
```

```sql
SELECT description FROM food WHERE description ILIKE '%konjac%'
   OR description ILIKE '%shirataki%' OR description ILIKE '%glucomannan%';
-- (0 rows)
```

Searched by name, by ingredient (konjac, glucomannan) and by category (noodles).
Nothing. Shirataki is close to 10 kcal per 100 g — it is water and indigestible
fibre — against `Noodles, cooked` at 138. A fallback here would be wrong by
14x in the direction that matters most (it is eaten specifically *because* it is
not caloric), so none is proposed.

#### F32. The motivating case reproduces at HEAD

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```
weak  pork jowl                          0.400  Pork jerky
ask   pork neck                          0.462  Pork, NFS
```

Recorded here only as a control: RESUME.md's `pork jowl -> Pork jerky` still
holds at this commit, so every score in this document is comparable with the
earlier audits. It matters in this domain too — `moksal` (Korean pork neck, the
second most-ordered cut at a Korean barbecue) and `chadolbagi` (brisket, thin
sliced) both return nothing, and `samgyeopsal` returns nothing while
`pork belly` is an `auto` at 1.000.

#### F33. `kanpyo` -> 0.269 against `Kanpyo, (dried gourd strips)`

kind: **reachability_gap** | category: `bad_fuzzy_matching`

```
== kanpyo  weak
    0.269 Kanpyo, (dried gourd strips) | sr_legacy_food
== gourd dried  ask
    0.462 Kanpyo, (dried gourd strips) | sr_legacy_food
```

The one SR row that carries a Japanese food name as its *primary* label, and the
Japanese name cannot reach it. The English gloss inside the same row's
parentheses can. Alongside `shoyu` (0.176), `sake` (0.172), `tteokbokki` (0.423)
and `kanpyo` (0.269), that is five rows in this domain that are named after the
query and are unreachable from it.

#### F34. Stock, umami and seasoning: nothing at all

kind: **entity_gap** | category: `missing_food_entity`

```
none  msg | none  monosodium glutamate | none  hondashi | none  bonito
none  tsuyu | none  mentsuyu | none  ganjang | none  jeotgal | none  saeujeot
weak  dried bonito                       0.353  Fig, dried
weak  umami seasoning                    0.333  Spices, poultry seasoning
weak  instant dashi                      0.321  Gravy, instant beef, dry
ask   skipjack tuna                      0.519  Fish, tuna, fresh, skipjack, raw
```

`monosodium glutamate` returning nothing is a sodium finding, not a curiosity:
MSG is roughly 12 g sodium per 100 g and it is the seasoning of the region.
`Fish sauce` auto-matches at 1.000, so the Southeast Asian equivalent is
present and the Japanese and Korean ones (`hondashi`, `aekjeot`, `saeujeot`) are
not. `bonito` alone returns nothing while `Fish, tuna, fresh, skipjack, raw` —
the same fish — sits at 0.519 behind the English name.

## Proposals

`target` names the USDA row by `fdc_id` and description; each was confirmed
present by `SELECT` and, where the argument turns on a number, that number is
quoted. Where a row exists in dry/cooked or raw/cooked pairs the proposal
names the *family* and leaves the state to the existing `state_conflicts`
guard — a synonym layer must not smuggle a preparation state in.

### High — a competent cook would not dispute it; safe to encode

| surface | relation | target | conf | rationale |
|---|---|---|---|---|
| `nori`, `nori sheet`, `gim`, `kim`, `laver` | synonym | 168458 `Seaweed, laver, raw` | high | Nori and gim are both *Pyropia/Porphyra*; "laver" is the English name of the same alga. `nori` returns nothing today; `laver` scores 0.333. 35 kcal, 48 mg Na. |
| `kombu`, `konbu`, `dashima`, `kelp` | synonym | 168457 `Seaweed, kelp, raw` | high | Kombu is *Laminaria*, i.e. kelp; dashima is the Korean name for the same. `kombu` currently reaches `Tea, kombucha`. 43 kcal, 233 mg Na. |
| `wakame`, `miyeok` | synonym | 170496 `Seaweed, wakame, raw` | high | Miyeok and wakame are both *Undaria pinnatifida* — the same species, the same cut, two languages. `wakame` scores 0.368 against its own name; `miyeok` returns nothing. 45 kcal, 872 mg Na. |
| `kanten` | synonym | 169280 `Seaweed, agar, raw` / 170090 `…dried` | high | Kanten is agar. |
| `soba` | synonym | `Noodles, japanese, soba` (dry 168927-family / cooked pair) | high | The row is named "soba" and scores 0.192. State left to `state_conflicts`. |
| `somen` | synonym | `Noodles, japanese, somen` (dry/cooked pair) | high | As above, 0.222. |
| `shoyu`, `shōyu`, `ganjang`, `joseon ganjang` | synonym | `Soy sauce` (2710085-family) / 174277 `Soy sauce made from soy and wheat (shoyu)` | high | Shoyu and ganjang are soy sauce. `shoyu` scores 0.176 against the row that names it. |
| `tamari` | synonym | 174278 `Soy sauce made from soy (tamari)` | high | Row names it; query currently reaches `Tamarind` (F29). 60 kcal, 5586 mg Na. |
| `shimeji`, `bunashimeji` | synonym | 2003603 `Mushroom, beech` | high | Bunashimeji is sold in English as beech mushroom. `shimeji` returns nothing. |
| `enoki`, `enokitake` | synonym | `Mushroom, enoki` (2003602-family) | high | Reachability only: bare `enoki` is 0.400, `enoki mushroom` is 1.000. |
| `maitake` | synonym | `Mushroom, maitake` | high | Reachability only, 0.500. |
| `hamachi`, `buri` | synonym | 175163 `Fish, yellowtail, mixed species` (raw/cooked pair) | high | *Seriola quinqueradiata*, inside USDA's "yellowtail, mixed species". Currently `Ham`. |
| `katsuo`, `bonito` | synonym | 175156 `Fish, tuna, fresh, skipjack, raw` | high | Katsuo is skipjack. `bonito` returns nothing. |
| `daikon`, `mu`, `korean radish`, `mooli` | synonym | 168451 `Radishes, oriental, raw` | high | Verified by category: `radish oriental` -> 0.714 for this row. `daikon` returns nothing; `daikon radish` reaches generic `Radish`. 18 kcal. |
| `gobo` | synonym | 169974 `Burdock root, raw` | high | `burdock root` already auto-matches at 0.812; only the Japanese name fails. |
| `renkon` | synonym | 169250 `Lotus root, raw` | high | Same shape: `lotus root` 0.786, `renkon` nothing. |
| `takenoko` | synonym | 169210 `Bamboo shoots, raw` | high | Same shape: `bamboo shoots` 0.778, `takenoko` nothing. |
| `hakusai`, `baechu` | synonym | 2709774 `Cabbage, Chinese, raw` / `Cabbage, napa` | high | Same cabbage; `napa cabbage` 0.684, both native names nothing. |
| `nashi`, `korean pear`, `japanese pear` | synonym | 2709255 `Pear, Asian, raw` | high | `asian pear` auto-matches 0.733; `korean pear` currently reaches `Bibimbap, Korean`. |
| `kanpyo` | synonym | 169241 `Kanpyo, (dried gourd strips)` | high | The row's own primary label, unreachable from it at 0.269. |
| `tteokbokki`, `ddeokbokki`, `topokki`, `dukboki` | synonym | 2708957 `Dukboki or Tteokbokki, Korean` | high | The row names two of these spellings. Best score from any of them today: 0.423. |
| `bibimbap`, `bibimbop`, `bibimbab`, `dolsot bibimbap` | synonym | 2708950 `Bibimbap, Korean` | high | 0.316-0.562 today; `bibimbap korean` is 1.000. |
| `kimchee`, `gimchi`, `baechu kimchi`, `kimchi jjigae`→ingredient | synonym | 2710077 `Kimchi` | high | One-letter romanisation variants of a row that already matches at 1.000. |
| `scallion`, `spring onion`, `negi`, `pa`, `daepa` | synonym | 170005 `Onions, spring or scallions (includes tops and bulb), raw` | high | The row carries both English names and neither reaches it (0.160, 0.240). 32 kcal. |
| `aburaage`, `atsuage`, `abura age` | synonym | 172451 `Tofu, fried` | high | These *are* deep-fried tofu; the row is exactly it. All return nothing today. |
| `koyadofu`, `kouyadofu`, `dried frozen tofu` | synonym | 172450 `Tofu, dried-frozen (koyadofu)` | high | Row names it in parentheses. |
| `tofu`, `momen tofu` (bare, no state word) | parent_category | 172476 `Tofu, raw, regular, prepared with calcium sulfate` | high | 76 kcal. Today the bare word takes `Tofu, fried` at 270 kcal (F10) and the correct row is not in the top six. |
| `firm tofu`, `momen` | parent_category | 172448 `Tofu, firm, prepared with … (nigari)` | high | 78 kcal, 12 mg Na. Today reaches a *silken* brand row. |
| `real wasabi`, `fresh wasabi`, `hon-wasabi`, `wasabi root` | synonym | 168583 `Wasabi, root, raw` | high | 109 kcal, 17 mg Na, against the paste's 292 kcal / 3390 mg. The disambiguating word is currently discarded (F9). |
| `konnyaku`, `shirataki`, `konjac` | — | *no target* | high (as a **gap**) | Recorded so a future author does not invent one. See Deliberately rejected. |

Normalisation rule, not a mapping, and the cheapest item here:

| rule | conf | rationale |
|---|---|---|
| Fold macrons / combining marks before search (NFKD + strip Mn) | high | `rāmen`, `shōyu`, `tōfu`, `gyōza` return **zero candidates** while their ASCII forms reach the list (F28). Strictly more permissive; cannot lose a match. |
| Treat Korean romanisation initial-consonant pairs as equivalent (g/k, d/t, b/p, j/ch) when generating search terms | high | `gimchi`/`kimchee`, `ddeokbokki`/`tteokbokki`, `bulgogi`/`pulgogi`, `galbi`/`kalbi`, `japchae`/`chapchae`, `gimbap`/`kimbap`, `gochujang`/`kochujang` (F23). Mechanical, and it is the documented RR/McCune-Reischauer difference. |

### Medium — plausible but variant-dependent; non-mandatory fallback only

| surface | relation | target | conf | rationale |
|---|---|---|---|---|
| `doenjang`, `korean soybean paste` | nutritional_fallback | 172442 `Miso` | medium | Same food class — salt-fermented soybean paste. Miso: 198 kcal, 3728 mg Na, 6.2 g sugar. Doenjang sits inside that range and is culturally distinct, so it must not be presented as an identity. Today every route reaches `Soybean oil` (900 kcal) or `Bean paste, sweetened` (124 mg Na, 33.9 g sugar) — both far worse than this. |
| `gochugaru`, `korean chili flakes`, `korean red pepper powder` | nutritional_fallback | 170932 `Spices, pepper, red or cayenne` | medium | Pure ground dried red chilli: 318 kcal, **30 mg** Na. Explicitly *not* `Spices, chili powder`, which is a blend at 2867 mg Na. Gochugaru is milder in capsaicin, which this database does not carry, so the difference is invisible to it. |
| `dangmyeon`, `japchae noodles`, `sweet potato noodles`, `glass noodles` | nutritional_fallback | 174258 `Noodles, chinese, cellophane or long rice (mung beans), dehydrated` | medium | 351 kcal, 10 mg Na, near-zero protein and fat — a pure starch noodle, which is what dangmyeon is. Different starch source (sweet potato vs mung bean), same macronutrient shape. Beats today's `Sweet potato, NFS` (a boiled root, ~90 kcal) by a wide margin (F22). |
| `katakuriko`, `potato starch` | nutritional_fallback | 169698 `Cornstarch` | medium | 381 kcal, 9 mg Na, 0 sugar; potato starch is within a few percent on every macronutrient. Different botanical source, so fallback not synonym. USDA has no standalone potato starch row (checked). |
| `kabocha`, `japanese pumpkin` | nutritional_fallback | 170489 `Squash, winter, all varieties, raw` (+ cooked rows) | medium | 34 kcal. Kabocha is drier and denser than the average winter squash, so the figure is conservative rather than exact. Today `japanese pumpkin` reaches `Pie, pumpkin`. |
| `takuan`, `danmuji`, `oshinko` | nutritional_fallback | 2710099 `Radishes, pickled` | medium | 34 kcal, 977 mg Na — the right order for a salt-pickled daikon. Takuan is additionally sweetened, so sugar is understated. `yellow pickled radish` already reaches this row at 0.560; the native names do not. |
| `yamaimo`, `nagaimo` | nutritional_fallback | 168432 `Mountain yam, hawaii, raw` | medium | 67 kcal. Both are *Dioscorea*; different species, similar composition. `mountain yam` reaches it at 0.542, the Japanese names at nothing. |
| `panko` | nutritional_fallback | 174928 `Bread, crumbs, dry, grated, plain` | medium | 395 kcal, 732 mg Na. Panko is coarser and less dense, and typically lower in sodium; per 100 g the class is right, and it is used in 10-30 g coatings where the error is small. `panko` returns nothing today. |
| `myeolchi`, `dried anchovies` | nutritional_fallback | 2706232 `Fish, anchovy` | medium | 210 kcal, 3668 mg Na — a salted anchovy, which is the right class. Dried myeolchi is drier still, so energy is understated. Proposed mainly to stop `dried anchovies` -> `Peppers, ancho, dried` (F26). |
| `sundubu`, `soft tofu`, `silken tofu` | parent_category | 172449 `Tofu, soft, prepared with … (nigari)` | medium | 61 kcal, 8 mg Na. Medium not high because "silken" (kinugoshi) and "soft" (momen, soft-pressed) are different processes that USDA does not separate outside brand rows; today the query lands on a MORI-NU brand row. |
| `maguro` | nutritional_fallback | `Fish, tuna, fresh, …` family | medium | Maguro spans akami to otoro, whose fat differs several-fold; a single row cannot represent it. Worth having as an escalation hint, not as an answer. |
| `guk ganjang`, `soup soy sauce` | nutritional_fallback | `Soy sauce` | medium | Materially saltier than ordinary ganjang; same class, understated sodium. |
| `sake` (standalone, or with a drink word) | synonym | 167723 `Alcoholic beverage, rice (sake)` | medium | 134 kcal. The row scores 0.172 against its own name (F11). Medium **only** because the token is overloaded — in a sushi context `sake` is salmon (`sake salmon` -> `Salmon salad` today). Encode only when the item is not adjacent to a fish word; that condition is what keeps it out of "high". |

## Deliberately rejected

| surface | what was considered | why rejected |
|---|---|---|
| `gochujang`, `kochujang` | `Sauce, hot chile, sriracha`; `Spices, chili powder`; `Miso`; `Peppers, hot chile, sun-dried` | Measured: sriracha 93 kcal / 2124 mg Na / 15.1 g sugar; chili powder 282 kcal / 2867 mg Na — a *blend* containing cumin, garlic and salt. Gochujang is a fermented rice-and-soy paste near 230-250 kcal with roughly 30 g carbohydrate, most of it from rice syrup. Every candidate is wrong in a different nutrient and all of them are wrong in energy. Searched by ingredient (`chili paste`, `red pepper paste`) and by category (`hot chili sauce`, `pepper sauce`) — F19. **True entity gap; leave it returning nothing so it escalates rather than resolving confidently to a wrong row.** |
| `hijiki`, `arame`, `dulse` | `Seaweed, kelp, raw`; `Seaweed, raw` | Different genera with different mineral profiles; the reason anyone logs hijiki (iron, and inorganic arsenic) is not carried in this database at all, so the fallback would deliver only the wrong sodium with none of the information that motivated the entry. Neighbour-searched by category (`hijiki seaweed`, `brown seaweed`) — nothing. An over-broad `-> seaweed` parent is the "halloumi -> cheese" failure: nutritionally almost useless. |
| `konnyaku`, `shirataki`, `konjac` | `Noodles, cooked` | Measured: `Noodles, cooked` 137 kcal against shirataki's ~10. **14x**, and in the one direction that destroys the entry's purpose — konnyaku is eaten *because* it is not caloric. No konjac/glucomannan row exists (`SELECT … ILIKE '%konjac%'` returns 0 rows). Leave as an entity gap. |
| `mirin`, `hon mirin` | `Wine, rice`; `Wine, dessert, sweet` | Measured: `Wine, rice` 134 kcal, **0 g sugar**. Mirin is roughly 258 kcal and 43 g sugar per 100 g. The available neighbour is wrong in the only nutrient that distinguishes the two, and mirin is used by the tablespoon in exactly the dishes where sugar is being counted. |
| `tteok`, `garaetteok` | `Rice cake` (392 kcal) | Measured 392 kcal against fresh garaetteok's ~230: the USDA row is a 4%-water puffed disc and tteok is 45%-water boiled dough. The mapping would look right (it is "rice cake") and be 1.7x wrong, which is the worst combination. `Dukboki or Tteokbokki, Korean` (131 kcal) is a finished dish, not the ingredient. |
| `matcha` | `Tea, hot, leaf, green` | Measured: the tea row is **1 kcal** per 100 g of brewed liquid; matcha is a whole-leaf powder near 325 kcal per 100 g, consumed by the gram. A three-hundred-fold unit mismatch dressed as the same plant. |
| `kkaennip` / `shiso` / `perilla leaf` | a synonym edge between them; `Basil`; `Mint` | All three return nothing and USDA has no *Perilla* row of any kind, so there is no target to map to. Both are *Perilla frutescens* but Korean kkaennip (var. *frutescens*) and Japanese shiso (var. *crispa*) are different leaves in use and in flavour, and creating the edge with no target only invites a later author to route one into the other's `user_product` row — the `-626 Pancetta/guanciale` mistake repeated. A herb parent (`Basil`) would be culturally wrong and nutritionally meaningless at 2 g per serving. |
| `tonkatsu sauce`, `okonomiyaki sauce` | `Sauce, worcestershire` (77 kcal, 1300 mg Na, 10 g sugar); `Teriyaki sauce` | Tonkatsu sauce is a thickened, sweetened Worcestershire derivative near 130 kcal with roughly 25 g sugar. Worcestershire understates sugar 2.5x and teriyaki has the wrong base entirely. Both are used by the tablespoon on a dish already being counted for its fried coating, so the error compounds with the one that matters. Recorded as a gap. |
| `dashi`, `hondashi`, `mentsuyu` | `Soup, chicken`; `Gravy, instant beef, dry` | Dashi is close to salted water with glutamate; any stock row in the database carries fat and protein it does not have. The cost of the gap is small (F13), the cost of the wrong row is not. |
| `msg`, `monosodium glutamate` | `Salt, table` | Roughly a third of table salt's sodium by mass and none of its chloride; a salt mapping would overstate sodium about 3x on an ingredient measured in grams. No row exists; leave the gap. |
| `wasabi` (bare) -> `Wasabi, root, raw` | re-pointing the bare word to the root | **Reviewed and deliberately not proposed.** The `Wasabi` row at 292 kcal / 3390 mg Na is the tube paste, and the tube paste is what is eaten. Changing the bare word to the root would make the common case wrong to fix the rare one. The proposal above adds routes for `real wasabi` / `wasabi root` and leaves the default alone. |
| `korean fried chicken`, `yangnyeom chicken` | `Orange chicken`; `Rice, fried, with chicken` | A composite dish that the parse tier should decompose. `Orange chicken` is a different sauce on a different cut, and encoding it would put a dish-level guess where a component list belongs. |
| `japanese curry`, `katsu curry` | `Beef curry` | Japanese curry roux is a wheat-and-fat block; the dish's energy is dominated by the roux and the rice, neither of which `Beef curry` represents. Dish-level mapping rejected; the components (rice, roux, cutlet) are the right unit and `curry roux` is itself a gap. |

## Notes

**The dominant failure in this domain is not a missing food, it is a missing
route to a food that is present.** Of 477 terms, the cases that would embarrass
a cook divide roughly as: 34 reachability gaps where USDA holds the exact row
and the native word cannot reach it, 5 wrong-confident `auto` matches, and a
long tail of genuine entity gaps (gochujang, mirin, konnyaku, dashi, MSG,
perilla) that are correctly returning nothing.

**Five rows in this domain are named after the query that cannot reach them.**
`Alcoholic beverage, rice (sake)` at 0.172, `Soy sauce … (shoyu)` at 0.176,
`Noodles, japanese, soba` at 0.192, `Kanpyo, (dried gourd strips)` at 0.269,
`Dukboki or Tteokbokki, Korean` at 0.423. Add `Onions, spring or scallions …`
at 0.160 for `scallion`. That is the strongest single argument in this audit for
a synonym layer over any ranking change: no similarity function separates these
from the noise, because the signal is *containment of a short token in a long
description*, and trigram similarity is a length ratio.

**The cuisine adjective is an active liability, and it fired in both
languages.** `japanese curry`, `japanese leek` and `japanese rice` all reach
`Cookie, tea, Japanese`; `korean pear` and `korean bbq` both reach
`Bibimbap, Korean`. Meanwhile appending the cuisine word to a *dish* that has a
row doubles its score (`tteokbokki` 0.423 -> `tteokbokki korean` 0.692;
`bibimbap` 0.562 -> 1.000). So the same word is a liability for ingredients and
a rescue for dishes, which means no global rule about it is safe — another
argument for explicit synonyms rather than a heuristic.

**Two surprises worth recording.**

1. *The bare word is almost always the worst query.* `enoki` 0.400 vs
   `enoki mushroom` 1.000. `soba` 0.192 vs `soba noodles` 0.500 vs
   `noodles japanese` 0.654. `tteokbokki` 0.423 vs `tteokbokki korean` 0.692.
   `scallion` 0.160 vs `green onion` 0.611. Users type bare words. The retrieval
   eval in RESUME.md reports short descriptions doing *best* (75.2%); this is the
   mirror image — short *queries* doing worst — and the two are the same length
   effect seen from opposite ends.

2. *Korea is essentially absent from USDA and Japan is half-present.* Five
   Korean-named rows exist in 8,204 loaded foods. Japan has a scattered dozen
   (`soba`, `somen`, `natto`, `wasabi`, `koyadofu`, `fuyu`, `kanpyo`,
   `Cabbage, japanese style, fresh, pickled`) — enough that most Japanese
   *ingredient* failures are reachability, while most Korean failures are real
   absence. The two cuisines therefore need different remedies: Japan needs
   synonyms, Korea needs synonyms **plus** an honest set of `user_product` rows
   for gochujang, doenjang-as-itself, tteok and gochugaru, entered from labels
   at the confirm gate rather than guessed.

**On the `auto` verdicts.** Only 34 of 477 (7%) reached `auto`, and most are
correct (`kimchi` 1.000, `natto` 1.000, `octopus` 1.000, `sesame oil` 1.000,
`burdock root` 0.812). Three are wrong in a way that would cache forever:
`tare sauce -> Tartar sauce` (F1), `rice cake -> Rice cake` when the user meant
tteok (F21), and `seaweed soup -> Soup, seaweed` is right but sits one letter
from `miyeok guk`, which returns nothing. The `tare` case is the one to fix
first: it is a sugar-and-soy glaze resolving to a mayonnaise, and yakitori is
the most-logged food in the Japanese half of this domain.

**What the audit did not test.** Portion and household-measure behaviour
(`db.portion_for` filtering out USDA household portions is a known golden-set
failure, and rice/noodle portions are where this domain's mass errors will
actually live), and any interaction with `food_alias`, which the probe
deliberately does not consult.
