# Knowledge audit — Eastern Europe and the Balkans

26 Aug 2026. Domain: Polish, Czech, Slovak, Hungarian, Ukrainian, Russian,
Romanian, Bulgarian, Serbian, Croatian, Bosnian, Albanian, Baltic.

Every line below marked `probe` is verbatim output of

```
.venv/bin/python scripts/probe_knowledge.py --file <list>
```

which calls `db.search_foods(term, limit=5, user_id=None)` — the label path
only, no aliases, no model `search_terms`. Where a verdict of `auto` is
claimed as a defect, the three `resolve_items` guards (`state_conflicts`,
`unrequested_qualifier`, `label_absent`) were re-run against the same candidate
list and the result is stated. Nutrient figures are from `food_nutrient`,
per 100 g, ids 1008/2047/2048 for energy.

Read `docs/resolution/RECONCILED.md` §1 first. Almost everything here is that
one fact — trigram similarity falls with description length — wearing a Slavic
hat, plus one new mechanism §1 does not name.

## Scale

840 probes across five batches (`ee_terms`, `ee2`…`ee5`), ~820 distinct terms.

| verdict | count | share |
|---|---|---|
| none | 391 | 47% |
| weak | 192 | 23% |
| ask  | 139 | 17% |
| auto | 118 | 14% |

For comparison, the same probe over 108 plain-English food names (batch `ee2`,
all of them the English paraphrase of something in this domain) returns
auto=54%, none=3%. **The knowledge is there. The words are not.**

---

## 0. The finding that subsumes the rest: there is no Polish surface at all

The user lives in Poland. Batch `ee3` is 110 ordinary Polish food nouns — not
dishes, staples.

```
none  chleb                              -      (nothing)
none  maslo                              -      (nothing)
none  jajko                              -      (nothing)
none  mleko                              -      (nothing)
none  ser                                -      (nothing)
none  kurczak                            -      (nothing)
none  wolowina                           -      (nothing)
none  ryz                                -      (nothing)
none  ziemniaki                          -      (nothing)
none  marchewka                          -      (nothing)
none  cebula                             -      (nothing)
none  jablko                             -      (nothing)
none  miod                               -      (nothing)
none  kawa                               -      (nothing)
none  olej                               -      (nothing)
none  platki owsiane                     -      (nothing)
none  owsianka                           -      (nothing)
```

92% of that batch returns nothing whatsoever. Cyrillic returns nothing at all:

```
none  творог                             -      (nothing)
none  борщ                               -      (nothing)
none  пельмени                           -      (nothing)
none  сметана                            -      (nothing)
none  gречка                             -      (nothing)
```

Two consequences worth separating.

**The model tier absorbs this and it mostly works.** The model writes English
`search_terms`, `_candidates` pools by `max()`, and the row is found. This is
the system working as designed and is not a defect on its own.

**But `label_absent` makes tier 2 structurally dead for this user.** The guard
disqualifies any candidate sharing no word with the *label*. No USDA
description contains `ziemniaki`, so for a Polish-language item the auto-match
can never fire, whatever the score. Every new Polish food costs a model call,
once, forever — which is the design's intent, but it means the alias table is
this user's entire vocabulary and a single bad model pick is permanent
(CLAUDE.md, "The alias tier caches these forever"). The value of the synonym
proposals below is that they move Polish names from *model-decided* to
*data-decided*.

---

## 1. Wrong-confident matches (verdict `auto`, guards verified not to block)

These are the dangerous class: silent, and they write an alias.

### 1.1 `oatmeal` → `Pie, oatmeal` (396 kcal against 76)

```
probe:  auto  oatmeal                            0.667  Pie, oatmeal
```

Guard re-run over the same list:

```
   0.667 Pie, oatmeal                                                 AUTO
   0.667 Oatmeal, NFS                                                 AUTO
   0.615 Roll, oatmeal
```

Both clear 0.62 and neither is blocked. `resolve_items` takes `next(...)` over
`cands` **in list order**, so the pie wins the tie. `Pie, oatmeal` (2708016) is
396 kcal / 6.1 P / 16.0 F / 56.9 C; `Oatmeal, NFS` (2708380) is 76 / 2.2 / 2.6 /
11.2. A 5.2× energy error on owsianka, the single most-eaten Polish breakfast,
cached as an alias on first sight.

`unrequested_qualifier` cannot see this: the first segment `Pie` shares no word
with the query, and the rule for `i == 0` only blocks a name that *echoes* the
query and adds to it. `Pie` does not echo `oatmeal`, so it is treated as a weak
match to be judged on similarity — and similarity says 0.667.

This is a general defect, not a Slavic one, but the family is:
`Roll, oatmeal`, `Bread, oatmeal`, `Muffin, oatmeal`, `Cookie, oatmeal`,
`Crackers, oatmeal` all rank above nothing and `Oatmeal, NFS` has no way to win.

### 1.2 `buckwheat kasha` → `Buckwheat` (raw, 343 kcal against cooked 92)

```
probe:  auto  buckwheat kasha                    0.625  Buckwheat
```

```
   0.625 Buckwheat                                                    AUTO
   0.455 Flour, buckwheat
   0.435 Buckwheat groats                                             qual:Buckwheat groats
   0.357 Buckwheat, whole grain                                       qual:whole grain
```

`Buckwheat` (170286) is the raw grain: 343 kcal / 13.3 P / 3.4 F / 71.5 C.
`Buckwheat groats, roasted, cooked` (170686) is 92 / 3.4 / 0.6 / 19.9 and is
**not on the candidate list at all**. Kasza gryczana is never eaten raw.
3.7× over on a food eaten by the 200 g portion.

Note the second-order damage: the FNDDS row `Buckwheat groats` (2708362, 118
kcal, i.e. already cooked) *is* on the list and is disqualified by
`unrequested_qualifier` for adding the word "groats". The guard removes the
better row and leaves the worse one.

`state_conflicts` would save this only if the model emits `state="cooked"`;
a bare `Buckwheat` says nothing about state, and per the docstring "a
description that says nothing about its state is not evidence against
anything", so it passes. Correct rule, wrong outcome here — the row is
*implicitly* raw and USDA does not say so.

### 1.3 `dried mushrooms` → `Fried mushrooms`

```
probe:  auto  dried mushrooms                    0.640  Mushrooms, shiitake, dried
```

The head is blocked, and the guard then walks to a worse row:

```
   0.640 Mushrooms, shiitake, dried                                   blocked qual:shiitake
   0.424 Mushroom, Asian, cooked, from dried                          qual:Asian
   0.312 Gravy, mushroom, dry, powder                                 qual:mushroom
   0.684 Fried mushrooms                                              AUTO
```

`Fried mushrooms` (2710053) is 222 kcal / 12.9 F — cooked in fat. Dried
porcini for a bigos or a wigilia sauce is ~300 kcal/100 g dry and is used at
10–20 g. One letter of difference, `dried`/`fried`, and the guards make it
worse rather than better: the only *correct* row on the list (shiitake, dried)
is the one disqualified.

USDA has no *Boletus*/porcini row at all — `ILIKE '%boletus%'` and
`'%porcini%'` return 0 rows — so the honest ceiling here is shiitake, dried.

### 1.4 `russian salad` → `Salad dressing, russian dressing` (355 kcal)

```
probe:  auto  russian salad                      0.636  Salad dressing, russian dressing
```

```
   0.636 Salad dressing, russian dressing                             AUTO
   0.400 White Russian                                                qual:White Russian
   0.333 Pea salad                                                    label_absent
```

`salad` is in `_QUALIFIER_STOP` (it is there for `Oil, olive, salad or
cooking`), so the first segment reduces to `{dressing}`, shares nothing with
the query, and `i == 0` lets it pass. The second segment contains `russian`,
so it does not block either. Result: sałatka jarzynowa / salat olivier — a
potato-and-mayonnaise salad at ~190 kcal — is logged as 355 kcal of condiment
(171005: 0.7 P / 26.2 F / 31.9 C). Macros are wrong in every direction.

### 1.5 `sauerkraut stew` → `Sauerkraut` (bigos as a vegetable)

```
probe:  auto  sauerkraut stew                    0.733  Sauerkraut
```

```
   0.733 Sauerkraut                                                   AUTO
```

One candidate, unblocked. `Sauerkraut` (2709982) is 40 kcal / 0.9 P / 2.5 F.
Bigos is sauerkraut plus pork, kiełbasa and often boczek — 120–160 kcal/100 g
and the protein and fat that come with it. A 300 g plate logs as 120 kcal
instead of ~420. This is the ingredient-for-dish substitution in its purest
form, and it is the same shape as `dried mushrooms`: the query names an
ingredient plus a dish word, the dish word is discarded, the ingredient row is
short, and short wins.

### 1.6 `carrot salad` → `Carrots, raw, salad`

```
probe:  auto  carrot salad                       0.632  Carrots, raw, salad
```
```
   0.632 Carrots, raw, salad                                          AUTO
```

Lower severity but the same shape. Surówka z marchewki is grated carrot with
apple, mayonnaise or oil and sugar; the row is plain raw carrot. Understates
by roughly half. Filed because it caches.

### 1.7 `pumpernickel` → `Roll, pumpernickel` / `Bagel, pumpernickel`

```
   0.722 Roll, pumpernickel                                           AUTO
   0.722 Bagel, pumpernickel                                          AUTO
   0.684 Bread, pumpernickel                                          AUTO
```

Four rows tie or beat the correct one; list order decides. Energy happens to
be close here (`Bread, pumpernickel` 250 kcal), so the harm is small — but the
mechanism is identical to 1.1 and it is worth recording that `Bread, X` loses
to `Roll, X` and `Bagel, X` purely on which row the planner emitted first.

---

## 2. Reachability gaps — USDA has the row, the query cannot reach it

The most valuable class. Every one of these was checked by ingredient and by
category, not only by name.

### 2.1 `kielbasa` — five right rows, none reachable

```
probe:  weak  kielbasa                           0.310  Kielbasa, fully cooked, grilled
```

USDA holds:

```
  173877 sr_legacy_food     Kielbasa, fully cooked, grilled
  173879 sr_legacy_food     Kielbasa, fully cooked, unheated
  173878 sr_legacy_food     Kielbasa, fully cooked, pan-fried
  174607 sr_legacy_food     Kielbasa, Polish, turkey and beef, smoked
  174577 sr_legacy_food     Polish sausage, pork            (326 kcal)
 2706188 survey_fndds_food  Polish sausage
  172954 sr_legacy_food     Sausage, Polish, pork and beef, smoked
```

and the English paraphrase reaches them instantly:

```
probe:  auto  polish sausage                     1.000  Polish sausage
```

`kielbasa` — the word the user will actually type, and a word USDA itself
uses as a *first segment* on four rows — lands at 0.310, below the weak floor,
because those descriptions are long. This is RECONCILED §1 exactly.

### 2.2 `pork jowl` — the motivating example reproduces in Polish (podgardle)

```
   0.208 Pork, fresh, variety meats and by-products, jowl, raw     qual:fresh
   0.400 Pork jerky                                                qual:Pork jerky
   0.357 Pork, NFS
```

Confirmed against 168269 (655 kcal / 6.4 P / 69.6 F). Relevant here for
podgardle, and for the Ukrainian/Polish *salo* family — where there **is** a
good row that is also hard to reach: `Pork, cured, salt pork, raw` (168287,
748 kcal / 80.5 F), which only surfaces on the contrived query
`raw cured pork` (auto 0.750).

### 2.3 `beetroot` returns nothing

```
probe:  none  beetroot                           -      (nothing)
probe:  ask   raw beetroot                       0.533  Beets, raw
```

`Beets, raw`, `Beets, pickled`, `Beets, cooked, boiled, drained` and nine more
all exist. `beetroot` is the ordinary British-English word and the one a Polish
speaker is taught for *burak*; neither the tsquery (`beetroot` ≠ `beet`) nor
the trigram floor reaches them. Buraczki, ćwikła, chłodnik and barszcz all
start here.

Related, and worse: `beet salad` returns a candidate list containing **no beet
row at all** —

```
   0.692 Beef salad                                                   blocked label_absent
   0.421 Black bean salad                                             label_absent
   0.400 Pea salad                                                    label_absent
```

`label_absent` is the only thing standing between ćwikła and beef. That is a
guard doing its job on a list that should never have been generated.

### 2.4 `kotlet schabowy` — FNDDS calls breading "coated"

```
probe:  none  kotlet schabowy                    -      (nothing)
probe:  weak  breaded pork cutlet                0.344  Chicken fillet, breaded
```

USDA has the exact dish:

```
 2705870 Pork, chop, coated, lean and fat eaten     229 kcal  25.1 P  10.6 F  7.2 C
 2705869 Pork, chop, coated, NS as to fat eaten     219 kcal
 2705871 Pork, chop, coated, lean only eaten        208 kcal
```

`coated` is the FNDDS word for breaded, and no query in this audit reached
these rows. The English query lands on *chicken*.

### 2.5 `polenta` returns nothing; USDA calls it cornmeal mush

```
probe:  none  polenta                            -      (nothing)
probe:  none  mamaliga                           -      (nothing)
probe:  none  kacamak                            -      (nothing)
probe:  ask   cornmeal mush                      0.583  Cornmeal mush, fat added
```

`Cornmeal mush, no added fat` (2708374) is 58 kcal / 1.1 P / 0.3 F / 12.5 C —
mămăligă and kačamak exactly. Nothing in the domain's vocabulary reaches it.

### 2.6 `flaki` / tripe

```
probe:  weak  flaki                              0.375  Flan
probe:  weak  flaczki                            0.300  Flan
probe:  weak  beef tripe cooked                  0.333  Beef, variety meats and by-products, tripe, cooked, simmered
probe:  ask   beef tripe                         0.545  Tripe
```

`Tripe` (2706162, 89 kcal) and the SR cooked row both exist. Even the *English*
query with a state word falls to 0.333 — again the length penalty, and again
the correct, more specific row is the one punished.

### 2.7 `cabbage rolls` — one perfect row, unreachable by any regional name

```
probe:  none  golabki                            -      (nothing)
probe:  none  golumpki                           -      (nothing)
probe:  none  sarma                              -      (nothing)
probe:  none  sarmale                            -      (nothing)
probe:  none  toltott kaposzta                   -      (nothing)
probe:  none  golubtsy                           -      (nothing)
probe:  weak  cabbage rolls                      0.350  Stuffed cabbage rolls with beef and rice
probe:  weak  stuffed cabbage                    0.400  Stuffed cabbage rolls with beef and rice
probe:  auto  stuffed cabbage rolls with beef and rice  1.000  Stuffed cabbage rolls with beef and rice
```

2706620: 114 kcal / 8.3 P / 5.1 F / 8.8 C. The row is right for gołąbki,
sarmale, töltött káposzta and golubtsy alike, and it takes the full 39-character
description to get there. Note `sarma` in the Balkan (vine-leaf) sense has a
*different* right row — `Grape leaves stuffed with rice` (auto 0.677 via
`stuffed grape leaves`) — which is why the two must not share a synonym.

### 2.8 `chicken broth` heads on a row that says "no broth"

```
probe:  ask   chicken broth                      0.609  Chicken, canned, no broth
```

`Soup, chicken broth, ready-to-serve` (174536, 6 kcal) and `Soup, chicken`
(2707134, 40 kcal) both exist. Rosół is the most-logged Polish soup there is
and the head of its candidate list is canned chicken meat with the broth
*removed*. `inverts_meaning` may or may not catch "no broth"; the ranking
should not have produced it.

### 2.9 `poppy seed cake` heads on a spice at 525 kcal

```
probe:  ask   poppy seed cake                    0.500  Spices, poppy seed
probe:  ask   poppy seed roll                    0.500  Spices, poppy seed
probe:  none  makowiec                           -      (nothing)
```

`Spices, poppy seed` (171330) is 525 kcal / 41.6 F. Makowiec is ~380 kcal.
The candidate list for a *cake* is headed by a spice jar because "cake" is a
common word and "poppy seed" is not. Model tier saves it; the list is nonsense.

### 2.10 `curd cheese` heads on tofu

```
probe:  ask   curd cheese                        0.579  Soybean, curd cheese
probe:  ask   farmer cheese                      0.609  Cottage cheese, farmer's
probe:  none  twarog                             -      (nothing)
probe:  none  quark                              -      (nothing)
```

`Soybean, curd cheese` is tofu. Handing the model a list headed by a soy
product for the single most-eaten Polish dairy item is the kind of candidate
list §3.3 is about. See §3.1 for why the *right* answer is also not here.

### 2.11 `rapeseed oil` — USDA files it under canola and never returns it

```
   0.688 Oil, grapeseed                                               blocked qual:grapeseed
   0.389 Oil, teaseed
   0.368 Flaxseed oil
   0.350 Oil, poppyseed
```

`Oil, canola` (172336, 748278) and `Canola oil` (2710188) exist and appear
**nowhere** on the list. Olej rzepakowy is the default Polish frying oil.
`rapeseed` is a substring of `grapeseed`, which is the entire reason the wrong
oil ranks; only `unrequested_qualifier` prevents a wrong-confident match, and
it does so by leaving the item with no usable candidate.

### 2.12 Short right rows that still lose to length

```
probe:  weak  feta                               0.417  Cheese, feta
probe:  weak  marjoram                           0.409  Spices, marjoram, dried
probe:  weak  turo                               0.333  Turtle
probe:  weak  wodka                              0.333  Vodka
probe:  weak  kefiiri                            0.400  Kefir
probe:  weak  sorrel                             0.333  Squirrel
```

`Cheese, feta` is the right row for feta and scores below the weak floor,
where the resolver's own report calls the database the problem. Four-letter
queries cannot clear 0.45 against any comma-separated description.

### 2.13 Everything else that exists in English and not in the domain's words

Verified present in `food`, verified `none` under the native name:

| native name (probe: `none`) | row that exists | probe on the English name |
|---|---|---|
| kaszanka | `Blood sausage` 171618, 379 kcal | `auto blood sausage 1.000` |
| salceson | `Head cheese` 2706180, 157 kcal | `auto head cheese 1.000` |
| smalec | `Lard` 171401, 902 kcal | `weak lard spread 0.417` |
| skwarki | `Pork, cracklings` | `auto pork cracklings 1.000` |
| placki ziemniaczane / bramborák / draniki | `Potato pancake` 2709552, 196 kcal | `auto potato pancakes 1.000` |
| naleśniki / palacsinta / blini | `Crepe, plain` 2708342, 224 kcal | `auto crepe plain 1.000` |
| pączki | `Doughnut, jelly` 2708074 · `Doughnuts, yeast-leavened, with jelly filling` 172759, 340 kcal | `auto jelly doughnut 1.000` |
| sernik | `Cheesecake, plain` 2707861, 399 kcal | `auto cheesecake plain 1.000` |
| szarlotka | `Strudel, apple` 175032 · `Cake or cupcake, apple` | `auto apple strudel 1.000` |
| rétes | `Strudel, apple` / `Strudel, cheese` | `auto strudel apple 1.000` |
| kopytka / gnocchi-shaped kluski | `Gnocchi, potato` 2708722, 135 kcal | `ask gnocchi 0.533` |
| knedlíky | `Dumpling, no meat` 2708344, 125 kcal | `ask meat filled dumpling 0.583` |
| kiszona kapusta | `Sauerkraut` 2709982 | `auto sauerkraut 1.000` |
| ogórki kiszone | `Pickles, dill` · `Pickles, cucumber, sour` | `auto dill pickles 1.000` |
| chrzan | `Horseradish` | `auto horseradish 1.000` |
| śmietana | `Sour cream, regular` 2705614, 196 kcal | head is `Sour cream, light`, blocked → escalates |
| kasza gryczana | `Buckwheat groats, roasted, cooked` 170686, 92 kcal | `ask cooked buckwheat 0.567` |
| kasza perłowa | `Barley, pearled, cooked` | `ask pearl barley 0.611` |
| krupnik | `Soup, barley` 2709147 | `auto barley soup 1.000` |
| barszcz czerwony | `Soup, borscht` 2710105, 20 kcal | `ask borscht 0.615` |
| langoš | `Bread, dough, fried` | `auto fried dough 0.667` |
| burek / banitsa / gibanica | `Spanakopita` 2708729 · `Phyllo dough` 172791 | `auto spanakopita 1.000` |
| pršut | `Ham, prosciutto` | `auto prosciutto 0.733` |
| rakija / slivovica / pálinka | `Brandy` 2710699 | `ask fruit brandy 0.538` |
| grochówka | `Soup, split pea, with meat` | `auto pea soup with smoked meat 0.633` |
| fasolka po bretońsku | `Soup, bean, with meat` / `Beans, baked, canned, with pork` | `auto bean soup with smoked meat 0.769` |
| papryka faszerowana / punjene paprike | `Stuffed pepper, with rice and meat` | `auto pepper stuffed with meat and rice 1.000` |
| gulyás | `Stew, beef` 2706592 | `ask hungarian beef stew 0.500` |
| pörkölt / paprikás | `Stew, beef` / `Stew, chicken` | `auto chicken stew 1.000` |

---

## 3. Entity gaps — searched by ingredient and category, and genuinely absent

### 3.1 Twaróg. The near-miss is real and the easy mapping is wrong.

This is the one the brief flags, and it survives the check.

```
probe:  none  twarog                             -      (nothing)
probe:  none  quark                              -      (nothing)
probe:  ask   curd cheese                        0.579  Soybean, curd cheese
probe:  ask   farmer cheese                      0.609  Cottage cheese, farmer's
probe:  auto  cottage cheese                     0.778  Cheese, cottage, NFS
```

Every candidate USDA offers, per 100 g:

```
 2705753 Cheese, cottage, dry curd                     72 kcal  10.3 P   0.3 F
 2705754 Cheese, cottage, salted, dry curd             71        10.2     0.3
  173417 Cheese, cottage, lowfat, 1% milkfat           72        12.4     1.0
 2705747 Cheese, cottage, NFS                          82        11.0     2.3
 2705749 Cottage cheese, farmer's                     148        11.0     9.7
 2346384 Cottage cheese, full fat                     105        11.6     4.2
  171248 Cheese, ricotta, part skim milk              138        11.4     7.9
```

Twaróg półtłusty is ~133 kcal / **18 P** / 4.7 F; twaróg chudy ~99 / **19.8 P** /
0.5 F. **No USDA row has more than 12.4 g protein**, because American cottage
cheese is a wet, uncompressed curd and twaróg is pressed. Mapping twaróg to any
of these under-reports protein by 40–50% — on a food this user will log several
times a week, and the error runs in the direction that matters most.

`Cottage cheese, farmer's` is the trap: the *name* is the standard English
gloss of twaróg and the numbers are the furthest wrong of the lean options
(9.7 g fat).

**Rejected**, all of it. Twaróg needs a `/food` panel from a Polish packet,
not a USDA mapping. Same for tvorog, tworóg, túró, curd cheese, and every dish
built on them (syrniki, leniwe, sernik z twarogu, knedle).

### 3.2 Sheep cheese as a class does not exist in this database

`ILIKE '%sheep%'` returns three rows: `Milk, sheep, fluid`, and two
sheepshead *fish*. There is no sheep-milk cheese of any kind.

That kills a clean mapping for **oscypek, bryndza, urda, telemea, sirene,
kashkaval, gjizë, kajmak**. The available neighbours are `Cheese, feta`
(173420: 265 kcal / 14.2 P / 21.5 F; 2705714: 273 / 19.7 / 19.1) and
`Cheese, goat, hard type` (172197: 452 / 30.5 / 35.6).

Feta is defensible for the *brined white* group — sirene, telemea, bryndza —
which is genuinely the same technology (brined, sheep or sheep/cow, 20% fat).
It is **not** defensible for oscypek, which is smoked, hard-pressed and
scalded, nor for kajmak, which is not a cheese at all but a clotted cream skin
(and `clotted cream` / `creme fraiche` return 0 rows).

### 3.3 Sorrel

```
probe:  weak  sorrel                             0.333  Squirrel
probe:  weak  sorrel green soup                  0.314  Soup, pea, green, canned, condensed
```

`ILIKE '%sorrel%'` → **0 rows**. Szczaw / zupa szczawiowa has no entity and no
near neighbour (spinach is the usual substitution and is a different plant with
different oxalate and vitamin C). Genuine entity gap.

### 3.4 Żurek / kvass — the fermented-rye family

```
probe:  none  zurek                              -      (nothing)
probe:  weak  sour rye soup                      0.368  Soup, hot and sour
probe:  none  kvass                              -      (nothing)
probe:  none  fermented rye drink                -      (nothing)
probe:  none  zakwas                             -      (nothing)
```

Nothing rye-and-fermented exists beyond flour and bread. `Soup, hot and sour`
is a Chinese soup and would be a culturally absurd fallback. Kvass's nearest
rows are `Malt beverage, includes non-alcoholic beer` (37 kcal) and
`Soft drink, root beer` (41 kcal) — both roughly right on energy and sugar and
both wrong about what it is. Reported; not proposed.

### 3.5 Ryazhenka / fermented baked milk

```
probe:  none  ryazhenka                          -      (nothing)
probe:  none  fermented baked milk               -      (nothing)
```

`Kefir` (2705394, 52 kcal / 3.6 P) exists and is the nearest fermented-milk
row. Ryazhenka is baked-then-fermented and typically 4% fat / ~67 kcal. Kefir
is a *medium* nutritional fallback, not a synonym; the cultures and the fat
differ.

### 3.6 Ajvar / lutenica / zacuscă

```
probe:  none  ajvar                              -      (nothing)
probe:  none  lutenitsa                          -      (nothing)
probe:  none  zacusca                            -      (nothing)
probe:  weak  roasted pepper spread              0.429  Roast beef spread
probe:  weak  red pepper spread                  0.393  Peppers, sweet, red, raw
```

Nearest by ingredient: `Peppers, sweet, red, sauteed` (168550: 133 kcal /
12.8 F) and `Eggplant dip` (2710049: 183 / 15.0 F). Ajvar is roasted red
pepper with oil, ~100–140 kcal — the sautéed-pepper row is close on both
energy and fat, and is defensible as a *fallback*. `Eggplant dip` is baba
ganoush and is the wrong vegetable for ajvar (right one for zacuscă and for
salată de vinete).

### 3.7 The grilled-minced-meat family

```
probe:  none  cevapi / cevapcici / pljeskavica / mici / mititei / kebapche / kyufte / qofte  -  (nothing)
probe:  ask   beef patty grilled                 0.542  Beef, ground, patty
probe:  weak  grilled minced meat                0.320  Shrimp, grilled
```

No kebab/kofta/ćevap row exists (`ILIKE '%kofta%'`, `'%kebab%'` → 0 rows;
`'%gyro%'` → `Gyro sandwich` only). `Meatballs, NS as to type of meat, with
sauce` carries a sauce. The honest target is `Beef, ground, patty` — right
technology, right macros, wrong shape — and only for the beef versions.
Ćevapi are usually a beef/lamb mix; pljeskavica often includes pork.
Proposed at medium, never as a synonym.

### 3.8 Others confirmed absent with no near neighbour

`aspic` / `kholodets` / `galareta` (0 rows for aspic; `Beef, cured, luncheon
meat, jellied` is a different food), `halva` (0 rows), `kashkaval` (0),
`ayran` (0; no yogurt-drink row of any kind), `boza` (0), `kompot` (0),
`kisiel` (0), `syrniki`, `pelmeni`, `khinkali`, `manti` (0 rows for any of
them; `Pierogi` and the wonton rows are the neighbourhood).

---

## 4. Mechanisms, beyond RECONCILED §1

§1's length rule explains §2 almost entirely. Three additional mechanisms
showed up here that it does not name, and all three produced *auto* verdicts.

**(a) Ties are broken by planner order.** `oatmeal` and `pumpernickel` both
produce two or more candidates at identical similarity, all clearing 0.62, and
`resolve_items` takes the first by list position. There is no tie-break at all
above `precedence` (which RECONCILED D1 shows never fires). `Pie, oatmeal` and
`Oatmeal, NFS` at 0.667 each is a coin flip decided by the query planner, and
it caches.

**(b) The first-segment leniency in `unrequested_qualifier` is a hole for
`DishForm, ingredient` rows.** The rule blocks a first segment only when it
echoes the query. USDA writes `Pie, oatmeal`, `Roll, oatmeal`, `Bagel,
pumpernickel`, `Soup, meatball` — the *form* first, the ingredient second — and
in every one the first segment shares nothing with an ingredient query, so it
passes free. The docstring's reasoning (a name sharing nothing is "a different
food and a weak match, judged by similarity") assumes similarity will sort it
out. For a two-segment description where the second segment *is* the whole
query, similarity does the opposite.

**(c) Ingredient-plus-dish-word queries lose the dish word.** `sauerkraut
stew` → `Sauerkraut`, `dried mushrooms` → `Fried mushrooms`, `carrot salad`
→ `Carrots, raw, salad`, `buckwheat kasha` → `Buckwheat`. The ingredient row
is short, the ingredient token dominates the trigram, and no guard treats "the
query names a preparation the candidate does not" as disqualifying —
`state_conflicts` covers raw/cooked/dry only. This is the class that produced
the largest errors in this domain (bigos at 3.5×, kasza at 3.7×) and it is
distinct from §1: here the *right* row is often not in USDA at all, so the
correct behaviour is to escalate, not to substitute the ingredient.

**(d) `label_absent` disables tier 2 for a non-English-typing user**, as in §0.
Not a bug; a cost and a fragility worth stating.

---

## 5. What I refuse to encode

- **twaróg → any cottage cheese row.** §3.1. 40–50% protein error, and the
  name that fits best (`Cottage cheese, farmer's`) has the worst numbers.
- **oscypek → any cheese row.** No sheep cheese exists; feta is brined and
  soft, oscypek is smoked and hard. An over-broad `→ cheese` is nutritionally
  useless and culturally wrong at once.
- **kajmak → sour cream / cream cheese.** Kajmak is a clotted milk skin,
  60–70% fat. Sour cream at 18% is not a fallback, it is a different food.
- **kvass → beer or root beer.** Energy and sugar happen to line up; nothing
  else does, and the mapping would survive as an alias forever.
- **zurek → `Soup, hot and sour`.** The only lexical neighbour is Chinese.
- **paneer/mozzarella-style substitutions for any curd cheese here.** Named
  in the brief as the worse-than-nothing case; it applies to bryndza and túró
  as much as to paneer.
- **ćevapi/mici → `Meatballs, ... with sauce`.** The sauce is a third of the
  carbohydrate.
- **kompot / kisiel → fruit juice or `Pudding, rice`.** Kompot is water with
  a little fruit and sugar; the juice rows are 3–4× the sugar. No row is close
  and a wrong one caches.
- **A blanket `-ka`/`-ki` transliteration rule.** `borsch`, `borshch`,
  `borscht` want one target; `barszcz` wants a different one (clear beetroot
  broth, ~25 kcal) from `ukrainian borscht` (a meat-and-vegetable stew at
  50–60 kcal), and `Soup, borscht` at 20 kcal is only right for the first.
  Folding them is a 2–3× error dressed up as a spelling fix.

---

## 6. Proposals

`synonym` means the surface should retrieve that row directly — same food.
`nutritional_fallback` means it is the least-wrong row and must never
auto-match silently. `parent_category` widens retrieval only.
All fdc_ids verified present in `food` on 26 Aug 2026.

### High confidence — a competent cook would not dispute it

| surface | relation | target | fdc_id |
|---|---|---|---|
| kielbasa, kiełbasa, kobasa, kolbász, kobasica | synonym | Polish sausage, pork | 174577 |
| kaszanka, krvavica, verivorst, kishka | synonym | Blood sausage | 171618 |
| salceson, sülze, presskopf, tlačenka | synonym | Head cheese | 2706180 |
| smalec | synonym | Lard | 171401 |
| skwarki, čvarci, jumări, tepertő | synonym | Pork, cracklings | 2705895 |
| salo, słonina, slanina, szalonna | synonym | Pork, cured, salt pork, raw | 168287 |
| pierogi ruskie, ruskie pierogi, perogi, pyrohy, varenyky, vareniki | synonym | Pierogi | 2708720 |
| gołąbki, golumpki, golubtsy, sarmale, töltött káposzta, holubtsi | synonym | Stuffed cabbage rolls with beef and rice | 2706620 |
| sarma (vine leaf), dolma, japrak | synonym | Grape leaves stuffed with rice | 2709064 |
| placki ziemniaczane, bramborák, draniki, deruny, kartoffelpuffer | synonym | Potato pancake | 2709552 |
| naleśniki, palacsinta, blini, blintz, palačinky, clătite | synonym | Crepe, plain | 2708342 |
| kasza gryczana, grechka, hrečka, kasha (buckwheat), pohanka | synonym | Buckwheat groats, roasted, cooked | 170686 |
| kasza perłowa, pęczak, jęczmienna | synonym | Barley, pearled, cooked | 170285 |
| krupnik | synonym | Soup, barley | 2709147 |
| śmietana, smetana, smântână, kisela pavlaka, tejföl | synonym | Sour cream, regular | 2705614 |
| kapusta kiszona, kiszona kapusta, kysané zelí, savanyú káposzta, kiselo zele | synonym | Sauerkraut | 2709982 |
| ogórki kiszone, kiszone ogórki, kwaszone ogórki, kwašeni krastavci | synonym | Pickles, dill | 2710078 |
| chrzan, křen, hren, torma, khren | synonym | Horseradish | 2710083 |
| buraczki, burak, beetroot, cvekla, sfeclă | synonym | Beets, raw | 169145 |
| ćwikła, pickled beetroot | synonym | Beets, pickled | 2710071 |
| kotlet schabowy, schabowy, řízek, rizek, bécsi szelet, schnitzel, šnicla | synonym | Pork, chop, coated, lean and fat eaten | 2705870 |
| mamaliga, mămăligă, kačamak, žganci, polenta | synonym | Cornmeal mush, no added fat | 2708374 |
| pączki, pączek, paczki, krofne, fánk | synonym | Doughnuts, yeast-leavened, with jelly filling | 172759 |
| sernik | synonym | Cheesecake, plain | 2707861 |
| szarlotka, jabłecznik, štrúdl, rétes, almás pite | synonym | Strudel, apple | 2708039 |
| kopytka, kluski śląskie, njoki | synonym | Gnocchi, potato | 2708722 |
| flaki, flaczki, dršťky, pacal, ciorbă de burtă (tripe part) | synonym | Tripe | 2706162 |
| barszcz czerwony, barszcz, borsch, borshch, boršč, borș | synonym | Soup, borscht | 2710105 |
| olej rzepakowy, rzepakowy, rapeseed oil, repkový olej | synonym | Oil, canola | 172336 |
| oatmeal, owsianka, płatki owsiane, ovesná kaše | synonym | Oatmeal, NFS | 2708380 |
| pršut, pršuta, njeguški pršut | synonym | Ham, prosciutto | 2705879 |
| lángos, langos | synonym | Bread, dough, fried | 2707653 |
| papryka faszerowana, punjene paprike, ardei umpluți, töltött paprika | synonym | Stuffed pepper, with rice and meat | 2709073 |
| grochówka, hrachová polévka | synonym | Soup, split pea, with meat | 2707458 |
| fasolka po bretońsku, pasulj, bob chorba, fazolová polévka | synonym | Soup, bean, with meat | 2707457 |
| rosół, bulion, wywar, vývar, húsleves | synonym | Soup, chicken | 2707134 |
| wątróbka drobiowa, pileća jetra, csirkemáj | synonym | Liver, chicken | 2706154 |
| kabanosy, kabanos, sudžuk, lukanka, kulen (dry) | synonym | Salami, dry or hard, pork | 172938 |
| pasztetowa, jaternice, májas hurka | synonym | Liverwurst | 2706213 |
| dried mushrooms, grzyby suszone, sušené houby | synonym | Mushrooms, shiitake, dried | 168436 |
| rakija, šljivovica, slivovice, pálinka, țuică, palinka | synonym | Brandy | 2710699 |
| sgushchenka, mleko skondensowane, kondenzované mléko | synonym | Milk, condensed, sweetened | 2705402 |

### Medium confidence — encode as fallback only, never as a silent auto-match

| surface | relation | target | fdc_id | why medium |
|---|---|---|---|---|
| bigos | nutritional_fallback | Stew, pork | 2706519 | sauerkraut-and-pork stew; the pork stew row is the right shape, wrong vegetable. **Never `Sauerkraut`** — see §1.5 |
| gulyás, gulasz, guláš, gulaš | nutritional_fallback | Stew, beef | 2706592 | paprika and lard are not in the row; energy within ~15% |
| pörkölt, paprikás, paprikash | nutritional_fallback | Stew, chicken | 2706678 | sour cream in paprikás adds ~25 kcal/100 g |
| svíčková, vepřo-knedlo-zelo | dish_ingredient | Stew, beef + Dumpling, no meat | 2706592 / 2708344 | must decompose; the sauce is cream-thickened |
| knedlíky, houskový knedlík, knedle | nutritional_fallback | Dumpling, no meat | 2708344 | 125 kcal; bread dumplings run 150–180 |
| pelmeni, manti, khinkali | nutritional_fallback | Wonton, dumpling or pot sticker, steamed | 2708708 | meat-filled boiled dough; wrapper is thicker |
| burek, byrek, banitsa, gibanica, placinta, bureka | nutritional_fallback | Spanakopita | 2708729 | phyllo-and-cheese pie; filling varies widely |
| ćevapi, ćevapčići, mici, mititei, pljeskavica, kebapche, ćufte, qofte, kyufte | nutritional_fallback | Beef, ground, patty | 2705855 | grilled minced meat; beef/lamb/pork mix varies |
| sirene, telemea, bryndza, feta (cyrillic spellings) | nutritional_fallback | Cheese, feta | 2705714 | brined white cheese; sheep vs cow fat differs |
| ajvar, lutenica, lutenitsa | nutritional_fallback | Peppers, sweet, red, sauteed | 168550 | roasted pepper with oil; 133 kcal against ajvar's 100–140 |
| zacuscă, salată de vinete, eggplant spread | nutritional_fallback | Eggplant dip | 2710049 | right vegetable, right fat; seasoning differs |
| ryazhenka, kiselo mlyako, zsiadłe mleko, maslanka (drinking) | nutritional_fallback | Kefir | 2705394 | fermented milk; ryazhenka is baked and fattier |
| golonka, koleno, csülök | nutritional_fallback | Pork, ham hocks | 2705900 | 268 kcal; roasted golonka runs higher |
| tatar, befsztyk tatarski, tatarák | nutritional_fallback | Beef, ground, 93% lean, raw | — | raw lean beef; needs the raw row, not a patty |
| kefir, kefiiri, kefir 1% | synonym | Kefir | 2705394 | already reachable at 1.000; listed so a Baltic spelling does not miss |
| kluski leniwe, leniwe pierogi, syrniki, túrógombóc | dish_ingredient | twaróg + egg + flour | — | blocked on §3.1; cannot be resolved until twaróg exists |
| makowiec, poppy seed roll, bejgli | dish_ingredient | Cake, pound + Spices, poppy seed | 2707882 / 171330 | no filled sweet-yeast-roll row; **not** `Spices, poppy seed` alone |
| pierogi z mięsem, pierogi z kapustą i grzybami | parent_category | Pierogi | 2708720 | 2708720 is the potato-and-cheese formulation; meat filling runs ~20% higher |
| ukrainian borscht, borshch with meat | parent_category | Soup, vegetable, with meat | 2710116 | 44 kcal, closer than `Soup, borscht`'s 20 for the hearty version |

### Structural, not a synonym

- **Break ties above `precedence`.** §4(a). Two rows at 0.667 decided by
  planner order is how `Pie, oatmeal` beats `Oatmeal, NFS`. RECONCILED D1
  already proposes a completeness column for exactly this slot; a
  form-noun demotion (`Pie|Roll|Bagel|Muffin|Cookie|Cracker|Soup, <query>`)
  would settle this family on its own.
- **Close the first-segment hole in `unrequested_qualifier`.** §4(b). A
  first segment that is a *culinary form* and shares nothing with the query
  should disqualify, not pass. The docstring's spaghetti-squash counter-example
  does not apply: `squash` is not a form noun.
- **Treat a dish word in the query as a state the candidate must not
  contradict.** §4(c). `stew`, `soup`, `salad`, `roll`, `pie`, `cake`,
  `fritter`, `pancake` in the query, absent from the description, should block
  the auto-match onto a bare ingredient row. This alone removes bigos→Sauerkraut,
  carrot salad→raw carrot and buckwheat kasha→raw buckwheat.
- **`beetroot`, `rapeseed`, `coated`, `groats`.** Four vocabulary bridges
  worth putting beside `nutrient.canonical_id` rather than in `parse.py`, per
  RECONCILED §3.1's treatment of `unsalted ≡ without salt`.
