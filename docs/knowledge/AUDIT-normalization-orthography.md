# AUDIT-normalization-orthography

Domain: cross-cutting. Question owned: **does the same food fail under a
different spelling?**

Method: `scripts/probe_knowledge.py` for the resolver verdict, plus read-only
SQL counting *how many rows a spelling can reach at all* (`ILIKE` /
`similarity`), because a top-hit comparison hides the case where a variant
reaches one lucky row out of 150.

Started 28 Aug 2026. Appended after every batch; nothing here is held in
memory only.

## Verdict counts

| batch | none | weak | ask | auto | n |
|---|---|---|---|---|---|
| 1 diacritics | 26 | 18 | 10 | 9 | 63 |
| 2 british/american | 16 | 38 | 16 | 21 | 91 |
| 3 plurals | 2 | 14 | 34 | 31 | 81 |
| 4 transliteration | 58 | 18 | 12 | 12 | 100 |
| 5 abbrev/menu/possessive | 18 | 31 | 17 | 16 | 82 |
| **total** | **120** | **119** | **89** | **89** | **417** |

## Findings

### F0 (structural, measured first) — the food table contains ZERO accented characters

```
select count(*) from food;                          -> 13651
select count(*) from food where description ~ '[^ -~]';  -> 2
select fdc_id, ascii(regexp_replace(description,'[ -~]','','g')) ...
  2710826 | 160     <- U+00A0 non-breaking space
  2727573 | 160     <- U+00A0 non-breaking space
```

Both "non-ASCII" rows are non-breaking spaces. **Not one row in USDA as loaded
carries an accented letter.** `pg_extension` holds `plpgsql, pg_trgm,
btree_gin` — **`unaccent` is not installed**, and `search_foods` applies no
folding of its own: it goes straight to `to_tsvector('english', ...)` and
`similarity()`, both of which treat `é` and `e` as different characters.

So the accented spelling can never win and frequently loses everything. This is
not a per-food gap; it is one missing normalisation step with a measured blast
radius below.

### F1 — DIACRITICS: accented spelling is strictly worse in 17 of 20 tested pairs

Verbatim, accented row immediately under its unaccented twin:

```
weak  jalapeno                           0.429  Peppers, jalapeno, raw
none  jalapeño                           -      (nothing)
auto  jalapeno pepper                    0.700  Peppers, jalapenos
ask   jalapeño pepper                    0.545  Peppers, jalapenos
auto  creme brulee                       1.000  Creme brulee
none  crème brûlée                       -      (nothing)
ask   puree                              0.545  Prune puree
none  purée                              -      (nothing)
auto  tomato puree                       0.650  Tomato, puree, canned
weak  tomato purée                       0.435  Tomato, puree, canned
weak  acai                               0.217  Fruit juice, acai blend
none  açaí                               -      (nothing)
weak  pate                               0.294  Liver, paste or pate
none  pâté                               -      (nothing)
ask   gruyere                            0.533  Cheese, gruyere
none  gruyère                            -      (nothing)
ask   souffle                            0.615  Lime souffle
weak  soufflé                            0.400  Lime souffle
auto  sauteed onions                     0.682  Onions, yellow, sauteed
ask   sautéed onions                     0.480  Onions, yellow, sauteed
weak  consomme                           0.188  Soup, beef broth bouillon and consomme, canned, condensed
none  consommé                           -      (nothing)
weak  anejo                              0.222  Cheese, mexican, queso anejo
none  añejo                              -      (nothing)
weak  queso anejo                        0.444  Cheese, mexican, queso anejo
weak  queso añejo                        0.368  Queso Asadero          <- different cheese
auto  pina colada                        1.000  Pina Colada
ask   piña colada                        0.600  Pina Colada
auto  cheese souffle                     1.000  Cheese souffle
auto  cheese soufflé                     0.765  Cheese souffle
weak  jamon                              0.429  Jam
weak  jamón                              0.429  Jam
weak  flambe / flambé                    0.333  Flan   (both equally wrong)
```

kind: reachability_gap | category: bad_normalization | confidence: high

`crème brûlée` typed correctly returns **nothing at all** while the row
`Creme brulee` sits in the table at similarity 1.000. Same for `purée`,
`gruyère`, `consommé`, `añejo`, `pâté`, `açaí`, `jalapeño`. A user who spells
their food properly is punished for it.

### F2 — DIACRITICS produce a WRONG-CONFIDENT MATCH, not merely a miss

The dangerous case. An accent does not only demote the right row; it can
promote a different one past the auto gate.

```
auto  chicken liver pate                 0.760  Pate, chicken liver, canned
auto  chicken liver pâté                 0.737  Liver, chicken
```

Both are `auto` — no model consulted, and an alias is cached forever
(`CLAUDE.md`, "The alias tier caches these forever"). The accented spelling
silently logs **plain chicken liver** instead of **pâté**:

```
 fdc_id  | description                 | kcal |  fat
  172928 | Pate, chicken liver, canned |  201 | 13.10
 2706154 | Liver, chicken              |  189 |  8.69
```

kind: wrong_confident_match | category: bad_normalization | confidence: high

The energy gap is modest (6%) but the fat gap is 34% low, and the semantic
error is total: pâté is liver plus fat, butter or cream. It is exactly the
"plausible number from the wrong row" class, arriving through orthography.

### F3 — ENTITY GAPS surfaced during the diacritic sweep (both spellings return nothing)

These are not normalisation failures — neither spelling reaches anything, so
folding accents would not help them. Recorded so a later taxonomy pass has
them, not proposed here:

```
none  doner / döner / doner kebab / döner kebab   -  (nothing)
none  zurek / żurek                               -  (nothing)
none  banh mi / bánh mì                           -  (nothing)
none  emmental / emmentaler                       -  (nothing)
none  manchego                                    -  (nothing)
none  mole poblano                                -  (nothing)
none  tourtiere / tourtière                       -  (nothing)
none  entrecote / entrecôte                       -  (nothing)
none  creme fraiche / crème fraîche               -  (nothing)
```

`creme fraiche` is the notable one: the *unaccented* spelling returns nothing
either, so this is a genuine entity gap and out of this domain's scope
(neighbour: `Cream, fluid, heavy whipping` / `Sour cream, cultured`).

### Method note — reachable-row counting

Top-hit comparison hides the case where a variant reaches one lucky row out of
150. Reachability = the row count satisfying `search_foods`' exact WHERE clause
(`to_tsvector @@ plainto_tsquery` OR `description % q`), run read-only:

```
      q       | covers_rows | trgm_rows | reachable | best_sim
 yogurt       |         153 |        20 |       153 |    0.636
 yoghurt      |           0 |         4 |         4 |    0.357
 shrimp       |          69 |        27 |        69 |    0.636
 prawn        |           0 |         0 |         0 |
 prawns       |           0 |         0 |         0 |
 zucchini     |          13 |         5 |        13 |    0.600
 courgette    |           0 |         0 |         0 |
 eggplant     |          15 |        11 |        15 |    0.692
 aubergine    |           0 |         0 |         0 |
 arugula      |           3 |         3 |         3 |    0.667
 rocket       |           0 |         0 |         0 |
 beets        |          25 |         7 |        26 |    0.600
 beetroot     |           0 |         0 |         0 |
 rutabaga     |           6 |         4 |         6 |    0.750
 swede        |           0 |         0 |         0 |
 snow peas    |           0 |         2 |         2 |    0.438
 mangetout    |           0 |         0 |         0 |
 cilantro     |           2 |         2 |         2 |    0.692
 coriander    |           4 |         3 |         4 |    0.476
 ground beef  |          59 |        41 |        82 |    1.000
 minced beef  |           0 |         3 |         3 |    0.438
 chili        |          44 |         9 |        44 |    0.600
 chilli       |           0 |         2 |         2 |    0.417
 chile        |           6 |         2 |         8 |    0.385
 green onion  |           6 |         6 |         9 |    0.611
 spring onion |           1 |         6 |         7 |    0.375
 scallion     |           2 |         0 |         2 |    0.200
```

This **confirms and extends** the prior agent's two numbers: `yoghurt` reaches
4 of 153 `yogurt` rows, `prawn` reaches **0** of 69 `shrimp` rows.

### F4 — BRITISH vocabulary is not partially reachable, it is unreachable

Eleven British words return **zero rows** while USDA holds the food under its
American name:

```
none  prawn / prawns / king prawns / tiger prawn   ->  0 rows   (shrimp: 69)
none  courgette                                    ->  0 rows   (zucchini: 13)
none  aubergine / roasted aubergine                ->  0 rows   (eggplant: 15)
none  rocket                                       ->  0 rows   (arugula: 3)
none  beetroot                                     ->  0 rows   (beets: 26)
none  swede                                        ->  0 rows   (rutabaga: 6)
none  mangetout                                    ->  0 rows   (snowpeas: 2)
none  porridge                                     ->  0 rows   (Oatmeal, NFS)
none  sultanas                                     ->  0 rows   (Raisins, golden)
none  rasher                                       ->  0 rows   (bacon)
none  gammon                                       ->  0 rows   (cured ham)
none  natural yoghurt                              ->  0 rows
```

kind: reachability_gap | category: missing_synonym | confidence: high

Not a ranking problem and not a USDA gap: recall is 0, so no ranking function
can reach it (RESUME.md, "unreachable by any ranking function").

Near misses in the same family, where the British word reaches something but
the wrong thing:

```
weak  grilled prawns     0.364  Shrimp, grilled          <- right row, below the floor
weak  grilled courgette  0.400  Fish, cod, grilled       <- carried entirely by "grilled"
weak  roasted beetroot   0.400  Beef, roast              <- carried entirely by "roast"
weak  rocket salad       0.353  Salmon salad             <- "rocket" contributed nothing
weak  crisps             0.357  Crisp, peach
weak  double cream       0.353  Cake, cream
weak  single cream       0.353  Cake, cream
weak  icing sugar        0.267  Italian Ice, no sugar added
weak  caster sugar       0.353  Sugar, NFS
weak  cornflour          0.333  Flour, coconut
weak  plain flour        0.207  Snacks, pretzels, hard, plain, made with unenriched flour, salted
weak  bacon rasher       0.353  Bacon bits
```

All below `WEAK_MATCH_SIMILARITY` = 0.45, so these escalate rather than
mis-log. The `label_absent` guard would also block them. The system is failing
safely here — but it is failing on every British word, on every meal.

### F5 — `oatmeal` auto-matches an OATMEAL PIE, and which row wins is a coin toss

The worst single result in this domain.

```
auto  oatmeal   0.667  Pie, oatmeal          (limit 5, production)
auto  oatmeal   0.667  Oatmeal, NFS          (limit 6)
```

The scores are identical to five decimal places and every tie-break in the
`ORDER BY` is exhausted:

```
 fdc_id  | description   | data_type         | precedence | sim    | score   | has_energy
 2708380 | Oatmeal, NFS  | survey_fndds_food |          3 | 0.6667 | 0.98207 | t
 2708016 | Pie, oatmeal  | survey_fndds_food |          3 | 0.6667 | 0.98207 | t
```

Same score, same data_type, same precedence, both with energy. The winner is
decided by the plan, and the plan changes with `LIMIT`. Production calls
`db.search_foods(q, limit=5, ...)` (`nutrai/llm/parse.py:341`), and at limit 5
it returns the pie, five runs out of five.

```
 description   | kcal |  fat  | sugar
 Pie, oatmeal  |  396 | 16.02 | 32.08
 Oatmeal, NFS  |   76 |  2.63 |  0.17
```

kind: wrong_confident_match | category: bad_fuzzy_matching | confidence: high

0.667 clears `AUTO_MATCH_SIMILARITY` = 0.62, so **no model is consulted and an
alias is written that is never re-checked**. A 250 g bowl of porridge logs as
990 kcal and 80 g of sugar instead of 190 kcal and 0.4 g — every morning, for
ever. `label_absent` does not fire ("oatmeal" is present in the description),
`unrequested_qualifier` does not fire ("Pie" is the *first* segment, and the
guard only checks segments after the first — see CLAUDE.md), and
`state_conflicts` has nothing to say. Every existing guard passes it.

The British spelling `porridge` returns nothing, so the user has no safe way to
type this food at all.

### F6 — `biscuit` auto-matches a KFC menu item

```
auto  biscuit    0.667  KFC, biscuit
ask   biscuits   0.500  KFC, biscuit
auto  cookie     0.636  Cookie, NFS
weak  digestive biscuit  0.364  KFC, biscuit
```

```
 description  | kcal |  fat  | sugar
 KFC, biscuit |  358 | 17.05 |  4.04
 Cookie, NFS  |  492 | 24.72 | 32.89
```

kind: wrong_confident_match | category: culturally_incorrect_mapping | confidence: high

A British "biscuit" is a cookie (492 kcal, 33 g sugar); an American one is a
savoury quick bread (358 kcal, 4 g sugar). The bare word auto-matches a
*branded restaurant row* with no model consulted. Note this is **not** fixable
by a synonym — see Deliberately rejected.

### F7 — the chilli / chili / chile three-way, measured

The sharp case, and the answer is: **do not fold it.**

```
weak  chilli             0.417  Chili, NFS                        <- the DISH
ask   chili              0.600  Chili, NFS                        <- the DISH
weak  chile              0.250  Sauce, hot chile, sriracha
weak  red chilli         0.333  Peppers, hot chili, red, raw      <- correct
ask   red chili pepper   0.615  Peppers, hot chili, red, raw      <- correct
weak  green chilli       0.393  Peppers, chili, green, canned
auto  chili powder       0.650  Spices, chili powder
weak  chilli flakes      0.308  Cereal, wheat flakes              <- absurd
weak  chilli oil         0.333  Corn oil
weak  chilli con carne   0.333  Chili con carne with beans, canned entree
weak  chili con carne    0.378  Chili con carne with beans, canned entree
```

Sense split of the 44 rows covering "chili", counted:

```
 dish/other  | 32   Chili, NFS | Chili with meat and beans | Chili hot dog ... | APPLEBEE'S, chili
 pepper      |  8   Peppers, hot chili, red, raw | Peppers, chili, green, canned | ...
 spice/sauce |  4   Spices, chili powder | Sauce, tomato chili sauce, bottled ...
```

kind: reachability_gap | category: other_semantic_failure | confidence: high

**73% of USDA's "chili" rows are the stew.** A British user typing `chilli`
means the pepper roughly always; an American typing `chili` means the stew
roughly always. Folding `chilli -> chili` would take a query that currently
lands *below* the weak floor (0.417, escalates to the model, which sees the
right list) and push it toward the dish. `Chili, NFS` is 118 kcal/100 g of
meat and beans; `Peppers, hot chili, red, raw` is 40 kcal of vegetable. The
current failure is safe; the "fix" would make it unsafe.

`chilli flakes -> Cereal, wheat flakes` at 0.308 is the standout absurdity, and
it is also harmless: below the floor, so it escalates.

### F8 — `mince` (BR) reaches only `Ham, minced`

```
weak  mince         0.417  Ham, minced
weak  minced beef   0.438  Ham, minced
weak  minced lamb   0.438  Ham, minced
weak  beef mince    0.333  Beef, NFS
weak  pork mince    0.169  Luncheon meat, pork with ham, minced, canned, includes Spam (Hormel)
auto  ground beef   1.000  Beef, ground
auto  ground lamb   1.000  Lamb, ground
```

reachable: `ground beef` 82 rows, `minced beef` 3 rows.

kind: reachability_gap | category: missing_synonym | confidence: high

`minced lamb` reaching `Ham, minced` is a species error carried entirely by the
word "minced"; `minced beef` scores *higher* against the ham row (0.438) than
`beef mince` does against `Beef, NFS` (0.333). All are below the floor today,
so they escalate — but `minced beef -> ground beef` is a mechanically safe
rewrite with no counterexample.

### F9 — PLURALS: retrieval is plural-safe, RANKING is not, and the SINGULAR is the dangerous one

The most generalisable result in this audit, and the opposite of what I
expected going in.

`to_tsvector('english', ...)` stems both sides, so a regular plural retrieves
**exactly the same row set**:

```
      q       | covers_rows | trgm_rows | reachable | best_sim
 almond       |          71 |        19 |        71 |    0.636
 almonds      |          71 |        19 |        71 |    0.667
 olive        |          22 |         7 |        22 |    0.667
 olives       |          22 |         5 |        22 |    0.636
 tomato       |         347 |        18 |       348 |    0.636
 tomatoes     |         347 |        30 |       348 |    0.692
 strawberry   |          64 |        34 |        66 |    0.733
 strawberries |          64 |        40 |        83 |    0.813
```

Identical `covers_rows` in every regular pair. But `similarity()` is raw string
comparison, it is not stemmed, and it is what `AUTO_MATCH_SIMILARITY` gates on.
So the *same* candidate set is ordered differently, and it lands differently
either side of 0.62.

**USDA names raw whole produce in the plural and its processed derivatives in
the singular** — `Tomatoes, raw` but `Tomato, roma`; `Strawberries, raw` but
`Pie, strawberry`; `Almonds, NFS` but `Oil, almond`. So the singular query
systematically pulls the processed row to the head:

```
auto  strawberry     0.733  Pie, strawberry        auto  strawberries  0.812  Strawberries, raw
auto  blueberry      0.714  Pie, blueberry         auto  blueberries   0.750  Blueberries, raw
auto  cranberry      0.625  Cranberry sauce        auto  cranberries   0.750  Cranberries, raw
auto  olive          0.667  Olive oil              auto  olives        0.636  Olives, NFS
auto  almond         0.636  Oil, almond            auto  almonds       0.667  Almonds, NFS
auto  walnut         0.636  Oil, walnut            ask   walnuts       0.471  Nuts, walnuts, glazed
```

```
 description        | kcal |  fat        description        | kcal |  fat
 Pie, strawberry    |  289 | 11.60       Strawberries, raw  |   36 |  0.30
 Pie, blueberry     |  300 | 15.52       Blueberries, raw   |   64 |  0.33
 Cranberry sauce    |  159 |  0.15       Cranberries, raw   |   46 |  0.13
 Olive oil          |  900 |100.00       Olives, NFS        |  116 | 10.90
 Oil, almond        |  884 |100.00       Almonds, NFS       |  598 | 52.54
 Oil, walnut        |  884 |100.00
```

kind: wrong_confident_match | category: bad_fuzzy_matching | confidence: high

`olive` -> `Olive oil` is **7.8x the energy and 9x the fat** of `Olives, NFS`,
taken with no model consulted and cached as an alias for ever. `strawberry` ->
`Pie, strawberry` is 7.9x. A person writing "50 g olive" in a salad gets 450
kcal instead of 58.

The same shape appears one tier down, where it is harmless because it
escalates: `apple -> Pie, apple` (0.600), `carrot -> Muffin, carrot` (0.500),
`onion -> Bread, onion` (0.500), `banana -> Banana, baked` (0.600), `egg ->
Bread, egg` (0.400), `bean -> Soup, bean` (0.500), `lentil -> Soup, lentil`
(0.583), `berry -> Pie, berry` (0.600), `noodle -> Soup, noodle, NFS` (0.467),
`oat -> Oil, oat` (0.571). Ten more instances of exactly the same mechanism,
all sitting just below the gate. The gate is what is protecting them, not any
guard, and 0.62 is documented as arbitrary (CLAUDE.md).

### F10 — IRREGULAR plurals break retrieval outright

The Snowball English stemmer handles `-s`/`-es`/`-ies` and nothing else:

```
none  loaves    -  (nothing)        loaf     -> 36 rows
none  geese     -  (nothing)        goose    -> 13 rows
weak  leaves    0.438  Taro leaves, raw       leaf -> 22 rows / leaves -> 33 rows
```

`loaf`/`loaves` and `goose`/`geese` retrieve disjoint sets; `leaf`/`leaves`
retrieve *different* sets (22 vs 33), so neither direction subsumes the other.

kind: reachability_gap | category: bad_normalization | confidence: high
(low practical impact — few foods are named this way — recorded for completeness)

### F11 — plural forms that are strictly worse than their singular

The asymmetry runs both ways, and where the plural loses it loses hard:

```
ask   anchovy      0.615  Fish, anchovy          weak  anchovies  0.353  Fish, anchovy
ask   sardine      0.533  Sardine sandwich       weak  sardines   0.429  Fish, sardines, canned
ask   prune        0.545  Prune puree            weak  prunes     0.385  Prune puree
weak  egg          0.400  Bread, egg             weak  eggs       0.250  Bread, egg
ask   bay leaf     0.562  Spices, bay leaf       weak  bay leaves 0.421  Spices, bay leaf
weak  cherry tomato 0.389 Tomato, roma           ask   cherry tomatoes 0.450 Tomatoes, raw
```

`anchovies` and `anchovy` reach the same 3 rows; only the score moves, by 0.26,
which is four times the width of the entire ask/auto band. Note `sardines`
finds the *better* row (`Fish, sardines, canned`) at the *lower* score than
`sardine` finds a sandwich.

kind: reachability_gap | category: bad_fuzzy_matching | confidence: high

### F12 — TRANSLITERATION: USDA carries exactly ONE spelling, and every variant is a cliff

Not a gradient. The spelling USDA chose scores 0.5-1.0; every other spelling of
the same word scores near zero or returns nothing:

```
   query      reachable   verdict / top row
 borscht          1       ask  0.615  Soup, borscht
 borsch           1       weak 0.429  Soup, borscht
 borshch          0       none
 barszcz          0       none
 hummus           5       ask  0.538  Hummus, plain
 houmous          0       none
 hommus           0       none
 humus            ?       weak 0.357  Hummus, plain
 tahini           5       auto 1.000  Tahini
 tahina           1       ask  0.556  Tahini
 tehina           0       none
 falafel          3       auto 1.000  Falafel
 felafel          1       ask  0.500  Falafel
 tzatziki         1       auto 0.692  Tzatziki dip
 dzatziki         ?       ask  0.467  Tzatziki dip
 tsatsiki         0       none
 kimchi           2       auto 1.000  Kimchi
 kimchee          1       ask  0.500  Kimchi
 pierogi          1       auto 1.000  Pierogi
 perogi           1       ask  0.500  Pierogi
 pierogies        ?       auto 0.636  Pierogi
 kefir            3       auto 1.000  Kefir
 kephir           1       weak 0.300  Kefir
 matzo            7       weak 0.400  Crackers, matzo
 matzah           0       none
 matzoh           0       none
 challah          2       weak 0.444  Bread, egg, Challah
 hallah           0       none
 naan             3       ask  0.455  Bread, naan
 nan              0       none
 tteokbokki       ?       weak 0.423  Dukboki or Tteokbokki, Korean
 ddeokbokki/topokki/tokbokki  0   none
 couscous         ?       auto 0.636  Couscous, dry
 cous cous        ?       ask  0.455  Couscous, dry
 kielbasa         4       weak 0.310  Kielbasa, fully cooked, grilled
 kiełbasa         0       none          <- Polish spelling, and this is a Polish user
```

kind: reachability_gap | category: spelling_transliteration_failure | confidence: high

Note the shape: the variant nearly always reaches **one** row by trigram alone
where the USDA spelling covers several. `houmous` (the standard British
supermarket spelling) reaches **zero** of the five `hummus` rows.

### F13 — `kebab` reaches nothing; USDA spells it `kabob`

```
none  kebab         ->  0 rows
none  kebap         ->  0 rows
none  kabab         ->  0 rows
none  shish kebab   ->  0 rows
weak  kabob   0.122  Fish shish kabob with vegetables, excluding potatoes   ->  9 rows
```

The nine rows USDA does hold:

```
 Beef / Pork / Lamb / Chicken or turkey / Shrimp / Fish shish kabob with vegetables
 Lamb, cubed for stew or kabob (leg and shoulder), ... raw / braised / broiled
```

kind: reachability_gap | category: spelling_transliteration_failure | confidence: high

`kebab` is the near-universal spelling outside US government datasets. Nine
usable rows are invisible to it. (`doner kebab` from batch 1 also returned
nothing — that one is a genuine entity gap, not this.)

### F14 — `beet soup` auto-matches `Soup, beef`

```
auto  beet soup    0.667  Soup, beef
ask   borscht      0.615  Soup, borscht
none  beetroot     -      (nothing)
```

```
 description   | kcal | protein | fat
 Soup, beef    |   47 |    3.28 | 2.05
 Soup, borscht |   20 |    0.52 | 0.37
```

kind: wrong_confident_match | category: bad_fuzzy_matching | confidence: high

`beet soup` has `covers_rows = 0` — no row contains both words as stemmed
tokens — so the COVERS_BOOST partition never engages and pure trigram decides.
"beet soup" and "Soup, beef" differ by one transposed letter, so trigram
overlap is high and the meaning inverts: a vegetable soup logs as a meat soup,
at 2.4x the energy and 6x the protein, **with no model consulted**. Meanwhile
`Soup, borscht` — the correct row — is in the table, and the British/Polish
spelling of its main ingredient (`beetroot`, `barszcz`) returns nothing.

This is the carbonara/guanciale shape exactly: the dish is reachable under one
spelling, its defining ingredient under none.

### F15 — `paneer` auto-matches a spinach curry while `Cheese, paneer` sits in the table

```
auto  paneer         0.636  Palak Paneer
auto  cheese paneer  1.000  Cheese, paneer
```

```
 fdc_id  | description   | kcal | protein | fat
 2705740 | Cheese, paneer|  299 |   15.86 | 15.52
 2709631 | Palak Paneer  |  101 |    5.42 |  7.02
```

kind: wrong_confident_match | category: ingredient_vs_dish_ambiguity | confidence: high

Only two rows contain the word, and the bare ingredient name auto-matches the
composite dish — 3x the energy and 3x the protein wrong, in the direction of
*under*-reporting, and cached. The user must know to type "cheese paneer" to
get the cheese. Same mechanism as F9's `olive -> Olive oil`: the ingredient
name is shorter than the ingredient's own USDA row and longer-named dishes win
on trigram.

### F16 — transliteration ENTITY GAPS (all spellings return nothing)

Checked by ingredient and category as well as by name; recorded for the
taxonomy pass rather than proposed here:

```
shawarma / shwarma / schawarma       halloumi / haloumi / halumi
char siu / cha siu / chashao         labneh / labne
gochujang / kochujang                baba ganoush / ghanoush / babaganush
bulgogi                              quark / tvorog / twarog / twaróg
latke / latkes                       smetana
ayran                                lassi
harissa                              zaatar / za'atar / zatar
sumac / sumak                        gyoza / jiaozi
udon                                 kasha
```

`quark`/`twaróg` is the one to flag: the nearest reachable rows are
`Cottage cheese, farmer's` (ask 0.609 for "farmer cheese") and
`Cheese, cottage, NFS` (auto 0.778) — plausible but not the same food, and
mapping it belongs to the taxonomy domain, not this one.

### F17 — `avocado` auto-matches `Oil, avocado`

The single worst ratio measured, and it needs no plural, no accent and no
foreign word to trigger — just the bare English name of a common food.

```
auto  avocado    0.667  Oil, avocado
weak  avacado    0.333  Oil, avocado        <- the typo still points at the oil
```

```
 fdc_id | description  | nutrient_id | amount
 173573 | Oil, avocado |        1008 |    884   kcal
 173573 | Oil, avocado |        1004 |    100   g fat
 2709223| Avocado, raw |             |    160   kcal / 14.66 g fat
```

kind: wrong_confident_match | category: ingredient_vs_dish_ambiguity | confidence: high

`Avocado, raw` exists (2709223). Half an avocado, ~100 g, logs as **884 kcal
and 100 g of fat** instead of 160 kcal and 14.7 g — with no model consulted,
and an alias written that is never re-checked.

Together with `olive -> Olive oil` (900 kcal), `almond -> Oil, almond` (884)
and `walnut -> Oil, walnut` (884) this is one repeating mechanism, not four
coincidences: **`Oil, X` is a short description, and short descriptions win on
trigram similarity** (RESUME.md: r = -0.87 to -0.94 between similarity and
description length). Every food that has a USDA oil row is exposed.

### F18 — `chicken with rice` auto-matches `Chicken curry with rice`

```
auto  chicken with rice   0.783  Chicken curry with rice
ask   chicken w/ rice     0.583  Chicken curry with rice
```

```
 Chicken curry with rice               | 116 kcal | 4.00 g fat
 Chicken or turkey and rice, no sauce  | 149 kcal | 5.84 g fat
```

kind: wrong_confident_match | category: other_semantic_failure | confidence: high

An unrequested qualifier — "curry" — that the `unrequested_qualifier` guard
cannot see, because that guard splits on commas and inspects segments after the
first (CLAUDE.md), and this description has no comma at all. The right row
exists. The error is modest in energy but the entry then reads back to the user
as a curry he did not eat.

### F19 — ABBREVIATIONS fail totally, and that is the safe failure

```
none  EVOO / evoo / veg / seasonal veg / tbsp / tsp / chx / pb / pb&j
none  avo / guac / parm / mozz
weak  mayo    0.128  Salad dressing, KRAFT Mayo Light Mayonnaise
weak  choc    0.300  Chorizo
weak  chx breast 0.333  Bread, cheese
weak  sm fries   0.429  Yuca fries
ask   grd beef   0.538  Gravy, beef
ask   lg coffee  0.533  Coffee, Latte
```

against their expansions:

```
auto  extra virgin olive oil            1.000  Oil, olive, extra virgin
auto  boneless skinless chicken breast  0.879  Chicken, breast, boneless, skinless, raw
ask   bnls sknls chicken breast         0.459  Chicken breast, stewed, skin eaten
auto  chocolate chip                    0.800  Chocolate chips
auto  guacamole                         0.714  Guacamole, NFS
auto  mayonnaise                        0.647  Mayonnaise, light
auto  chocolate milk                    0.789  Chocolate milk, NFS
```

kind: reachability_gap | category: missing_synonym | confidence: high (for the
expansions), and note the failure mode is benign — every abbreviation lands at
`none` or `weak`, so it escalates to the model tier rather than mis-logging.
`choc -> Chorizo` and `chx breast -> Bread, cheese` are the funny ones and both
are safely below the floor.

Two caveats worth recording: `grd beef -> Gravy, beef` (0.538) and
`lg coffee -> Coffee, Latte` (0.533) sit in the `ask` band, so the model tier
would see a candidate list headed by the wrong food.

### F20 — MENU LANGUAGE degrades safely; nothing to fix

```
none  catch of the day / chef special / daily special
ask   side salad       0.500  McDONALD'S, Side Salad
weak  house salad      0.375  Salmon salad
weak  garden salad     0.188  Asian chicken or turkey garden salad, ...
ask   house dressing   0.450  Rice dressing
weak  soup of the day  0.321  Soup, cream of tomato
weak  mixed grill      0.333  Fish, white, mixed species, grilled
weak  side of fries    0.316  Yuca fries
weak  steamed greens   0.364  Oysters, steamed
```

kind: (no finding) | confidence: high that no action is warranted

Menu phrases are genuinely underdetermined — "seasonal veg" has no correct row
— and every one of them lands at or below the `ask` band. This is the resolver
behaving exactly as designed. `side salad -> McDONALD'S, Side Salad` at 0.500
is the only one to watch: it is 0.12 below the auto gate, and the gate is
documented as arbitrary.

### F21 — POSSESSIVES are already handled; do not build anything

```
auto  shepherd's pie   1.000  Shepherd's pie
auto  shepherd pie     0.929  Shepherd's pie
auto  shepherds pie    0.750  Shepherd's pie
ask   sheperds pie     0.500  Shepherd's pie      <- misspelling, escalates
auto  caesar dressing  1.000  Caesar dressing
auto  cesar dressing   0.722  Caesar dressing
auto  eggs benedict    0.800  Egg, Benedict
auto  egg benedict     1.000  Egg, Benedict
ask   brocoli          0.500  Broccoli, raw
```

kind: (no finding) | confidence: high

All three possessive forms reach the same correct row above the auto gate.
Trigram similarity absorbs an apostrophe and a missing `s` without help.
Single-character typos (`brocoli`, `cesar`) degrade one band and still point at
the right row. **This is the one part of the domain that needs no work**, and
saying so is as much of the answer as the failures are.

Adjacent failures that are *not* possessive failures:

```
weak  cottage pie      0.364  Cheese, cottage, NFS   <- beef dish -> a cheese
weak  hunters chicken  0.400  Fat, chicken
weak  caesar salad     0.448  Salad dressing, caesar dressing, regular
weak  fish and chips   0.333  Fish, anchovy
weak  full english     0.400  Muffin, English
none  bangers and mash / toad in the hole
```

All below the floor, all escalate. `cottage pie -> Cheese, cottage` is the
clearest illustration that a wrong answer here costs nothing while the gate
holds.

## Proposals

## Deliberately rejected

## Notes
