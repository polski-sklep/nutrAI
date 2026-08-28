# AUDIT-south-america

28 Aug 2026. Brazilian, Peruvian, Argentinian, Chilean, Colombian, Venezuelan,
Bolivian, Ecuadorian, Uruguayan, Paraguayan. Probed with
`scripts/probe_knowledge.py` against the live `food` table (13,651 rows:
7,793 sr_legacy, 5,432 fndds, 411 foundation, 15 user_product). Read-only
throughout; every line quoted is verbatim probe output.

Method: for every dish, its defining ingredients are probed separately. A dish
that resolves while its signature ingredient returns nothing is the
carbonara/guanciale failure this audit exists to find.

## Verdict counts

(running tally — updated after each batch)

| batch | terms | none | weak | ask | auto |
|---|---|---|---|---|---|
| 1 Brazilian dishes + ingredients | 82 | 68 | 13 | 0 | 1 |
| 2 Peruvian dishes + ingredients | 81 | 57 | 16 | 6 | 2 |
| 3 Argentina/Uruguay/Chile/Paraguay | 83 | 63 | 15 | 3 | 2 |
| 4 Colombia/Venezuela/Bolivia/Ecuador | 81 | 67 | 13 | 0 | 1 |
| 5 proposal-target + ingredient verification (English) | 86 | 1 | 17 | 23 | 45 |
| 6 diacritics, orthography, fruits, fish | 61 | 37 | 15 | 3 | 6 |
| **total** | **474** | **293** | **89** | **35** | **57** |
| *native vocabulary only (1,2,3,4,6)* | *388* | *292* | *72* | *12* | *12* |

Batch 5 was deliberately English-language target verification, so it inverts the
distribution and must be read separately. Across the five native-vocabulary
batches, **75% of terms return an empty candidate list** and only 3% reach the
`auto` band.

## Layout

Findings are recorded batch by batch below (SA-1 .. SA-53), each with its
verbatim probe output and the neighbour search behind it. The consolidated
`Proposals`, `Deliberately rejected` and `Notes` sections are at the end of the
file.

---

# Batch 1 — Brazilian dishes and ingredients (82 terms)

Verdicts: `auto=1 (1%)  none=68 (83%)  weak=13 (16%)  ask=0`

83% of a Brazilian vocabulary returns an empty candidate list. Not one Brazilian
term reached the `ask` band; the single `auto` was the English words "palm oil".
Verbatim:

```
weak  feijoada                           0.429  Feijoa, raw
none  feijoada completa                  -      (nothing)
none  moqueca                            -      (nothing)
none  moqueca baiana                     -      (nothing)
none  moqueca capixaba                   -      (nothing)
none  acaraje                            -      (nothing)
none  vatapa                             -      (nothing)
none  caruru                             -      (nothing)
none  bobo de camarao                    -      (nothing)
none  coxinha                            -      (nothing)
none  pao de queijo                      -      (nothing)
none  brigadeiro                         -      (nothing)
none  beijinho                           -      (nothing)
none  farofa                             -      (nothing)
none  farinha de mandioca                -      (nothing)
weak  tapioca                            0.444  Tapioca, pearl, dry
weak  tapioca crepe                      0.333  Tapioca, pearl, dry
none  beiju                              -      (nothing)
weak  acai                               0.217  Fruit juice, acai blend
none  acai bowl                          -      (nothing)
none  acai pulp                          -      (nothing)
weak  acai puree                         0.375  Prune puree
weak  acai smoothie                      0.375  Fruit smoothie, NFS
none  cupuacu                            -      (nothing)
none  graviola                           -      (nothing)
none  jabuticaba                         -      (nothing)
weak  pitanga                            0.296  Pitanga, (surinam-cherry), raw
none  caju                               -      (nothing)
weak  cashew apple                       0.421  Apple, candied
none  dende                              -      (nothing)
weak  dende oil                          0.308  Oil, oat
auto  palm oil                           1.000  Oil, palm
none  carne seca                         -      (nothing)
none  carne de sol                       -      (nothing)
none  charque                            -      (nothing)
none  linguica                           -      (nothing)
none  linguica calabresa                 -      (nothing)
none  picanha                            -      (nothing)
none  fraldinha                          -      (nothing)
none  maminha                            -      (nothing)
none  alcatra                            -      (nothing)
weak  churrasco                          0.385  Churros
none  feijao tropeiro                    -      (nothing)
none  tutu de feijao                     -      (nothing)
none  virado a paulista                  -      (nothing)
none  escondidinho                       -      (nothing)
none  baiao de dois                      -      (nothing)
none  arroz carreteiro                   -      (nothing)
none  pamonha                            -      (nothing)
none  curau                              -      (nothing)
none  canjica                            -      (nothing)
none  mungunza                           -      (nothing)
none  paçoca                             -      (nothing)
none  pacoca                             -      (nothing)
none  quindim                            -      (nothing)
none  brigadeiro de colher               -      (nothing)
none  romeu e julieta                    -      (nothing)
none  goiabada                           -      (nothing)
none  doce de leite                      -      (nothing)
none  requeijao                          -      (nothing)
none  catupiry                           -      (nothing)
none  queijo minas                       -      (nothing)
none  queijo coalho                      -      (nothing)
weak  pastel                             0.273  Puerto Rican pasteles
none  pastel de feira                    -      (nothing)
weak  empada                             0.429  Empanada, NFS
none  esfiha                             -      (nothing)
none  kibe                               -      (nothing)
none  misto quente                       -      (nothing)
none  bauru                              -      (nothing)
none  x-tudo                             -      (nothing)
none  pao frances                        -      (nothing)
none  pao de forma                       -      (nothing)
none  cuscuz paulista                    -      (nothing)
none  cuscuz nordestino                  -      (nothing)
none  tacaca                             -      (nothing)
weak  jambu                              0.429  Jam
none  tucupi                             -      (nothing)
none  maniçoba                           -      (nothing)
none  manicoba                           -      (nothing)
none  pirarucu                           -      (nothing)
none  tambaqui                           -      (nothing)
```

## Findings — batch 1

### SA-1 `picanha` — REACHABILITY GAP (missing_synonym) — **high**

```
none  picanha                            -      (nothing)
```

Picanha *is* the top sirloin cap (rump cap, coulotte). USDA holds it under that
exact anatomical name, raw and grilled, all three grades:

```
 173061 | sr_legacy_food | Beef, loin, top sirloin cap steak, boneless, separable lean and fat, trimmed to 1/8" fat, all grades, cooked, grilled
 174706 | sr_legacy_food | Beef, loin, top sirloin cap steak, boneless, separable lean and fat, trimmed to 1/8" fat, all grades, raw
 172170 | sr_legacy_food | Beef, loin, top sirloin cap steak, boneless, separable lean only, trimmed to 1/8" fat, all grades, cooked, grilled
 171739 | sr_legacy_food | Beef, Australian, imported, grass-fed, loin, top sirloin cap-off steak/roast, boneless, separable lean and fat, raw
```

Not a near neighbour — the identical cut, fat cap on, which is the whole point
of picanha. Zero recall on the most-typed South American beef word there is.

Note `171739` is *cap-**off***, the complement of picanha; a naive substring rule
on "sirloin cap" lands on it. The target must be pinned by fdc_id, not a string.

### SA-2 `dende` / `dende oil` — REACHABILITY GAP (missing_synonym) — **high**

```
none  dende                              -      (nothing)
weak  dende oil                          0.308  Oil, oat
auto  palm oil                           1.000  Oil, palm
```

Dendê *is* palm oil — the same commodity, `Oil, palm` (171015), which the
English phrase auto-matches at 1.000. The Portuguese word reaches nothing and
the two-word form lands on **oat oil**, an unsaturated seed oil, standing in for
a fat that is ~49% saturated. Moqueca baiana, vatapá, acarajé and caruru are all
*defined* by dendê and every one is a `none` above — dish unreachable, signature
fat resolving to the wrong lipid profile. The carbonara/guanciale shape exactly.

### SA-3 `acai` — ENTITY GAP for the pulp, BAD FALLBACK for the bowl — **high as a gap; no mapping proposed**

```
weak  acai                               0.217  Fruit juice, acai blend
none  acai bowl                          -      (nothing)
none  acai pulp                          -      (nothing)
weak  acai puree                         0.375  Prune puree
weak  acai smoothie                      0.375  Fruit smoothie, NFS
```

Full candidate list for `acai` — the database holds **three** açaí rows and all
three are sweetened beverages:

```
    0.217 Fruit juice, acai blend
    0.143 Beverages, Acai berry drink, fortified
    0.139 Beverages, V8 V- FUSION Juices, Acai Berry
```

Neighbour search by ingredient and category confirms no pulp row exists:

```
select fdc_id, data_type, description from food where description ~* '(acai|açaí)'
  173175 | sr_legacy_food    | Beverages, Acai berry drink, fortified
  174170 | sr_legacy_food    | Beverages, V8 V- FUSION Juices, Acai Berry
 2710777 | survey_fndds_food | Fruit juice, acai blend
```

The brief asked whether the sweetened commercial product differs hugely from
pure pulp. Measured answer: USDA has **only** the commercial product. Unsweetened
açaí pulp is a high-fat fruit (~5 g fat/100 g, near-zero sugar); a juice blend is
near-zero fat and mostly added sugar. Opposite foods.

`acai puree -> Prune puree` at 0.375 is the worst line in the batch: a
purple-fruit purée that is ~38 g sugar and 0 g fat per 100 g standing in for one
that is the reverse.

**Deliberately not proposing a fallback** — see Deliberately rejected.

### SA-4 `farinha de mandioca` / `farofa` — REACHABILITY GAP (missing_synonym) — **high**

```
none  farofa                             -      (nothing)
none  farinha de mandioca                -      (nothing)
```

USDA has the flour as a Foundation row, and cassava in several states:

```
 2512377 | foundation_food   | Flour, cassava
 2709564 | survey_fndds_food | Cassava, cooked
  169985 | sr_legacy_food    | Cassava, raw
 2709566 | survey_fndds_food | Casabe, cassava bread
 2709565 | survey_fndds_food | Yuca fries
  173152 | sr_legacy_food    | Snacks, yucca (cassava) chips, salted
```

`Flour, cassava` is exactly farinha de mandioca. Farofa is that flour toasted in
fat, so the flour is its parent ingredient rather than its equal — dish_ingredient,
not synonym.

### SA-5 `goiabada` — REACHABILITY GAP (missing_synonym) — **high**

```
none  goiabada                           -      (nothing)
```
```
 2710307 | survey_fndds_food | Guava paste
```

Goiabada *is* guava paste — same sugar-set fruit block, sold under both names.
Also the missing half of `romeu e julieta` (none), which is goiabada plus cheese.

### SA-6 `doce de leite` — SPELLING/TRANSLITERATION FAILURE — **high**

```
none  doce de leite                      -      (nothing)
```

USDA has it **twice**, under the Spanish spelling:

```
  173461 | sr_legacy_food    | Dulce de Leche
 2705699 | survey_fndds_food | Dulce de leche
```

Identical food; two letters apart; reaches nothing. No ranking function can
bridge `doce`→`dulce` because whole-phrase trigram overlap stays under the floor.

### SA-7 `feijoada` -> `Feijoa, raw` — BAD FUZZY MATCHING — **high as a finding**

```
weak  feijoada                           0.429  Feijoa, raw
```

Feijoa is a fruit (pineapple guava); feijoada is a black bean and salt-pork stew.
The similarity is pure orthography — `feijoa` is a prefix of `feijoada`. At 0.429
it is below the 0.62 gate so it escalates rather than caching; that is the system
working. Recorded because it shows what a slightly looser gate would produce, and
because feijoada is a dish that must decompose to ingredients, never map to a fruit.

### SA-8 `churrasco` -> `Churros` — BAD FUZZY MATCHING — **medium**

```
weak  churrasco                          0.385  Churros
```

Grilled beef against fried sugared dough. Below the gate, escalates. Churrasco is
a cooking method over beef cuts (SA-1), not a food entity.

### SA-9 `linguica` — ENTITY GAP, fallback available — **medium**

```
none  linguica                           -      (nothing)
none  linguica calabresa                 -      (nothing)
```

Neighbour search across the whole sausage category:

```
 2706179 | survey_fndds_food | Chorizo
  332864 | foundation_food   | Sausage, pork, chorizo, link or ground, cooked, pan-fried
  173859 | sr_legacy_food    | Sausage, pork, chorizo, link or ground, raw
  174584 | sr_legacy_food    | Sausage, smoked link sausage, pork
  174585 | sr_legacy_food    | Sausage, smoked link sausage, pork and beef
  174577 | sr_legacy_food    | Polish sausage, pork
  173877 | sr_legacy_food    | Kielbasa, fully cooked, grilled
  171618 | sr_legacy_food    | Blood sausage
```

USDA has no linguiça row and no Portuguese sausage row at all. `Sausage, smoked
link sausage, pork` (174584) is the honest fallback for linguiça calabresa —
coarse smoked pork link, same fat class. **Medium, not high**: linguiça is
garlic-and-paprika cured pork, calabresa is smoked, and they differ in moisture.
Deliberately *not* mapped to chorizo — see Deliberately rejected.

### SA-10 `carne seca` / `charque` — ENTITY GAP, fallback available — **medium**

```
none  carne seca                         -      (nothing)
none  carne de sol                       -      (nothing)
none  charque                            -      (nothing)
```
```
 2705858 | survey_fndds_food | Beef, dried, chipped, uncooked
 2705859 | survey_fndds_food | Beef, dried, chipped, cooked in fat
 2705860 | survey_fndds_food | Beef jerky
  170199 | sr_legacy_food    | Beef, cured, corned beef, brisket, raw
```

`Beef, dried, chipped, uncooked` is salt-cured air-dried beef — the same process.
**Medium**: charque is rehydrated and desalted before eating, so as-eaten sodium
is far below the dry row's and the stated mass is the rehydrated mass. Fallback
only, never an auto-match.

### SA-11 dish-level entity gaps — filed, not mapped

`pao de queijo`, `coxinha`, `brigadeiro`, `moqueca`, `vatapa`, `acaraje`,
`tacaca`, `quindim`, `escondidinho`, `baiao de dois` — all `none`. Nearest
composites in the database are `Chicken or turkey cake, patty, or croquette`
(2706545) and `Ham croquette` (2706508). These are dishes, not entities; correct
treatment is ingredient decomposition at the model tier, which is unreachable
today only because the *ingredients* are unreachable. Fixing SA-2, SA-4 and the
cheeses fixes these without one dish mapping.

### SA-12 `queijo minas`, `queijo coalho`, `requeijao`, `catupiry` — cheese gaps — **filed; low on any mapping**

All four `none`. Every candidate mapping deliberately rejected — fat runs 3% to
28% across them; see Deliberately rejected.

---

# Batch 2 — Peruvian dishes and ingredients (81 terms)

Verdicts: `ask=6 (7%)  auto=2 (2%)  none=57 (70%)  weak=16 (20%)`

```
auto  ceviche                            1.000  Ceviche
ask   cebiche                            0.455  Ceviche
weak  ceviche de pescado                 0.421  Ceviche
ask   leche de tigre                     0.450  Dulce de Leche
weak  lomo saltado                       0.316  Lomi salmon
none  aji de gallina                     -      (nothing)
none  causa                              -      (nothing)
none  causa limena                       -      (nothing)
none  anticuchos                         -      (nothing)
none  anticucho de corazon               -      (nothing)
none  rocoto relleno                     -      (nothing)
none  papa a la huancaina                -      (nothing)
weak  huancaina sauce                    0.318  Hoisin sauce
none  tacu tacu                          -      (nothing)
none  arroz con pollo peruano            -      (nothing)
none  seco de res                        -      (nothing)
none  carapulcra                         -      (nothing)
none  olluquito                          -      (nothing)
none  chupe de camarones                 -      (nothing)
none  aguadito                           -      (nothing)
none  pollo a la brasa                   -      (nothing)
none  salchipapa                         -      (nothing)
none  papa rellena                       -      (nothing)
weak  tamal peruano                      0.300  Tamale, pork
none  juane                              -      (nothing)
none  pachamanca                         -      (nothing)
none  arroz chaufa                       -      (nothing)
none  tallarin saltado                   -      (nothing)
none  aji amarillo                       -      (nothing)
none  aji panca                          -      (nothing)
none  aji rocoto                         -      (nothing)
none  rocoto                             -      (nothing)
none  aji limo                           -      (nothing)
none  huacatay                           -      (nothing)
none  chicha morada                      -      (nothing)
none  chicha de jora                     -      (nothing)
none  lucuma                             -      (nothing)
none  maca                               -      (nothing)
weak  maca powder                        0.368  Baobab powder
none  kiwicha                            -      (nothing)
ask   amaranth                           0.600  Flour, amaranth
ask   quinoa                             0.538  Flour, quinoa
ask   red quinoa                         0.471  Quinoa, cooked
weak  black quinoa                       0.368  Flour, quinoa
weak  white quinoa                       0.368  Flour, quinoa
none  canihua                            -      (nothing)
weak  purple corn                        0.318  Cereal, corn puffs
none  choclo                             -      (nothing)
weak  corn on the cob                    0.192  Corn, sweet, white, frozen, kernels on cob, unprepared
none  cancha                             -      (nothing)
weak  maiz morado                        0.224  Corn flour, whole-grain, blue (harina de maiz morado)
none  camote                             -      (nothing)
none  olluco                             -      (nothing)
none  oca                                -      (nothing)
none  mashua                             -      (nothing)
none  yacon                              -      (nothing)
none  tarwi                              -      (nothing)
weak  chirimoya                          0.412  Cherimoya, raw
auto  cherimoya                          0.714  Cherimoya, raw
weak  granadilla                         0.314  Passion-fruit, (granadilla), purple, raw
none  aguaymanto                         -      (nothing)
weak  golden berry                       0.353  Pie, berry
weak  tuna fruit                         0.444  Turnover, fruit
ask   prickly pear                       0.611  Prickly pears, raw
none  sacha inchi                        -      (nothing)
none  paiche                             -      (nothing)
none  corvina                            -      (nothing)
none  cuy                                -      (nothing)
none  guinea pig                         -      (nothing)
weak  alpaca meat                        0.312  Meat, NFS
weak  llama meat                         0.333  Meat, NFS
none  inca kola                          -      (nothing)
none  pisco                              -      (nothing)
none  pisco sour                         -      (nothing)
none  algarrobina                        -      (nothing)
none  manjar blanco                      -      (nothing)
none  picarones                          -      (nothing)
none  suspiro limeno                     -      (nothing)
none  mazamorra morada                   -      (nothing)
none  turron de dona pepa                -      (nothing)
none  alfajor peruano                    -      (nothing)
```

## Findings — batch 2

### SA-13 `chirimoya` vs `cherimoya` — SPELLING FAILURE, one row, two verdicts — **high**

```
weak  chirimoya                          0.412  Cherimoya, raw
auto  cherimoya                          0.714  Cherimoya, raw
```

The cleanest demonstration in the whole audit that orthography alone decides
reachability. **Same row, same fdc_id**, one letter apart. The English
transliteration auto-matches at 0.714 with no model consulted; the Spanish
spelling every South American writes falls to 0.412 — below the weak floor,
i.e. "the right answer was probably never on the list", when it is literally at
the top of the list. Nothing about the food changed; only the vowel did.

### SA-14 `aguaymanto` / `golden berry` — REACHABILITY GAP (missing_synonym) — **high**

```
none  aguaymanto                         -      (nothing)
weak  golden berry                       0.353  Pie, berry
```

USDA has the fruit, under two *other* English common names:

```
  173043 | sr_legacy_food | Groundcherries, (cape-gooseberries or poha), raw
```

Physalis peruviana. Aguaymanto (Peru), uchuva (Colombia), golden berry, cape
gooseberry and groundcherry are all the same species; USDA carries three of the
five names in one description and neither of the two a South American would
type. `golden berry -> Pie, berry` is the pathological line — a fruit becoming a
pastry because "berry" is the only token that survives.

### SA-15 `kiwicha` — REACHABILITY GAP (missing_synonym) — **high**

```
none  kiwicha                            -      (nothing)
ask   amaranth                           0.600  Flour, amaranth
```

```
  170683 | sr_legacy_food  | Amaranth grain, cooked
  170682 | sr_legacy_food  | Amaranth grain, uncooked
 2512371 | foundation_food | Flour, amaranth
  168385 | sr_legacy_food  | Amaranth leaves, raw
```

Kiwicha *is* amaranth grain — the Quechua name, and the one printed on the bag
in Peru. Zero recall. Note the target must be the **grain**, not `Flour,
amaranth` and emphatically not `Amaranth leaves, raw` (a green vegetable, 23
kcal against 371) — three unrelated foods share the word.

### SA-16 `camote` — REACHABILITY GAP (missing_synonym) — **high**

```
none  camote                             -      (nothing)
```

USDA holds ~35 sweet potato rows including a full cooked-state family:

```
 2709697 | survey_fndds_food | Sweet potato, NFS
 2709699 | survey_fndds_food | Sweet potato, baked, no added fat
 2709702 | survey_fndds_food | Sweet potato, boiled, no added fat
```

Camote is the standard word for sweet potato across Peru, Ecuador and Mexico.
Nothing reachable.

### SA-17 `maiz morado` — REACHABILITY GAP, length dilution — **high as a finding, medium as a mapping**

```
weak  maiz morado                        0.224  Corn flour, whole-grain, blue (harina de maiz morado)
weak  purple corn                        0.318  Cereal, corn puffs
```

The row's description **contains the query verbatim** — `harina de maiz morado`
— and the query scores 0.224 against it, below the weak floor. This is the
length-dilution effect RESUME.md measured (r = −0.87 to −0.94 of similarity
against description length) in its purest form: an exact substring match
discarded because the surrounding description is long.

Mapping confidence is only **medium**, and the distinction matters: 168921 is
blue corn *flour*, whereas chicha morada is brewed from whole dried purple cobs
and drunk as a sweetened infusion. Same maize, different product. Recorded as a
reachability finding about the ranking; the mapping is a fallback at best.

### SA-18 `leche de tigre` -> `Dulce de Leche` — BAD FUZZY MATCHING — **medium**

```
ask   leche de tigre                     0.450  Dulce de Leche
```

Leche de tigre is the citrus-and-fish-juice ceviche marinade — sour, salty,
about 30 kcal per 100 g. Dulce de leche is a ~315 kcal caramelised sweetened
condensed milk. They share the word "leche" and nothing else. It lands in the
`ask` band so it escalates rather than caching — the system working — but a
model handed `Dulce de Leche` as the top candidate for a savoury fish marinade
is being actively misled by its own candidate list.

### SA-19 `cebiche` / `ceviche de pescado` — length and spelling both cost the match — **high**

```
auto  ceviche                            1.000  Ceviche
ask   cebiche                            0.455  Ceviche
weak  ceviche de pescado                 0.421  Ceviche
```

Three routes to one row, 1.000 / 0.455 / 0.421. `cebiche` is the spelling the
Peruvian Academy prefers and is standard on Lima menus; it costs 0.545 of
similarity. Adding the two words a person naturally says — "de pescado" —
pushes it *below the weak floor* against a row that is a perfect subset of the
query. Both are ranking pathologies, not knowledge gaps.

### SA-20 `aji amarillo`, `aji panca`, `rocoto`, `huacatay` — ENTITY GAPS — **filed; mapping medium-to-rejected**

```
none  aji amarillo                       -      (nothing)
none  aji panca                          -      (nothing)
none  rocoto                             -      (nothing)
none  aji limo                           -      (nothing)
none  huacatay                           -      (nothing)
```

Neighbour search across the entire pepper category — USDA carries Mexican and
US chiles only, and no Peruvian ají at all:

```
  169396 | sr_legacy_food | Peppers, ancho, dried
  168570 | sr_legacy_food | Peppers, hot chile, sun-dried
  168579 | sr_legacy_food | Peppers, pasilla, dried
  169395 | sr_legacy_food | Peppers, serrano, raw
  168576 | sr_legacy_food | Peppers, jalapeno, raw
  170932 | sr_legacy_food | Spices, pepper, red or cayenne
```

`Peppers, hot chile, sun-dried` (168570) is a defensible **medium** fallback for
ají panca (a dried chile). For ají amarillo — fresh, or as the yellow paste that
is the base of ají de gallina and huancaína — `Peppers, serrano, raw` is a
fresh hot chile of similar water content: medium. Huacatay (Tagetes minuta, a
marigold herb) has no neighbour of any kind and is a true entity gap; used in
gram quantities, so the nutritional cost of leaving it unresolved is near zero
and encoding a guess would be pure fabrication.

### SA-21 `choclo` — ENTITY GAP; both obvious mappings measured and one rejected — **medium**

```
none  choclo                             -      (nothing)
weak  corn on the cob                    0.192  Corn, sweet, white, frozen, kernels on cob, unprepared
```

The brief asked to test choclo against sweet corn. Measured, per 100 g:

```
 Corn, sweet, yellow, cooked, boiled, drained, without salt | Protein       | 3.41 G
                                                            | Total Sugars  | 4.54 G
                                                            | Energy        |   96 KCAL
                                                            | Calcium, Ca   |    3 MG
 Hominy, cooked                                             | Protein       | 1.45 G
                                                            | Sugars, Total | 1.47 G
                                                            | Energy        |   88 KCAL
                                                            | Calcium, Ca   |   10 MG
```

Choclo is a large-kernel starchy maize: protein comparable to sweet corn, sugar
much lower. **Sweet corn is the better fallback (medium)** — protein right,
sugar overstated by roughly 3 g/100 g. **Hominy is rejected**: nixtamalisation
more than halves the protein (1.45 vs 3.41 g) and triples the calcium, so
picking it for kernel-size resemblance would trade a right protein figure for a
wrong one. Kernel size is not a nutrient.

### SA-22 `cancha` -> corn nuts — MAPPING MEASURED AND REJECTED

```
none  cancha                             -      (nothing)
```
```
 Corn nuts | Energy            |  446 KCAL
           | Total lipid (fat) | 15.64 G
```

`Corn nuts` (2708195) is the same *form* — a toasted whole-kernel corn snack —
and is deep-fried, at 15.6 g fat per 100 g. Cancha is dry-toasted in a pan with
little or no oil. Accepting this mapping would add roughly 100 kcal and 13 g of
fat per 100 g on a snack eaten by the handful. Rejected; recorded as an entity gap.

### SA-23 `cuy` / `guinea pig`, `alpaca meat`, `llama meat`, `paiche`, `corvina` — ENTITY GAPS — **filed; no mapping**

```
none  cuy                                -      (nothing)
none  guinea pig                         -      (nothing)
weak  alpaca meat                        0.312  Meat, NFS
weak  llama meat                         0.333  Meat, NFS
none  paiche                             -      (nothing)
none  corvina                            -      (nothing)
```

USDA's game-meat family is thorough — antelope, bear, beaver, bison, boar,
caribou, deer, elk, rabbit — and contains no camelid and no rodent:

```
  172521 | sr_legacy_food | Game meat, rabbit, domesticated, composite of cuts, raw
  175294 | sr_legacy_food | Game meat, beaver, raw
```

Genuine entity gaps. `Meat, NFS` at 0.31 is the resolver correctly refusing.
Deliberately not mapping alpaca to any of these: camelid meat is notably leaner
than most of the list and picking a neighbour by "also a game animal" is exactly
the wrong-row-plausible-number failure.

### SA-24 `lucuma`, `maca`, `sacha inchi`, `yacon`, `oca`, `olluco`, `mashua`, `canihua`, `tarwi` — Andean entity gaps — **filed; no mapping**

All `none`; `maca powder -> Baobab powder` at 0.368 is the resolver reaching for
the only other exotic powder in the database, which is the right verdict (weak)
for the wrong reason. No USDA row exists for any of these Andean crops. Lúcuma
and maca are eaten in tens of grams as powders and would benefit from a
`user_product` from the pack; oca, olluco and mashua are tubers with no
neighbour that is not simply "potato", which is over-broad.

---

# Batch 3 — Argentina, Uruguay, Chile, Paraguay (83 terms)

Verdicts: `ask=3 (4%)  auto=2 (2%)  none=63 (76%)  weak=15 (18%)`

```
none  asado                              -      (nothing)
none  asado de tira                      -      (nothing)
none  vacio                              -      (nothing)
none  entrana                            -      (nothing)
ask   bife de chorizo                    0.500  Chorizo
none  bife de lomo                       -      (nothing)
none  bife de costilla                   -      (nothing)
none  ojo de bife                        -      (nothing)
none  matambre                           -      (nothing)
none  matambre arrollado                 -      (nothing)
none  colita de cuadril                  -      (nothing)
none  tapa de asado                      -      (nothing)
none  chinchulines                       -      (nothing)
none  mollejas                           -      (nothing)
auto  sweetbreads                        1.000  Sweetbreads
weak  morcilla                           0.333  Mortadella
ask   chorizo criollo                    0.533  Chorizo
weak  choripan                           0.417  Chorizo
weak  chimichurri                        0.333  Churros
weak  salsa criolla                      0.333  Salsa, NFS
none  provoleta                          -      (nothing)
none  milanesa                           -      (nothing)
none  milanesa napolitana                -      (nothing)
weak  suprema de pollo                   0.303  Soup, sopa or caldo de pollo
weak  empanada salteña                   0.429  Empanada, NFS
weak  empanada tucumana                  0.429  Empanada, NFS
weak  empanada mendocina                 0.440  Empanada, no meat
none  humita                             -      (nothing)
none  humita en chala                    -      (nothing)
none  locro                              -      (nothing)
none  guiso de lentejas                  -      (nothing)
none  puchero                            -      (nothing)
none  carbonada                          -      (nothing)
none  pastel de papa                     -      (nothing)
none  tarta de jamon y queso             -      (nothing)
none  fugazza                            -      (nothing)
none  fugazzeta                          -      (nothing)
none  faina                              -      (nothing)
none  pizza a la piedra                  -      (nothing)
none  medialuna                          -      (nothing)
none  factura                            -      (nothing)
none  alfajor                            -      (nothing)
none  alfajor de maicena                 -      (nothing)
auto  dulce de leche                     1.000  Dulce de Leche
weak  dulce de membrillo                 0.333  Dulce de Leche
none  membrillo                          -      (nothing)
weak  quince paste                       0.316  Quinces, raw
none  mate                               -      (nothing)
none  yerba mate                         -      (nothing)
none  mate cocido                        -      (nothing)
none  submarino                          -      (nothing)
none  mantecol                           -      (nothing)
none  chocotorta                         -      (nothing)
none  vigilante                          -      (nothing)
weak  queso cremoso                      0.368  Queso cotija
weak  queso sardo                        0.316  Queso Fresco
none  reggianito                         -      (nothing)
none  pastel de choclo                   -      (nothing)
none  curanto                            -      (nothing)
none  completo                           -      (nothing)
ask   italiano                           0.538  Italian Ice
none  merken                             -      (nothing)
none  merquen                            -      (nothing)
none  pebre                              -      (nothing)
none  cazuela                            -      (nothing)
none  charquican                         -      (nothing)
none  porotos granados                   -      (nothing)
weak  sopaipilla                         0.367  Sopaipilla with syrup or honey
none  manjar                             -      (nothing)
none  mote con huesillo                  -      (nothing)
none  machas                             -      (nothing)
none  loco chileno                       -      (nothing)
weak  congrio                            0.364  Congee
none  reineta                            -      (nothing)
none  chupe de jaiba                     -      (nothing)
none  chapalele                          -      (nothing)
none  milcao                             -      (nothing)
none  sopa paraguaya                     -      (nothing)
weak  chipa                              0.333  Soy chips
none  mbeju                              -      (nothing)
none  vori vori                          -      (nothing)
none  tereré                             -      (nothing)
none  bori bori
```

## Findings — batch 3

### SA-25 `bife de chorizo` -> `Chorizo` — WRONG NEIGHBOUR, and the most dangerous shape in the domain — **high**

```
ask   bife de chorizo                    0.500  Chorizo
ask   chorizo criollo                    0.533  Chorizo
weak  choripan                           0.417  Chorizo
```

Bife de chorizo is a **strip steak** — the sirloin/short-loin cut, the default
order at any Argentine parrilla. It is not sausage and contains no sausage. The
resolver's top candidate is `Chorizo` (2706179), a pimentón pork sausage, at
0.500. `chorizo criollo` and `choripan` land on the same row and for *those* it
is roughly right.

USDA has the correct row, twice, under the American name:

```
 2727572 | foundation_food | Beef, short loin (NY strip steak), raw
  174714 | sr_legacy_food  | Beef, loin, top loin steak, boneless, lip-on, trimmed to 1/8" fat, all grades, cooked, grilled
  169429 | sr_legacy_food  | Beef, grass-fed, strip steaks, lean only, raw
```

This is the finding to act on carefully. It sits at 0.500, in the `ask` band, so
today it escalates — but it is the one case in this domain where a **synonym
rule would make things worse if written naively**: any global rule of the form
`chorizo -> Chorizo` would fire on the substring inside `bife de chorizo` and
turn a lean beef steak into a fatty pork sausage with no model consulted, and
then cache the alias forever. The whole phrase must be the key, and it must beat
the substring.

### SA-26 `mollejas` — REACHABILITY GAP (missing_synonym) — **high**

```
none  mollejas                           -      (nothing)
auto  sweetbreads                        1.000  Sweetbreads
```

```
 2706158 | survey_fndds_food | Sweetbreads
  170195 | sr_legacy_food    | Beef, variety meats and by-products, thymus, cooked, braised
  170194 | sr_legacy_food    | Beef, variety meats and by-products, thymus, raw
  173092 | sr_legacy_food    | Beef, New Zealand, imported, sweetbread, cooked, boiled
```

Mollejas *are* sweetbreads (thymus), the standard first course of an asado. The
English word auto-matches at 1.000; the Spanish word returns an empty list.

### SA-27 `morcilla` -> `Mortadella` — REACHABILITY GAP + bad fuzzy match — **high**

```
weak  morcilla                           0.333  Mortadella
```

```
  171618 | sr_legacy_food    | Blood sausage
 2706173 | survey_fndds_food | Blood sausage
```

Morcilla *is* blood sausage. The row exists twice and is unreachable; what the
query reaches instead is mortadella — an emulsified pork bologna — purely
because `mort`/`morc` overlap. Blood sausage carries roughly 20 mg iron per
100 g against mortadella's 1.4; substituting one for the other inverts the one
nutrient anybody eats morcilla for.

### SA-28 Argentine and Uruguayan beef cuts — REACHABILITY GAPS, all high

```
none  asado de tira                      -      (nothing)
none  vacio                              -      (nothing)
none  entrana                            -      (nothing)
none  bife de lomo                       -      (nothing)
none  ojo de bife                        -      (nothing)
none  colita de cuadril                  -      (nothing)
none  matambre                           -      (nothing)
```

Every one has an exact or near-exact USDA anatomical row, and every one returns
an empty list. Measured neighbours:

```
entraña  -> 173397 Beef, plate steak, boneless, outside skirt, separable lean and fat, trimmed to 0" fat, all grades, cooked, grilled
ojo de bife -> 173387 Beef, rib eye steak, bone-in, lip-on, separable lean and fat, trimmed to 1/8" fat, all grades, cooked, grilled
asado de tira -> 171222 Beef, chuck, short ribs, boneless, separable lean and fat, trimmed to 0" fat, all grades, cooked, braised
bife de lomo -> 170237 Beef, loin, tenderloin steak, boneless, separable lean and fat, trimmed to 0" fat, all grades, cooked, grilled
colita de cuadril -> 169558 Beef, bottom sirloin, tri-tip roast, separable lean and fat, trimmed to 0" fat, all grades, cooked, roasted
vacío   -> 168733 Beef, flank, steak, separable lean and fat, trimmed to 0" fat, all grades, cooked, broiled
```

The first five are **high** — a butcher on either continent would call them the
same muscle. `vacío` is **medium**: it is the flap/bavette off the flank region
and Argentine butchery does not cut it identically, and `matambre` is **medium**
for the same reason (the thin sheet between hide and ribs, nearest flank).

Together with picanha (SA-1) this is the largest single cluster in the domain:
an entire beef vocabulary, in a cuisine defined by beef, with **zero** recall,
against a database that is exhaustively detailed about beef anatomy — 55+ skirt
rows and 40+ tenderloin rows alone. Nothing here is a missing food. It is
entirely a missing name.

### SA-29 `provoleta` — REACHABILITY GAP (missing_synonym) — **high**

```
none  provoleta                          -      (nothing)
```
```
  170850 | sr_legacy_food    | Cheese, provolone
 2705733 | survey_fndds_food | Cheese, Provolone
 2647440 | foundation_food   | Cheese, provolone, sliced
```

Provoleta is a thick disc of provolone grilled on the parrilla. Same cheese;
the cooking loses water, so the honest treatment is provolone plus a state, not
a distinct food.

### SA-30 `chinchulines` — REACHABILITY GAP — **medium**

```
none  chinchulines                       -      (nothing)
```
```
 2706163 | survey_fndds_food | Chitterlings
  167856 | sr_legacy_food    | Pork, fresh, variety meats and by-products, chitterlings, cooked, simmered
```

Chinchulines are beef small intestine; chitterlings are pork large intestine.
Same tissue class and similar fat, different species and section — **medium**,
fallback only. Recorded rather than raised to high precisely because "also
intestine" is the kind of resemblance that is anatomical, not nutritional.

### SA-31 `membrillo` / `dulce de membrillo` — ENTITY GAP; the obvious mapping rejected, a better one proposed — **medium**

```
none  membrillo                          -      (nothing)
weak  dulce de membrillo                 0.333  Dulce de Leche
weak  quince paste                       0.316  Quinces, raw
```

USDA has exactly one quince row:

```
  168163 | sr_legacy_food    | Quinces, raw
```

`Quinces, raw` is **rejected** as the target: membrillo is a sugar-set paste at
roughly 250 kcal and 60 g sugar per 100 g against raw quince at 57 kcal and
~9 g. Eaten in 30 g slices with cheese, that mapping loses about 60 kcal a
serving and nearly all of the sugar. The structurally correct fallback is the
*other* sugar-set fruit paste USDA does carry:

```
 2710307 | survey_fndds_food | Guava paste
```

Same product class, same manufacture, comparable sugar loading. **Medium** —
different fruit, right food.

Note also `dulce de membrillo -> Dulce de Leche`: a second "dulce de …" collision
after SA-18, from the same two shared words.

### SA-32 Chilean, Paraguayan and Argentine dish gaps — filed, not mapped

```
none  pastel de choclo   none  curanto     none  charquican   none  porotos granados
none  humita             none  locro       none  cazuela      none  mote con huesillo
none  sopa paraguaya     none  chipa       none  mbeju        none  vori vori
none  milanesa           none  medialuna   none  alfajor      none  faina
```

All dishes, all unreachable, and all decomposable to ingredients that are
themselves unreachable — choclo (SA-21), cassava flour (SA-4), queso (SA-12).
Two worth naming:

- `chipa -> Soy chips` at 0.333 — a cassava-and-cheese bread reaching a soy
  snack on three shared letters.
- `sopaipilla -> Sopaipilla with syrup or honey` at 0.367: the row *is* named
  for the query, and length dilution pushes it below the weak floor. It is also
  the wrong sopaipilla — the Chilean one is a savoury pumpkin fry-bread, the
  USDA row is the sweetened New Mexican pastry. A rare case where reaching the
  matching name would still be a `preparation_state_mismatch`.

### SA-33 `merken` / `merquen` — ENTITY GAP — **medium**

```
none  merken                             -      (nothing)
none  merquen                            -      (nothing)
```
```
  171329 | sr_legacy_food | Spices, paprika
  168570 | sr_legacy_food | Peppers, hot chile, sun-dried
```

Merkén is smoked dried ají cacho de cabra ground with coriander seed. `Spices,
paprika` is the nearest thing in the database and is the same product class
(dried ground capsicum) — **medium**, and used in gram quantities so the
nutritional stake is small either way.

### SA-34 `yerba mate` / `tereré` — ENTITY GAP, no neighbour at all — **filed, no mapping**

```
none  mate                               -      (nothing)
none  yerba mate                         -      (nothing)
none  mate cocido                        -      (nothing)
none  tereré                             -      (nothing)
```

`select ... where description ilike '%yerba%'` returns **zero rows**. USDA has no
maté of any kind. This is a true entity gap and a benign one — an infusion of
near-zero energy — but it is the single most-consumed item in Argentina,
Uruguay and Paraguay by volume, and a user logging it will get nothing back.
Deliberately not mapping it to tea: the caffeine and the polyphenol profile
differ, and a "close enough" hot-drink parent buys nothing since both are ~0 kcal.

---

# Batch 4 — Colombia, Venezuela, Bolivia, Ecuador (81 terms)

Verdicts: `auto=1 (1%)  none=67 (83%)  weak=13 (16%)  ask=0`

```
weak  arepa                              0.353  Arepa Dominicana
weak  arepa de queso                     0.318  Queso Asadero
none  arepa reina pepiada                -      (nothing)
none  arepa boyacense                    -      (nothing)
none  bandeja paisa                      -      (nothing)
none  ajiaco                             -      (nothing)
none  ajiaco bogotano                    -      (nothing)
none  sancocho                           -      (nothing)
none  sancocho de gallina                -      (nothing)
none  pabellon criollo                   -      (nothing)
none  hallaca                            -      (nothing)
none  hallacas                           -      (nothing)
none  cachapa                            -      (nothing)
weak  tequenos                           0.308  Tequila
none  guasacaca                          -      (nothing)
none  guayoyo                            -      (nothing)
none  patacon                            -      (nothing)
none  patacones                          -      (nothing)
none  tostones                           -      (nothing)
none  maduros                            -      (nothing)
none  chicharron                         -      (nothing)
none  chicharron colombiano              -      (nothing)
none  carne desmechada                   -      (nothing)
none  carne mechada                      -      (nothing)
none  mondongo                           -      (nothing)
none  lechona                            -      (nothing)
none  tamal tolimense                    -      (nothing)
none  changua                            -      (nothing)
none  calentado                          -      (nothing)
none  arroz con coco                     -      (nothing)
weak  arroz con leche                    0.356  Restaurant, Latino, arroz con leche (rice pudding)
none  buñuelo                            -      (nothing)
weak  bunuelo                            0.156  Restaurant, Latino, bunuelos (fried yeast bread)
none  almojabana                         -      (nothing)
none  pandebono                          -      (nothing)
none  pan de bono                        -      (nothing)
none  aborrajado                         -      (nothing)
none  mazamorra                          -      (nothing)
none  agua de panela                     -      (nothing)
none  panela                             -      (nothing)
none  papelon                            -      (nothing)
none  melao                              -      (nothing)
none  guarapo                            -      (nothing)
weak  malta                              0.308  Milk, malted
weak  harina pan                         0.304  Masa harina, cooked
none  masarepa                           -      (nothing)
auto  masa harina                        0.632  Masa harina, cooked
weak  cornmeal                           0.429  Cornmeal, blue (Navajo)
weak  precooked corn flour               0.370  Pasta, gluten-free, corn and rice flour, cooked
none  suero costeno                      -      (nothing)
weak  queso costeno                      0.421  Queso cotija
weak  queso llanero                      0.400  Queso Asadero
weak  nata                               0.375  Natto
weak  natilla                            0.312  Tortilla, NFS
none  obleas                             -      (nothing)
none  arequipe                           -      (nothing)
none  bocadillo veleño                   -      (nothing)
none  salteña                            -      (nothing)
none  saltena                            -      (nothing)
none  silpancho                          -      (nothing)
none  pique macho                        -      (nothing)
none  anticucho boliviano                -      (nothing)
none  chuño                              -      (nothing)
none  tunta                              -      (nothing)
none  api morado                         -      (nothing)
none  llajua                             -      (nothing)
none  majadito                           -      (nothing)
none  sopa de mani                       -      (nothing)
none  humintas                           -      (nothing)
none  fritanga                           -      (nothing)
none  encebollado                        -      (nothing)
none  bolon de verde                     -      (nothing)
none  llapingacho                        -      (nothing)
none  fanesca                            -      (nothing)
none  seco de chivo                      -      (nothing)
none  guatita                            -      (nothing)
none  ceviche de camaron ecuatoriano     -      (nothing)
none  locro de papa                      -      (nothing)
none  hornado                            -      (nothing)
none  cuy asado                          -      (nothing)
none  tigrillo                           -      (nothing)
```

## Findings — batch 4

### SA-35 `arepa` -> `Arepa Dominicana` — CULTURALLY INCORRECT MAPPING, correct row ranked second at a third of the score — **high**

Full candidate list — the database returns exactly two rows and puts the wrong
one on top:

```
arepa -> weak
    0.353 Arepa Dominicana
    0.12  Restaurant, Latino, arepa (unleavened cornmeal bread)
```

`Restaurant, Latino, arepa (unleavened cornmeal bread)` (168070) **is** the
Colombian/Venezuelan arepa. `Arepa Dominicana` (2707828) is a different food
that happens to share the word: a sweet baked pudding of cornmeal, coconut milk
and sugar. One is a plain maize griddle bread, the other is a dessert.

The correct row scores **0.12** — a third of the wrong one — for the reason
RESUME.md already established: it is a long description and the query is one
word. Every additional qualifier USDA added to make the row precise pushed it
further out of reach. `arepa de queso` does worse still, landing on a Mexican
cheese (`Queso Asadero`) rather than on either arepa.

This is simultaneously a reachability gap, a length-dilution demonstration, and
a culturally incorrect near-neighbour. It is the second-most consumed staple in
this domain after rice.

### SA-36 `chicharron` — REACHABILITY GAP (missing_synonym) — **high**, with the target chosen on measurement

```
none  chicharron                         -      (nothing)
none  chicharron colombiano              -      (nothing)
auto  pork rinds                         0.688  Pork skin rinds
```

Two candidate rows, measured per 100 g:

```
 2705902 | Pork skin rinds   | Protein 61.3 G | Fat 31.3 G | Energy 544 KCAL
 2705895 | Pork, cracklings  | Protein 45.0 G | Fat 41.7 G | Energy 569 KCAL
```

**`Pork, cracklings` (2705895) is the right target, not `Pork skin rinds`.**
Chicharrón as eaten in Colombia, Peru and Bolivia is fried pork belly with the
fat and a layer of meat still attached; puffed pork rinds are skin alone.
Cracklings carry 10 g more fat and 16 g less protein per 100 g, which is the
correct direction. The English phrase auto-matches the *wrong* one of the two at
0.688 — so this is a reachability gap where fixing it naively (chicharrón →
whatever "pork rinds" resolves to) would inherit the error.

### SA-37 `patacon` / `tostones` / `maduros` — REACHABILITY GAP (missing_synonym) — **high**

```
none  patacon                            -      (nothing)
none  patacones                          -      (nothing)
none  tostones                           -      (nothing)
none  maduros                            -      (nothing)
```

USDA has the whole plantain family in every state, including the two that matter:

```
  168199 | sr_legacy_food    | Plantains, green, fried          <- tostones / patacones
  168200 | sr_legacy_food    | Plantains, yellow, fried, Latino restaurant   <- maduros
  168216 | sr_legacy_food    | Plantains, green, boiled
 2710843 | foundation_food   | Plantains, overripe, raw
 2710817 | foundation_food   | Plantains, ripe, raw
 2710818 | foundation_food   | Plantains, underripe, raw
 2709563 | survey_fndds_food | Plantain chips
```

Green versus yellow is exactly the tostón/maduro distinction and USDA models it
correctly — sugar roughly triples from green to ripe. Both names are
unreachable. **High**, and unusually clean: the ripeness state is preserved by
the mapping rather than lost by it.

### SA-38 `bunuelo` / `buñuelo` and `arroz con leche` — LENGTH DILUTION AT ITS MOST EXTREME — **high**

```
none  buñuelo                            -      (nothing)
weak  bunuelo                            0.156  Restaurant, Latino, bunuelos (fried yeast bread)
weak  arroz con leche                    0.356  Restaurant, Latino, arroz con leche (rice pudding)
```

Both rows contain the query **verbatim**, and both score below the weak floor —
`bunuelo` at **0.156** against a description that literally spells "bunuelos".
0.156 is the resolver reporting "the right answer was probably never on the
list" about a row whose name is the query. And the tilded spelling, which is the
correct one in every Spanish-speaking country, returns nothing at all.

The `Restaurant, Latino, ...` prefix is doing the damage: USDA prepends a
seven-character qualifier to a family of exactly the Latin American dishes this
domain needs, and that prefix is enough to bury each of them. Same mechanism as
SA-35. This is a systematic defect against one whole slice of the database, not
a run of unlucky individual rows.

### SA-39 `masarepa` / `harina pan` — ENTITY GAP; the obvious mapping measured and REJECTED — **high as a refusal**

```
none  masarepa                           -      (nothing)
weak  harina pan                         0.304  Masa harina, cooked
auto  masa harina                        0.632  Masa harina, cooked
```

Masarepa (sold as Harina P.A.N.) is *precooked* corn flour and is the flour
arepas are made from. Masa harina is *nixtamalised* corn flour and is what
tortillas are made from. They are not interchangeable in a kitchen and they are
not interchangeable nutritionally, because nixtamalisation is a lime treatment:

```
  169694 | Corn flour, masa, enriched, white                  | Calcium, Ca | 138.0 MG
 2710835 | Corn flour, masa harina, white or yellow, dry, raw | Calcium, Ca | 111.6 MG
```

Masa harina carries 110–140 mg calcium per 100 g that comes from the lime, not
the maize. Mapping masarepa onto it would credit roughly 130 mg of calcium per
100 g of flour to a food that does not contain it — the phantom-nutrient failure
in reverse. **Deliberately rejected.** Masarepa is a genuine entity gap; the
honest treatment is a `user_product` from the packet.

### SA-40 `panela` / `papelon` — ENTITY GAP, fallback available — **medium**

```
none  panela                             -      (nothing)
none  papelon                            -      (nothing)
none  agua de panela                     -      (nothing)
none  melao                              -      (nothing)
```

USDA has no panela, piloncillo or rapadura. The sugar family:

```
  170674 | sr_legacy_food | Sugar, turbinado
  168833 | sr_legacy_food | Sugars, brown
 2710260 | survey_fndds_food | Sugar, brown
  168820 | sr_legacy_food | Molasses
```

`Sugar, turbinado` (170674) is unrefined cane sugar and is the closest by
process — **medium**. Molasses is **rejected**: it is the syrup fraction, about
290 kcal against panela's ~380, with several times the potassium and iron.
Panela is whole evaporated cane juice, closer to turbinado than to either
refined brown sugar or molasses.

### SA-41 Colombian, Venezuelan, Bolivian, Ecuadorian dish gaps — filed, not mapped

```
none  bandeja paisa    none  ajiaco       none  sancocho     none  pabellon criollo
none  hallaca          none  cachapa      none  tequenos     none  guasacaca
none  lechona          none  mondongo     none  salteña      none  silpancho
none  llapingacho      none  fanesca      none  encebollado  none  guatita
none  sopa de mani     none  llajua       none  chuño        none  tunta
```

Every one `none`. `tequenos -> Tequila` at 0.308 is the batch's best joke and its
worst candidate: a cheese stick reaching a spirit.

Two are ingredient-level and worth separating from the dishes:

- **`chuño` / `tunta`** — Andean freeze-dried potato, no USDA neighbour of any
  kind. Deliberately not mapped to dehydrated potato flakes: chuño is
  freeze-dried whole tuber, rehydrated before eating, so the as-eaten mass and
  the dry row's density are different questions. Entity gap.
- **`guasacaca`, `llajua`, `pebre`** — fresh chile-and-herb table sauces, eaten
  by the spoon, no neighbour. Nutritionally near-free; leaving them unresolved
  costs almost nothing and guessing costs credibility.

### SA-42 Latin cheeses — the near-neighbour trap — **filed; all mappings low**

```
weak  queso costeno                      0.421  Queso cotija
weak  queso llanero                      0.400  Queso Asadero
weak  queso cremoso                      0.368  Queso cotija
weak  queso sardo                        0.316  Queso Fresco
weak  arepa de queso                     0.318  Queso Asadero
```

USDA's Latin cheese family is entirely **Mexican**:

```
  170898 | Cheese, mexican, queso cotija      2647443 | Cheese, cotija, solid
  173437 | Cheese, mexican, queso asadero     2647441 | Cheese, oaxaca, solid
  172223 | Cheese, fresh, queso fresco        2647442 | Cheese, queso fresco, solid
  172201 | Cheese, mexican, queso anejo       172224 | Cheese, white, queso blanco
  172222 | Cheese, dry white, queso seco
```

Every South American queso in this batch lands on a Mexican one on the strength
of the shared word `queso` and nothing else. `queso sardo` is the clearest
error: it is Argentina's hard grating cheese, a Sardo/pecorino analogue at ~35%
fat, and it reaches `Queso Fresco`, a fresh curd at ~20% fat and ten times the
moisture. **Every mapping in this cluster is rejected** — see Deliberately
rejected. `queso` is a category word, not a food, and the resolver is treating
it as an identity.

---

# Batch 5 — proposal-target verification and defining ingredients (86 terms)

Verdicts: `ask=23 (27%)  auto=45 (52%)  none=1 (1%)  weak=17 (20%)`

Two purposes: check that every row this audit proposes as a target is a real,
reachable row, and probe the *defining ingredients* of the dishes above so a
dish that resolves while its signature ingredient does not is caught.

```
weak  top sirloin cap                    0.208  Beef, loin, top sirloin cap steak, boneless, separable lean and fat, trimmed to 1/8" fat, select, raw
weak  sirloin cap steak                  0.221  Beef, loin, top sirloin cap steak, boneless, separable lean and fat, trimmed to 1/8" fat, select, raw
weak  strip steak                        0.323  Beef, steak, strip, lean only eaten
none  new york strip                     -      (nothing)
weak  outside skirt steak                0.237  Beef, plate steak, boneless, outside skirt, separable lean only, trimmed to 0" fat, select, raw
weak  skirt steak                        0.375  Steak sauce
weak  rib eye steak                      0.187  Beef, rib eye steak, boneless, lip off, separable lean only, trimmed to 0" fat, select, raw
auto  beef short ribs                    0.722  Beef, shortribs
auto  beef tenderloin                    0.727  Beef, steak, tenderloin
weak  tri-tip                            0.099  Beef, bottom sirloin, tri-tip roast, separable lean and fat, trimmed to 0" fat, select, raw
auto  flank steak                        0.706  Beef, steak, flank
auto  sweetbreads                        1.000  Sweetbreads
weak  beef thymus                        0.273  Beef, variety meats and by-products, thymus, raw
auto  chitterlings                       1.000  Chitterlings
auto  blood sausage                      1.000  Blood sausage
auto  smoked pork sausage                0.792  Sausage, smoked link sausage, pork
auto  cassava flour                      1.000  Flour, cassava
auto  cassava                            0.667  Cassava, raw
ask   yuca                               0.455  Yuca fries
auto  guava paste                        1.000  Guava paste
auto  dulce de leche                     1.000  Dulce de Leche
auto  amaranth grain                     0.682  Amaranth grain, cooked
auto  sweet potato                       0.812  Pie, sweet potato
weak  groundcherries                     0.385  Groundcherries, (cape-gooseberries or poha), raw
weak  cape gooseberry                    0.341  Groundcherries, (cape-gooseberries or poha), raw
auto  cherimoya                          0.714  Cherimoya, raw
ask   provolone                          0.588  Cheese, provolone
auto  pork cracklings                    1.000  Pork, cracklings
auto  green plantain fried               0.870  Plantains, green, fried
ask   ripe plantain fried                0.520  Plantains, ripe, raw
auto  turbinado sugar                    1.000  Sugar, turbinado
ask   hot chile pepper                   0.552  Peppers, hot chile, sun-dried
auto  serrano pepper                     0.667  Peppers, serrano, raw
ask   paprika                            0.533  Spices, paprika
auto  black beans                        0.733  Black beans, NFS
ask   black turtle beans                 0.529  Beans, black turtle, mature seeds, raw
weak  collard greens                     0.375  Poke greens, cooked
ask   salt pork                          0.500  Pork, cured, salt pork, raw
auto  pork belly                         1.000  Pork, belly
auto  pork ribs                          1.000  Pork, ribs
ask   smoked pork                        0.500  Sausage, smoked link sausage, pork
ask   bacon                              0.600  Bacon bits
ask   kale                               0.556  Kale, raw
ask   okra                               0.556  Okra, raw
auto  peanuts                            0.667  Peanuts, raw
auto  peanut butter                      1.000  Peanut butter
auto  cashews                            0.667  Cashews, NFS
auto  dried shrimp                       1.000  Shrimp, dried
auto  shrimp                             0.636  Shrimp, NFS
auto  coconut milk                       1.000  Coconut milk
auto  lime juice                         0.733  Lime juice, raw
ask   red onion                          0.600  Onions, red, raw
auto  cilantro                           0.692  Cilantro, raw
ask   coriander leaf                     0.536  Spices, coriander leaf, dried
auto  parsley                            0.667  Parsley, raw
auto  garlic                             0.636  Garlic, raw
auto  white rice cooked                  0.643  Rice, white, cooked, glutinous
auto  brown rice                         0.647  Flour, rice, brown
auto  lentils                            0.667  Lentils, dry
auto  chickpeas                          0.714  Chickpeas, NFS
weak  navy beans                         0.393  Beans, navy, mature seeds, raw
auto  pinto beans                        0.750  Pinto beans, NFS
auto  kidney beans                       0.765  Kidney beans, NFS
auto  potato boiled                      0.778  Potato, boiled, NFS
weak  yellow potato                      0.265  Potatoes, yellow fleshed, french fried, frozen, unprepared
auto  condensed milk                     0.625  Milk, condensed, sweetened
auto  evaporated milk                    0.727  Milk, evaporated, whole
auto  heavy cream                        1.000  Cream, heavy
ask   egg yolk                           0.600  Egg, yolk, dried
weak  wheat flour                        0.444  Wheat flour, whole-grain, soft wheat
auto  corn starch                        0.643  Cornstarch
ask   beef heart                         0.545  Heart
ask   beef tripe                         0.545  Tripe
auto  beef liver                         1.000  Liver, beef
ask   chicken thigh                      0.467  Chicken thigh, stewed, skin eaten
ask   chicken breast                     0.517  Chicken breast, roll, oven-roasted
weak  pork loin                          0.435  Pork, loin, boneless, raw
ask   goat meat                          0.529  Game meat, goat, raw
weak  sea bass                           0.290  Fish, sea bass, mixed species, raw
ask   cod                                0.500  Cape Cod
auto  octopus                            1.000  Octopus
weak  squid                              0.364  Squirrel
auto  mussels                            1.000  Mussels
ask   clams                              0.600  Clams, raw
ask   scallops                           0.600  Scallops, fried
ask   crab meat                          0.500  Imitation crab meat
```

## Findings — batch 5

### SA-43 `sweet potato` -> `Pie, sweet potato` — **WRONG-CONFIDENT MATCH. The worst class in the brief, found in plain English, and it blocks SA-16.** — **high**

```
sweet potato -> auto
    0.812 Pie, sweet potato          <- taken, no model consulted, alias cached forever
    0.765 Sweet potato, NFS          <- the right row, 0.047 behind
    0.722 Sweet potato paste
    0.722 Sweet potato tots
    0.684 Bread, sweet potato
```

Measured, per 100 g:

```
 Pie, sweet potato | Energy 269 KCAL | Fat 9.8 G | Sugars 25.2 G | Carb 41.1 G
 Sweet potato, NFS | Energy 115 KCAL | Fat 4.5 G | Sugars  6.0 G | Carb 17.1 G
```

Typing the name of a vegetable auto-matches a **dessert**: 2.3× the energy, 4×
the sugar, and no model is consulted because 0.812 clears the 0.62 gate. Per
CLAUDE.md the alias tier then caches it forever and there is no command that
repoints an alias, so every sweet potato that user ever logs is a slice of pie.

Two consequences:

1. This is the single highest-severity finding in the domain and it is not a
   South American word at all — it is the plain English name of a vegetable
   eaten across the whole continent (camote, batata doce, boniato).
2. **It blocks SA-16.** The camote proposal must target `Sweet potato, NFS`
   (2709697) **by fdc_id**. Any mapping expressed as a string — `camote ->
   "sweet potato"` — inherits this bug and turns camote into pie.

Note this is the `unrequested_qualifier` guard's exact shape (`Food, qualifier`
where the qualifier is a different food) failing in the *other* direction: the
guard only inspects segments after the first, and here the wrong word is the
first segment. `Pie, sweet potato` names a pie; the food asked for is the second
segment. A guard that checked whether the *head noun* of the description is the
query would catch it.

### SA-44 `brown rice` -> `Flour, rice, brown` — WRONG-CONFIDENT MATCH — **high**

```
brown rice -> auto
    0.647 Flour, rice, brown
    0.647 Rice flour, brown
    0.55  Beans and brown rice
```

Auto-matched onto flour. Both top rows are flour; the cooked grain is not on the
list at all. Rice flour is a dry ~360 kcal/100 g powder; cooked brown rice is
~112. A 200 g portion of "brown rice" logged this way is roughly 500 kcal too
many, and it caches.

Included here because `arroz` appears in half this domain's dishes — arroz con
pollo, arroz chaufa, arroz carreteiro, baião de dois, tacu tacu, calentado —
and because it shows SA-43 is not an isolated row but a pattern: **the
processed-product row outranks the plain-food row for the plain-food query.**

### SA-45 `collard greens` -> `Poke greens, cooked`, while `collards` auto-matches correctly — **high**

```
collard greens -> weak
    0.375 Poke greens, cooked
    0.36  Mustard greens, raw
    0.36  Beet greens, cooked
collards -> auto
    0.692 Collards, raw
couve -> none
```

Adding the English word people actually say — "greens" — moves a correct
auto-match to a weak match on a *different plant* (pokeweed). And `couve`, the
Portuguese name and the mandatory side of feijoada, returns nothing against a
database holding eight collard rows:

```
  170406 | Collards, raw            170407 | Collards, cooked, boiled, drained, without salt
  168523 | Collards, cooked, boiled, drained, with salt
  170408 | Collards, frozen, chopped, unprepared
```

### SA-46 Every proposed beef target is itself unreachable by its English name — an architectural finding — **high**

```
weak  top sirloin cap                    0.208  Beef, loin, top sirloin cap steak, ...
weak  outside skirt steak                0.237  Beef, plate steak, boneless, outside skirt, ...
weak  rib eye steak                      0.187  Beef, rib eye steak, boneless, lip off, ...
weak  tri-tip                            0.099  Beef, bottom sirloin, tri-tip roast, ...
none  new york strip                     -      (nothing)
weak  skirt steak                        0.375  Steak sauce
```

`tri-tip` scores **0.099** against a row named "tri-tip roast". `skirt steak`
reaches **steak sauce**. `new york strip` reaches nothing.

This is the load-bearing consequence for the whole knowledge layer: a synonym
table whose targets are *strings* would fail on exactly these entries, because
the English target string does not resolve either. **Every mapping this audit
proposes is expressed as an fdc_id.** RESUME.md's measurement (long descriptions
recall 28.7%) predicts this; batch 5 confirms it holds for the specific rows
this domain needs.

The short FNDDS rows behave correctly by contrast — `beef short ribs` 0.722,
`flank steak` 0.706, `beef tenderloin` 0.727 — so where FNDDS carries a short
equivalent it is the better target even when SR Legacy is more precise.

### SA-47 Ingredient probes: the defining ingredients mostly resolve, which localises the damage — **note**

Of the signature ingredients behind this domain's dishes, most are reachable in
English: `black beans` 0.733, `pork belly` 1.000, `pork ribs` 1.000, `dried
shrimp` 1.000, `coconut milk` 1.000, `peanuts` 0.667, `cashews` 0.667, `lime
juice` 0.733, `cilantro` 0.692, `octopus` 1.000, `mussels` 1.000, `beef liver`
1.000.

So the carbonara/guanciale failure in this domain is concentrated in a short
list — dendê (SA-2), cassava flour (SA-4), açaí (SA-3), choclo (SA-21), ají
(SA-20), masarepa (SA-39) and the beef cuts (SA-1, SA-28) — rather than being
spread evenly. That is good news for the fix: the dishes are unreachable, but
their parts are mostly not, so a model tier that decomposes a dish into
ingredients recovers most of this domain *provided* those seven are repaired.

Three ingredient-level defects picked up in passing, all outside this domain's
own vocabulary but all reachable from it:

```
ask   bacon                              0.600  Bacon bits
ask   crab meat                          0.500  Imitation crab meat
auto  white rice cooked                  0.643  Rice, white, cooked, glutinous
weak  squid                              0.364  Squirrel
```

`bacon -> Bacon bits` (frequently textured soy) and `crab meat -> Imitation crab
meat` (surimi) are both the imitation outranking the real food; both are in the
`ask` band so they escalate today. `white rice cooked -> Rice, white, cooked,
glutinous` **is** an auto onto the wrong variety — glutinous rice is a different
cultivar with a different starch profile — and belongs with SA-43 and SA-44.
`squid -> Squirrel` at 0.364 is harmless because it is weak, but it is the
purest illustration that this similarity metric has no idea what a food is.

---

# Batch 6 — diacritics, orthographic variants, fruits and fish (61 terms)

Verdicts: `ask=3 (5%)  auto=6 (10%)  none=37 (61%)  weak=15 (25%)`

```
none  açaí                               -      (nothing)
weak  acai berry                         0.314  Beverages, Acai berry drink, fortified
none  cupuaçu                            -      (nothing)
none  maracujá                           -      (nothing)
none  maracuja                           -      (nothing)
auto  passion fruit                      0.778  Passion fruit, raw
none  mandioca                           -      (nothing)
none  aipim                              -      (nothing)
none  macaxeira                          -      (nothing)
none  manioc                             -      (nothing)
none  batata doce                        -      (nothing)
none  boniato                            -      (nothing)
none  camote asado                       -      (nothing)
none  feijão preto                       -      (nothing)
none  feijao preto                       -      (nothing)
weak  frijoles negros                    0.258  Restaurant, Latino, Arroz con frijoles negros (rice and black beans)
none  poroto negro                       -      (nothing)
none  caraotas negras                    -      (nothing)
none  couve                              -      (nothing)
none  couve manteiga                     -      (nothing)
auto  collards                           0.692  Collards, raw
weak  palmito                            0.308  Oil, palm
auto  heart of palm                      0.650  Hearts of palm, raw
none  lúcuma                             -      (nothing)
weak  lucuma powder                      0.333  Baobab powder
none  quinua                             -      (nothing)
none  kinwa                              -      (nothing)
none  chuno                              -      (nothing)
weak  papa seca                          0.333  Papad
none  maíz                               -      (nothing)
weak  maiz                               0.333  Mai Tai
none  choclo peruano                     -      (nothing)
weak  corn kernels                       0.283  Corn, sweet, yellow and white kernels,  fresh, raw
none  elote                              -      (nothing)
none  jurel                              -      (nothing)
weak  anchoveta                          0.353  Fish, anchovy
ask   anchovy                            0.615  Fish, anchovy
none  pejerrey                           -      (nothing)
none  merluza                            -      (nothing)
none  hake                               -      (nothing)
weak  dorado fish                        0.312  Fish, raw
none  mero                               -      (nothing)
weak  salmón                             0.308  Salmon salad
none  langostino                         -      (nothing)
none  prawn                              -      (nothing)
none  chirimoya peruana                  -      (nothing)
weak  guanabana                          0.391  Guanabana nectar, canned
auto  soursop                            0.667  Soursop, raw
weak  carambola                          0.417  Carambola, (starfruit), raw
auto  starfruit                          0.714  Starfruit, raw
none  pitahaya                           -      (nothing)
auto  dragon fruit                       1.000  Dragon fruit
weak  mamey                              0.353  Sapote, mamey, raw
none  zapote                             -      (nothing)
weak  naranjilla                         0.275  Naranjilla (lulo) pulp, frozen, unsweetened
weak  lulo                               0.125  Naranjilla (lulo) pulp, frozen, unsweetened
none  tomate de arbol                    -      (nothing)
ask   tamarillo                          0.462  Tamarind
ask   tree tomato                        0.467  Tomato, roma
none  borojo                             -      (nothing)
none  copoazu                            -      (nothing)
```

## Findings — batch 6

### SA-48 A diacritic is a total loss of recall, measured across seven pairs — **high, and cross-cutting**

Every accented spelling in this domain — the *correct* spelling, and the one a
Portuguese or Spanish keyboard produces — returns strictly fewer candidates than
its stripped form:

```
none  açaí        vs  weak  acai         0.217  Fruit juice, acai blend
none  buñuelo     vs  weak  bunuelo      0.156  Restaurant, Latino, bunuelos (fried yeast bread)
none  chuño       vs  none  chuno
none  maíz        vs  weak  maiz         0.333  Mai Tai
none  salteña     vs  none  saltena
none  lúcuma      vs  none  lucuma
none  tereré      vs  (n/a)
weak  salmón      0.308  Salmon salad    <- vs the plain English "salmon"
none  cupuaçu     none  maracujá         none  feijão preto
```

Not one accented form ever scores *higher*. `açaí` returns an empty list against
a database with three açaí rows; `maíz` returns nothing while `maiz` at least
reaches a cocktail. `salmón` — a word whose ASCII form is an unambiguous English
noun — falls to 0.308 against `Salmon salad`.

This is a normalisation defect, not a knowledge gap: no synonym table entry can
fix it, because the fix is upstream of lookup. It multiplies every other finding
in this audit, since the natural spelling of most of this domain's vocabulary
carries a diacritic. Flagged for the `normalization-orthography` audit as a
South American corroboration.

### SA-49 `palmito` -> `Oil, palm` — REACHABILITY GAP + wrong food class — **high**

```
weak  palmito                            0.308  Oil, palm
auto  heart of palm                      0.650  Hearts of palm, raw
```

```
  167714 | sr_legacy_food    | Hearts of palm, raw
  168569 | sr_legacy_food    | Hearts of palm, canned
 2709954 | survey_fndds_food | Palm hearts, cooked
```

Palmito is heart of palm: a 20 kcal, near-zero-fat vegetable eaten by the jar in
Brazil. The query reaches **palm oil** — 884 kcal and 100% fat — because they
share the word "palm". A 100 g serving mis-scored this way is a 44-fold error in
energy and the largest single-item magnitude in the whole audit. It is weak, so
it escalates; but the model tier is handed a bottle of oil as the best guess for
a salad vegetable.

### SA-50 Spanish/Portuguese fruit names lose to English on rows named after the Spanish name — **high**

```
weak  carambola                          0.417  Carambola, (starfruit), raw
auto  starfruit                          0.714  Starfruit, raw

weak  guanabana                          0.391  Guanabana nectar, canned
auto  soursop                            0.667  Soursop, raw

weak  naranjilla                         0.275  Naranjilla (lulo) pulp, frozen, unsweetened
weak  lulo                               0.125  Naranjilla (lulo) pulp, frozen, unsweetened

weak  mamey                              0.353  Sapote, mamey, raw
none  zapote                             -      (nothing)
```

`Carambola, (starfruit), raw` (171715) is *named* carambola and the query
`carambola` scores 0.417 against it, while `starfruit` auto-matches a different,
shorter row at 0.714. `Naranjilla (lulo) pulp` contains **both** Spanish names
and neither reaches it — `lulo` at 0.125.

Worse, the two Spanish queries land on the **sweetened commercial** forms while
the English ones land on the raw fruit:

```
  168196 | Guanabana nectar, canned   <- what "guanabana" reaches
  167761 | Soursop, raw               <- what "soursop" reaches
```

Same inversion as açaí (SA-3): typing the Latin American name for a fruit
selects the processed sugared product, typing the English name selects the
fruit. Three independent instances now (açaí, guanábana, naranjilla), so it is a
pattern rather than a coincidence: USDA's *processed* rows tend to be short and
carry the foreign name, its *raw* rows tend to be short and carry the English
name, and length dilution decides between them.

### SA-51 `mandioca` / `aipim` / `macaxeira` / `manioc` — four names, zero recall — **high**

```
none  mandioca                           -      (nothing)
none  aipim                              -      (nothing)
none  macaxeira                          -      (nothing)
none  manioc                             -      (nothing)
auto  cassava                            0.667  Cassava, raw
```

Brazil calls this root by a different name in each region — mandioca in the
south-east, aipim in Rio, macaxeira in the north-east — and Anglophone
food-science calls it manioc. All four return nothing; only the Caribbean
Spanish-via-English `cassava` works. `yuca` (0.455, `Yuca fries`) is a fifth
name, half-working, and lands on a fried preparation rather than the root.

### SA-52 Black bean names — the base of half this domain's dishes, unreachable — **high**

```
none  feijão preto                       -      (nothing)
none  feijao preto                       -      (nothing)
weak  frijoles negros                    0.258  Restaurant, Latino, Arroz con frijoles negros (rice and black beans)
none  poroto negro                       -      (nothing)
none  caraotas negras                    -      (nothing)
auto  black beans                        0.733  Black beans, NFS
```

Feijoada, pabellón criollo, tutu de feijão, baião de dois, tacu tacu, calentado
and gallo pinto are all built on this one legume, and none of its four regional
names reaches it. USDA is generous here:

```
 2707359 | survey_fndds_food | Black beans, NFS
 2707361 | survey_fndds_food | Black beans, from dried, no added fat
  173735 | sr_legacy_food    | Beans, black, mature seeds, cooked, boiled, without salt
  175187 | sr_legacy_food    | Beans, black turtle, mature seeds, cooked, boiled, without salt
```

`frijoles negros` at 0.258 lands on a *composite* row — rice **and** beans —
which would roughly halve the protein density if taken.

### SA-53 Pacific fish — ENTITY GAPS, one high-confidence synonym — **mixed**

```
weak  anchoveta                          0.353  Fish, anchovy
none  jurel                              -      (nothing)
none  merluza                            -      (nothing)
none  hake                               -      (nothing)
none  pejerrey                           -      (nothing)
none  mero                               -      (nothing)
none  corvina                            -      (nothing)     (batch 2)
none  paiche                             -      (nothing)     (batch 2)
none  langostino                         -      (nothing)
none  prawn                              -      (nothing)
```

`anchoveta` is the Peruvian anchovy, *Engraulis ringens* — the same genus and
the same oily small pelagic as `Fish, anchovy` (2706232). **High** as a synonym.

The rest are true entity gaps and USDA has no hake row at all (`hake` itself
returns nothing), so there is no neighbour to point merluza at. `langostino` and
`prawn` both returning nothing while `shrimp` auto-matches at 0.636 is a plain
synonym gap: prawn is the standard word outside North America.

`dorado fish -> Fish, raw` at 0.312 is the resolver falling back to the category
noun, which is the correct behaviour and worth noting as such.

---

# Proposals

Every target is an **fdc_id**, never a string, for the reason measured in SA-46:
the English name of the target row frequently does not resolve to it either
(`tri-tip` 0.099, `new york strip` nothing, `sweet potato` -> a pie). A
string-keyed synonym table would inherit those defects.

`relation` is one of synonym | parent_category | nutritional_fallback |
dish_ingredient.

## High confidence — safe to encode automatically

| surface | relation | target fdc_id | target description | rationale |
|---|---|---|---|---|
| picanha | synonym | 173061 | Beef, loin, top sirloin cap steak, boneless, sep. lean and fat, 1/8" fat, all grades, cooked, grilled | Same cut, fat cap on. Raw form 174706. Do **not** use 171739 (cap-**off**) |
| dendê, dende, azeite de dendê | synonym | 171015 | Oil, palm | Same commodity; "palm oil" already auto-matches this at 1.000 |
| farinha de mandioca | synonym | 2512377 | Flour, cassava | Identical product |
| mandioca, aipim, macaxeira, manioc | synonym | 169985 | Cassava, raw | Four regional names, one root |
| goiabada | synonym | 2710307 | Guava paste | Same sugar-set fruit block |
| doce de leite | synonym | 173461 | Dulce de Leche | Portuguese spelling of the same food |
| aguaymanto, uchuva, golden berry, cape gooseberry | synonym | 173043 | Groundcherries, (cape-gooseberries or poha), raw | Same species, *Physalis peruviana* |
| kiwicha | synonym | 170683 | Amaranth grain, cooked | Quechua name for amaranth grain. **Not** the leaf rows (168385, 23 kcal vs 371) |
| camote, batata doce, boniato | synonym | 2709697 | Sweet potato, NFS | Pinned by id specifically to route around SA-43 |
| mollejas | synonym | 2706158 | Sweetbreads | Thymus; "sweetbreads" auto-matches this at 1.000 |
| morcilla, moronga | synonym | 171618 | Blood sausage | Same food; the current neighbour (mortadella) inverts the iron |
| entraña | synonym | 173397 | Beef, plate steak, boneless, outside skirt, sep. lean and fat, 0" fat, all grades, cooked, grilled | Outside skirt = diaphragm = entraña |
| ojo de bife | synonym | 173387 | Beef, rib eye steak, bone-in, lip-on, sep. lean and fat, 1/8" fat, all grades, cooked, grilled | Ribeye |
| asado de tira, tira de asado | synonym | 171222 | Beef, chuck, short ribs, boneless, sep. lean and fat, 0" fat, all grades, cooked, braised | Cross-cut short rib |
| bife de lomo, lomo fino | synonym | 170237 | Beef, loin, tenderloin steak, boneless, sep. lean and fat, 0" fat, all grades, cooked, grilled | Tenderloin |
| colita de cuadril, picana | synonym | 169558 | Beef, bottom sirloin, tri-tip roast, sep. lean and fat, 0" fat, all grades, cooked, roasted | Tri-tip |
| bife de chorizo, bife angosto | synonym | 2727572 | Beef, short loin (NY strip steak), raw | **Whole-phrase key only** — see SA-25. Must outrank any `chorizo` substring rule |
| provoleta | synonym | 170850 | Cheese, provolone | Same cheese, grilled |
| arepa, arepa de maíz | synonym | 168070 | Restaurant, Latino, arepa (unleavened cornmeal bread) | Must beat `Arepa Dominicana` (2707828), a different food (SA-35) |
| chicharrón | synonym | 2705895 | Pork, cracklings | Belly with fat and meat. **Not** `Pork skin rinds` (2705902): +10 g fat, −16 g protein per 100 g |
| patacón, patacones, tostones | synonym | 168199 | Plantains, green, fried | Twice-fried green plantain |
| maduros, plátano maduro frito, tajadas | synonym | 168200 | Plantains, yellow, fried, Latino restaurant | Ripe fried plantain; sugar differs ~3x from green |
| palmito | synonym | 167714 | Hearts of palm, raw | Canned form 168569. Current neighbour is palm **oil**, a 44x energy error |
| feijão preto, frijoles negros, caraotas negras, poroto negro | synonym | 2707359 | Black beans, NFS | Base of feijoada, pabellón, tacu tacu, calentado |
| couve, couve manteiga, couve mineira | synonym | 170406 | Collards, raw | Cooked form 170407 |
| anchoveta | synonym | 2706232 | Fish, anchovy | *Engraulis ringens*, same genus and oily-pelagic class |
| langostino, prawn, gamba | synonym | 2706360 | Shrimp, NFS | Standard word for shrimp outside North America |
| carambola | synonym | 171715 | Carambola, (starfruit), raw | The row is *named* carambola and scores 0.417 against it |
| guanábana, guanabana | synonym | 167761 | Soursop, raw | Raw fruit. **Not** `Guanabana nectar, canned` (168196), which is what the query reaches today |
| mamey, zapote, sapote | synonym | 167760 | Sapote, mamey, raw | Row contains "mamey"; query scores 0.353 |
| chirimoya | synonym | 173953 | Cherimoya, raw | Same row `cherimoya` auto-matches at 0.714 |
| maracujá, maracuya | synonym | 2709248 | Passion fruit, raw | |
| cebiche | synonym | 2706463 | Ceviche | Peruvian Academy spelling; costs 0.545 of similarity today |
| quinua | synonym | 168917 | Quinoa, cooked | Spanish spelling |

## Medium confidence — non-mandatory nutritional fallback only, never an auto-match

| surface | relation | target fdc_id | target description | rationale and its limit |
|---|---|---|---|---|
| farofa | dish_ingredient | 2512377 | Flour, cassava | Farofa is that flour toasted in fat; the fat is a second component |
| linguiça, linguiça calabresa | nutritional_fallback | 174584 | Sausage, smoked link sausage, pork | Same fat class. Differs in cure and moisture; chorizo rejected below |
| carne seca, charque, carne de sol | nutritional_fallback | 2705858 | Beef, dried, chipped, uncooked | Same process. Charque is desalted and rehydrated before eating, so as-eaten sodium is far lower and the stated mass is the wet mass |
| ají panca | nutritional_fallback | 168570 | Peppers, hot chile, sun-dried | Dried chile, correct class |
| ají amarillo, ají limo, rocoto | nutritional_fallback | 169395 | Peppers, serrano, raw | Fresh hot chile, comparable water content. Used in gram quantities |
| choclo, maíz choclo | nutritional_fallback | 169999 | Corn, sweet, yellow, cooked, boiled, drained, without salt | Protein matches (3.41 g); sugar overstated by ~3 g/100 g. Hominy rejected below |
| vacío | nutritional_fallback | 168733 | Beef, flank, steak, sep. lean and fat, 0" fat, all grades, cooked, broiled | Flap off the flank region; Argentine butchery does not cut it identically |
| matambre | nutritional_fallback | 168733 | Beef, flank, steak, ... cooked, broiled | Thin sheet between hide and ribs; nearest is flank |
| chinchulines | nutritional_fallback | 2706163 | Chitterlings | Beef small intestine vs pork large intestine. Same tissue class, different species |
| membrillo, dulce de membrillo | nutritional_fallback | 2710307 | Guava paste | Same product class and sugar loading, different fruit. `Quinces, raw` rejected below |
| panela, papelón, rapadura, chancaca | nutritional_fallback | 170674 | Sugar, turbinado | Unrefined cane sugar. Molasses rejected below |
| merkén, merquén | nutritional_fallback | 171329 | Spices, paprika | Dried ground capsicum; merkén is smoked and carries coriander seed |
| lulo, naranjilla | nutritional_fallback | 167790 | Naranjilla (lulo) pulp, frozen, unsweetened | Correct fruit but a pulp row, not the whole fruit |

## Entity gaps — filed, deliberately unmapped

No USDA row and no defensible neighbour. Recorded so the model tier and `/food`
know these need a `user_product`, not a fallback.

`açaí pulp` · `cupuaçu` · `lúcuma` · `maca` · `sacha inchi` · `yacón` · `oca` ·
`olluco` · `mashua` · `cañihua` · `tarwi` · `chuño` · `tunta` · `masarepa
(Harina P.A.N.)` · `huacatay` · `yerba mate` · `tereré` · `cuy` · `alpaca` ·
`llama` · `paiche` · `corvina` · `merluza` · `jurel` · `pejerrey` · `queijo
minas` · `queijo coalho` · `requeijão` · `Catupiry` · `queso llanero` · `queso
costeño` · `suero costeño` · `borojó` · `cancha` · `chipá` · `mbejú`

---

# Deliberately rejected

| surface | what was considered | why rejected |
|---|---|---|
| açaí (pulp or bowl) | `Fruit juice, acai blend` (2710777); any berry | USDA holds only sweetened beverages. Unsweetened pulp is a **high-fat** fruit (~5 g/100 g, near-zero sugar); the juice blend is the reverse. Mapping either way inverts the food's whole nutritional signature. The measured `acai puree -> Prune puree` (0.375) shows what the near-neighbour space actually offers. Entity gap, not a fallback |
| masarepa / Harina P.A.N. | `Masa harina, cooked` (2708376); `Corn flour, masa, enriched` (169694) | Masa harina is nixtamalised: 111–138 mg calcium per 100 g **from the lime**, not the maize. Masarepa is precooked, not lime-treated. The mapping would credit ~130 mg of phantom calcium per 100 g of flour |
| choclo | `Hominy, cooked` (2709933) | Measured: hominy protein 1.45 g/100 g vs sweet corn 3.41 and choclo ~3. Picking hominy for kernel-size resemblance trades a right protein figure for a wrong one. Kernel size is not a nutrient |
| cancha | `Corn nuts` (2708195) | Measured: 446 kcal and 15.64 g fat per 100 g. Corn nuts are deep-fried; cancha is dry-toasted. About +100 kcal and +13 g fat per 100 g on a food eaten by the handful |
| membrillo | `Quinces, raw` (168163) | Raw quince ~57 kcal / ~9 g sugar against membrillo's ~250 / ~60. The only quince row in the database is the wrong form of the food |
| panela | `Molasses` (168820) | Molasses is the syrup fraction: ~290 kcal against panela's ~380, with several times the potassium and iron. Panela is whole evaporated cane juice |
| linguiça | `Chorizo` (2706179) | Culturally adjacent, nutritionally not. Chorizo is pimentón-heavy and often markedly fattier. "Both are Iberian-descended pork sausage" is a genealogy, not a fat figure |
| queijo minas, queijo coalho, requeijão, Catupiry, queso llanero, queso costeño, queso sardo, queso cremoso | any `Cheese, mexican, queso …` row | Fat runs 3% to 28% across this set. Every match is carried by the shared word `queso`, which is a category noun. `queso sardo` (hard grating, ~35% fat) reaching `Queso Fresco` (fresh curd, ~20% fat, ten times the moisture) is the clearest case. Over-broad and culturally wrong at once |
| queijo coalho | halloumi | RESUME.md already records `halloumi` as returning nothing. Mapping one unreachable food onto another buys nothing |
| chicharrón | `Pork skin rinds` (2705902) / `Snacks, pork skins, plain` (167961) | Measured: 61.3 g protein / 31.3 g fat, against cracklings' 45.0 / 41.7. Skin-only is the wrong half of the animal for the dish as eaten |
| alpaca, llama, cuy | any `Game meat, …` row (rabbit 172521, beaver 175294) | Selecting a neighbour by "also a game animal" is the wrong-row-plausible-number failure. Camelid meat is notably leaner than most of that list |
| yerba mate, tereré | tea | Different plant, different caffeine and polyphenol profile, and both are ~0 kcal, so the mapping buys nothing while asserting an equivalence |
| guasacaca, llajua, pebre, chimichurri | `Salsa, NFS` | Herb-and-oil sauces (chimichurri is largely oil) against a tomato salsa. Eaten by the spoon, so leaving them unresolved costs near nothing and a wrong parent costs a fat figure |
| chuño, tunta | dehydrated potato flakes | Freeze-dried whole tuber, rehydrated before eating. The as-eaten mass and the dry row's density are different questions and the mapping silently answers the wrong one |
| tuna (fruit) | `Prickly pears, raw` | The word is a homograph with the fish and `tuna` alone already reaches `Fish, tuna, NFS` at 0.357. Encoding `tuna -> prickly pear` would break the far more common reading. Only the disambiguated `tuna fruit` / `higo chumbo` should ever carry it |
| sopaipilla (Chilean) | `Sopaipilla with syrup or honey` | Name matches, food does not: the Chilean one is a savoury pumpkin fry-bread, the USDA row is the sweetened New Mexican pastry. A `preparation_state_mismatch` that would survive a name-based fix |
| maíz morado / chicha morada | `Corn flour, whole-grain, blue (harina de maiz morado)` (168921) | Right maize, wrong product: a flour standing in for a sweetened infusion brewed from dried cobs. Kept as a reachability finding (SA-17), not encoded as a mapping |
| feijoada, moqueca, ajiaco, sancocho, bandeja paisa and every other composite dish | any single row | These are dishes. Invariant 5 and the model tier exist for exactly this; a dish→row mapping would let one number stand for a plate whose composition varies by household. Fix the ingredients instead |

---

# Notes

**The domain's shape, in one line.** 474 terms probed: `none` 293 (62%), `weak`
89 (19%), `ask` 35 (7%), `auto` 57 (12%). Strip out batch 5, which was
deliberately English-language target verification, and the four native-vocabulary
batches run **292 none / 72 weak / 12 ask / 12 auto out of 388** — **75% of a
South American food vocabulary returns an empty candidate list**, and only 3%
reaches the `auto` band. Not a bad match: no match. Ranking cannot help; recall
is zero.

**Almost none of it is a missing food.** The single largest cluster is beef cuts
— picanha, entraña, ojo de bife, asado de tira, bife de lomo, colita de cuadril,
vacío, matambre — in cuisines defined by beef, against a database carrying 55+
skirt rows and 40+ tenderloin rows. Every one has a USDA row and every one has
zero recall. The same holds for palmito, morcilla, mollejas, provoleta,
chicharrón, patacón, couve, feijão preto, mandioca and goiabada. This domain is
overwhelmingly **reachability**, not entity gaps.

**Three mechanisms produce nearly all of it**, and only the first is a knowledge
problem:

1. *No global synonym layer.* The Spanish or Portuguese word has nowhere to live.
   This is the gap RESUME.md already identified.
2. *Length dilution.* Measured here at its most extreme: `bunuelo` scores
   **0.156** against a row spelling "bunuelos", `lulo` **0.125** against a row
   spelling "(lulo)", `tri-tip` **0.099** against "tri-tip roast", the correct
   `Restaurant, Latino, arepa` row **0.12**. USDA's `Restaurant, Latino, …`
   family is precisely the set of Latin American dishes this domain needs and
   the prefix buries every one of them.
3. *Diacritics.* Seven measured pairs; the accented form never once scored
   higher and usually returned nothing at all (SA-48). Upstream of lookup, so no
   table entry can fix it.

**The surprise: the worst finding is in English.** `sweet potato` auto-matches
`Pie, sweet potato` at 0.812, beating `Sweet potato, NFS` by 0.047 — 2.3x the
energy, 4x the sugar, no model consulted, alias cached forever with no command
to repoint it. `brown rice` auto-matches `Flour, rice, brown`. `white rice
cooked` auto-matches the glutinous cultivar. All three are the same shape: **the
processed-product row outranking the plain-food row for the plain-food query**,
and the existing `unrequested_qualifier` guard cannot see it because the wrong
word sits in the *first* segment, which that guard deliberately skips. A guard
asking "is the head noun of this description the thing the query names?" would
catch all three. This was found while verifying targets for Spanish synonyms and
would not have been found by probing Spanish alone.

**The second surprise: the foreign name selects the processed product.** Three
independent instances — `guanabana -> Guanabana nectar, canned` while `soursop
-> Soursop, raw`; `acai -> Fruit juice, acai blend` with no raw row at all;
`naranjilla -> Naranjilla (lulo) pulp, frozen`. USDA tends to name its processed
rows in the source language and its raw rows in English, and length dilution
then does the rest. Any synonym written for a Latin American fruit must pin the
**raw** row explicitly or it will encode the sweetened one.

**What this means for the fix.** Batch 5 is the good news: the *defining
ingredients* mostly resolve in English — black beans 0.733, pork belly 1.000,
dried shrimp 1.000, coconut milk 1.000, cashews 0.667, lime juice 0.733,
octopus 1.000. So a model tier that decomposes an unreachable dish into
ingredients recovers most of this domain, **provided** seven ingredients are
repaired first: dendê, cassava flour, açaí, choclo, ají, masarepa and the beef
cuts. Those seven are the carbonara/guanciale cases here — the dish is
unreachable *and* its signature ingredient is unreachable or resolves to the
wrong lipid profile.

**One caution for whoever writes the synonym table.** `bife de chorizo` (SA-25)
is the trap. A rule keyed on `chorizo` fires inside it and turns a lean strip
steak into a fatty pork sausage, silently, forever. Whole-phrase keys must
outrank substring keys, and this domain supplies at least four more of the same
shape: `bife de lomo` vs `lomo`, `tuna fruit` vs `tuna`, `arepa de queso` vs
`queso`, `maiz morado` vs `maiz`.
