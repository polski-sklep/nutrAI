# AUDIT-middle-east-central-asia-america

28 Aug 2026. Domain: Persian/Iranian, Iraqi, Gulf, Yemeni, Afghan, Uzbek,
Kazakh, Uyghur, plus American regional (New England/Louisiana/Texas/Carolina/
Memphis/Cincinnati/Philadelphia/Chicago/Southwest/Hawaii).

Method: `scripts/probe_knowledge.py`, batched through `--file`. Every claim
below is pasted probe output or a read-only `SELECT` against the live database.
No writes. The integration suite was not run.

For every dish probed, its defining ingredients were probed separately — the
carbonara/guanciale failure is a dish that resolves while its signature
ingredient resolves to nothing.

## Verdict counts

Running tally, updated each batch. Per-batch figures are the probe's own
summary lines, recorded at the time each batch ran.

| batch | terms | none | weak | ask | auto |
|---|---|---|---|---|---|
| 1 Persian | 91 | 58 (64%) | 20 (22%) | 12 (13%) | 1 (1%) |
| 2 Gulf/Iraqi/Yemeni | 91 | 62 (68%) | 17 (19%) | 9 (10%) | 3 (3%) |
| 3 Afghan/Central Asian | 91 | 60 (66%) | 20 (22%) | 5 (5%) | 6 (7%) |
| 4 American regional | 95 | 31 (33%) | 39 (41%) | 13 (14%) | 12 (13%) |
| 5 defining ingredients | 96 | 4 (4%) | 21 (22%) | 29 (30%) | 42 (44%) |
| 6 variants + target checks | 92 | 17 (18%) | 31 (34%) | 14 (15%) | 30 (33%) |
| 7 dish ingredients | 53 | 1 (2%) | 13 (25%) | 14 (26%) | 25 (47%) |
| **total** | **609** | **233 (38%)** | **161 (26%)** | **96 (16%)** | **119 (20%)** |

## Findings

### F1 — `kebab` is spelled `kabob` in USDA, and nothing bridges the two

This is the widest-blast-radius finding in the domain: it breaks Persian,
Turkish, Levantine, Afghan, Uzbek and Uyghur queries at once.

```
none  kebab                              -      (nothing)
weak  kabob                              0.122  Fish shish kabob with vegetables, excluding potatoes
none  shish kebab                        -      (nothing)
weak  shish kabob                        0.245  Pork shish kabob with vegetables, excluding potatoes
weak  lamb kebab                         0.312  Lamb, chop
weak  beef kebab                         0.333  Beef, NFS
ask   chicken kebab                      0.500  Chicken kiev
auto  ground beef kebab                  0.667  Beef, ground
```

USDA has exactly nine rows and every one of them spells it `kabob`:

```
SELECT fdc_id,data_type,description FROM food WHERE description ILIKE '%kabob%';
2706730|survey_fndds_food|Beef shish kabob with vegetables, excluding potatoes
2706783|survey_fndds_food|Chicken or turkey shish kabob with vegetables, excluding potatoes
2706867|survey_fndds_food|Fish shish kabob with vegetables, excluding potatoes
2706780|survey_fndds_food|Lamb shish kabob with vegetables, excluding potatoes
2706779|survey_fndds_food|Pork shish kabob with vegetables, excluding potatoes
2706855|survey_fndds_food|Shrimp shish kabob with vegetables, excluding potatoes
172509|sr_legacy_food|Lamb, cubed for stew or kabob (leg and shoulder), separable lean only, trimmed to 1/4" fat, cooked, braised
172510|sr_legacy_food|Lamb, cubed for stew or kabob (leg and shoulder), separable lean only, trimmed to 1/4" fat, cooked, broiled
172508|sr_legacy_food|Lamb, cubed for stew or kabob (leg and shoulder), separable lean only, trimmed to 1/4" fat, raw
```

    SELECT count(*) FROM food WHERE description ILIKE '%kebab%';  -> 0

- **kind:** reachability_gap
- **category:** spelling_transliteration_failure
- **expected row:** `2706780 Lamb shish kabob with vegetables, excluding potatoes`
  for "lamb shish kebab"; `172510 Lamb, cubed for stew or kabob ... broiled` for
  a plain meat kebab.
- **why it is bad:** trigram similarity cannot cross `kebab`/`kabob` — one
  character differs but it splits three of the five trigrams. The English
  spelling a person types is the one USDA does not use, so the *entire* skewered
  grilled meat category is invisible. Note `lamb kebab` scores 0.312 against
  `Lamb, chop` while the purpose-built row `172510` sits unreachable.

### F2 — `lamb shank` misses the braised foreshank row USDA actually has

```
weak  lamb shank                         0.400  Stew, lamb
```

Neighbour search by cut, not by name:

```
SELECT fdc_id,data_type,description FROM food WHERE description ILIKE '%lamb%' AND description ILIKE '%shank%';
172481|sr_legacy_food|Lamb, foreshank, separable lean and fat, trimmed to 1/4" fat, choice, raw
172482|sr_legacy_food|Lamb, foreshank, separable lean and fat, trimmed to 1/4" fat, choice, cooked, braised
172483|sr_legacy_food|Lamb, foreshank, separable lean only, trimmed to 1/4" fat, choice, raw
172484|sr_legacy_food|Lamb, foreshank, separable lean only, trimmed to 1/4" fat, choice, cooked, braised
172485|sr_legacy_food|Lamb, leg, shank half, separable lean and fat, trimmed to 1/4" fat, choice, cooked, roasted
...
```

- **kind:** reachability_gap
- **category:** missing_synonym
- **expected row:** `172482 Lamb, foreshank, ... cooked, braised` — a lamb shank
  in abgoosht, dizi or a Gulf stew is braised foreshank, by definition.
- **why it is bad:** USDA writes the cut as one word, `foreshank`. `shank`
  is a substring of `foreshank` but trigram similarity is length-penalised and
  the description is 76 characters, so the correct row never surfaces. The user
  gets `Stew, lamb` — a *composite* row that already contains vegetables and
  broth, so logging 300 g of it against 300 g of meat understates protein badly.

### F3 — `basmati rice` reaches a bread

```
weak  basmati rice                       0.333  Bread, rice
weak  persian rice                       0.412  Rice paper
ask   saffron rice                       0.500  Spices, saffron
```

    SELECT count(*) FROM food WHERE description ILIKE '%basmati%';  -> 0

Neighbour search by category:

```
2708408|survey_fndds_food|Rice, white, cooked, no added fat
2708403|survey_fndds_food|Rice, white, cooked, NS as to fat
790214|foundation_food|Flour, rice, white, unenriched
```

- **kind:** reachability_gap
- **category:** missing_synonym
- **expected row:** `2708408 Rice, white, cooked, no added fat`
- **why it is bad:** basmati is white long-grain rice; nutritionally the white
  rice row is right to within noise. This is not an exotic term — it is the
  single most-typed rice word in the English-speaking world, and it lands on
  *bread*. `saffron rice` going to `Spices, saffron` is the same failure with a
  worse consequence: saffron is a 0.1 g spice and the rice is 200 g.

### F4 — Persian is an almost total entity void

58 of 91 batch-1 terms returned **nothing at all**. Confirmed zero rows anywhere
in `food`:

    barberry/zereshk | lavash | sumac | kashk | basmati | kebab

Every named Persian dish returned `none`: chelow kabab, koobideh, jujeh kebab,
kabab barg, ghormeh sabzi, gheimeh, fesenjan, tahdig, tahchin, ash reshteh,
kuku sabzi, zereshk polo, baghali polo, sabzi polo, adas polo, halim, abgoosht,
dizi, mirza ghasemi, kashke bademjan, doogh, sholeh zard, faloodeh, bastani.

- **kind:** entity_gap
- **category:** missing_food_entity
- **why it matters, and what it does not mean:** this is a real gap but it is
  *not* the dangerous class. A `none` verdict escalates to the model tier with
  an empty candidate list, which is honest. The dangerous rows are F1–F3, where
  a plausible wrong row is returned instead.

### F5 — `mutton` loses to a meat *loaf* while USDA's own `Mutton` row sits third

```
weak mutton
   0.368  Lamb or mutton loaf  [survey_fndds_food]
   0.269  Lamb or mutton with gravy  [survey_fndds_food]
   0.250  Mutton, cooked, roasted (Navajo)  [sr_legacy_food]
   0.233  Stew, mutton, corn, squash (Navajo)  [sr_legacy_food]
   0.226  Stew, hominy with mutton (Navajo)  [sr_legacy_food]
```

- **kind:** reachability_gap
- **category:** bad_fuzzy_matching
- **expected row:** `167634 Mutton, cooked, roasted (Navajo)` — the only plain
  mutton row USDA has, and it is a plain roasted meat.
- **why it is bad:** the head is a *loaf*, a bound processed product with
  breadcrumb filler, and the query word `mutton` appears in every candidate, so
  ranking is decided purely by description length. This is the RESUME.md
  length-dominance pattern (r = -0.87 to -0.94) reproduced exactly. Mutton is
  the default meat across Gulf, Yemeni, Afghan and South Asian cooking, so this
  is a high-volume term, not a curiosity.
- Mitigating: the verdict is `weak`, so it escalates and the right row is on the
  list the model sees. This is a ranking defect, not a silent corruption.

### F6 — Gulf/Yemeni is an entity void, and the aromatics are absent too

62 of 91 batch-2 terms returned nothing. Confirmed **zero rows** in `food`:

```
labneh  0     zaatar/za'atar  0     kibbeh/kubba  0     shakshuka  0
camel   0     sumac (batch 1) 0     basmati       0     kebab      0
```

Every Gulf/Yemeni dish name returned `none`: machboos, kabsa, mandi, madfoon,
zurbian, harees, jareesh, saltah, hilbeh, malawach, lahoh, khubz, ragag,
balaleet, luqaimat, aseeda, masoub, mutabbaq, masgouf, quzi, tashreeb, tharid,
maqluba, mujadara, kushari, baharat, hawaij.

- **kind:** entity_gap
- **category:** missing_food_entity
- **note:** `camel` returning zero is worth stating plainly — camel meat and
  camel milk are staple Gulf foods and USDA has no analogue at all. Unlike the
  Persian dishes, there is no near neighbour by ingredient either: camel milk
  differs from cow milk in fat and lactose, and `camel milk` currently reaches
  `Oat milk` at 0.333, which is a plant drink with no protein. Deliberately not
  proposing a mapping — see Deliberately rejected.

### F7 — what *does* work, and why it is informative

```
auto  falafel                            1.000  Falafel
auto  tahini                             1.000  Tahini
auto  medjool dates                      1.000  Dates, medjool
ask   hummus                             0.538  Hummus, plain
ask   cardamom                           0.562  Spices, cardamom
ask   goat meat                          0.529  Game meat, goat, raw
```

Every Middle Eastern term that resolves cleanly is one that entered American
English decades ago and therefore entered FNDDS under its English spelling.
The pattern across both batches is not "Arabic food is hard" — it is that the
database's vocabulary is US supermarket English, and reachability tracks
naturalisation into that dialect, not culinary importance.

### F8 — `scallion` returns exactly one candidate, it is correct, and it is called weak

```
weak  scallion
   0.160  Onions, spring or scallions (includes tops and bulb), raw  [sr_legacy_food]
```

That is the entire candidate list. The single row returned is the *right* row,
and the word `scallions` is in it verbatim.

- **kind:** reachability_gap
- **category:** bad_fuzzy_matching
- **expected row:** `Onions, spring or scallions (includes tops and bulb), raw`
- **why it is bad:** `WEAK_MATCH_SIMILARITY = 0.45` means the resolver reports
  this as "a best candidate exists but the right answer was probably never on
  the list". It was the only thing on the list and it was right. The 56-character
  description is what sinks it — the same length dominance as F5, but here it
  produces a *false confidence signal* rather than a wrong row, which is
  arguably worse because it is the signal the model tier is handed.
- The same shape, verbatim, for `lamb shoulder` (0.222) and `beef shoulder`
  (0.175) — both heads are exactly correct cuts and both are called weak.

### F9 — three everyday aromatics land on the wrong kind of food

```
weak  dill
   0.385  Pickles, dill              [survey_fndds_food]   <- a pickled cucumber
   0.312  Dill weed, fresh           [sr_legacy_food]      <- the herb, correct
   0.312  Spices, dill seed          [sr_legacy_food]
   0.238  Spices, dill weed, dried   [sr_legacy_food]

weak  red pepper flakes
   0.385  Peppers, red, cooked            [survey_fndds_food]  <- a vegetable
   0.357  Peppers, bell, red, raw         [foundation_food]
   0.345  Peppers, sweet, red, raw        [sr_legacy_food]
   0.343  Spices, pepper, red or cayenne  [sr_legacy_food]     <- correct, 5th

weak  yellow carrot
   0.346  Hominy, canned, yellow  [sr_legacy_food]
   0.333  Corn grain, yellow      [sr_legacy_food]
   0.333  Muffin, carrot          [survey_fndds_food]
   0.300  Carrots, raw            [sr_legacy_food]   <- correct, 4th
```

- **kind:** reachability_gap
- **category:** bad_fuzzy_matching / ingredient_vs_dish_ambiguity
- **why it is bad:** all three are herbs and vegetables used by the handful in
  Central Asian and Persian cooking, and all three rank a *dish* above the
  ingredient. `Peppers, bell, red, raw` above `Spices, pepper, red or cayenne`
  is the sharpest: bell pepper and cayenne are not interchangeable in any
  respect, and if 5 g of "red pepper flakes" resolved to bell pepper the mass
  would be nonsense in the other direction too. `yellow carrot` reaching
  *hominy* is decided entirely by the shared word "yellow".
- Yellow carrot is the defining vegetable of Uzbek plov, so this is the
  domain's dish-ingredient test failing on the ingredient side.

### F10 — Central Asian dish names and dairy return nothing

60 of 91 batch-3 terms returned nothing. Confirmed zero: `kurt`/`qurut`,
`kumis`, `ayran`, `katyk`, `suzma`, `kaymak`, `plov`, `lagman`, `beshbarmak`,
`manti`/`mantu`, `shashlik`, `lepyoshka`, `chuchvara`, `pelmeni`, `dumba`.

- **kind:** entity_gap
- **category:** missing_food_entity
- **notable near-miss:** `samsa` -> 0.444 `Samosa` (weak, just under the floor).
  These are genuinely cognate pastries but not nutritionally equal — an Uzbek
  samsa is baked in a tandoor with lamb and tail fat, a samosa is deep-fried
  with potato. Recorded, not proposed. See Deliberately rejected.
- `horse meat` -> 0.550 `Game meat, horse, raw` is the one Central Asian
  animal product that works, and it works because USDA carries a game-meat
  series. `kazy` (horse sausage) still returns nothing.

### F11 — bare `clam chowder` heads to Manhattan, and the two bases differ by 2.7x energy

The domain brief asked for this test explicitly. Measured:

```
weak  clam chowder
   0.444  Soup, Manhattan clam chowder    [survey_fndds_food]   <- tomato base
   0.414  Soup, New England clam chowder  [survey_fndds_food]   <- cream base
   0.308  CAMPBELL'S CHUNKY, New England Clam Chowder
   0.293  Soup, clam chowder, manhattan, canned, condensed
```

Both named forms resolve perfectly when the region is typed:

```
auto  new england clam chowder           0.828  Soup, New England clam chowder
auto  manhattan clam chowder             0.815  Soup, Manhattan clam chowder
```

The consequence, per 100 g, straight from `food_nutrient`:

```
Soup, Manhattan clam chowder    Energy 35 KCAL   Fat 0.51 g   Protein 2.48 g
Soup, New England clam chowder  Energy 93 KCAL   Fat 4.80 g   Protein 3.12 g
```

- **kind:** wrong_confident_match (by rank; verdict is `weak`, so it escalates)
- **category:** bad_fallback
- **expected row:** `2707139 Soup, New England clam chowder`. In US usage
  unqualified "clam chowder" means the New England, cream-based one; Manhattan
  is the form that is always named, precisely because it is the exception.
- **why it is bad:** a 350 g bowl scores 122 kcal instead of 326 kcal, and
  1.8 g of fat instead of 16.8 g — a 9.4x fat error on a food that is
  *entirely* about its fat. The head is decided by "Manhattan" being one
  character shorter than "New England", which is not a fact about chowder.
- **`rhode island clam chowder` -> 0.385 New England** is wrong in the other
  direction: Rhode Island chowder is the clear-broth third form, closer to
  Manhattan minus tomato than to either. Not proposing a mapping; USDA has no
  clear-broth row.

### F12 — `cheesesteak` written as one word cannot reach USDA's four cheesesteak rows

```
weak  cheesesteak
   0.353  Cheese, NFS       [survey_fndds_food]
   0.353  Cheese dip        [survey_fndds_food]
   0.333  Cheese, cheddar   [foundation_food]
   0.333  Cheese, blue      [sr_legacy_food]

none  philly cheesesteak                 -      (nothing)
weak  philadelphia cheese steak          0.333  Strudel, cheese
```

USDA has the dish, spelled as two words:

```
SELECT ... WHERE description ILIKE '%steak sandwich%';
2706958|survey_fndds_food|Steak sandwich or sub on white
2706959|survey_fndds_food|Steak sandwich or sub on wheat
2706960|survey_fndds_food|Cheese steak sandwich or sub on white
2706961|survey_fndds_food|Cheese steak sandwich or sub on wheat
```

    SELECT count(*) FROM food WHERE description ILIKE '%cheesesteak%';  -> 0

- **kind:** reachability_gap
- **category:** spelling_transliteration_failure / bad_normalization
- **expected row:** `2706960 Cheese steak sandwich or sub on white`
- **why it is bad:** the closed compound is the only spelling anyone uses, and
  it resolves to *a block of cheese*. Logging a cheesesteak as `Cheese, NFS`
  drops the roll and the beef entirely and triples the fat density. Note also
  that adding the city makes it strictly worse — `philly cheesesteak` returns
  nothing at all, because the extra token dilutes every trigram.

### F13 — `collard greens` reaches pokeweed; `Collards` is what USDA calls it

```
weak  collard greens
   0.375  Poke greens, cooked   [survey_fndds_food]   <- pokeweed, a wild plant
   0.360  Mustard greens, raw   [sr_legacy_food]
   0.360  Beet greens, cooked   [survey_fndds_food]
   0.360  Greens, canned, cooked
   0.333  Collards, raw         [foundation_food]     <- correct, 6th
```

USDA has a full collard series and never uses the word "greens" for it:

```
2709576 Collards, raw          2709579 Collards, NS as to form, cooked
2709582 Collards, fresh, cooked with oil
2709584 Collards, frozen, cooked with oil
```

- **kind:** reachability_gap
- **category:** missing_synonym
- **expected row:** `2709582 Collards, fresh, cooked with oil` for the Southern
  braised dish; `2709579` for plain cooked.
- **why it is bad:** "collard greens" is the *only* name this vegetable has in
  American English; "collards" alone is the regional short form. The query is
  penalised for containing the second half of its own name, and the four rows
  that outrank the right one are four different plants. Poke greens are
  pokeweed — a plant that is toxic raw and is not eaten outside a narrow
  Appalachian tradition.

### F14 — one dish, two names: `country fried steak` auto-matches, `chicken fried steak` goes to fried rice

```
auto  country fried steak                0.800  Beef, steak, country fried

ask   chicken fried steak
   0.467  Rice, fried, with chicken           [survey_fndds_food]
   0.406  Beef, steak, country fried          [survey_fndds_food]  <- correct
   0.500  Stew, chicken                       [survey_fndds_food]
   0.389  Chicken, meatless, breaded, fried
   0.378  Chicken wing, fried, coated, from raw
```

- **kind:** reachability_gap
- **category:** missing_synonym / ingredient_vs_dish_ambiguity
- **expected row:** `Beef, steak, country fried` — the same row the other name
  already auto-matches.
- **why it is bad:** these are the same dish under two regional names (Texas
  and the South say chicken fried, the rest say country fried); there is no
  chicken in either. The word "chicken" drags every candidate to poultry and
  the top hit is *fried rice*. This is the highest-value American finding after
  F11 because it is a single synonym away from an already-correct row.

### F15 — Louisiana and Hawaii: entity gaps with no near neighbour

Confirmed **zero rows**: `etouffee`, `kalua`, `cheesesteak`, `boudin`,
`muffuletta`, `po'boy`, `andouille`, `tasso`, `roux`, `hoppin john`,
`loco moco`, `malasada`, `saimin`.

- **kind:** entity_gap
- **category:** missing_food_entity
- `kalua pork -> 0.333 Kung Pao pork` is the culturally-wrong pairing to note:
  Hawaiian imu-roasted pork reaching a Sichuan-American stir-fry. Verdict weak,
  so it escalates, but it is the head of the list handed to the model.
- `carolina pulled pork -> 0.308 Pork, carnitas` is the same shape.
- Hawaii is otherwise unusually well covered — `poi`, `haupia`, `lomi lomi
  salmon` and `laulau` all auto-match, because FNDDS surveys Hawaii. `poke`
  in every form returns nothing, which is the one real Hawaiian gap.

### F16 — `hominy grits` and `crawfish`: state and spelling

```
weak  hominy grits
   0.310  Cereals, QUAKER, hominy grits, white, quick, dry   <- DRY
   0.283  Cereals, QUAKER, hominy grits, white, regular, dry <- DRY
   0.353  Grits, NFS                                          <- correct
   0.350  Hominy, cooked

weak  crawfish
   0.333  Crayfish, fried    [survey_fndds_food]
   0.333  Crayfish, cooked   [survey_fndds_food]
```

- **kind:** reachability_gap (both)
- **category:** preparation_state_mismatch (grits) / spelling_transliteration_failure (crawfish)
- **why grits is bad:** nobody eats dry grits. Dry grits are ~370 kcal/100 g
  against ~60 for cooked — a 6x error if a bowl mass is applied to the dry row.
  `state_conflicts` should catch "dry" against an unstated state, but the query
  states no state, and the guard is documented to treat silence as no evidence.
  So the head stays dry.
- **why crawfish is bad:** `crawfish` is the Louisiana spelling and the only one
  used where the food is eaten; USDA uses `crayfish` exclusively. Both
  candidates are the same species, so the mapping is safe, but the head is the
  *fried* form for a query that stated no preparation.

### F17 — `cooked white rice` AUTO-matches *glutinous* rice — the worst finding in this audit

```
auto  white rice cooked
   0.643  Rice, white, cooked, glutinous     [survey_fndds_food]   <- taken, no model
   0.600  Rice, white, cooked, no added fat  [survey_fndds_food]   <- correct
   0.581  Rice, white, cooked, NS as to fat
   0.581  Rice, white, cooked, made with oil
   0.562  Rice, white, cooked, as ingredient

auto  cooked white rice        -> same list, same head
```

Per 100 g:

```
2708422  Rice, white, cooked, glutinous     Energy  96   Protein 2.01  Carb 20.97
2708408  Rice, white, cooked, no added fat  Energy 129   Protein 2.67  Carb 27.99
```

- **kind:** wrong_confident_match
- **category:** culturally_incorrect_mapping / bad_fallback
- **expected row:** `2708408 Rice, white, cooked, no added fat`
- **why it is the worst one here:** glutinous rice is a *different cultivar* —
  sticky/sweet rice, used in East and Southeast Asian cooking and essentially
  never in Persian, Afghan, Gulf, Uzbek or Louisiana food. It undercounts energy
  by 26% and carbohydrate by 25%. Rice is the single largest mass in chelow
  kabab, plov, kabsa, mandi, biryani, jambalaya and red beans and rice, so a
  250 g serving loses 82 kcal, every time.
- **and it caches.** Verdict is `auto`, which per CLAUDE.md means no model is
  consulted *and* an alias is written that is never re-checked. One meal fixes
  the wrong row into every subsequent meal of the staple.
- The head wins on 0.643 vs 0.600 — the word "glutinous" is shorter than
  "no added fat". Nothing about the query suggested sticky rice.
- Related, and also bad: `white rice` alone -> `ask 0.524 Beans and white rice`
  (a composite dish); `steamed rice` -> `weak 0.351`; `plain rice` ->
  `ask 0.458 Cereal, rice crispy, plain`. There is no phrasing of "plain cooked
  white rice" that reaches `2708408` cleanly.

### F18 — `hot sauce` AUTO-matches a Thai sauce with 3.2x the sodium

```
auto  hot sauce
   0.667  Hot Thai sauce                          [survey_fndds_food]  <- taken
   0.588  Hot pepper sauce                        [survey_fndds_food]  <- correct
   0.417  Sauce, hot chile, sriracha              [sr_legacy_food]
   0.533  Hoisin sauce                            [survey_fndds_food]
   0.294  Sauce, ready-to-serve, pepper or hot    [sr_legacy_food]
```

Per 100 g:

```
Hot Thai sauce     Energy 74 KCAL   Sodium 2055 MG
Hot pepper sauce   Energy 12 KCAL   Sodium  633 MG
```

- **kind:** wrong_confident_match
- **category:** culturally_incorrect_mapping
- **expected row:** `2710093 Hot pepper sauce` — the vinegar-and-cayenne
  Louisiana style, which is what "hot sauce" means on a po'boy, on wings, on
  gumbo, and in every American kitchen.
- **why it is bad:** a sugared Thai chilli sauce is a different condiment with
  6x the energy and 3.2x the sodium. Auto, so it caches. Sodium is a targeted
  nutrient with a ceiling, and hot sauce is a food people use repeatedly.

### F19 — `seaweed` AUTO-matches a soup

```
auto  seaweed
   0.667  Soup, seaweed     [survey_fndds_food]   <- taken, no model
   0.667  Seaweed, raw      [survey_fndds_food]   <- correct, identical sim
   0.615  Seaweed, dried    [survey_fndds_food]
   0.533  Seaweed, pickled
```

- **kind:** wrong_confident_match
- **category:** ingredient_vs_dish_ambiguity
- **expected row:** `2709805 Seaweed, raw`
- **why it is bad:** the two heads tie at 0.667 exactly and the *dish* wins the
  tiebreak. A soup is mostly water, so 10 g of nori logged as seaweed soup is
  nutritionally nothing. The same shape as `onion -> Bread, onion` (0.500,
  above `Onions, raw` at 0.417) and `cornbread -> Chicken cornbread` (0.588) —
  in all three a composite dish outranks the bare ingredient. This is a
  systematic bias, not three accidents: FNDDS dish names are short, and short
  wins.

### F20 — exact-word rows called weak, again

```
weak  ribeye        0.206  Beef, steak, ribeye, lean only eaten
weak  boston butt   0.169  Pork, fresh, shoulder, (Boston butt), blade (steaks), separable lean only, raw
weak  country ham   0.197  Cereals, QUAKER, Instant Grits, Redeye Gravy & Country Ham flavor, dry
weak  kielbasa      0.310  Kielbasa, fully cooked, grilled
weak  succotash     0.345  Succotash, (corn and limas), raw
weak  pork shoulder 0.292  Pork, fresh, shoulder, whole, separable lean only, raw
```

- **kind:** reachability_gap
- **category:** bad_fuzzy_matching
- **why it is bad:** in five of six the head is the *correct food* and the
  verdict still says the right answer was probably never on the list. The
  exception is instructive: `country ham` heads to a **dry instant grits mix
  flavoured with country ham**, which is not ham at all. Length is doing all the
  work; the query words are present verbatim in every case.

### F21 — what auto-matched correctly, for calibration

42 of 96 batch-5 terms auto-matched and the large majority were right:
`coleslaw`, `dirty rice`, `pecan pie`, `key lime pie`, `banana pudding`,
`fried green tomatoes`, `chitterlings`, `scrapple`, `spam`, `lard`,
`buttermilk`, `heavy cream`, `molasses`, `brown sugar`, `boiled peanuts`,
`fried catfish`, `deviled eggs`, `italian sausage`, `oyster crackers`.

`butter -> auto 0.636 Butter, tub` was checked and **is not a finding**:

```
Butter, tub     Energy 731  Fat 78.30
Butter, stick   Energy 743  Fat 82.20
Butter, salted  Energy 717  Fat 81.11
```

a 1.6% energy spread. Recorded so the next reader does not re-open it.

The pattern: auto-match is reliable when the food is a *named American dish or
product*, and fails when the query is a *bare ingredient* whose name is a prefix
of a shorter dish name (F17, F18, F19).

### F22 — `sweet potato` AUTO-matches a *pie*

```
auto  sweet potato
   0.812  Pie, sweet potato    [survey_fndds_food]   <- taken, no model
   0.765  Sweet potato, NFS    [survey_fndds_food]   <- correct
   0.722  Sweet potato tots
   0.722  Sweet potato paste
   0.684  Bread, sweet potato

auto  sweet potatoes
   0.632  Pie, sweet potato    <- same head on the plural
```

Per 100 g:

```
Pie, sweet potato   Energy 269 KCAL   Fat 9.75 g
Sweet potato, NFS   Energy 115 KCAL   Fat 4.53 g
```

- **kind:** wrong_confident_match
- **category:** ingredient_vs_dish_ambiguity
- **expected row:** `Sweet potato, NFS`
- **why it is bad:** 2.3x energy and 2.2x fat, on a plain vegetable, taken with
  no model consulted, and cached as an alias afterwards. Both the singular and
  the plural fail. Sweet potato is a Southern US staple and a common side
  everywhere; this is not an exotic query. Note the pie wins by 0.047 purely
  because `Pie, sweet potato` is two characters shorter than `Sweet potato, NFS`.

### F23 — `grits cooked` reaches *garlic*

```
weak  grits cooked / cooked grits
   0.421  Garlic, cooked        [survey_fndds_food]
   0.409  Poke greens, cooked   [survey_fndds_food]
   0.391  Greens, canned, cooked
   0.391  Beet greens, cooked
   0.389  Teff, cooked          [sr_legacy_food]
   0.389  Couscous, cooked      [sr_legacy_food]
```

USDA has nine cooked grits rows and none is on the list:

```
2708363 Grits, NFS                    2708366 Grits, regular or quick, made with water, fat added
2708370 Grits, instant, made with water, no added fat
2708369 Grits, with cheese, fat added
```

Bare `grits` works: `ask 0.600 Grits, NFS`.

- **kind:** reachability_gap
- **category:** bad_normalization / bad_fuzzy_matching
- **expected row:** `2708363 Grits, NFS`
- **why it is bad:** the entire candidate list is decided by the word "cooked".
  Grits is hominy — nixtamalised corn — and it lands on a bulb, three leaf
  vegetables and two unrelated grains.

### F24 — the cross-cutting pattern: adding a true qualifier makes the match worse

This is the single most reusable observation from the domain, and it is
measured, not inferred:

```
grits          ask   0.600  Grits, NFS          ->  cooked grits   weak 0.421 Garlic, cooked
crawfish       weak  0.333  Crayfish, fried     ->  crawfish boiled       none (nothing)
cheesesteak    weak  0.353  Cheese, NFS         ->  philly cheesesteak    none (nothing)
hot sauce      auto  0.667  Hot Thai sauce      ->  louisiana hot sauce  weak 0.400
barberries     weak  0.438  Berries, NFS        ->  barberries uzbek     weak 0.318
saffron        ask   0.571  Spices, saffron     ->  saffron threads      weak 0.364
cardamom       ask   0.562  Spices, cardamom    ->  green cardamom       weak 0.409
lobster roll   ask   0.615  Lobster             ->  connecticut lobster roll weak 0.320
clam chowder   weak  0.444  Manhattan           ->  rhode island clam chowder weak 0.385
```

- **kind:** reachability_gap
- **category:** bad_normalization
- **why it matters:** a user who is *more* specific is punished. This is the
  same mechanism RESUME.md measured for saved products ("naming your own food
  precisely makes it less reachable"), reproduced here on ordinary USDA rows.
  Every regional qualifier in this domain — Persian, Uzbek, Louisiana, Philly,
  Hatch, Texas, Memphis — is a token USDA does not carry, so it can only dilute.

### F25 — even USDA's own spelling of the kebab rows is only `weak`

```
weak  lamb shish kabob     0.333  Lamb shish kabob with vegetables, excluding potatoes
weak  beef shish kabob     0.333  Beef shish kabob with vegetables, excluding potatoes
weak  chicken shish kabob  0.312  Chicken or turkey shish kabob with vegetables, excluding potatoes
```

Reinforces F1: fixing only the `kebab`->`kabob` spelling still lands at 0.333,
because the rows carry 28 characters of ", with vegetables, excluding potatoes"
that no user will ever type. The spelling bridge is necessary and not
sufficient.

Also worth recording next to the audit's motivating case:

```
weak  cured pork jowl    0.440  Pork, cured, salt pork, raw
weak  pork jowl cured    0.440  Pork, cured, salt pork, raw
weak  jowl bacon         0.400  Bacon bits
none  hog jowl           -      (nothing)
```

`hog jowl` — the standard American English name for the cut, and the defining
ingredient of hoppin' john — returns nothing at all, while USDA holds
`Pork, fresh, variety meats and by-products, jowl, raw`.

### F26 — `ghee` cannot reach the row that has the word `ghee` in it

```
weak  ghee               0.227  Butter, Clarified butter (ghee)   [sr_legacy_food]
auto  clarified butter   0.773  Butter, Clarified butter (ghee)   [sr_legacy_food]
```

- **kind:** reachability_gap
- **category:** bad_fuzzy_matching
- **expected row:** `171314 Butter, Clarified butter (ghee)`
- **why it is bad:** the same row, the same query intent, 0.227 versus 0.773,
  decided by nothing but the query's length relative to the description. Ghee /
  roghan is the standard cooking fat in Persian, Afghan and Gulf cooking and is
  ~900 kcal/100 g, so a miss here is a large one. This is the cleanest possible
  demonstration of the length effect: the four-letter native word is inside the
  target description and still fails.

### F27 — `collard greens cooked` reaches pokeweed at a *higher* confidence

```
ask   collard greens cooked   0.583  Poke greens, cooked   [survey_fndds_food]
```

Worse than F13: adding "cooked" pushes the *wrong* plant from `weak` (0.375) up
to `ask` (0.583), so the resolver is now more confident in pokeweed. Poke greens
must be boiled through several changes of water to be safe to eat and are not a
substitute for collards in any sense.

### F28 — more ingredient-to-dish inversions, and exact rows called weak

```
ask   cinnamon      0.600  Bread, cinnamon                 <- Spices, cinnamon outranked by a bread
weak  feta          0.417  Cheese, feta                    <- correct row, weak
weak  turmeric      0.391  Spices, turmeric, ground        <- correct row, weak
weak  cloves        0.350  Spices, cloves, ground          <- correct row, weak
weak  tomato paste  0.342  Tomato, paste, canned, without salt added  <- correct row, weak
weak  vermicelli    0.440  Vermicelli, made from soy       <- soy noodles, not wheat
weak  wheat berries 0.444  Berries, NFS                    <- wrong food entirely
none  aubergine     -      (nothing)                       <- eggplant -> auto 0.692
```

`vermicelli` is the one with teeth: `Vermicelli, made from soy` is a
transparent bean-thread noodle, and reshteh in ash reshteh is a wheat noodle.
`wheat berries` reaching `Berries, NFS` is the same error class as `barberries`
in batch 1 — the token "berries" pulls a fruit row over a grain.

## Proposals

Encode `high` only. `medium` is a non-mandatory fallback — offered, never
auto-taken. Nothing `low` appears here; low-confidence candidates are in
Deliberately rejected with their reasons.

Target rows below were each verified reachable by probing the target's own
words, so the proposal is a *surface* problem and not a data problem.

| surface | relation | target | confidence | rationale |
|---|---|---|---|---|
| `kebab`, `kebap`, `kabab`, `kebob`, `kabab` | synonym | USDA spelling `kabob` | high | F1. `kebab` -> 0 rows, `kabob` -> 9 rows. Pure orthography; no semantic claim is made. |
| `shish kebab`, `shish kabab` | synonym | `shish kabob` | high | F1/F25. Same word, same dish. |
| `lamb shank`, `braised lamb shank` | nutritional_fallback | `172482 Lamb, foreshank, separable lean and fat, trimmed to 1/4" fat, choice, cooked, braised` | high | F2. A lamb shank is the foreshank and is braised by definition; USDA's own word for the cut is `foreshank`. Verified: `stew meat lamb` -> auto, so the family is reachable, this surface is not. |
| `mutton` | synonym | `167634 Mutton, cooked, roasted (Navajo)` | high | F5. USDA's only plain mutton row; currently third behind a meat loaf. |
| `basmati rice`, `basmati` | nutritional_fallback | `Rice, white, long-grain, regular, enriched, cooked` | high | F3. Basmati is white long-grain rice. Target verified: `long grain white rice cooked` -> `auto 0.674` onto that row. |
| `white rice` / `cooked white rice` / `steamed rice` / `plain rice` (state cooked, no cultivar stated) | nutritional_fallback | `2708408 Rice, white, cooked, no added fat` | high | F17. Must displace `Rice, white, cooked, glutinous`, which is a different cultivar and 26% lower in energy. This is the highest-value single entry in the table. |
| `collard greens`, `collard green` | synonym | `Collards` (`2709579` cooked / `2709576` raw) | high | F13/F27. Verified: `collards` -> `auto 0.692`. Currently reaches pokeweed. |
| `cheesesteak`, `philly cheesesteak`, `philadelphia cheesesteak` | synonym | `2706960 Cheese steak sandwich or sub on white` | high | F12. Closed-compound to open-compound normalisation. Verified: `cheese steak sandwich` -> `ask 0.600`. |
| `chicken fried steak`, `chicken-fried steak` | synonym | `Beef, steak, country fried` | high | F14. Same dish, two regional names; the other name already auto-matches at 0.800. No chicken in either. |
| `clam chowder` (region unstated) | nutritional_fallback | `2707139 Soup, New England clam chowder` | high | F11. US default sense. 93 vs 35 kcal/100 g. Manhattan is always named because it is the marked form. |
| `crawfish` | synonym | `crayfish` | high | F16. Louisiana spelling of the same species; both USDA rows are `Crayfish`. |
| `hog jowl`, `pork jowl`, `jowl bacon` | synonym | `Pork, fresh, variety meats and by-products, jowl` | high | F25. The audit's motivating cut, under its American English name. `hog jowl` currently returns nothing. |
| `scallion`, `scallions`, `spring onion`, `green onion` | synonym | `Onions, spring or scallions (includes tops and bulb), raw` | high | F8. The target names two of these surfaces verbatim and still scores 0.160. |
| `hot sauce` (unqualified), `louisiana hot sauce` | nutritional_fallback | `2710093 Hot pepper sauce` | high | F18. Must displace `Hot Thai sauce` (3.2x sodium, 6x energy). Verified: `hot pepper sauce` -> `auto 1.000`. |
| `sweet potato`, `sweet potatoes` | synonym | `Sweet potato, NFS` | high | F22. Must displace `Pie, sweet potato` (2.3x energy). A vegetable is not a dessert. |
| `seaweed` (unqualified) | synonym | `2709805 Seaweed, raw` | high | F19. Must displace `Soup, seaweed`. Verified: `seaweed raw` -> `auto 1.000`. |
| `grits`, `cooked grits`, `grits cooked`, `hominy grits` | synonym | `2708363 Grits, NFS` | high | F16/F23. Must displace `Garlic, cooked` and the *dry* QUAKER rows (6x energy error). |
| `ghee`, `roghan` | synonym | `171314 Butter, Clarified butter (ghee)` | high | F26. The word is already inside the target description. |
| `aubergine` | synonym | `Eggplant` | high | F28. British spelling; `eggplant` -> `auto 0.692`, `aubergine` -> nothing. |
| `dill` (as herb) | synonym | `172233 Dill weed, fresh` | high | F9. Must displace `Pickles, dill`, which is a cucumber. Verified: `dill weed` -> `auto 0.625`. |
| `red pepper flakes`, `crushed red pepper`, `cayenne`, `cayenne pepper` | synonym | `170932 Spices, pepper, red or cayenne` | high | F9. Must displace `Peppers, red, cooked` and `Peppers, bell, red, raw` — a sweet vegetable is not a hot spice in either direction. |
| `country ham` | nutritional_fallback | `Ham` (the plain FNDDS ham row; `tasso ham` already reaches it at 0.400) | high | F20. Currently reaches `Cereals, QUAKER, Instant Grits, Redeye Gravy & Country Ham flavor, dry` — a **dry cereal mix**, not ham. Country ham is saltier and drier than the generic row, so the sodium figure is understated by the fallback; the current head is not a meat at all, so this is strictly better. Flagged as fallback rather than synonym for that reason. |
| `ribeye`, `boston butt`, `pork shoulder`, `lamb shoulder`, `beef shoulder`, `kielbasa`, `succotash`, `feta`, `turmeric`, `cloves`, `tomato paste` | (no new target) | their existing correct head | high | F8/F20/F28. These need **no synonym** — the correct row is already the head. What they need is for the weak-floor verdict not to be computed from a length-penalised similarity. Recorded here so the knowledge layer does not add mappings that are not the problem. |
| `chelow`, `chelo`, `challow`, `polo` (plain, unqualified) | nutritional_fallback | `2708408 Rice, white, cooked, no added fat` | medium | Chelow is plain steamed long-grain white rice, but it is usually finished with butter or oil, and `Rice, white, cooked, made with butter` also exists. Offer, do not auto-take. |
| `lavash`, `khubz`, `khobz`, `taftoon`, `regag`, `lepyoshka`, `non` | nutritional_fallback | `Bread, pita, white, enriched` | medium | All are thin leavened white-flour flatbreads of similar flour:water ratio. Variant-dependent (thickness and enrichment vary widely), so fallback only. Explicitly **excludes** sangak — see Deliberately rejected. |
| `doogh`, `ayran` | dish_ingredient | yogurt (whole or low-fat) + water + salt | medium | Both are salted diluted yogurt. Dilution ratio varies 1:1 to 1:3, so the mass split is the uncertain part, not the identity. |
| `kalua pork`, `kalua pig` | nutritional_fallback | `Pork, fresh, shoulder, blade, boston (roasts), separable lean only, cooked, roasted` | medium | Kalua pig is salted, slow-roasted pork shoulder, shredded. Currently reaches `Kung Pao pork`. Medium because the imu method renders more fat than oven roasting. |
| `carolina pulled pork` | nutritional_fallback | `Pulled pork in barbecue sauce` | medium | Currently reaches `Pork, carnitas` (a Mexican confit). The USDA row is sweeter than a Carolina vinegar sauce, so the sugar figure is variant-dependent. Better than carnitas either way. |
| `fesenjan`, `fesenjoon` | dish_ingredient | walnuts + pomegranate juice/molasses + chicken thigh + onion | medium | Every component verified reachable: `walnuts` ask 0.471, `pomegranate juice` auto 0.818, `chicken thigh` ask 0.467. The ratio is the variant-dependent part. |
| `ghormeh sabzi` | dish_ingredient | parsley + cilantro + leek + kidney beans + lamb + dried lime | medium | Components verified: `parsley` auto 0.667, `cilantro` auto 0.692, `leek` ask 0.571, `kidney beans` auto 0.765, `ground lamb` auto 1.000. |
| `mujadara`, `mujaddara` | dish_ingredient | lentils + white rice + fried onion + olive oil | medium | Components all auto or ask. `lentils` auto 0.667, `olive oil` auto 1.000. |
| `hoppin john` | dish_ingredient | black-eyed peas + white rice + hog jowl or bacon | medium | `black eyed peas` ask 0.591; hog jowl needs the synonym proposed above. |
| `harees`, `halim`, `haleem` | dish_ingredient | cracked wheat + meat (lamb or chicken) + ghee | medium | `cracked wheat` and `pearl barley` both reachable; the wheat:meat ratio varies by region. |

## Deliberately rejected

Recorded so they are not re-proposed. Each was considered and refused.

| surface | what was considered | why rejected |
|---|---|---|
| `camel milk` | `Milk, whole` or `Goat milk` | Camel milk differs materially in fat (~3.0% but a different fatty-acid profile), lactose and it carries essentially no beta-lactoglobulin. Currently reaching `Oat milk` (0.333) is wrong, but replacing one wrong answer with a confident wrong answer is worse than escalating. USDA has zero camel rows; this is a true entity gap and should stay one. |
| `camel meat` | `Beef, ground` / `Game meat, ...` | Same reasoning. Leaner than beef, and no USDA analogue. Let it escalate. |
| `kashk` | `Whey, acid, dried` or `Yogurt, plain` | Kashk is drained, salted, sun-dried fermented whey-and-curd — roughly 4x the protein density of yogurt and nothing like fluid whey. The two candidate rows sit on opposite sides of the real value. Encoding either would fabricate a number. |
| `labneh` | `Yogurt, plain, whole milk` | Labneh is strained to roughly half its water; energy and protein per 100 g are about double. An unstrained-yogurt mapping is a systematic ~2x undercount on a food eaten by the tablespoon. Reject rather than guess the strain ratio. |
| `qurut`, `kurt`, `suzma`, `katyk`, `kaymak` | dairy parent category | Same family of failure as kashk and labneh: each is a different point on a draining/fermentation/fat continuum, and a single dairy parent is nutritionally useless. An over-broad parent here is worse than nothing. |
| `polenta` | `Grits, NFS` | Tempting and wrong. Grits are **hominy** — nixtamalised, lime-treated corn — and polenta is plain ground maize. Macros are close, but nixtamalisation is precisely what liberates niacin and adds calcium, so the two rows differ on the nutrients the mapping would exist to supply. `polenta` returns nothing today and should keep doing so until a cornmeal-mush row is identified. |
| `samsa`, `somsa` | `Samosa` (0.444, just under the floor) | Genuinely cognate pastries and still not interchangeable: an Uzbek samsa is tandoor-baked with lamb and tail fat, a samosa is deep-fried with spiced potato. Fat and protein both move a long way. The near-miss score is a coincidence of spelling, not evidence. |
| `sangak` | `Bread, pita, white, enriched` (the flatbread fallback above) | Deliberately carved out of that fallback. Sangak is a whole-wheat sourdough, so fibre and phytate differ from white pita in the direction a user would actually care about. Better to escalate than to log a wholemeal bread as white. |
| `barberries`, `zereshk` | `Cranberries, dried, sweetened` | Both tart dried berries, but commercial dried cranberries are sweetened to ~65 g sugar/100 g and barberries are not sweetened at all. The mapping would invent most of a day's sugar allowance from a garnish. |
| `sumac`, `za'atar`, `baharat`, `hawaij`, `advieh`, `golpar` | any spice parent | True entity gaps, and correctly left alone: these are used in gram quantities where any plausible spice row contributes a rounding error. Machinery here buys nothing. |
| `rhode island clam chowder` | `Soup, New England clam chowder` (current head) or Manhattan | It is the clear-broth third form and USDA has no clear-broth row. Neither existing row is right; escalation is the honest outcome. |
| `boudin`, `boudin blanc` | `Sausage, pork` | Boudin is 40-60% cooked rice by weight. A pork sausage row roughly doubles the fat and halves the carbohydrate. Reject. |
| `etouffee`, `po'boy`, `muffuletta`, `loco moco`, `frito pie` variants, `burnt ends` | composite dish rows | No USDA row and no defensible single-row fallback. `frito pie` already auto-matches its own row at 1.000, so only the others are gaps, and they should escalate to the model tier with their ingredient lists. |
| `kabuli pulao`, `plov`, `osh`, `kabsa`, `machboos`, `mandi`, `zurbian`, `biryani`-adjacent Gulf rice dishes | `Rice, white, with ...` composites, or FNDDS `Biryani with meat` | The meat:rice:fat ratio is the entire nutritional content and it varies more between these dishes than any single row could cover. A dish_ingredient decomposition is right here, but only once the rice fallback (F17) is fixed — otherwise every one of them inherits the glutinous-rice error. Deferred, not encoded. |
| `tahdig` | any rice row | Tahdig is the oil-saturated crust. Mapping it to plain rice would understate fat by most of what tahdig is. No row exists; leave it. |
| `butter` -> anything | `Butter, tub` (current auto head) | **Not a defect.** Measured: `Butter, tub` 731 kcal / 78.3 g fat, `Butter, stick` 743 / 82.2, `Butter, salted` 717 / 81.1. A 1.6% energy spread. Recorded so it is not re-opened. |
| `hatch green chile` -> `Peppers, hot chili, green, raw` | current weak head | **Not a defect.** Hatch chile is a green chile cultivar; the current head is right, only the confidence is low. Needs no mapping. |

## Notes

**The domain splits cleanly in two, and the split is not culinary.** Persian,
Gulf, Yemeni and Central Asian terms are 64-68% `none`. American regional terms
are 33% `none` and 44% `auto`. But the American failures are the *dangerous*
ones. Every wrong-confident match in this audit (F11, F12, F17, F18, F19, F22)
is an English-language query, because a term has to be reachable before it can
be confidently wrong. A `none` verdict escalates honestly; an `auto` verdict
takes a wrong row and caches an alias for it forever.

**One mechanism explains most of the reachability findings: description length.**
RESUME.md records r = -0.87 to -0.94 within a single food, and this domain
reproduces it on rows nobody hand-picked:

- `ghee` 0.227 vs `clarified butter` 0.773 -> *the same row*
- `scallion` 0.160 against a row containing the word "scallions"
- `boston butt` 0.169 against a row containing "(Boston butt)"
- `mutton` beaten by `Lamb or mutton loaf` because the loaf's name is shorter
- `Pie, sweet potato` (17 chars) beats `Sweet potato, NFS` (17 chars) on the
  trailing ", NFS" being noise the query does not contain

The corollary, F24, is the part worth carrying to the knowledge-layer design:
**a more specific query scores worse.** Users who add the region, the cultivar
or the preparation are punished for it, and every regional qualifier in this
domain — Persian, Uzbek, Louisiana, Philly, Hatch, Memphis — is a token USDA
does not carry.

**A second, independent mechanism: short dish names outrank bare ingredients.**
`Soup, seaweed` over `Seaweed, raw`; `Bread, onion` over `Onions, raw`;
`Bread, cinnamon` over `Spices, cinnamon`; `Chicken cornbread` over cornbread;
`Pie, sweet potato` over the vegetable; `Pickles, dill` over `Dill weed`;
`Poke greens, cooked` over `Collards`. And it runs the other way too —
`steak sandwich` auto-matches `Beef, sandwich steak`, the raw meat, over
USDA's actual `Steak sandwich or sub on white`. So the bias is not "dish beats
ingredient"; it is only ever "short beats long", and which side that lands on
is an accident of FNDDS naming.

**What surprised me.** Hawaii is the best-covered region in the whole domain —
`poi`, `haupia`, `lomi lomi salmon` and `laulau` all auto-match correctly,
because FNDDS surveys Hawaii and carries the Hawaiian names. Navajo foods are
in there too (`Mutton, cooked, roasted (Navajo)`, `Cornmeal, blue (Navajo)`,
`Stew, hominy with mutton (Navajo)`). The database is not indifferent to
minority cuisines — it is indifferent to cuisines that are not surveyed *in the
United States*. That reframes the entity gaps: they are not a judgement about
which foods matter, they are a map of NHANES's sampling frame, and the fix is
therefore a vocabulary layer rather than a data-collection argument.

**A measurement caveat for whoever builds on this.** `db.search_foods` orders by
a composite of `ts_rank`, trigram `sim`, a covers-boost and `has_energy`, but
`probe_knowledge.verdict()` is computed from the raw `sim` of whatever row the
composite put first. These disagree: for `chicken fried steak` the head has
sim 0.467 while the third candidate has 0.500, and for `steamed rice` the head
has 0.351 while the second has 0.400. So a `weak` verdict does not mean "no
candidate scored above 0.45" — it means "the row the ranker chose did not". Any
threshold tuning done against these numbers should account for that.

**Provenance note.** The batched term files were written to the session
scratchpad, and partway through the run a concurrently-running domain auditor
overwrote them (`b1.txt` came back holding Brazilian terms). The term *lists*
are therefore not recoverable from disk; the verdict counts above are the
probe's own summary lines, captured per batch as they ran, and they reconcile
exactly against the totals (233 + 161 + 96 + 119 = 609).

Because of that collision, all 24 headline results were **re-probed at the end
of the run** and every one reproduced identically — same verdict, same score,
same row, including all six wrong-confident autos (F11, F12, F17, F18, F19,
F22). The resolver is deterministic here and the findings do not depend on the
lost files. CLAUDE.md's standing caution about a second session working in this
repo applies to the scratchpad as well as to the git tree.
