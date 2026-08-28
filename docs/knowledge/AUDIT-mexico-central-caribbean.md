# AUDIT-mexico-central-caribbean

28 Aug 2026. Mexican (Oaxacan, Yucatecan, Poblano, Norteño), Guatemalan,
Salvadoran, Honduran, Costa Rican, Cuban, Puerto Rican, Dominican, Jamaican,
Trinidadian, Haitian. Probed with `scripts/probe_knowledge.py` against the live
`food` table. Read-only throughout; every line quoted is verbatim probe output.

## Verdict counts

(running tally — updated after each batch)

| batch | terms | none | weak | ask | auto |
|---|---|---|---|---|---|
| 1 Mexican dishes | 77 | 33 | 17 | 10 | 17 |
| 2 Mexican ingredients | 84 | 24 | 30 | 10 | 20 |
| 3 Central American + Caribbean | 84 | 35 | 31 | 15 | 6 |
| 4 English paraphrases + ingredients | 82 | 6 | 27 | 28 | 21 |
| 5 bare ingredient nouns | 82 | 2 | 19 | 30 | 31 |
| 6 proposal-target verification | 28 | 0 | 3 | 3 | 22 |
| **total** | **437** | **100** | **127** | **96** | **117** |

## Findings

### B1-1 `menudo` — REACHABILITY GAP (missing_synonym)

```
none  menudo                             -      (nothing)
weak  tripe soup                         0.379  Restaurant, Latino, tripe soup
```

USDA has the dish under an English gloss:

```
  168069 | sr_legacy_food    | Restaurant, Latino, tripe soup
 2706725 | survey_fndds_food | Stewed tripe, with potatoes, Puerto Rican style
  174769 | sr_legacy_food    | Beef, variety meats and by-products, tripe, cooked, simmered
```

The single word every Mexican speaker uses returns an empty list; the row that
*is* the dish sits at 0.379 behind an English paraphrase nobody types. Nothing
in the ranking can help — recall is 0 for the actual query.

### B1-2 `sope` / `sopes` — REACHABILITY GAP (bad_normalization)

```
none  sope                               -      (nothing)
none  sopes                              -      (nothing)
ask   gordita                            0.615  Gordita, meat
```

USDA literally contains the word:

```
 2707818 | survey_fndds_food | Gordita/sope shell, plain, no filling
```

`gordita` reaches its own row at 0.615 and `sope` — spelled identically inside
the same description — reaches nothing, because the slash in `Gordita/sope` is
not a token boundary for either trigram or tsvector. This is the purest
normalisation defect in the batch: same row, same word, one punctuation mark.

### B1-3 `mole negro` / `poblano` / `verde` / `amarillo` — REACHABILITY GAP (bad_fuzzy_matching)

```
ask   mole                               0.455  Mole sauce
none  mole negro                         -      (nothing)
none  mole poblano                       -      (nothing)
none  mole verde                         -      (nothing)
none  mole amarillo                      -      (nothing)
none  mole coloradito                    -      (nothing)
auto  chicken in mole sauce              0.704  Chicken with mole sauce
```

`Mole sauce` (2707151) and `Chicken with mole sauce` (2706439) exist. The bare
head word reaches them; **naming the variety makes the food unreachable**, which
is §1 of RECONCILED.md running backwards — a person who knows the cuisine types
the more precise term and gets less. All seven moles are one sauce family
nutritionally distinguishable mostly by chocolate and nut content, and USDA has
one row for all of them, so the right behaviour is that every variety reaches
`Mole sauce`.

### B1-4 `pozole rojo/verde/blanco` — same shape

```
ask   pozole                             0.583  Soup, pozole
weak  pozole rojo                        0.412  Soup, pozole
weak  pozole verde                       0.389  Soup, pozole
weak  pozole blanco                      0.368  Soup, pozole
```

The right row is found every time and the score *falls* monotonically as the
user adds the colour. `pozole` alone escalates (correct); the three named
varieties drop below the weak floor and the model tier stops being offered the
row it should get. Adding one true word costs 0.17-0.21 of similarity.

### B1-5 `chile relleno` singular — REACHABILITY GAP (bad_normalization)

```
weak  chile relleno                      0.414  Chiles rellenos, cheese-filled
```

```
 2710043 | survey_fndds_food | Chiles rellenos, cheese-filled
 2710044 | survey_fndds_food | Chiles rellenos, filled with meat and cheese
```

Spanish agreement: one is `chile relleno`, two are `chiles rellenos`. USDA
stores only the plural. A person logging one stuffed pepper — the normal case —
falls under the weak floor against the exact row.

### B1-6 `flauta` -> `Flan` — WEAK, but the shape is a warning (bad_fuzzy_matching)

```
weak  flauta                             0.333  Flan
auto  taquito                            0.667  Taquito, egg
```

Flautas and taquitos are the same food (rolled fried filled tortilla; flauta is
the flour/longer one). USDA has four `Taquito, *` rows plus two frozen SR rows.
`flauta` reaches a custard dessert instead. It stays below the auto gate so it
escalates rather than caching — the guards holding — but recall for the correct
row is 0.

### B1-7 Absent entities with no near neighbour at all

Searched by name, by ingredient and by category (`~* 'barbacoa|birria|pastor|
machaca|pibil|tinga|carne asada|elote|esquite|shredded beef|beef, .*stew|goat'`)
— see the neighbour dump in Notes. `barbacoa`, `birria`, `carnitas`-adjacent
`al pastor`, `machaca`, `cochinita pibil`, `tinga`, `carne asada`, `elote`,
`esquites`, `tlayuda`, `huarache`, `aguachile`, `torta ahogada`, `cemita`,
`molletes`, `migas`, `champurrado`, `tejate`, `agua de jamaica` return nothing.
Of these only a few have a defensible neighbour (below); the rest are genuine
entity gaps whose only honest treatment is a parent category.

Notably `carnitas` **does** have its own row and auto-matches correctly:

```
auto  carnitas                           0.643  Pork, carnitas
auto  pork carnitas                      1.000  Pork, carnitas
```

so the absence of `barbacoa` and `al pastor` beside it is a USDA coverage
accident, not a design.

### B1-8 `beef barbacoa` -> `Beef, bacon, cooked` — WRONG, though weak (bad_fuzzy_matching)

```
none  barbacoa                           -      (nothing)
weak  beef barbacoa                      0.364  Beef, bacon, cooked
```

`barbacoa` -> `bacon` is pure trigram noise across a language boundary. It sits
below the weak floor so nothing is cached, but it is the top of the list handed
to a model that is told these are candidates.

### B1-9 `al pastor` -> `Almond paste`

```
weak  al pastor                          0.353  Almond paste
none  tacos al pastor                    -      (nothing)
```

Same class. Spit-roast marinated pork against a confectionery ingredient.

### B2-1 The chile family — the flagship REACHABILITY GAP (bad_normalization)

USDA writes peppers as `Peppers, <variety>, <state>`. It never uses the word
*chile*. Adding it — the word every cook uses — does not merely lower the score,
it removes the row from the result set entirely:

```
none  ancho chile                        -      (nothing)
none  chile ancho                        -      (nothing)
ask   ancho pepper                       0.571  Peppers, ancho, dried
auto  dried ancho pepper                 0.857  Peppers, ancho, dried
weak  ancho                              0.300  Peppers, ancho, dried
```

The row is right there:

```
  169396 | sr_legacy_food    | Peppers, ancho, dried
  168579 | sr_legacy_food    | Peppers, pasilla, dried
  169395 | sr_legacy_food    | Peppers, serrano, raw
  168576 | sr_legacy_food    | Peppers, jalapeno, raw
```

**Mechanism, read off `db.search_foods`:** the WHERE clause is
`to_tsvector(desc) @@ plainto_tsquery(q) OR desc % q`. `ancho chile` fails the
tsquery because the description has no token `chile`, and the extra five
characters drop trigram similarity below pg_trgm's 0.3 `%` threshold — so the
row is not a low-ranked candidate, it is *not returned at all*. `ancho` alone
survives at exactly 0.300, on the threshold. This is a hard recall cliff, not a
ranking problem, and no ranking change of any kind can reach it.

The same word costs `pasilla` and `poblano` too:

```
weak  pasilla                            0.381  Peppers, pasilla, dried
none  pasilla chile                      -      (nothing)
none  poblano                            -      (nothing)
weak  poblano pepper                     0.350  Pepper steak
weak  dried poblano                      0.389  Pear, dried
```

### B2-2 `jalapeño` with the tilde returns nothing (spelling_transliteration_failure)

```
weak  jalapeno                           0.429  Peppers, jalapeno, raw
none  jalapeño                           -      (nothing)
```

`Peppers, jalapeno, raw` and `Peppers, jalapenos` both exist. One diacritic —
the *correct* spelling, and the one an iOS keyboard produces from autocorrect —
takes the food from findable to invisible. Same shape will apply to `piña`,
`plátano`, `jamón`.

### B2-3 Fresh/dried pairs are NOT distinguished — the pair does not exist

Tested explicitly per the brief. USDA has `Peppers, ancho, dried` and no fresh
poblano row at all; `poblano` returns nothing and `dried poblano` returns
`Pear, dried`. So the fresh/dried distinction that matters most in this cuisine
(poblano fresh, 20 kcal/100 g water-heavy vegetable, vs ancho dried, **281
kcal/100 g**, a 14x energy difference) is not merely unmodelled — the fresh half
has no row. Any mapping of `poblano` onto `Peppers, ancho, dried` would be a
14x energy error. This is the clearest case in my domain for refusing to encode
a plausible-looking synonym.

```
  169396 | Peppers, ancho, dried         | 281 kcal | 8.2 g fat
  170106 | Peppers, hot chili, red, raw  |  40 kcal | 0.44 g fat
```

### B2-4 `panela cheese` -> `Cheese, paneer` — top candidate is wrong; the guards catch it (culturally_incorrect_mapping)

```
auto  panela cheese                      0.647  Cheese, paneer
weak  queso panela                       0.300  Queso Fresco
```

USDA has **no** panela row (searched `~* 'panela|queso'`; the Mexican cheeses it
carries are queso fresco, cotija, asadero, chihuahua, anejo, blanco, seco,
oaxaca). The probe reports `auto`, which would be the worst class in the brief —
so I ran it through the real guards rather than assuming:

```
panela cheese -> Cheese, paneer   state=None label_absent=False qual=paneer
```

`unrequested_qualifier` blocks it and the item **escalates to the model tier**.
That is the guard wave working, measured not assumed. What remains is still bad,
because the escalated candidate list is headed by the wrong cheese:

```
 2705740 | Cheese, paneer                | 299 kcal | 15.52 g fat | 15.86 prot |  185 mg Na
 2705745 | Queso Fresco                  | 298 kcal | 23.36 g fat | 18.88 prot |  626 mg Na
  172223 | Cheese, fresh, queso fresco   | 299 kcal | 23.82 g fat | 18.09 prot |  751 mg Na
```

Paneer is unsalted and lower-fat; queso panela is a salted pressed fresh cow's
cheese and belongs with the queso fresco rows — ~8 g fat and ~450 mg sodium per
100 g apart. Note the perversity: the *Spanish* phrasing `queso panela` lands
weakly on the right family; the anglicised one heads its list with the wrong
continent.

### B2-5 `queso oaxaca` -> nothing useful while `oaxaca cheese` auto-matches (bad_normalization)

```
weak  queso oaxaca                       0.300  Queso Fresco
auto  oaxaca cheese                      0.700  Cheese, oaxaca, solid
```

`Cheese, oaxaca, solid` (2647441) is a Foundation row with a full profile. The
Spanish head-noun-first word order — how it is written on the packet and on
every menu — reaches a *different cheese* instead. Compare `queso fresco` and
`queso cotija`, which both auto-match at 1.000 because USDA happens to store
them Spanish-first. So the same user, typing the same construction, gets a
perfect match for two cheeses and a wrong one for the third, for no reason
visible to them.

### B2-6 `pepita` — the parenthesis costs 0.42 (bad_normalization)

```
weak  pepita                             0.231  Seeds, pumpkin seeds (pepitas), raw
auto  pumpkin seed                       0.650  Pumpkin seeds, salted
```

The word `pepitas` is inside the description, in brackets. It scores 0.231 —
below the weak floor — against the row that contains it.

### B2-7 Absent entities, neighbours searched

`~* 'chile|pepper.*(...)|panela|oaxaca|queso|annatto|achiote|sour cream|crema|
epazote|smut'` returns no row for: guajillo, mulato, morita, arbol, piquin,
cascabel, habanero, New Mexico chile, huitlacoche, achiote/annatto (as a food —
only `Seasoning mix, dry, sazon, coriander & annatto`), crema mexicana,
requeson, piloncillo, canela, hoja santa.

Of these:
- **habanero, guajillo, arbol, piquin, cascabel, morita** have a defensible
  neighbour in `Peppers, hot chili, red, raw` (fresh) / `Peppers, hot chile,
  sun-dried` (dried) — but the fresh/dried split is nutritionally the whole
  question (§B2-3) and a single mapping cannot serve both.
- **crema mexicana** has a good one: `Sour cream, regular` (2705614). Crema is
  a thinner, slightly less sour cultured cream; sour cream is the standard
  substitution in every recipe that crosses the border.
- **huitlacoche, hoja santa, epazote-adjacent aromatics, piloncillo, canela**
  are genuine entity gaps. `epazote` is the exception and resolves correctly:
  `auto epazote 0.667 Epazote, raw`.
- **achiote/annatto** is used in gram quantities as a colourant; its calorie
  contribution is nil and its absence is not a nutritional defect.

### B2-8 `masa harina` vs cornmeal — the nixtamalisation test

```
auto  masa harina                        0.632  Masa harina, cooked
weak  masa                               0.263  Masa harina, cooked
none  nixtamalized corn                  -      (nothing)
weak  cornmeal                           0.429  Cornmeal, blue (Navajo)
weak  corn flour                         0.407  Corn flour, whole-grain, white
```

USDA does distinguish them — `Corn flour, masa harina, white or yellow, dry,
raw` (Foundation, 2710835), three SR `Corn flour, *, masa` rows, and plain
`Corn flour, whole-grain, white`. So the calcium difference nixtamalisation
creates is representable. The defect is only that the bare word `masa` — what
anyone making tortillas says — scores 0.263 against its own row, and
`cornmeal` lands on a Navajo blue cornmeal rather than the plain row.


## Deliberately rejected

## Notes
