# AUDIT-mexico-central-caribbean

28 Aug 2026. Domain: **Mexico (Oaxacan, Yucatecan, Poblano, Norteño),
Guatemala, El Salvador, Honduras, Cuba, Puerto Rico, the Dominican Republic,
Jamaica, Trinidad, Haiti.**

Method: every term below went through `scripts/probe_knowledge.py` against the
live `food` table, read-only. Every line in a fenced block is verbatim probe
output; nothing is paraphrased and no claim appears without the line behind it.

**A probe verdict of `auto` is not by itself a wrong-confident match.**
`probe_knowledge.py` measures `db.search_foods` alone. The shipped resolver
then applies four more disqualifiers — `inverts_meaning`, `state_conflicts`,
`unrequested_qualifier` and `label_absent` — and takes the best candidate that
survives *all* of them. Every dangerous-looking `auto` in this audit was
re-run through those guards with a scratchpad script that mirrors the
`auto = next(...)` selector in `nutrai/llm/parse.py` line-for-line. Where the
guards fire, the case escalates to the model tier, which is the system working,
and it is recorded as such. See §"Which claimed autos survive the guards".

Verdicts: `none` (nothing returned) | `weak` (< 0.45) | `ask` (0.45–0.62, goes
to the model tier — the system working) | `auto` (>= 0.62, taken with no model
consulted — the dangerous one when wrong, because it also caches an alias that
no command can ever repoint).

## Verdict counts

**416 terms probed**, plus a systematic scan of 108 `Form, tail` rows.

| batch | terms | none | weak | ask | auto |
|---|---|---|---|---|---|
| 1 Mexican dishes | 86 | 37 | 15 | 14 | 20 |
| 2 Mexican ingredients | 98 | 25 | 38 | 14 | 21 |
| 3 Central America + Caribbean | 113 | 50 | 37 | 16 | 10 |
| 4 English paraphrases | 101 | 1 | 27 | 30 | 43 |
| verification probes | 18 | 1 | 8 | 5 | 4 |
| **total** | **416** | **114 (27%)** | **125 (30%)** | **79 (19%)** | **98 (24%)** |

The headline is the contrast between batch 3 (**44% `none`**) and batch 4
(**1% `none`**) — the same foods, named in Spanish and Kreyòl versus named in
English. Findings, the guard reconciliation, rejections and notes are at the end
of the file, after the five batch sections.

---

## Batch 1 — Mexican dishes (86 terms)

```
ask   mole                               0.455  Mole sauce
none  mole negro                         -      (nothing)
none  mole poblano                       -      (nothing)
none  mole verde                         -      (nothing)
none  mole amarillo                      -      (nothing)
none  mole coloradito                    -      (nothing)
weak  mole rojo                          0.312  Mole sauce
ask   chicken mole                       0.542  Chicken with mole sauce
auto  chicken in mole sauce              0.704  Chicken with mole sauce
none  cochinita pibil                    -      (nothing)
none  pibil                              -      (nothing)
none  barbacoa                           -      (nothing)
weak  beef barbacoa                      0.364  Beef, bacon, cooked
none  lamb barbacoa                      -      (nothing)
none  birria                             -      (nothing)
none  birria de res                      -      (nothing)
none  quesabirria                        -      (nothing)
none  tinga                              -      (nothing)
none  tinga de pollo                     -      (nothing)
ask   chicken tinga                      0.500  Chicken, tail
auto  chilaquiles                        1.000  Chilaquiles
auto  chilaquiles verdes                 0.667  Chilaquiles
auto  chilaquiles rojos                  0.667  Chilaquiles
ask   pozole                             0.583  Soup, pozole
weak  pozole rojo                        0.412  Soup, pozole
weak  pozole verde                       0.389  Soup, pozole
weak  pozole blanco                      0.368  Soup, pozole
weak  tamal                              0.417  Tamale, NFS
ask   tamales                            0.533  Tamales (Navajo)
auto  tamale                             0.636  Tamale, NFS
auto  pork tamale                        1.000  Tamale, pork
none  sope                               -      (nothing)
none  sopes                              -      (nothing)
none  huarache                           -      (nothing)
none  huaraches                          -      (nothing)
none  tlayuda                            -      (nothing)
none  tlacoyo                            -      (nothing)
ask   gordita                            0.615  Gordita, meat
none  elote                              -      (nothing)
none  esquites                           -      (nothing)
ask   grilled corn                       0.500  Fish, cod, grilled
weak  mexican street corn                0.308  Mexican pizza
none  aguachile                          -      (nothing)
auto  carnitas                           0.643  Pork, carnitas
auto  pork carnitas                      1.000  Pork, carnitas
weak  al pastor                          0.353  Almond paste
none  tacos al pastor                    -      (nothing)
none  machaca                            -      (nothing)
none  menudo                             -      (nothing)
weak  chile relleno                      0.414  Chiles rellenos, cheese-filled
ask   chiles rellenos                    0.593  Chiles rellenos, cheese-filled
auto  enchilada                          0.714  Enchilada, NFS
weak  enchiladas verdes                  0.391  Enchilada, NFS
weak  tostada                            0.400  Tostada shells, corn
weak  flauta                             0.333  Flan
auto  taquito                            0.667  Taquito, egg
auto  quesadilla                         0.733  Quesadilla, egg
auto  burrito                            0.667  Burrito, NFS
auto  chimichanga                        0.706  Chimichanga, meat
weak  torta                              0.308  Cake, torte
none  torta ahogada                      -      (nothing)
none  cemita                             -      (nothing)
none  molletes                           -      (nothing)
none  migas                              -      (nothing)
none  carne asada                        -      (nothing)
none  tacos de carne asada               -      (nothing)
ask   salsa verde                        0.571  Salsa verde or salsa, green
ask   salsa roja                         0.500  Salsa, red
auto  pico de gallo                      0.700  Salsa, pico de gallo
auto  guacamole                          0.714  Guacamole, NFS
auto  refried beans                      1.000  Refried beans
weak  frijoles refritos                  0.304  Frijoles rojos volteados (Refried beans, red, canned)
none  frijoles charros                   -      (nothing)
none  arroz rojo                         -      (nothing)
ask   mexican rice                       0.481  ON THE BORDER, Mexican rice
ask   sopa de fideo                      0.583  Soup, sopa de fideo aguada
ask   caldo de res                       0.542  Soup, sopa or caldo de res
none  menudo rojo                        -      (nothing)
auto  tortilla soup                      1.000  Soup, tortilla
auto  churro                             0.667  Churros
ask   tres leches                        0.588  Cake, tres leche
auto  flan                               1.000  Flan
weak  horchata                           0.391  Horchata, made with milk
none  agua de jamaica                    -      (nothing)
none  champurrado                        -      (nothing)
auto  atole                              1.000  Atole

ask=14 (16%)  auto=20 (23%)  none=37 (43%)  weak=15 (17%)
```

### B1-1 Naming the variety makes the dish unreachable — `mole` and `pozole`

```
ask   mole                               0.455  Mole sauce
none  mole negro                         -      (nothing)
none  mole poblano                       -      (nothing)
none  mole verde                         -      (nothing)
none  mole amarillo                      -      (nothing)
none  mole coloradito                    -      (nothing)
weak  mole rojo                          0.312  Mole sauce
```

```
ask   pozole                             0.583  Soup, pozole
weak  pozole rojo                        0.412  Soup, pozole
weak  pozole verde                       0.389  Soup, pozole
weak  pozole blanco                      0.368  Soup, pozole
```

`Mole sauce` (2707151) and `Soup, pozole` exist and are the right rows for all
of these — USDA carries one row per family. The bare head word finds it; adding
a true, correct second word costs 0.14 to 0.22 of similarity and, for five of
the six moles, drops the row out of the result set entirely. `mole negro` is
not a weak match against `Mole sauce`; it returns **nothing**, because
`plainto_tsquery('mole negro')` requires both tokens and `desc % q` falls under
pg_trgm's 0.3 floor once the extra six characters are added.

This is RECONCILED.md §1 running in the user's direction: the person who knows
the cuisine types the more precise term and gets *less*. It is the single most
repeated shape in this whole domain — see B1-2 (`chilaquiles verdes`, which
survives only because its head row is short), B3 (`sancocho de pollo`) and B4.

### B1-2 `chilaquiles verdes` survives where `mole verde` does not, and the difference is description length

```
auto  chilaquiles                        1.000  Chilaquiles
auto  chilaquiles verdes                 0.667  Chilaquiles
auto  chilaquiles rojos                  0.667  Chilaquiles
```

Verified through the guards — this one really is an auto:

```
'chilaquiles verdes' state=None
   0.667  Chilaquiles                                                    OK
  => AUTO -> Chilaquiles
```

Worth recording as the control case. The mechanism that kills `mole verde` is
purely arithmetic: `Chilaquiles` is a single-word description so the added
colour word costs 0.33 and lands above the gate, while `Mole sauce` is already
diluted by `sauce` and the same addition falls off the cliff. Nothing semantic
distinguishes the two, which is why no ranking change reaches this.

### B1-3 `sope` — the purest normalisation defect in the domain (bad_normalization)

```
none  sope                               -      (nothing)
none  sopes                              -      (nothing)
weak  sope shell                         0.429  Pie shell
ask   gordita                            0.615  Gordita, meat
weak  gordita sope                       0.444  Gordita, meat
```

USDA contains the literal word:

```
 2707818 | survey_fndds_food  | Gordita/sope shell, plain, no filling
            kcal 260  fat 11.19  prot 3.85  carb 37.2  sugar 0.72  fibre 2.9  Na 376  Ca 55  Fe 3.7  chol 0
```

`gordita` reaches its own family at 0.615; `sope` — spelled identically, in the
same description, six characters to the right — reaches nothing at all, because
the slash in `Gordita/sope` is not a token boundary for either `to_tsvector` or
pg_trgm. Same row, same word, one punctuation mark. `sope shell` then lands on
`Pie shell`, which is the `Dish, ingredient` inversion recorded in
AUDIT-taxonomy-fallback arriving from a different direction.

### B1-4 `menudo` — entity gap behind an English gloss (missing_synonym)

```
none  menudo                             -      (nothing)
none  menudo rojo                        -      (nothing)
weak  tripe soup                         0.379  Restaurant, Latino, tripe soup
weak  stewed tripe                       0.302  Stewed tripe, with potatoes, Puerto Rican style
ask   beef tripe                         0.545  Tripe
```

The rows exist and are good ones:

```
   168069 | sr_legacy_food     | Restaurant, Latino, tripe soup
            kcal 74  fat 2.58  prot 8.61  carb 4.07  Na 411  Ca 22  Fe 0.68  chol 59
  2706725 | survey_fndds_food  | Stewed tripe, with potatoes, Puerto Rican style
  2706162 | survey_fndds_food  | Tripe
            kcal 89  fat 3.85  prot 12.6  carb 0  Na 425  Ca 72  Fe 0.62  chol 127
```

The word every speaker of the language uses returns an empty list; the row that
*is* the dish sits at 0.379 behind an English paraphrase nobody types. Recall
is 0 for the actual query, so no ranking function can reach it. Note also that
`menudo` in Puerto Rican and Filipino usage is a *different* dish — pork and
liver stew — which is an argument for a synonym that escalates rather than one
that auto-matches.

### B1-5 The absent entities, neighbours searched

Searched by name and by category, read-only:

```
$ q.py find "barbacoa|birria|pastor|machaca|pibil|tinga|carne asada|elote|esquite|tlayuda|huarache|sope|menudo|tripe"
   173095 | sr_legacy_food     | Beef, New Zealand, imported, variety meats and by-products, tripe cooked, boiled
   173096 | sr_legacy_food     | Beef, New Zealand, imported, variety meats and by-products, tripe uncooked, raw
   174769 | sr_legacy_food     | Beef, variety meats and by-products, tripe, cooked, simmered
   170599 | sr_legacy_food     | Beef, variety meats and by-products, tripe, raw
   172962 | sr_legacy_food     | Chicken breast, fat-free, mesquite flavor, sliced
   174228 | sr_legacy_food     | Fish, bass, striped, cooked, dry heat
   171948 | sr_legacy_food     | Fish, bass, striped, raw
   175124 | sr_legacy_food     | Fish, mullet, striped, cooked, dry heat
   175123 | sr_legacy_food     | Fish, mullet, striped, raw
  2707818 | survey_fndds_food  | Gordita/sope shell, plain, no filling
   168069 | sr_legacy_food     | Restaurant, Latino, tripe soup
  2706725 | survey_fndds_food  | Stewed tripe, with potatoes, Puerto Rican style
  2706162 | survey_fndds_food  | Tripe
(13 rows)
```

Thirteen rows for fourteen search words, and nine of them matched `tripe` or the unrelated word `striped`: **there is no row anywhere in the
table containing `barbacoa`, `birria`, `pastor`, `machaca`, `pibil`, `tinga`,
`carne asada`, `elote`, `esquite`, `tlayuda` or `huarache`.** These are entity
gaps, not ranking failures. `carnitas` sitting beside them with its own
Foundation-quality row and a clean auto-match —

```
auto  carnitas                           0.643  Pork, carnitas
auto  pork carnitas                      1.000  Pork, carnitas
```

— shows the absences are a USDA coverage accident rather than a design.

### B1-6 Cross-language trigram noise: `barbacoa` -> bacon, `al pastor` -> almond paste

```
weak  beef barbacoa                      0.364  Beef, bacon, cooked
weak  al pastor                          0.353  Almond paste
weak  torta                              0.308  Cake, torte
weak  flauta                             0.333  Flan
ask   chicken tinga                      0.500  Chicken, tail
weak  mexican street corn                0.308  Mexican pizza
ask   grilled corn                       0.500  Fish, cod, grilled
```

All below the auto gate except none, so nothing is cached — the low scores are
doing the work, not any check. `chicken tinga -> Chicken, tail` at 0.500 is the
one worth flagging: it is inside the `ask` band, so the model tier is handed a
candidate list headed by a cut of poultry that is not in the dish, for a query
whose correct row does not exist. `grilled corn -> Fish, cod, grilled` is the
same shape with the state word doing the matching and the food doing nothing.

### B1-7 THE MAIN CORRECTION — five probe `auto`s the guards stop or redirect

This is the class the brief asks about, and the answer is that the shipped
resolver is better than the probe suggests.

```
'taquito' state=None
   0.667  Taquito, egg                                                   qual:egg
   0.500  Taquito, chicken                                               below_gate,qual:chicken
   0.400  Taquito, cheese only                                           below_gate,qual:cheese only
   0.381  Taquito, beef or pork                                          below_gate,qual:beef or pork
   0.159  Taquitos, frozen, chicken and cheese, oven-heated              below_gate,qual:frozen
  => ESCALATES to model tier

'chimichanga' state=None
   0.706  Chimichanga, meat                                              qual:meat
   0.706  Chimichanga, chicken                                           qual:chicken
   0.522  Chimichanga, with beans                                        below_gate,qual:with beans
  => ESCALATES to model tier
```

The probe says `auto 0.667 Taquito, egg` and `auto 0.706 Chimichanga, meat`;
`unrequested_qualifier` disqualifies every candidate and both items go to the
model tier, which is exactly where an unspecified filling belongs. **Neither is
a wrong-confident match in production.**

Two more where the guard does not block the item but *reorders* it onto the
right row, which the probe cannot see because it reports only the head:

```
'quesadilla' state=None
   0.733  Quesadilla, egg                                                qual:egg
   0.733  Quesadilla, NFS                                                OK
  => AUTO -> Quesadilla, NFS

'burrito' state=None
   0.667  Burrito, NFS                                                   OK
   0.667  Egg burrito                                                    qual:Egg burrito
  => AUTO -> Burrito, NFS

'tamale' state=None
   0.636  Tamale, NFS                                                    OK
   0.583  Tamale, pork                                                   below_gate,qual:pork
  => AUTO -> Tamale, NFS
```

`Quesadilla, egg` and `Quesadilla, NFS` tie at 0.733 and the probe prints
whichever the sort returned first; the resolver takes the NFS row. Any audit
that reads probe output alone would have filed two false positives here.

Clean, correct autos in this batch, confirmed through the guards:
`chilaquiles`, `carnitas`, `pork carnitas`, `churro -> Churros`, `flan`,
`atole`, `refried beans`, `tortilla soup -> Soup, tortilla`,
`guacamole -> Guacamole, NFS`, `pico de gallo -> Salsa, pico de gallo`,
`enchilada -> Enchilada, NFS`, `chicken in mole sauce -> Chicken with mole
sauce` (0.704, only candidate surviving, and the right row at 137 kcal).

---

## Batch 2 — Mexican ingredients: chiles, cheeses, aromatics, masa (98 terms)

```
weak  ancho                              0.300  Peppers, ancho, dried
none  ancho chile                        -      (nothing)
none  chile ancho                        -      (nothing)
ask   ancho pepper                       0.571  Peppers, ancho, dried
auto  dried ancho pepper                 0.857  Peppers, ancho, dried
none  guajillo                           -      (nothing)
none  guajillo chile                     -      (nothing)
weak  guajillo pepper                    0.318  Pepper steak
weak  pasilla                            0.381  Peppers, pasilla, dried
none  pasilla chile                      -      (nothing)
ask   pasilla pepper                     0.591  Peppers, pasilla, dried
none  mulato                             -      (nothing)
none  mulato chile                       -      (nothing)
ask   chipotle                           0.474  Chipotle dip, light
weak  chipotle pepper                    0.346  Chipotle dip, light
weak  chipotle in adobo                  0.321  Chipotle dip, light
weak  morita                             0.308  Margarita
none  morita chile                       -      (nothing)
none  chile de arbol                     -      (nothing)
none  arbol chile                        -      (nothing)
none  piquin                             -      (nothing)
weak  chile piquin                       0.316  Chilaquiles
none  cascabel chile                     -      (nothing)
none  habanero                           -      (nothing)
weak  habanero pepper                    0.320  Pepper, banana, raw
ask   scotch bonnet                      0.500  Scotch
weak  scotch bonnet pepper               0.333  Scotch
weak  serrano                            0.400  Peppers, serrano, raw
weak  serrano chile                      0.308  Peppers, serrano, raw
auto  serrano pepper                     0.667  Peppers, serrano, raw
weak  jalapeno                           0.429  Peppers, jalapeno, raw
none  jalapeño                           -      (nothing)
auto  jalapeno pepper                    0.700  Peppers, jalapenos
none  poblano                            -      (nothing)
weak  poblano pepper                     0.350  Pepper steak
none  poblano chile                      -      (nothing)
weak  fresh poblano                      0.333  Parsley, fresh
weak  dried poblano                      0.389  Pear, dried
none  new mexico chile                   -      (nothing)
none  hatch chile                        -      (nothing)
weak  chile                              0.250  Sauce, hot chile, sriracha
ask   chiles                             0.583  Chilaquiles
weak  dried chile                        0.429  Peppers, hot chile, sun-dried
auto  chili powder                       0.650  Spices, chili powder
weak  chipotle powder                    0.385  Spices, chili powder
auto  epazote                            0.667  Epazote, raw
none  hoja santa                         -      (nothing)
weak  mexican oregano                    0.364  Mexican pizza
weak  oregano                            0.381  Spices, oregano, dried
auto  cilantro                           0.692  Cilantro, raw
none  achiote                            -      (nothing)
weak  annatto                            0.400  Natto
weak  achiote paste                      0.368  Almond paste
ask   tomatillo                          0.562  Tomatillos, raw
auto  tomatillos                         0.733  Tomatillos, raw
ask   green tomato                       0.619  Tomato, green, pickled
none  huitlacoche                        -      (nothing)
weak  corn smut                          0.400  Corn syrup
auto  nopales                            0.667  Nopales, raw
weak  nopal                              0.385  Nopales, raw
weak  cactus pads                        0.438  Cactus, raw
ask   prickly pear                       0.611  Prickly pears, raw
auto  queso fresco                       1.000  Queso Fresco
auto  queso cotija                       1.000  Queso cotija
ask   cotija                             0.538  Queso cotija
auto  cotija cheese                      0.684  Cheese, cotija, solid
weak  queso oaxaca                       0.300  Queso Fresco
auto  oaxaca cheese                      0.700  Cheese, oaxaca, solid
weak  queso panela                       0.300  Queso Fresco
auto  panela cheese                      0.647  Cheese, paneer
auto  queso asadero                      1.000  Queso Asadero
ask   asadero                            0.571  Queso Asadero
ask   queso chihuahua                    0.536  Cheese, mexican, queso chihuahua
none  requeson                           -      (nothing)
weak  crema mexicana                     0.318  Mexican pizza
weak  mexican crema                      0.400  Mexican pizza
auto  sour cream                         0.647  Sour cream, light
auto  masa harina                        0.632  Masa harina, cooked
weak  masa                               0.263  Masa harina, cooked
weak  corn masa                          0.323  Corn flour, masa, enriched, white
none  nixtamalized corn                  -      (nothing)
ask   hominy                             0.500  Hominy, cooked
weak  cornmeal                           0.429  Cornmeal, blue (Navajo)
weak  corn flour                         0.407  Corn flour, whole-grain, white
auto  corn tortilla                      1.000  Tortilla, corn
auto  flour tortilla                     1.000  Tortilla, flour
auto  tortilla chips                     0.714  Tortilla chips, plain
none  piloncillo                         -      (nothing)
ask   mexican chocolate                  0.545  Baking chocolate, mexican, squares
none  canela                             -      (nothing)
weak  mexican cinnamon                   0.391  Bread, cinnamon
weak  pepita                             0.231  Seeds, pumpkin seeds (pepitas), raw
weak  pepitas                            0.320  Seeds, pumpkin seeds (pepitas), raw
auto  pumpkin seed                       0.650  Pumpkin seeds, salted
ask   lime                               0.556  Lime, raw
weak  mexican lime                       0.421  Mexican pizza
auto  avocado                            0.667  Oil, avocado
weak  tomatillo salsa                    0.409  Tomatillos, raw

ask=14 (14%)  auto=21 (21%)  none=25 (26%)  weak=38 (39%)
```

### B2-1 **`avocado` auto-matches `Oil, avocado`. 884 kcal against 160.**

The highest-value finding in this domain, and it survives every guard — this is
not a probe artefact, it is what production does:

```
'avocado' state=None
   0.667  Oil, avocado                                                   OK
   0.667  Avocado, raw                                                   OK
   0.471  Avocado dressing                                               below_gate,qual:Avocado dressing
   0.421  Sushi roll, avocado                                            below_gate
   0.333  Avocado, Hass, peeled, raw                                     below_gate,qual:Hass
  => AUTO -> Oil, avocado
```

```
   173573 | Oil, avocado
            kcal 884  fat 100  prot 0  carb 0  fibre 0  Na 0  Ca 0  Fe 0
  2709223 | Avocado, raw
            kcal 160  fat 14.66  prot 2  carb 8.53  sugar 0.66  fibre 6.7  Na 7  Ca 12  Fe 0.55  chol 0
```

Half an avocado, 100 g, logged as **884 kcal and 100 g of fat** instead of 160
and 14.7 — and the fibre, potassium and folate that are the reason anyone eats
one are all zero. `avocado` is not an exotic word: it is the base of guacamole,
which is itself the cleanest auto-match in batch 1.

Mechanism. `Oil, avocado` and `Avocado, raw` are both twelve characters and
both contain the query as one whole word, so `similarity()` returns **the same
0.667 for both** and the ordering falls through to a tiebreak that has nothing
to do with which food was meant. Then:

- `label_absent` passes — "avocado" is in the description.
- `unrequested_qualifier` passes, and the reason is precise. Segment 0 is
  `Oil`, which shares no word with the query, so the `i == 0` branch's "only a
  name that echoes the query can narrow it" condition is false and the segment
  is **skipped**. Segment 1 is `avocado`, which *does* intersect the query, so
  it is not a qualifier either. The row contains the word "oil" and no guard
  ever looks at it.

This is the `Pie, strawberry` finding of AUDIT-taxonomy-fallback with a *form*
word rather than a dish word in the head, and it is worse, because the tie means
the correct row is sitting at the identical score one line below.

### B2-2 The same defect, and the giveaway: word order decides which way it fails

```
'coconut' state=None
   0.667  Oil, coconut                                                   OK
   0.667  Oil, coconut                                                   OK
   0.667  Coconut oil                                                    qual:Coconut oil
   0.615  Coconut milk                                                   below_gate,qual:Coconut milk
  => AUTO -> Oil, coconut

'olive' state=None
   0.667  Olive oil                                                      qual:Olive oil
   0.417  Olives, NFS                                                    below_gate
  => ESCALATES to model tier
```

`Coconut oil` and `Oil, coconut` are the same substance written two ways.
`unrequested_qualifier` blocks the first — `Coconut oil` is segment 0, echoes
the query and adds "oil" — and cannot see the second, because USDA put the
comma in a different place. **The guard is actively selecting the more
dangerous of two identical rows.** `olive` escapes only because USDA happens to
have no `Oil, olive` row shorter than its usage note, so the tail-first
spelling is the only one on the list and the guard catches it.

`palm`, `sesame` and `corn` escalate on score alone, not on any check.

### B2-3 The chile family — a hard recall cliff, not a ranking problem (bad_normalization)

USDA writes peppers as `Peppers, <variety>, <state>` and never uses the word
*chile*. Adding it — the word every cook in the cuisine uses — does not lower
the score, it removes the row from the result set:

```
weak  ancho                              0.300  Peppers, ancho, dried
none  ancho chile                        -      (nothing)
none  chile ancho                        -      (nothing)
ask   ancho pepper                       0.571  Peppers, ancho, dried
auto  dried ancho pepper                 0.857  Peppers, ancho, dried
weak  pasilla                            0.381  Peppers, pasilla, dried
none  pasilla chile                      -      (nothing)
ask   pasilla pepper                     0.591  Peppers, pasilla, dried
weak  serrano                            0.400  Peppers, serrano, raw
weak  serrano chile                      0.308  Peppers, serrano, raw
auto  serrano pepper                     0.667  Peppers, serrano, raw
```

`serrano` scores 0.400 and `serrano chile` scores 0.308 against the same row —
adding a true word *loses* 0.09. `ancho` is on pg_trgm's 0.3 `%` threshold
exactly; `ancho chile` falls off it and the row stops being retrieved at all.
`ask -> auto` swings on the single word "pepper" vs "chile" for both ancho and
serrano. No ranking change reaches a row that recall never returns.

Only these chiles have any row at all: **ancho, pasilla, serrano, jalapeno**.

```
none  guajillo                           -      (nothing)
none  mulato                             -      (nothing)
none  morita chile                       -      (nothing)
none  chile de arbol                     -      (nothing)
none  piquin                             -      (nothing)
none  cascabel chile                     -      (nothing)
none  habanero                           -      (nothing)
none  new mexico chile                   -      (nothing)
none  hatch chile                        -      (nothing)
```

with only cross-language noise where a query does return something:

```
weak  guajillo pepper                    0.318  Pepper steak
weak  habanero pepper                    0.320  Pepper, banana, raw
weak  morita                             0.308  Margarita
weak  chile piquin                       0.316  Chilaquiles
weak  chipotle in adobo                  0.321  Chipotle dip, light
```

`habanero -> Pepper, banana` is the one to note: a banana pepper is 0 SHU and a
habanero is 200,000, and the two words differ by a transposition. All are below
the gate, so the escalation is the system working — but the model tier is being
handed a list on which the right food does not appear.

### B2-4 Fresh/dried pairs are not distinguished, and for poblano the fresh half does not exist

Tested explicitly, because it is where the nutrition actually diverges:

```
none  poblano                            -      (nothing)
weak  poblano pepper                     0.350  Pepper steak
none  poblano chile                      -      (nothing)
weak  fresh poblano                      0.333  Parsley, fresh
weak  dried poblano                      0.389  Pear, dried
auto  dried ancho pepper                 0.857  Peppers, ancho, dried
```

A poblano dried *is* an ancho — the same fruit, one name for each state — and
USDA carries only the dried one. So the pair a knowledge layer would most
naturally encode (`poblano` ≡ `ancho`) is the one that must **not** be encoded:
`Peppers, ancho, dried` is 281 kcal/100 g and a fresh poblano is roughly 20, a
14x energy error on a food used 100 g at a time in a chile relleno. The honest
answer is that the fresh half has no row and the term must escalate.

Note that the state word is doing all the retrieval work, not the food word:
`dried poblano -> Pear, dried` and `fresh poblano -> Parsley, fresh`.

### B2-5 `jalapeño` with the tilde returns nothing (spelling_transliteration_failure)

```
weak  jalapeno                           0.429  Peppers, jalapeno, raw
none  jalapeño                           -      (nothing)
auto  jalapeno pepper                    0.700  Peppers, jalapenos
```

The *correct* spelling — the one an iOS keyboard autocorrects to — takes the
food from findable to invisible. The same will hold for `piña`, `plátano`,
`jamón`, `frijol`. Guard-checked, and the unaccented form does resolve well:

```
'jalapeno pepper' state=None
   0.700  Peppers, jalapenos                                             qual:jalapenos
   0.682  Peppers, jalapeno, raw                                         OK
   0.667  Stuffed jalapeno pepper                                        qual:Stuffed jalapeno pepper
  => AUTO -> Peppers, jalapeno, raw
```

The guards do good work here: they drop `Stuffed jalapeno pepper` — a battered
fried appetiser — and land on the raw pepper.

### B2-6 `masa harina` auto-matches the **cooked** row; dry masa is 3.9x the energy

```
'masa harina' state=None
   0.632  Masa harina, cooked                                            OK
   0.255  Corn flour, masa harina, white or yellow, dry, raw             below_gate,qual:white or yellow
  => AUTO -> Masa harina, cooked
```

```
  2708376 | Masa harina, cooked
            kcal 97  fat 0.99  prot 2.26  carb 20.5  sugar 0.43  fibre 1.7  Na 283  Ca 44  Fe 1.33
  2710835 | Corn flour, masa harina, white or yellow, dry, raw
            kcal 376  fat 4.34  prot 7.56  carb 76.69  fibre 7.04  Na 2.7  Ca 111.6  Fe 1.70
```

Masa harina is a flour: it is bought dry, weighed dry, and "200 g of masa
harina" means the powder. The auto-match takes the reconstituted dough at 97
kcal — a **3.9x** understatement — and 283 mg of sodium the flour does not have.
The Foundation dry row scores 0.255 because it is 49 characters long, which is
RECONCILED.md §1 exactly.

**The state guard saves this, when the model supplies a state:**

```
'masa harina' state=dry
   0.632  Masa harina, cooked                                            state:cooked
   0.255  Corn flour, masa harina, white or yellow, dry, raw             below_gate,qual:white or yellow
  => ESCALATES to model tier
```

So this one is conditional and worth stating precisely: it is a wrong-confident
match **only when `state` is absent or `unknown`**, which for a flour named in a
recipe is the common case. Recorded as a partial catch, not a clean one.

### B2-7 The nixtamalisation question, answered: USDA can represent it, the words cannot reach it

```
auto  masa harina                        0.632  Masa harina, cooked
weak  masa                               0.263  Masa harina, cooked
weak  corn masa                          0.323  Corn flour, masa, enriched, white
none  nixtamalized corn                  -      (nothing)
weak  cornmeal                           0.429  Cornmeal, blue (Navajo)
weak  corn flour                         0.407  Corn flour, whole-grain, white
ask   hominy                             0.500  Hominy, cooked
```

The calcium difference nixtamalisation creates is in the data and is large:

```
  2710835 | Corn flour, masa harina, white or yellow, dry, raw    Ca 111.6
   169694 | Corn flour, masa, enriched, white                     Ca 138
```

against plain `Corn flour, whole-grain, white` — so the distinction is
representable and the audit's answer to the brief is that it is a *reachability*
problem, not a coverage one. `masa` — the word anyone making tortillas says —
scores 0.263 against its own row, and `cornmeal` lands on a Navajo blue cornmeal
rather than the plain one.

### B2-8 Mexican cheeses: five of eight reachable, and the word order decides

```
auto  queso fresco                       1.000  Queso Fresco
auto  queso cotija                       1.000  Queso cotija
auto  queso asadero                      1.000  Queso Asadero
weak  queso oaxaca                       0.300  Queso Fresco
weak  queso panela                       0.300  Queso Fresco
auto  oaxaca cheese                      0.700  Cheese, oaxaca, solid
auto  cotija cheese                      0.684  Cheese, cotija, solid
auto  panela cheese                      0.647  Cheese, paneer
ask   queso chihuahua                    0.536  Cheese, mexican, queso chihuahua
none  requeson                           -      (nothing)
```

`Cheese, oaxaca, solid` (2647441) is a full Foundation row. The Spanish
head-noun-first order — how it is written on the packet and on every menu —
reaches a *different cheese* at 0.300, while `queso fresco` and `queso cotija`
hit 1.000 because USDA happens to store those two Spanish-first. The same user,
typing the same construction, gets a perfect match for two cheeses and the
wrong one for the third, for no reason visible to them.

`queso oaxaca` and `queso panela` both landing on `Queso Fresco` at exactly
0.300 is the pg_trgm floor: they are not ranked below it, they are the only
thing that clears retrieval.

Guard-checked. **`panela cheese -> Cheese, paneer` is NOT a production
auto-match** — `unrequested_qualifier` blocks "paneer" and every alternative:

```
'panela cheese' state=None
   0.647  Cheese, paneer                                                 qual:paneer
   0.389  Cheese, NFS                                                    below_gate
  => ESCALATES to model tier
```

and the two correct-looking autos are also **not** autos, blocked on "solid":

```
'oaxaca cheese'  0.700  Cheese, oaxaca, solid    qual:solid   => ESCALATES
'cotija cheese'  0.684  Cheese, cotija, solid    qual:solid   => ESCALATES
```

Three probe `auto`s, three escalations. Worth noting the cost of the good news:
`solid` is a Foundation-only sample-form word appearing on the best rows in the
table, and treating it as a narrowing qualifier sends correct matches to the
model tier. That is the safe direction to fail in, but it is a fee paid on
every Foundation cheese.

The numbers, for the record — panela is a salted pressed fresh cow's cheese and
belongs with the queso fresco rows, not with paneer:

```
  2705740 | Cheese, paneer            kcal 299  fat 15.52  prot 15.86  Na 185  Ca 597
  2647442 | Cheese, queso fresco, solid  kcal 297.6  fat 23.36  prot 18.88  Na 626.5  Ca 601.8
  2647443 | Cheese, cotija, solid     kcal 351.4  fat 27.24  prot 23.84  Na 1625  Ca 699.6
  2647441 | Cheese, oaxaca, solid     kcal 297.1  fat 22.1  prot 22.15  Na 734.2  Ca 532.3
```

Paneer is unsalted: 185 mg sodium against 626 for queso fresco, a 3.4x gap on
the nutrient the cheese is actually watched for. Cotija at 1625 mg is a
different order again, which is why a single "Mexican fresh cheese" fallback
would be wrong for all three.

### B2-9 `sour cream` and `pumpkin seed` — probe `auto`, production escalation

```
'sour cream' state=None
   0.647  Sour cream, light                                              qual:light
   0.647  Sour cream, light                                              qual:light
   0.579  Cream, sour, full fat                                          below_gate,qual:full fat
   0.579  Sour cream, fat free                                           below_gate,qual:fat free
  => ESCALATES to model tier

'pumpkin seed' state=None
   0.650  Pumpkin seeds, salted                                          qual:Pumpkin seeds
   0.632  Pumpkin seeds, NFS                                             qual:Pumpkin seeds
   0.462  Seeds, pumpkin seeds (pepitas), raw                            below_gate
  => ESCALATES to model tier
```

Both are guards working exactly as designed: `Sour cream, light` is 136 kcal
against 196 for `Sour cream, regular` (2705614), and "light" is a fat grade the
user never asked for. Note that `Sour cream, regular` — the right row — is not
even on the first page.

### B2-10 The `Mexican pizza` magnet

```
weak  mexican oregano                    0.364  Mexican pizza
weak  crema mexicana                     0.318  Mexican pizza
weak  mexican crema                      0.400  Mexican pizza
weak  mexican lime                       0.421  Mexican pizza
weak  mexican street corn                0.308  Mexican pizza   (batch 1)
```

Five distinct queries, one fast-food row. The adjective is the longest token in
each query and it is the only word the row shares, so `Mexican pizza` — 15
characters, short enough to score well — heads the candidate list for every
Mexican *ingredient* whose English name carries the nationality. All are weak,
so nothing caches; the cost is that the model tier's list is topped by a pizza
five times over. `crema mexicana` has a good fallback in `Sour cream, regular`
and cannot reach it.

### B2-11 Aromatics: two clean wins and three absences

```
auto  epazote                            0.667  Epazote, raw     => AUTO -> Epazote, raw
auto  cilantro                           0.692  Cilantro, raw    => AUTO -> Cilantro, raw
auto  tomatillos                         0.733  Tomatillos, raw  => AUTO -> Tomatillos, raw
auto  nopales                            0.667  Nopales, raw     => AUTO -> Nopales, raw
```

Four guard-verified correct auto-matches, including two foods that exist almost
nowhere outside this cuisine. Against them:

```
none  hoja santa                         -      (nothing)
none  huitlacoche                        -      (nothing)
weak  corn smut                          0.400  Corn syrup
none  achiote                            -      (nothing)
weak  annatto                            0.400  Natto
none  piloncillo                         -      (nothing)
none  canela                             -      (nothing)
```

`annatto -> Natto` is a fermented soybean against a seed colourant, one letter
apart; `label_absent` catches it independently of the score:

```
'annatto' state=None
   0.400  Natto                                                          below_gate,label_absent
   0.195  Seasoning mix, dry, sazon, coriander & annatto                 below_gate,qual:sazon
  => ESCALATES to model tier
```

Also note the singular/plural asymmetry that runs through the whole batch:
`nopales` 0.667 auto vs `nopal` 0.385 weak; `tomatillos` 0.733 auto vs
`tomatillo` 0.562 ask; `pepitas` 0.320 vs `pepita` 0.231 — both weak against
the row that literally contains the word, in brackets:
`Seeds, pumpkin seeds (pepitas), raw`.

---

## Batch 3 — Central America and the Caribbean (113 terms)

```
ask   pupusa                             0.583  Pupusa, meat
weak  pupusas                            0.429  Pupusa, meat
weak  pupusa de queso                    0.333  Pupusa, meat
weak  pupusa revuelta                    0.333  Pupusa, meat
none  curtido                            -      (nothing)
none  salvadoran slaw                    -      (nothing)
weak  gallo pinto                        0.333  Salsa, pico de gallo
none  baleada                            -      (nothing)
none  baleadas                           -      (nothing)
none  tamal guatemalteco                 -      (nothing)
none  pepian                             -      (nothing)
none  jocon                              -      (nothing)
none  kak ik                             -      (nothing)
none  chuchito                           -      (nothing)
none  plato tipico                       -      (nothing)
weak  casamiento                         0.333  Pimiento
ask   yuca frita                         0.571  Yuca fries
weak  platano frito                      0.412  Frito pie
none  tajadas                            -      (nothing)
weak  carne guisada                      0.421  Guisada, beef
none  ropa vieja                         -      (nothing)
weak  picadillo                          0.333  Armadillo
none  lechon asado                       -      (nothing)
none  lechon                             -      (nothing)
auto  cuban sandwich                     1.000  Cuban sandwich
none  medianoche                         -      (nothing)
none  moros y cristianos                 -      (nothing)
weak  congri                             0.400  Congee
none  tostones                           -      (nothing)
none  mofongo                            -      (nothing)
weak  mangu                              0.333  Mango, raw
weak  mangú                              0.333  Mango, raw
weak  arroz con gandules                 0.304  Restaurant, Latino, Arroz con grandules (rice and pigeonpeas)
none  arroz con pollo                    -      (nothing)
none  pernil                             -      (nothing)
weak  pasteles                           0.429  Puerto Rican pasteles
none  alcapurria                         -      (nothing)
auto  bacalaitos                         0.733  Bacalaitos fritos
weak  sofrito                            0.235  Sauce, sofrito, prepared from recipe
none  recaito                            -      (nothing)
weak  sazon                              0.146  Seasoning mix, dry, sazon, coriander & annatto
weak  adobo seasoning                    0.333  Spices, poultry seasoning
weak  mojo                               0.333  Mojito
none  mojo criollo                       -      (nothing)
none  sancocho                           -      (nothing)
none  sancocho de pollo                  -      (nothing)
none  mondongo                           -      (nothing)
weak  la bandera dominicana              0.393  Arepa Dominicana
none  habichuelas guisadas               -      (nothing)
none  locrio                             -      (nothing)
none  chimichurri dominicano             -      (nothing)
ask   jerk                               0.455  Pork jerky
ask   jerk chicken                       0.471  Fat, chicken
auto  jerk pork                          0.818  Pork jerky
weak  jerk seasoning                     0.345  Spices, poultry seasoning
none  ackee                              -      (nothing)
weak  ackee and saltfish                 0.300  Fish, mackerel, salted
weak  saltfish                           0.333  Fish sauce
weak  salt cod                           0.235  Fish, cod, Atlantic, dried and salted
none  bammy                              -      (nothing)
none  festival                           -      (nothing)
none  callaloo                           -      (nothing)
weak  callaloo greens                    0.346  Greens, canned, cooked
ask   rice and peas                      0.500  Babyfood, peas and brown rice
weak  oxtail stew                        0.316  Beef, oxtails
none  jamaican patty                     -      (nothing)
ask   beef patty                         0.611  Corned beef patty
none  escovitch                          -      (nothing)
weak  escovitch fish                     0.333  Fish, eel
ask   curry goat                         0.455  Goat
ask   goat curry                         0.455  Goat
weak  doubles                            0.207  BURGER KING, Double Cheeseburger
weak  bara                               0.333  Barley
ask   channa                             0.583  Channa Saag
none  pelau                              -      (nothing)
weak  roti                               0.217  Bread, chappatti or roti
none  buss up shut                       -      (nothing)
none  trinidad roti                      -      (nothing)
none  pholourie                          -      (nothing)
none  griot                              -      (nothing)
none  griyo                              -      (nothing)
none  pikliz                             -      (nothing)
weak  soup joumou                        0.312  Soup, NFS
none  diri ak pwa                        -      (nothing)
none  legume                             -      (nothing)
none  tasso                              -      (nothing)
none  accra                              -      (nothing)
weak  conch                              0.200  Mollusks, conch, baked or broiled
ask   conch fritters                     0.474  Fritter, corn
auto  plantain                           0.692  Plantain, raw
auto  green plantain                     0.667  Plantains, green, raw
auto  ripe plantain                      0.684  Plantains, ripe, raw
auto  cassava                            0.667  Cassava, raw
ask   yuca                               0.455  Yuca fries
none  malanga                            -      (nothing)
ask   taro                               0.556  Taro, raw
weak  name yam                           0.308  Yam, raw
none  calabaza                           -      (nothing)
weak  ají dulce                          0.333  Dulce de Leche
weak  aji dulce                          0.333  Dulce de Leche
weak  culantro                           0.375  Cilantro, raw
none  recao                              -      (nothing)
ask   allspice                           0.450  Spices, allspice, ground
ask   pimento                            0.533  Pimento, canned
weak  pimento pepper                     0.381  Pimento, canned
ask   scotch bonnet                      0.500  Scotch
none  annatto oil                        -      (nothing)
auto  coconut milk                       1.000  Coconut milk
auto  tamarind                           1.000  Tamarind
ask   guava                              0.600  Guava, raw
auto  soursop                            0.667  Soursop, raw
weak  guanabana                          0.391  Guanabana nectar, canned
weak  mamey                              0.353  Sapote, mamey, raw

ask=16 (14%)  auto=10 (9%)  none=50 (44%)  weak=37 (33%)
```

44% `none` — by a wide margin the worst-covered batch in the audit.

### B3-1 The correction the brief asks for: `jerk pork` at 0.818 is stopped

The single highest-scoring dangerous-looking match in the whole domain, and it
never reaches production:

```
'jerk pork' state=None
   0.818  Pork jerky                                                     qual:Pork jerky
   0.385  Pork, NFS                                                      below_gate
   0.357  Pork, ribs                                                     below_gate,qual:ribs
  => ESCALATES to model tier
```

`jerk` and `jerky` are unrelated words — *jerk* is from Taíno *charqui* by way
of the barbecue pit, *jerky* is dried strips — and at 0.818 the probe verdict is
`auto` with a comfortable margin. `unrequested_qualifier` sees segment 0
`Pork jerky` echoing the query's "pork" and adding "jerky", and blocks it.
Every fallback is below the gate, so the item escalates.

`Pork jerky` is roughly 410 kcal per 100 g of dried meat against ~250 for
stewed jerk pork, so this would have been a real error; it is also the case
that would have been *cached forever*, since `jerk pork` is a name a person
types repeatedly. Recorded as the guards earning their keep.

```
ask   jerk                               0.455  Pork jerky
ask   jerk chicken                       0.471  Fat, chicken
```

Both stay in the `ask` band. `jerk chicken -> Fat, chicken` is the same
cross-language noise one gate lower.

### B3-2 `bacalaitos` — the guards firing on the *right* row

```
'bacalaitos' state=None
   0.733  Bacalaitos fritos                                              qual:Bacalaitos fritos
  => ESCALATES to model tier
```

The only candidate in the table is the correct one, and `unrequested_qualifier`
blocks it because segment 0 echoes "bacalaitos" and adds "fritos" — which is
not a narrowing qualifier, it is half the food's name (a bacalaito *is* fried).
The cost is one model call, which is the right price; recorded because it is the
clearest example in the domain of the guard's known false-positive shape: a
two-word Spanish dish name in the head segment.

The same shape costs `Bacalaitos` nothing worse, but note `oaxaca cheese` and
`cotija cheese` in B2-8 paying the same fee on `solid`.

### B3-3 `callaloo` — two correct rows exist, the word reaches neither, and which is right depends on the island

```
none  callaloo                           -      (nothing)
weak  callaloo greens                    0.346  Greens, canned, cooked
```

```
$ q.py find "ackee|callaloo|mofongo|tostone|sancocho|escovitch|pikliz|griot|pelau|jerk chicken|jerk pork|saltfish|dried and salted|amaranth leaves|taro leaves"
   168492 | sr_legacy_food     | Amaranth leaves, cooked, boiled, drained, with salt
   169202 | sr_legacy_food     | Amaranth leaves, cooked, boiled, drained, without salt
   168385 | sr_legacy_food     | Amaranth leaves, raw
   174190 | sr_legacy_food     | Fish, cod, Atlantic, dried and salted
  2709633 | survey_fndds_food  | Taro leaves, cooked
   168488 | sr_legacy_food     | Taro leaves, cooked, steamed, without salt
   168487 | sr_legacy_food     | Taro leaves, raw
(7 rows)
```

and both botanical identities resolve perfectly under their English names:

```
auto  amaranth leaves                    0.800  Amaranth leaves, raw
auto  taro leaves                        0.750  Taro leaves, raw
```

Callaloo is **amaranth leaves** in Jamaica and **taro leaves** in Trinidad and
the eastern Caribbean. Both rows are in the table; neither is reachable from
the word. And they are not interchangeable:

```
   168385 | Amaranth leaves, raw   kcal 23  prot 2.46  Ca 215  Fe 2.32  Na 20
   168487 | Taro leaves, raw       kcal 42  prot 4.98  Ca 107  Fe 2.25  Na 3
```

1.8x the energy, 2x the protein, half the calcium. This is the cleanest case in
the domain for a synonym that **escalates rather than auto-matches**: the
mapping is genuinely ambiguous and only a person can say which island's callaloo
they ate.

### B3-4 Confirmed entity gaps with no row in the table at all

The same scan above shows **no row anywhere in `food` contains** `ackee`,
`callaloo`, `mofongo`, `tostone`, `sancocho`, `escovitch`, `pikliz`, `griot` or
`pelau`. Adding the probe results:

```
none  curtido                            -      (nothing)
none  baleada                            -      (nothing)
none  pepian                             -      (nothing)
none  jocon                              -      (nothing)
none  ropa vieja                         -      (nothing)
none  lechon                             -      (nothing)
none  moros y cristianos                 -      (nothing)
none  tostones                           -      (nothing)
none  mofongo                            -      (nothing)
none  arroz con pollo                    -      (nothing)
none  pernil                             -      (nothing)
none  alcapurria                         -      (nothing)
none  recaito                            -      (nothing)
none  mojo criollo                       -      (nothing)
none  sancocho                           -      (nothing)
none  mondongo                           -      (nothing)
none  habichuelas guisadas               -      (nothing)
none  locrio                             -      (nothing)
none  ackee                              -      (nothing)
none  bammy                              -      (nothing)
none  festival                           -      (nothing)
none  callaloo                           -      (nothing)
none  jamaican patty                     -      (nothing)
none  escovitch                          -      (nothing)
none  pelau                              -      (nothing)
none  buss up shut                       -      (nothing)
none  pholourie                          -      (nothing)
none  griot                              -      (nothing)
none  pikliz                             -      (nothing)
none  diri ak pwa                        -      (nothing)
none  tasso                              -      (nothing)
none  accra                              -      (nothing)
none  malanga                            -      (nothing)
none  calabaza                           -      (nothing)
none  recao                              -      (nothing)
none  gandules                           -      (nothing)
```

**Haiti is entirely absent**: `griot`, `griyo`, `pikliz`, `soup joumou`
(0.312 `Soup, NFS`), `diri ak pwa`, `legume`, `tasso`, `accra` — eight for
eight, no row, no neighbour. **Guatemala is seven for seven.** Puerto Rico and
the Dominican Republic fare better only because FNDDS carries a handful of
"Puerto Rican style" rows, and those are reached by their English glosses
rather than by their names.

### B3-5 The dish/ingredient split, this domain's version of carbonara/guanciale

Every row below is a dish that resolves — or nearly — beside its signature
ingredient that does not:

| dish | verdict | defining ingredient | verdict |
|---|---|---|---|
| `ackee and saltfish` | weak 0.300 `Fish, mackerel, salted` | `ackee` | **none** |
| — | — | `saltfish` | weak 0.333 `Fish sauce` |
| `pupusa` | ask 0.583 `Pupusa, meat` | `curtido` | **none** |
| `mofongo` | **none** | `green plantain` | **auto 0.667, correct** |
| `escovitch fish` | weak 0.333 `Fish, eel` | `escovitch` | **none** |
| `doubles` | weak 0.207 `BURGER KING, Double Cheeseburger` | `bara` / `channa` | weak 0.333 `Barley` / ask 0.583 `Channa Saag` |
| `arroz con gandules` | weak 0.304 (right row) | `gandules` | **none** |
| `griot` | **none** | `pikliz` | **none** |
| `jerk chicken` | ask 0.471 `Fat, chicken` | `jerk seasoning` | weak 0.345 `Spices, poultry seasoning` |
| `cuban sandwich` | **auto 1.000, correct** | `lechon asado` | **none** |
| `sancocho` | **none** | `malanga` / `calabaza` / `yuca` | **none** / **none** / ask 0.455 `Yuca fries` |

`mofongo` is the sharpest instance: the dish returns nothing while its one
substantial ingredient — green plantain, which is 80% of the mass — is a clean
guard-verified auto-match:

```
'green plantain' state=None
   0.667  Plantains, green, raw                                          OK
   0.609  Plantains, green, fried                                        below_gate
   0.583  Plantains, green, boiled                                       below_gate
  => AUTO -> Plantains, green, raw
```

That is the position CLAUDE.md's "The model may not invent what it was not
told" describes: the model can reach the parts but has no row for the whole,
and the pressure is on it to write a plausible ingredient list rather than say
so. `mofongo` is fried then mashed with pork crackling; an item list of "green
plantain, raw 200 g" would be a substantial understatement of both fat and
energy, and nothing downstream can see it.

`ackee and saltfish -> Fish, mackerel, salted` is the same failure with a
number attached: ackee is a fruit with roughly 15 g of fat per 100 g and
mackerel is a different species entirely. Both halves are wrong and both are
weak, so it escalates.

### B3-6 Salt cod: the right row exists, and the phrasing decides whether it is found

```
weak  saltfish                           0.333  Fish sauce
weak  salt cod                           0.235  Fish, cod, Atlantic, dried and salted
weak  salted cod                         0.333  Fish, cod, Atlantic, dried and salted
ask   dried salted cod                   0.485  Fish, cod, Atlantic, dried and salted
```

```
   174190 | Fish, cod, Atlantic, dried and salted
            kcal 290  fat 2.37  prot 62.82  Na 7027  Ca 160  Fe 2.5  chol 152
```

**7,027 mg of sodium per 100 g** — roughly three days' ceiling in 50 g of fish —
so this is the row in the domain where being unreachable costs the most. The
Caribbean word `saltfish` reaches `Fish sauce` instead; `salt cod` reaches the
right row at 0.235, twelve hundredths *below* the weak floor. Only the fullest
English phrasing, which nobody says, gets into the `ask` band.

### B3-7 `pimento` and `allspice` — the name collision, measured

Asked explicitly by the brief, and the answer is that the collision is real,
that the resolver lands on the wrong plant, and that it does not matter much.

```
ask   allspice                           0.450  Spices, allspice, ground
ask   pimento                            0.533  Pimento, canned
weak  pimento pepper                     0.381  Pimento, canned
```

```
$ q.py find "allspice|pimento|pimiento"
   170854 | sr_legacy_food     | Cheese, pasteurized process, pimento
   332791 | foundation_food    | Olives, green, Manzanilla, stuffed with pimiento
   174576 | sr_legacy_food     | Pickle and pimiento loaf, pork
   168559 | sr_legacy_food     | Pimento, canned
  2709979 | survey_fndds_food  | Pimiento
   171315 | sr_legacy_food     | Spices, allspice, ground
(6 rows)
```

```
   168559 | Pimento, canned          kcal 23   fat 0.3   carb 5.1   fibre 1.9   Ca 6
   171315 | Spices, allspice, ground kcal 263  fat 8.69  carb 72.12 fibre 21.6  Ca 661
```

*Pimenta dioica* (allspice, the berry, called **pimento** everywhere in Jamaica
and in every jerk recipe) and *Capsicum annuum* (the sweet pimiento pepper) are
different plants, and USDA files the Jamaican one under `allspice` and gives
the *pepper* the word `pimento`. A Jamaican typing "pimento" gets the pepper —
and it is not caught by any guard on the grounds of being wrong, only by being
below the auto gate:

```
'pimento' state=None
   0.533  Pimento, canned                                                below_gate,qual:canned
   0.545  Pimiento                                                       below_gate,label_absent
   0.242  Cheese, pasteurized process, pimento                           below_gate,qual:pasteurized process
  => ESCALATES to model tier
```

Note the second line: `Pimiento` at 0.545 is flagged `label_absent` because the
guard's prefix stemming cannot bridge *pimento* and *pimiento* — an internal
vowel, not a suffix. That is a correct outcome reached for the wrong reason,
and it will misfire the other way on any Spanish/English spelling pair.

**Deliberately not proposed as a fix.** Allspice is used at 1–3 g in a jerk
marinade; at that mass the 240 kcal/100 g difference is under 8 kcal, and both
rows are below the gate so nothing is cached. Recording it as a collision that
exists and does not need machinery is more useful than encoding a synonym whose
correctness depends on which island the user is from.

### B3-8 Plantain: the best-served food in the domain, and it is worth saying why

```
'plantain' state=None       0.692  Plantain, raw            OK   => AUTO
'green plantain' state=None 0.667  Plantains, green, raw    OK   => AUTO
'ripe plantain' state=None  0.684  Plantains, ripe, raw     OK   => AUTO
auto  boiled green plantain              0.875  Plantains, green, boiled
ask   fried plantain                     0.609  Plantains, green, fried
```

USDA carries `Plantains, {green, ripe, overripe, underripe, yellow}, {raw,
boiled, fried}` and the resolver reaches the right one every time, including
the ripeness axis it explicitly refuses to model for bananas (CLAUDE.md,
"Things that will look like bugs and are not"). The reason it works here and
nowhere else in this audit is that USDA's words and the cook's words are the
same words: *green*, *ripe*, *fried*. Every failure above is a case where they
are not.

Other guard-verified correct autos in this batch: `cassava -> Cassava, raw`,
`cuban sandwich -> Cuban sandwich` (1.000), `coconut milk -> Coconut milk`,
`tamarind -> Tamarind`, `soursop -> Soursop, raw`.

### B3-9 Assorted cross-language noise, all below the gate

```
weak  picadillo                          0.333  Armadillo
weak  congri                             0.400  Congee
weak  mangu                              0.333  Mango, raw
weak  casamiento                         0.333  Pimiento
weak  mojo                               0.333  Mojito
weak  ají dulce                          0.333  Dulce de Leche
weak  bara                               0.333  Barley
weak  doubles                            0.207  BURGER KING, Double Cheeseburger
weak  platano frito                      0.412  Frito pie
weak  gallo pinto                        0.333  Salsa, pico de gallo
weak  culantro                           0.375  Cilantro, raw
weak  guanabana                          0.391  Guanabana nectar, canned
```

`picadillo -> Armadillo` and `mojo -> Mojito` are trigram accidents and harmless
at these scores. Three are worth separating out because the *right* row is in
the table and the query cannot reach it:

- `culantro -> Cilantro, raw` (0.375). Culantro (*Eryngium foetidum*, recao) and
  cilantro (*Coriandrum sativum*) are different plants used for the same purpose;
  USDA has no culantro row, so this is a defensible fallback that the score
  denies. `recao` returns nothing at all.
- `guanabana -> Guanabana nectar, canned` (0.391) while `soursop` auto-matches
  the fruit at 0.667. Same fruit, two names, and the Spanish one lands on a
  sweetened juice: the nectar row carries added sugar the fruit does not.
- `sofrito` at 0.235 against `Sauce, sofrito, prepared from recipe` — its own
  row, named exactly, 40 characters long, and RECONCILED.md §1 pushes it under
  the floor. Likewise `sazon` at **0.146** against
  `Seasoning mix, dry, sazon, coriander & annatto`.

---

## Batch 4 — the English paraphrases a model would actually search on (101 terms)

Every failure above assumes the user's own word reaches the database. It often
does not, and the model tier's job is then to rewrite it into USDA's language.
This batch probes what that rewrite lands on. It is the only batch with a
`none` rate near zero (1%) and the highest `auto` rate (43%) — which is
precisely why it holds the worst findings.

```
weak  shredded beef                      0.333  Soup, beef
weak  shredded pork                      0.345  Cheese, parmesan, shredded
weak  slow cooked pork shoulder          0.339  Pork, fresh, shoulder, whole, separable lean only, cooked, roasted
weak  pork shoulder                      0.292  Pork, fresh, shoulder, whole, separable lean only, raw
weak  pork butt                          0.400  Pork, bones
auto  beef chuck                         0.647  Beef, steak, chuck
weak  beef cheek                         0.429  Burrito, beef, cheese
weak  beef shank                         0.400  Beef, steak, flank
auto  goat                               1.000  Goat
weak  lamb shoulder                      0.222  Lamb, shoulder, arm, separable lean and fat, trimmed to 1/4" fat, choice, raw
ask   fried pork skin                    0.455  Pork skin rinds
none  chicharron                         -      (nothing)
ask   pork rind                          0.529  Pork skin rinds
auto  pork cracklings                    1.000  Pork, cracklings
auto  stewed chicken                     0.750  Stew, chicken
weak  shredded chicken                   0.429  Chicken skin
weak  grilled steak                      0.389  CRACKER BARREL, grilled sirloin steak
weak  skirt steak                        0.375  Steak sauce
auto  flank steak                        0.706  Beef, steak, flank
weak  marinated pork                     0.320  Pork, steak, coated
ask   spit roasted pork                  0.526  Pork, roast
auto  dried beef                         0.688  Beef, cured, dried
auto  beef jerky                         1.000  Beef jerky
ask   salted fish                        0.571  Fish, mackerel, salted
auto  stuffed pepper                     0.625  Stuffed jalapeno pepper
ask   corn dough                         0.538  Corn dog
weak  corn husk                          0.357  Corn dog
weak  banana leaf                        0.400  Banana, baked
auto  lime juice                         0.733  Lime juice, raw
ask   orange juice                       0.619  Orange juice, 100%, NFS
weak  bitter orange                      0.389  Orange, raw
weak  sour orange                        0.438  Orange, raw
ask   white onion                        0.611  Onions, white, raw
ask   red onion                          0.600  Onions, red, raw
auto  garlic                             0.636  Garlic, raw
weak  cumin                              0.353  Spices, cumin seed
auto  coriander seed                     0.714  Spices, coriander seed
ask   bay leaf                           0.562  Spices, bay leaf
weak  clove                              0.238  Spices, cloves, ground
ask   thyme                              0.500  Thyme, fresh
weak  scallion                           0.160  Onions, spring or scallions (includes tops and bulb), raw
ask   green onion                        0.611  Onions, green, raw
auto  ginger                             0.636  Tea, ginger
weak  turmeric                           0.391  Spices, turmeric, ground
auto  curry powder                       0.650  Spices, curry powder
auto  coconut                            0.667  Oil, coconut
auto  coconut cream                      0.765  Pie, coconut cream
auto  condensed milk                     0.625  Milk, condensed, sweetened
auto  evaporated milk                    0.727  Milk, evaporated, whole
auto  lard                               1.000  Lard
auto  vegetable oil                      0.778  Vegetable oil, NFS
ask   white rice                         0.524  Beans and white rice
auto  brown rice                         0.647  Flour, rice, brown
ask   long grain rice                    0.457  Rice, brown, long grain, unenriched, raw
auto  black beans                        0.733  Black beans, NFS
auto  pinto beans                        0.750  Pinto beans, NFS
ask   red kidney beans                   0.515  Beans, kidney, red, mature seeds, raw
auto  white hominy                       0.650  Hominy, canned, white
weak  corn kernels                       0.283  Corn, sweet, yellow and white kernels,  fresh, raw
ask   sweet corn                         0.524  Corn, sweet, white, raw
auto  white corn                         0.647  Corn grain, white
auto  cabbage                            0.667  Cabbage, raw
ask   carrot                             0.500  Muffin, carrot
auto  radish                             1.000  Radish
auto  lettuce                            0.667  Lettuce, raw
weak  romaine                            0.421  Romaine lettuce, raw
auto  tomato                             0.636  Tomato, roma
auto  green bell pepper                  0.708  Peppers, bell, green, raw
auto  red bell pepper                    0.714  Peppers, bell, red, raw
ask   bell pepper                        0.524  Peppers, bell, red, raw
ask   sweet pepper                       0.545  Peppers, sweet, red, raw
weak  chayote                            0.444  Chayote, fruit, raw
auto  jicama                             0.636  Jicama, raw
weak  squash blossom                     0.280  Flowers or blossoms of sesbania, squash, or lily, cooked
auto  pumpkin                            0.727  Pie, pumpkin
auto  butternut squash                   0.630  Squash, winter, butternut, raw
auto  sweet potato                       0.812  Pie, sweet potato
weak  white potato                       0.343  Potatoes, white, flesh and skin, raw
weak  egg                                0.400  Bread, egg
ask   queso                              0.462  Queso cotija
auto  cheese                             0.636  Cheese, NFS
ask   milk                               0.556  Milk, NFS
ask   cream                              0.600  Cake, cream
auto  butter                             0.636  Butter, tub
auto  shrimp                             0.636  Shrimp, NFS
ask   fish fillet                        0.571  Fish, mullet
ask   snapper                            0.615  Fish, snapper
ask   tilapia                            0.471  Fish, tilapia, raw
ask   cod                                0.500  Cape Cod
ask   mackerel                           0.500  Fish, mackerel, NFS
auto  salmon                             0.700  Salmon salad
auto  crab                               1.000  Crab
auto  lobster                            1.000  Lobster
auto  octopus                            1.000  Octopus
weak  squid                              0.364  Squirrel
ask   chicken thigh                      0.467  Chicken thigh, stewed, skin eaten
ask   chicken breast                     0.517  Chicken breast, roll, oven-roasted
auto  chicken wing                       0.650  Chicken wing, stewed
auto  turkey                             0.636  Fat, turkey
ask   beef                               0.556  Beef, NFS
ask   pork                               0.556  Pork, NFS

ask=30 (30%)  auto=43 (43%)  none=1 (1%)  weak=27 (27%)
```

### B4-1 THE HEADLINE — `Form, food` in the head segment: nine wrong auto-matches, none of which any guard stops

B2-1 found `avocado -> Oil, avocado`. It is not an isolated row. Every one of
the following was re-run through the shipped guards and **auto-matches in
production**:

```
'turkey' state=None
   0.636  Fat, turkey                                                    OK
   0.636  Turkey, NFS                                                    OK
   0.636  Turkey, tail                                                   qual:tail
  => AUTO -> Fat, turkey

'ginger' state=None
   0.636  Tea, ginger                                                    OK
   0.467  Ginger root, raw                                               below_gate,qual:Ginger root
  => AUTO -> Tea, ginger

'coconut cream' state=None
   0.765  Pie, coconut cream                                             OK
   0.481  Coconut cream, canned, sweetened                               below_gate,qual:canned
  => AUTO -> Pie, coconut cream

'coconut' state=None
   0.667  Oil, coconut                                                   OK
   0.667  Coconut oil                                                    qual:Coconut oil
  => AUTO -> Oil, coconut

'avocado' state=None
   0.667  Oil, avocado                                                   OK
   0.667  Avocado, raw                                                   OK
  => AUTO -> Oil, avocado

'pumpkin' state=None
   0.727  Pie, pumpkin                                                   OK
   0.667  Pumpkin, raw                                                   OK
  => AUTO -> Pie, pumpkin

'sweet potato' state=None
   0.812  Pie, sweet potato                                              OK
   0.765  Sweet potato, NFS                                              OK
  => AUTO -> Pie, sweet potato

'salmon' state=None
   0.700  Salmon salad                                                   OK
   0.438  Fish, salmon, raw                                              below_gate
  => AUTO -> Salmon salad

'brown rice' state=None
   0.647  Flour, rice, brown                                             OK
   0.647  Rice flour, brown                                              qual:Rice flour
  => AUTO -> Flour, rice, brown
```

Measured cost per 100 g:

```
   173571 | Fat, turkey         kcal 900  fat 99.8   prot 0      chol 102
  2706104 | Turkey, NFS         kcal 139  fat 2.06   prot 28.81  Na 467     <- 6.5x energy, 48x fat
   173573 | Oil, avocado        kcal 884  fat 100    fibre 0
  2709223 | Avocado, raw        kcal 160  fat 14.66  fibre 6.7              <- 5.5x energy, 6.8x fat
   171412 | Oil, coconut        kcal 892  fat 99.06
  2710507 | Tea, ginger         kcal 1    fat 0.01   carb 0.18
   169231 | Ginger root, raw    kcal 80   fat 0.75   carb 17.77             <- 1/80th the energy
  2708006 | Pie, coconut cream  kcal 297  fat 17.83  sugar 18.66  Na 169
  2707571 | Coconut cream, canned, sweetened  kcal 357  fat 16.31  sugar 51.5
```

**`turkey` is the one to read twice.** CLAUDE.md records a turkey wrap on 25 Aug
whose fabricated "deli" qualifier cost 751 mg of sodium and prompted a schema
rule. The plain word `turkey`, correctly parsed, with no fabrication anywhere,
auto-matches **turkey fat at 900 kcal and 99.8 g of fat per 100 g** — and
`Turkey, NFS`, the right row, is tied at the identical 0.636 on the very next
line. A 90 g portion logs as 810 kcal instead of 125.

Mechanism, stated exactly, because it is one line of one guard. `unrequested_
qualifier` walks the description's comma segments:

- **segment 0** (`Fat`, `Oil`, `Pie`, `Tea`, `Flour`) shares no word with the
  query, so the `i == 0` branch's condition `(words & q) and extra` is false and
  the segment is **skipped entirely**. The comment above it says why: "a name
  that shares nothing with the query is a different food and a weak match,
  judged by similarity like anything else". That reasoning is correct for
  `Spaghetti squash` vs `spaghetti` and false for `Fat, turkey` vs `turkey`,
  because a form word in the head is not a competing name — it is a
  transformation of the food that follows it.
- **segment 1** is the food's own name and intersects the query, so it is not a
  qualifier either.

Nothing in the row's text is ever tested against the word "fat".

This confirms and extends AUDIT-taxonomy-fallback's `Pie, strawberry` finding —
that audit found the dish-word case; this domain adds the **form-word** case
(`Fat`, `Oil`, `Flour`, `Tea`), which is worse because the energy ratios are
larger and the words are commoner. And the tie is the part that stings: for
`turkey`, `avocado`, `pumpkin` and `sweet potato` the correct row is on the
list at the same score or within 0.05, and the wrong one is taken because a
sort order decided it.

`salmon -> Salmon salad` is the same shape with the dish word trailing, and
`Fish, salmon, raw` sits at 0.438 — the length penalty again.

### B4-2 The guards firing correctly, for contrast

```
'stuffed pepper' state=None
   0.625  Stuffed jalapeno pepper                                        qual:Stuffed jalapeno pepper
   0.600  Stuffed pepper, with meat                                      below_gate,qual:with meat
   0.441  Stuffed pepper, with rice, meatless                            below_gate,inverts,qual:with rice
  => ESCALATES to model tier

'tomato' state=None
   0.636  Tomato, roma                                                   qual:roma
   0.636  Tomato, roma                                                   qual:roma
   0.583  Soup, tomato                                                   below_gate
   0.429  Tomatoes, raw                                                  below_gate
  => ESCALATES to model tier

'butter' state=None
   0.636  Butter, tub                                                    qual:tub
   0.636  Butter, NFS                                                    OK
  => AUTO -> Butter, NFS
```

Three probe `auto`s: two escalations and one reorder onto the right row. The
difference from B4-1 is entirely whether USDA put the qualifying word before or
after the comma. `Tomato, roma` is caught; `Fat, turkey` is not; they are the
same defect written in opposite orders.

`stuffed pepper` also shows `inverts_meaning` doing its job on
`Stuffed pepper, with rice, meatless`.

### B4-3 What the model tier can and cannot rescue

Good news first — where the model rewrites a Latin American term into USDA's
own words, the resolver mostly lands correctly, guard-verified:

```
auto  pork cracklings                    1.000  Pork, cracklings
auto  flank steak                        0.706  Beef, steak, flank
auto  dried beef                         0.688  Beef, cured, dried
auto  stewed chicken                     0.750  Stew, chicken
auto  lime juice                         0.733  Lime juice, raw
auto  green bell pepper                  0.708  Peppers, bell, green, raw
auto  red bell pepper                    0.714  Peppers, bell, red, raw
auto  white hominy                       0.650  Hominy, canned, white
auto  black beans                        0.733  Black beans, NFS
auto  pinto beans                        0.750  Pinto beans, NFS
'goat' 1.000 Goat  OK  => AUTO -> Goat
```

So `chicharron` (**none**) is rescued by `pork cracklings` at 1.000, and
`curry goat` (ask 0.455) by `goat` at 1.000. That is the escalation path
working as designed and it is worth saying plainly: for this domain the model
tier is not a fallback, it is the primary mechanism.

What it cannot rescue is the B4-1 class, because there the rewrite is *correct*
and the wrong row is taken anyway. A model that turns "aguacate" into "avocado"
has done its job perfectly and the item still lands on 884 kcal of oil.

Nor can it rescue the cuts, which the length penalty puts out of reach even in
plain English:

```
weak  pork shoulder                      0.292  Pork, fresh, shoulder, whole, separable lean only, raw
weak  lamb shoulder                      0.222  Lamb, shoulder, arm, separable lean and fat, trimmed to 1/4" fat, choice, raw
weak  slow cooked pork shoulder          0.339  Pork, fresh, shoulder, whole, separable lean only, cooked, roasted
weak  scallion                           0.160  Onions, spring or scallions (includes tops and bulb), raw
weak  corn kernels                       0.283  Corn, sweet, yellow and white kernels,  fresh, raw
```

Every one of those descriptions is the right row for the query, and every one
scores below the weak floor because it is long. `pork shoulder` is the base of
carnitas, cochinita pibil, pernil and lechón — four of the domain's headline
dishes — and it is the single most consequential unreachable row here after
salt cod. `scallion` at 0.160 against a row containing the word "scallions" is
the most extreme length penalty measured anywhere in this audit.

### B4-4 `beef cheek` -> `Burrito, beef, cheese`

```
weak  beef cheek                         0.429  Burrito, beef, cheese
weak  beef shank                         0.400  Beef, steak, flank
weak  skirt steak                        0.375  Steak sauce
weak  pork butt                          0.400  Pork, bones
weak  shredded beef                      0.333  Soup, beef
weak  shredded pork                      0.345  Cheese, parmesan, shredded
```

Barbacoa and birria are made from beef cheek and shank; both queries land on
something else, both below the gate. `shredded pork -> Cheese, parmesan,
shredded` is the state word matching and the food word not, the same shape as
`grilled corn -> Fish, cod, grilled` in batch 1. `pork butt -> Pork, bones` is
the one with a nutritional edge to it — bones are not food — but at 0.400 it
escalates.

---

## Batch 5 — how wide is the `Form, food` blind spot? (systematic scan, 108 tails)

B4-1 is not a handful of unlucky rows, so I measured its extent rather than
guessing. Scratchpad `formscan.py` (read-only) takes every `food` row spelled
`<FormWord>, <tail>` for fourteen **form** words — a transformation of a food,
not a dish made from it — feeds the **tail alone** to `db.search_foods` as if a
person had typed it, applies all four shipped guards, and reports the tails
where the form row is what production would take.

Form words scanned: `Oil`, `Fat`, `Flour`, `Tea`, `Syrup`, `Juice`, `Seeds`,
`Spices`, `Nuts`, `Fish oil`, `Vegetable oil`, `Candies`, `Puddings`, `Snacks`.

```
108 candidate tails from 14 form words
...
65 of 108 tails auto-match their own form row
```

Most of the 65 are correct — for a spice or a confectionery the form word *is*
the food, so `coriander seed -> Spices, coriander seed` and
`mounds candy bar -> Candies, MOUNDS Candy Bar` are right answers. Filtered to
tails that are ordinary food nouns whose plain form is a **different food**,
verbatim from the scan (runner-up shown where there is one):

```
auto  avocado                      0.667  Oil, avocado   runner-up 0.667 Avocado, raw
auto  turkey                       0.636  Fat, turkey   runner-up 0.636 Turkey, NFS
auto  chicken                      0.667  Fat, chicken   runner-up 0.615 Chicken feet
auto  ginger                       0.636  Tea, ginger   runner-up 0.467 Ginger root, raw
auto  coconut                      0.667  Oil, coconut   runner-up 0.667 Oil, coconut
auto  peanut                       0.636  Oil, peanut   runner-up 0.636 Peanut oil
auto  almond                       0.636  Oil, almond   runner-up 0.636 Almond oil
auto  walnut                       0.636  Oil, walnut   runner-up 0.636 Walnut oil
auto  soybean                      0.667  Oil, soybean   runner-up 0.667 Soybean oil
auto  beef tallow                  0.750  Fat, beef tallow
auto  rice bran                    0.714  Oil, rice bran   runner-up 0.714 Bread, rice bran
auto  tomatoseed                   0.733  Oil, tomatoseed   runner-up 0.375 Tomato, roma
auto  apricot kernel               0.789  Oil, apricot kernel   runner-up 0.421 Apricot, raw
auto  cocoa butter                 0.765  Oil, cocoa butter   runner-up 0.421 Cashew butter
auto  walrus (alaska native)       0.840  Oil, walrus (Alaska Native)   runner-up 0.700 Walrus, meat, raw (Alaska Native)
```

### B5-1 `chicken` auto-matches `Fat, chicken` — 900 kcal, and there is no `Chicken, NFS` to lose to

The worst single row in this audit, verified through the guards:

```
'chicken' state=None
   0.667  Fat, chicken                                                   OK
   0.615  Chicken skin                                                   below_gate,qual:Chicken skin
   0.615  Chicken, tail                                                  below_gate,qual:tail
   0.615  Chicken, back                                                  below_gate,qual:back
   0.615  Chicken feet                                                   below_gate,qual:Chicken feet
  => AUTO -> Fat, chicken
```

```
   173564 | Fat, chicken   kcal 900  fat 99.8  prot 0  chol 85
  2705967 | Chicken breast, grilled without sauce, skin eaten
                           kcal 206  fat 10.62  prot 25.72  Na 329

$ q.py find "^Chicken, (NFS|nfs)|^Chicken breast, NFS|^Chicken, roasted|^Chicken, cooked"
(0 rows)
```

`turkey` at least has `Turkey, NFS` tied one line below; **chicken has no
generic row at all**, so the first page is chicken fat, chicken skin, chicken
feet, chicken tail and chicken back, and the only one clearing the gate is the
rendered fat. A 150 g portion logs as 1,350 kcal and 150 g of fat instead of
roughly 310 kcal and 16 g.

This matters more here than in most domains: `tinga de pollo`, `arroz con
pollo`, `mole poblano`, `jerk chicken`, `pepián` and `jocón` all return nothing
or near-nothing from their own names (batches 1 and 3), so "chicken" is exactly
the word the model tier is most likely to fall back to. Note batch 3's
`jerk chicken -> Fat, chicken` at 0.471 arriving at the same row one gate lower.

### B5-2 The nuts and oils, and why `soybean` is different from `almond`

```
'almond' 0.636 Oil, almond OK / 0.636 Almond oil qual:Almond oil  => AUTO -> Oil, almond
'peanut' 0.636 Peanut oil qual / 0.636 Oil, peanut OK             => AUTO -> Oil, peanut
'walnut' 0.636 Oil, walnut OK / 0.636 Walnut oil qual             => AUTO -> Oil, walnut
```

```
   171031 | Oil, almond    kcal 884  fat 100    prot 0
  2707485 | Almonds, NFS   kcal 598  fat 52.54  prot 20.96
  2707512 | Peanuts, NFS   kcal 587  fat 49.66  prot 24.35
```

`almond`, `peanut` and `walnut` are foods people eat by the handful and the
resolver takes the pressed oil: 884 kcal against 598, and — the part a calorie
ratio hides — **zero protein against 21 g**. Note in each case the tail-first
spelling (`Almond oil`, `Peanut oil`, `Walnut oil`) is sitting at the identical
score and is correctly blocked by `unrequested_qualifier`; the guard is again
selecting the one row it cannot see.

`soybean`, `canola`, `safflower`, `sunflower` and `grapeseed` are on the list
too and are **not** filed as defects: nobody eats a raw safflower, so the oil is
the only sane reading of the bare word. Likewise `beef tallow`, `cocoa butter`,
`apricot kernel` and `walrus`. The line between the two groups is whether the
unprocessed food is itself something a person logs — which is a judgement, and
is stated here as one rather than encoded.

### B5-3 What the scan says about the shape of the fix

`unrequested_qualifier`'s head-segment rule is the whole cause, and its own
comment states the case it was protecting: blocking `Spaghetti, spinach, cooked`
promoted `Spaghetti squash, cooked`, so a head segment sharing nothing with the
query is treated as a different food and judged by similarity alone. That is
right for `Spaghetti squash` and wrong for `Fat, chicken`, and the difference is
not similarity — it is that `Fat`, `Oil`, `Flour`, `Tea` and `Pie` are not
*names of foods* at all. They are a closed, small, enumerable set of
transformations, which is what makes this fixable without a knowledge layer:
a head segment drawn from that set is a transformation the user did not ask for,
and the same disqualification the tail gets should apply.

AUDIT-taxonomy-fallback reached the same conclusion from the dish-word side
(`Pie, strawberry`, `Soup, seaweed`, `Salmon salad`). This scan adds the form
words and the measurement that **the guards do not catch any of them**, which
is the claim the brief asks to be checked rather than assumed.

---

## Which claimed autos survive the guards

The brief's central methodological question, answered case by case. Fourteen
probe `auto` verdicts in this domain looked dangerous enough to re-run through
the shipped `auto = next(...)` selector. **Six were false alarms.**

| term | probe head | production outcome |
|---|---|---|
| `taquito` | 0.667 `Taquito, egg` | **escalates** — `qual:egg`, all fallbacks below gate |
| `chimichanga` | 0.706 `Chimichanga, meat` | **escalates** — `qual:meat`, `qual:chicken` |
| `panela cheese` | 0.647 `Cheese, paneer` | **escalates** — `qual:paneer` |
| `cotija cheese` | 0.684 `Cheese, cotija, solid` | **escalates** — `qual:solid` (a correct row lost) |
| `oaxaca cheese` | 0.700 `Cheese, oaxaca, solid` | **escalates** — `qual:solid` (a correct row lost) |
| `sour cream` | 0.647 `Sour cream, light` | **escalates** — `qual:light` |
| `pumpkin seed` | 0.650 `Pumpkin seeds, salted` | **escalates** — `qual:Pumpkin seeds` |
| `jerk pork` | 0.818 `Pork jerky` | **escalates** — `qual:Pork jerky` |
| `bacalaitos` | 0.733 `Bacalaitos fritos` | **escalates** — `qual:Bacalaitos fritos` (correct row lost) |
| `stuffed pepper` | 0.625 `Stuffed jalapeno pepper` | **escalates** |
| `tomato` | 0.636 `Tomato, roma` | **escalates** — `qual:roma` |
| `quesadilla` | 0.733 `Quesadilla, egg` | **reordered** onto `Quesadilla, NFS`, correct |
| `burrito` | 0.667 `Burrito, NFS` (tied `Egg burrito`) | **reordered**, correct |
| `jalapeno pepper` | 0.700 `Peppers, jalapenos` | **reordered** onto `Peppers, jalapeno, raw`, correct |
| `butter` | 0.636 `Butter, tub` | **reordered** onto `Butter, NFS`, correct |
| `tamale` | 0.636 `Tamale, NFS` | auto, correct |

So: eleven escalations and five reorders, of which four land on a better row
than the probe reported. **An audit reading probe output alone would have filed
sixteen wrong-confident matches here and been wrong about every one.**

Three of the escalations (`cotija cheese`, `oaxaca cheese`, `bacalaitos`) are
the guard's known false-positive shape — a Foundation sample-form word (`solid`)
or a two-word Spanish dish name in the head segment. That is the safe direction
to fail in and it costs one model call.

Against that, the guards do **not** catch the `Form, food` class at all:
`chicken`, `turkey`, `avocado`, `coconut`, `ginger`, `coconut cream`,
`peanut`, `almond`, `walnut`, `salmon`, `pumpkin`, `sweet potato`,
`brown rice` and `masa harina` (state-free) all auto-match a transformation of
the food in production. Every one of those was verified, not assumed.

## Findings

Ordered by what they would cost a real day's logging.

**F1 — `Form, food` head segments auto-match with no guard able to see them.**
`chicken -> Fat, chicken` (900 kcal), `turkey -> Fat, turkey` (900 vs 139),
`avocado -> Oil, avocado` (884 vs 160), `coconut -> Oil, coconut`,
`ginger -> Tea, ginger` (1 vs 80), `coconut cream -> Pie, coconut cream`,
`almond`/`peanut`/`walnut -> Oil, *`. Verified through the guards; §B4-1, §B5-1,
§B5-2. Fixable as a fifth guard or as an extension of `unrequested_qualifier`
over a closed set of form words; no knowledge layer required.

**F2 — adding a true qualifying word removes the row from the result set.**
`mole negro`, `mole poblano`, `mole verde`, `mole amarillo`, `mole coloradito`,
`ancho chile`, `pasilla chile`, `poblano chile`, `guajillo chile`,
`morita chile` and `chile de arbol` all return **nothing** while their head word
returns the right row. `pozole rojo/verde/blanco` and `serrano chile` fall from
`ask` to `weak` the same way. §B1-1, §B2-3.

**F3 — the chile vocabulary is the domain's largest reachability gap.** USDA
never writes the word *chile*; only ancho, pasilla, serrano and jalapeño have
rows at all, and the word every cook uses is the one that breaks retrieval.
Guajillo, mulato, morita, árbol, piquín, cascabel, habanero, New Mexico and
Hatch have no row anywhere. §B2-3.

**F4 — `masa harina` takes the cooked row, 97 kcal against 376.** A 3.9x
understatement on a flour, and it is an auto-match whenever `state` is absent;
`state=dry` blocks it. §B2-6.

**F5 — Haiti and Guatemala are entirely absent.** Fifteen for fifteen no-rows
across `griot`, `griyo`, `pikliz`, `soup joumou`, `diri ak pwa`, `legume`,
`tasso`, `accra`, `pepián`, `jocón`, `kak ik`, `chuchito`, `tamal
guatemalteco`, `plato típico`, `curtido`. §B3-4.

**F6 — the dish/ingredient split, eleven instances.** `mofongo` returns nothing
while `green plantain` auto-matches correctly; `ackee and saltfish` and both its
halves fail; `pupusa` resolves and `curtido` does not. §B3-5.

**F7 — salt cod is the costliest unreachable row.** 7,027 mg sodium per 100 g,
and the Caribbean word `saltfish` reaches `Fish sauce`. §B3-6.

**F8 — `sope` is invisible because of a slash.** `Gordita/sope shell` contains
the word; neither tsvector nor pg_trgm treats `/` as a boundary. §B1-3.

**F9 — Spanish head-noun-first word order costs the Mexican cheeses.**
`queso oaxaca` 0.300 vs `oaxaca cheese` 0.700, against a full Foundation row.
`queso fresco` and `queso cotija` hit 1.000 only because USDA stored those two
Spanish-first. §B2-8.

**F10 — one diacritic makes a food invisible.** `jalapeño` **none**,
`jalapeno` 0.429. §B2-5.

**F11 — the length penalty puts correct rows below the floor.** `sofrito` 0.235
against `Sauce, sofrito, prepared from recipe`; `sazon` **0.146** against a row
naming it; `scallion` 0.160; `pork shoulder` 0.292 — the base of carnitas,
cochinita pibil, pernil and lechón. §B3-9, §B4-3.

**F12 — `menudo` returns nothing while `Restaurant, Latino, tripe soup` sits at
0.379 behind an English paraphrase.** §B1-4.

## Deliberately rejected

Mappings that look obvious, are wrong, and must not be encoded.

- **`poblano` → `Peppers, ancho, dried`.** A poblano dried *is* an ancho, so
  the synonym is botanically exact and nutritionally a **14x energy error**
  (~20 kcal/100 g fresh against 281 dried). USDA has no fresh poblano row. The
  correct behaviour is that `poblano` escalates. §B2-4.

- **`callaloo` → any single row.** Amaranth leaves in Jamaica, taro leaves in
  Trinidad; both rows exist, and they differ by 1.8x energy, 2x protein and 2x
  calcium. A synonym here must offer both and let a human choose. §B3-3.

- **`pimento` → `Spices, allspice, ground`.** The Jamaican reading is correct
  and the fix is not worth having: allspice is used at 1–3 g, so the 240
  kcal/100 g gap is under 8 kcal, and both candidate rows are already below the
  auto gate. Recording the collision is more useful than encoding it. §B3-7.

- **A single "Mexican fresh cheese" fallback for panela / oaxaca / cotija /
  asadero.** Sodium runs 185 → 626 → 734 → 1625 mg per 100 g across the family.
  Four foods, not one. §B2-8.

- **`culantro` → `Cilantro, raw`.** Defensible as flavour and as mass (both are
  herbs used in grams), and different plants. Left as an escalation because the
  score already denies it and nothing is lost by asking.

- **`guanabana` → `Guanabana nectar, canned`** is what happens today at 0.391;
  the right target is `Soursop, raw`, which `soursop` already auto-matches. This
  is a **spelling** synonym, not a taxonomy one, and is the safest proposal in
  the file — but it is still a proposal, not a finding, and is not encoded here.

- **Any neighbour for `barbacoa`, `birria`, `al pastor`, `machaca`, `tinga`,
  `cochinita pibil`, `mofongo`, `sancocho`, `ropa vieja`, `griot`.** No row in
  the table contains any of these words and none has a fallback whose numbers I
  can defend. `beef barbacoa -> Beef, bacon, cooked` and
  `al pastor -> Almond paste` are what the ranking offers, and both are noise.
  The honest treatment is the model tier with a parent category, which is what
  happens today.

## Notes

- Everything here is `SELECT`-only. No row was written; `probe_knowledge.py`
  does not consult `food_alias` by design, so nothing measured is a cache.
- `scripts/probe_knowledge.py` reports the **head** of `db.search_foods`. Where
  a verdict mattered I re-ran the term through a scratchpad script mirroring the
  `auto = next(...)` selector in `nutrai/llm/parse.py` — same four guards, same
  order, `asked_for` set to the label alone. Using the label alone is the
  conservative reading: the model's `search_terms` can only add words to the
  query, and every guard here turns on words the query lacks, so including them
  could only make more candidates survive, never fewer.
- The `state` argument was exercised where a state is plausible (`masa harina`
  with `state=dry`). Elsewhere it is `None`, which is what the resolver sees
  when the parse leaves `state` unset or `unknown` — `_STATE_EXCLUDES` has no
  entry for either, so the guard is inert in exactly that case.
- The `Form, food` scan (`formscan.py`) restricted tails to three words or fewer
  with no internal comma, which is why it reports 108 candidates out of a much
  larger set of `Head, tail` rows. It under-counts.
