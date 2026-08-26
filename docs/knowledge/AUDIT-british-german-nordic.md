# Knowledge audit — British / Irish / German / Austrian / Swiss / Dutch / Nordic

26 Aug 2026. 994 distinct terms probed with `scripts/probe_knowledge.py`
(no aliases consulted, no model called). Read-only against the live database.

    none = 351 (35%)   weak = 337 (34%)   ask = 164 (17%)   auto = 142 (14%)

Probe lists are in the scratchpad; every line quoted below is verbatim probe or
`psql` output.

---

## 0. The mechanism reproduces in this domain

`RECONCILED.md` §1 measures r = −0.87…−0.94 between USDA description length and
similarity. Recomputed here over this domain's own rows:

```
herring: -0.881  n=12
cabbage: -0.914  n=44
lamb:    -0.734  n=319
bacon:   -0.692  n=68
oats:    -0.577  n=308
```

But this domain adds a **second, larger** mechanism that §1 does not cover:
**the query and the row are in different dialects of English.** When that
happens the length effect is irrelevant, because the right row is not in the
candidate set at all. Retrieval is `to_tsvector @@ plainto_tsquery OR
description % query`, and neither arm crosses a vocabulary boundary.

Measured, over the rows that contain the American word:

```
uk term        rows reachable by UK word   by US word
yoghurt                 4                     153
prawn                   0                      69
porridge                0                      98
gherkin                 0                      53
sultanas                0                      37
beetroot                0                      25
aubergine               0                      15
courgette               0                      13
swede                   0                       6
rocket                  0                       3
cornflour               0                       2
mangetout               0                       0   (see snow pea, below)
```

`yoghurt` is the headline. 149 of the 153 yogurt rows in this database are
**invisible** to a person who spells it the way most of the English-speaking
world outside North America spells it:

```
Yogurt, NFS                       sim('yogurt')=0.636   sim('yoghurt')=0.357
Yogurt, plain, whole milk         sim('yogurt')=0.292   sim('yoghurt')=0.185
```

```
weak  yoghurt                            0.357  Yogurt, NFS
none  natural yoghurt                    -      (nothing)
weak  greek yoghurt                      0.423  Yogurt, Greek, with oats
```

`greek yoghurt` reaching a **flavoured oat** product is the shape of the damage:
one letter drops the whole namespace below the floor and what is left is
whatever happened to survive.

---

## 1. Wrong-confident matches (`auto` onto a semantically wrong row)

Worst class: silent, and `resolve_items` writes an alias that is never
re-checked (CLAUDE.md, "The alias tier caches these forever").

### 1.1 `scotch egg` → Scotch whisky. The candidate list has exactly one row.

```
auto  scotch egg                         0.636  Scotch
auto  scotch pie                         0.636  Scotch
ask   scotch broth                       0.538  Scotch
ask   scotch pancake                     0.467  Scotch
```

```
## scotch egg auto
    0.636 Scotch          <- the entire candidate list
```

```
Scotch|Protein|0|G
Scotch|Total lipid (fat)|0|G
Scotch|Carbohydrate, by difference|0|G
Scotch|Energy|231|KCAL
Scotch|Alcohol, ethyl|33.4|G
```

fdc_id 2710701 is FNDDS for a measure of whisky. A Scotch egg is a boiled egg
in sausagemeat and breadcrumbs — roughly 240 kcal, 13 g protein, 17 g fat per
100 g. The energy figure is close enough to raise nothing; the macros are
entirely wrong and every 100 g logs **33.4 g of ethanol the user did not
drink**. There is no escape hatch: with one candidate, the model tier could not
have helped even if it had been asked.

`scotch pie` (a mutton pie), `scotch broth` (barley and lamb soup) and
`scotch pancake` (a drop scone) all funnel into the same row.

### 1.2 `oatmeal` → oatmeal pie, 5.2× the energy

```
## oatmeal auto
    0.667 Pie, oatmeal       <- taken
    0.667 Oatmeal, NFS       <- correct, identical similarity, ranked second
    0.615 Roll, oatmeal
```

```
2708016|Pie, oatmeal|396      kcal/100 g
2708380|Oatmeal, NFS|76       kcal/100 g
```

A tie in `sim` broken by `ts_rank` in favour of the dessert. A 300 g bowl of
porridge logs as 1,188 kcal instead of 228, with no model consulted and an
alias written. `porridge`, the British word for the same bowl, returns nothing
at all, so a UK user reaches this row by typing the *American* word.

### 1.3 `rapeseed oil` → grapeseed oil

```
auto  rapeseed oil                       0.688  Oil, grapeseed
```

```
171028|sr_legacy_food|Oil, grapeseed|0.688
2710188|survey_fndds_food|Canola oil|0.200
748278|foundation_food|Oil, canola|0.200
172336|sr_legacy_food|Oil, canola|0.200
```

Rapeseed **is** canola — same plant, and canola oil is the default cooking oil
in British and German kitchens. The correct row scores 0.200; the wrong one
0.688 on the strength of one shared trigram run. Both are 884 kcal so energy
hides it, but the fat profile is a different food: grapeseed is 69.9 g linoleic
/ 16.1 g MUFA per 100 g, canola is roughly the inverse and carries the ALA that
is the whole nutritional point of the oil.

### 1.4 `jam sandwich` → Spam sandwich

```
## jam sandwich auto
    0.625 Spam sandwich      <- taken, 266 kcal, cured pork
    0.529 Sandwich, NFS
```

One letter. Auto, and cached.

### 1.5 `bacon sandwich` / `sausage sandwich` → US fast-food biscuit sandwiches

```
auto  bacon sandwich                     0.682  Bacon biscuit sandwich
auto  sausage sandwich                   0.652  Sausage biscuit sandwich
```

```
## bacon sandwich auto
    0.682 Bacon biscuit sandwich
    0.556 Bacon, for use on a sandwich   <- the component the card actually wants
```

A bacon butty is bread and bacon. A bacon biscuit sandwich is a buttermilk
biscuit with a fried egg's worth of extra fat in the crumb.

### 1.6 `roast chicken` → chicken roll (deli loaf)

```
## roast chicken auto
    0.65  Chicken, chicken roll, roasted        <- taken, 164 kcal, a pressed loaf
    0.483 Chicken breast, roll, oven-roasted
    0.361 Chicken, roasting, meat only, cooked, roasted   <- correct, rank 4
```

Note also that the taken row scores 0.65 while a row *lower in the list* scores
0.419 — the list is ordered by `sim + ts_rank`, so the head is not the maximum
`sim`, and the probe's verdict floor is applied to whatever the ordering
surfaced. See §5.

### 1.7 `brown bread` → Boston brown bread

```
## brown bread auto
    0.625 Bread, Boston Brown      <- 274 kcal, a steamed molasses bread
    0.429 Bread, rye
```

British "brown bread" is wholemeal. `Bread, whole wheat` (2707709, 254 kcal) is
not on the list. Energy is close, fibre and sugar are not.

### 1.8 `biscuit` → `KFC, biscuit`

```
## biscuit auto
    0.667 KFC, biscuit      <- 358 kcal, a savoury quick bread from one chain
    0.667 Biscuit, NFS      <- 370 kcal, the US generic
    0.571 Marie biscuit     <- 406 kcal, the nearest thing to a British biscuit
```

`Cookie, NFS` is 492 kcal. This is the genuinely-two-different-foods case, and
it is **not safe to encode either way** — see §4.

---

## 2. Reachability gaps — USDA has the row and the query cannot get to it

The most valuable class. Every one of these was verified by searching USDA by
ingredient and by category, not by name.

### 2.1 Dialect synonyms, right row present, zero reachability

| query | probe result | the row that exists |
|---|---|---|
| `prawn` / `prawns` / `king prawns` | `none` | 69 rows containing `shrimp`, e.g. `Shrimp, NFS` |
| `porridge` / `porridge oats` | `none` | `Oatmeal, regular or quick, made with water, no added fat` 2708381 |
| `courgette` | `none` | `Squash, summer, zucchini, includes skin, raw` 169291 |
| `aubergine` | `none` | `Eggplant, raw` |
| `rocket` | `none` | `Arugula, raw` |
| `swede` | `none` | `Rutabaga, raw` 2709804 (37 kcal) |
| `beetroot` | `none` | `Beets, raw` |
| `gherkin` | `none` | `Pickles, cucumber, dill or kosher dill` 168558 |
| `sultanas` | `none` | `Raisins, golden, seedless` 168164 |
| `cornflour` | `weak 0.333 Flour, coconut` | `Cornstarch` (probes `auto 1.000`) |
| `mange tout` / `mangetout` / `snow pea` | `none` / `none` / `weak 0.357 Pea salad` | `Peas, edible-podded, raw` 170010 |
| `fish finger` / `fish fingers` | `weak 0.357 Fish, eel` | `Fish, stick` 2706231 |
| `reindeer` | `none` | `Caribou, hind quarter meat, raw (Alaska Native)` 168050 — same species |
| `lingonberry` | `none` | `Cranberry, low bush or lingenberry, raw (Alaska Native)` 169805 |
| `blutwurst` / `black pudding` | `weak 0.429 Bratwurst` / `ask 0.474 Pudding, bread` | `Blood sausage` 171618, 379 kcal |
| `emmental` / `emmentaler` | `none` | `Cheese, Swiss` 2705735 — Swiss cheese *is* Emmental |
| `brunost` / `geitost` | `none` | `Cheese, gjetost` 171240 |

`lingonberry` is the purest case in the audit: USDA spells it **lingenberry**,
one letter off, and the query returns nothing while `lingonberries` returns
`Loganberries, frozen`.

`black pudding` deserves its own line because the list is all-desserts:

```
## black pudding ask
    0.474 Pudding, bread
    0.474 Banana pudding
    0.421 Pudding, rice
    0.316 Bread, black
```

```
select ... similarity('Blood sausage','black pudding') = 0.077
```

### 2.2 Right row present, scored below the floor by length alone

These are §1-of-RECONCILED in this domain's clothing. The top hit is *correct*
and the verdict is still `weak`, so the resolver treats a solved case as an
unsolved one.

```
weak  kipper                             0.188  Fish, herring, Atlantic, kippered
weak  whelks                             0.188  Mollusks, whelk, unspecified, raw
weak  suet                               0.119  Beef, variety meats and by-products, suet, raw
weak  nettle                             0.125  Stinging Nettles, blanched (Northern Plains Indians)
weak  weetabix                           0.220  Cereals ready-to-eat, WEETABIX whole grain cereal
weak  chapati                            0.170  Bread, chapati or roti, plain, commercially prepared
weak  rack of lamb                       0.167  Lamb, New Zealand, imported, rack - fully frenched, ...
weak  lamb neck                          0.172  Lamb, New Zealand, imported, neck chops, ...
weak  beef shin                          0.175  Beef, New Zealand, imported, hind shin, ...
weak  roast lamb                         0.120  Lamb, Australian, imported, fresh, rack, roast, frenched, ...
weak  breaded veal                       0.220  Veal, leg (top round), separable lean only, cooked, pan-fried, breaded
weak  spring onion                       0.240  Onions, spring or scallions (includes tops and bulb), raw
weak  scallion                           0.160  Onions, spring or scallions (includes tops and bulb), raw
weak  sourdough                          0.238  Bread, french or vienna (includes sourdough)
weak  turbot                             0.280  Fish, turbot, european, raw
weak  cloudberry                         0.273  Cloudberries, raw (Alaska Native)
weak  edam                               0.417  Cheese, edam
weak  swedish meatballs                  0.429  Swedish meatballs with cream or white sauce
weak  cabbage boiled                     0.375  Cabbage, cooked, boiled, drained, without salt
weak  self raising flour                 0.308  Wheat flour, white, all-purpose, self-rising, enriched
```

`edam` against `Cheese, edam` at 0.417 — an exact-substring, exactly-correct row
falling below the weak floor purely because the query is four characters — is
the cleanest possible statement of the problem, and `cloudberry` /
`Cloudberries, raw (Alaska Native)` shows the plural-plus-provenance-suffix
version of it.

### 2.3 Compound-word normalisation

British and German orthography closes compounds that USDA writes open.

```
weak  sweetcorn                          0.348  Corn, sweet, white, raw
weak  cornflakes                         0.346  Cereal, corn flakes, plain
weak  blackcurrant                       0.323  Currants, european black, raw
weak  apple sauce                        0.438  Mole sauce       (Applesauce, regular is rank 3 at 0.409)
ask   applesauce                         0.611  Cookie, applesauce
weak  pitta                              0.308  Bread, pita
```

`apple sauce` reaching **Mole sauce** before `Applesauce, regular` is the
failure at its most literal.

### 2.4 `cottage pie` — the whole candidate list is cottage cheese

```
## cottage pie weak
    0.364 Cheese, cottage, NFS
    0.308 Cheese, cottage, dry curd
    0.308 Cheese, cottage, low fat
```

`Shepherd's pie` (2706594, 123 kcal) is the only minced-meat-and-mash row in the
database and it is absent from the list. Meanwhile:

```
auto  shepherds pie                      0.750  Shepherd's pie
auto  shepherd's pie                     1.000  Shepherd's pie
```

The meat question the task asks about is real and cuts the *other* way from what
one expects: in British usage shepherd's pie is lamb and cottage pie is beef,
but FNDDS `Shepherd's pie` is the American item, which is beef. So the row is a
better match for **cottage pie** than for the name it carries. Both are within
a few percent on energy and the difference is saturated fat, so the fallback is
defensible in either direction — but it should be recorded as a fallback, not as
an identity.

### 2.5 `back bacon` vs `streaky bacon` — a 3.75× split, and neither reaches a pork row

```
## streaky bacon weak
    0.346 Bacon strip, meatless          <- the entire list, both rows meat-free
    0.333 Bacon bits

## back bacon ask
    0.5   Bacon bits
    0.353 Bacon, meatless
    0.333 Turkey, back
    0.316 Beef, bacon, cooked
    0.312 Chicken, back
```

```
Pork, cured, bacon, cooked, baked   548 kcal/100 g
Canadian bacon, cooked, pan-fried   146 kcal/100 g
Bacon strip, meatless               309 kcal/100 g
```

British streaky bacon is US bacon; British back bacon is the loin cut USDA
calls Canadian bacon. Neither reaches its own row, both reach a vegetarian
product, and confusing the two is a 3.75× energy error. Sorting this out is
worth more than any single dish mapping in this audit.

### 2.6 `zucchini` and `cod` — the candidate list is ordered dessert-first

```
## zucchini ask
    0.6   Bread, zucchini
    0.562 Muffin, zucchini
    0.529 Zucchini, pickled
    0.429 Cake or cupcake, zucchini
    0.36  Squash, zucchini, baby, raw
    0.231 Squash, summer, zucchini, includes skin, raw     <- the vegetable, rank 6

## cod ask
    0.5   Cape Cod                <- a vodka-and-cranberry cocktail, 98 kcal
    0.308 Fish, cod, NFS          <- the fish, 217 kcal
```

Both are `ask`, so the model tier gets consulted and the system is technically
working. They are listed because the *list itself* is nonsense: the model is
handed four baked goods before the vegetable, and a cocktail before the fish.
`limit=5` is the recall ceiling RECONCILED §3.1 already flags — for `zucchini`
the correct row is outside it.

### 2.7 `wiener schnitzel` — zero rows for the word, and the exact row exists

```
none  schnitzel                          -      (nothing)
none  wiener schnitzel                   -      (nothing)
none  wienerschnitzel                    -      (nothing)
weak  breaded veal                       0.220  Veal, leg (top round), separable lean only, cooked, pan-fried, breaded
```

```
173819|Veal, leg (top round), separable lean and fat, cooked, pan-fried, breaded
175271|Veal, leg (top round), separable lean only, cooked, pan-fried, breaded
```

`select ... where description ilike '%schnitzel%'` returns **zero rows**, and
173819 is Wiener Schnitzel described in USDA's own vocabulary. See §4 for why
the *generic* word `schnitzel` must not be mapped to it.

---

## 3. Entity gaps — searched by ingredient and by category, genuinely absent

Each of these was checked with `ilike` on the dish name, on its defining
ingredient, and on its category before being filed.

- **haggis** — `none`. `sheeps pluck`, `sheep lung`, `lamb lung`, `mutton suet`
  all `none` or weak; `Lamb, variety meats and by-products, lungs, raw` exists
  (`weak 0.182`) but there is no offal-and-oatmeal row of any kind. The signature
  ingredient is as unreachable as the dish. Genuine gap; the honest treatment is
  a `dish_ingredient` decomposition (lamb offal + oatmeal + suet + onion), all
  four of whose parts do exist.
- **quark** — `select ... ilike '%quark%'` returns zero rows. Nearest by
  category is the `Cheese, cottage, dry curd` family (2705753) — a fresh
  acid-set curd, which is what quark is. This is a fallback, not a synonym.
- **skyr** — zero rows. Nearest is `Yogurt, Greek, nonfat milk, plain`
  (2705424); skyr is technically a cheese and nutritionally a nonfat strained
  yogurt.
- **muesli** — zero rows; `Cereals ready-to-eat, granola, homemade` (171646) is
  the only uncooked-oat-and-fruit-and-nut mixture. Granola is oil-and-syrup
  toasted and muesli is not, so this is a weak fallback at best. Recorded and
  **not** proposed.
- **marzipan** — zero rows; `Almond paste` (2707535) exists. Different
  almond:sugar ratio (roughly 1:1 vs 2:1), so energy is close and the sugar
  figure is not.
- **raclette, appenzeller, vasterbotten, wensleydale, red leicester, double
  gloucester, caerphilly, stilton** — all `none`. `Cheese, blue` (172175) and
  `Cheese, cheddar` are real neighbours for some of them; see §4 for which ones
  I will and will not encode.
- **stollen, sachertorte, kaiserschmarrn, bienenstich, spaetzle, knödel,
  maultaschen, currywurst, leberkäse, weisswurst, rösti, bitterballen,
  stroopwafel, speculaas, oliebollen, smørrebrød, gravlax, rakfisk,
  surströmming, leverpostej, remoulade, knäckebröd, semla, kanelbulle,
  frikadeller, aebleskiver, lutefisk, karjalanpiirakka** — all `none`. Nothing
  in the database is a near neighbour by ingredient *and* by preparation for
  most of these. They are composed dishes and belong to `dish_ingredient`
  decomposition, not to a synonym table.
- **marmite / vegemite / bovril** — `none`, but `Yeast extract spread` probes
  `auto 0.667`. That one is a clean synonym.
- **crumpet / crumpets, pikelet, teacake, bap, barm cake, oatcake, flapjack,
  hobnob, digestives, malt loaf, parkin, treacle, mushy peas, faggots** — `none`
  and no near neighbour by ingredient. Genuine gaps.

---

## 4. Deliberately not encoded

I am judged on these as much as on the proposals.

- **`biscuit` → anything.** British biscuit is a sweet baked good (`Cookie, NFS`,
  492 kcal); US biscuit is a savoury quick bread (`Biscuit, NFS`, 370 kcal, and
  what the resolver currently auto-takes via `KFC, biscuit`). They are different
  foods and the correct answer depends on who is typing. An alias would be
  wrong for half the users and would cache. The right fix is to **remove the
  auto-match** (so the model, which sees the meal context, decides) — not to add
  a mapping.
- **`schnitzel` → `Veal, leg (top round), ..., breaded`.** Only *Wiener*
  Schnitzel is veal, and in Germany and Austria it is legally protected as such
  precisely because the unqualified word overwhelmingly means pork. Encode
  `wiener schnitzel` → the veal row (high). Leave bare `schnitzel` to the model,
  or map it to a breaded pork cutlet — which this database does not have
  (`ilike '%pork%' and '%breaded%'` returns only bacon and sausage rows).
- **`halloumi` → `cheese`, and any "British/Nordic cheese → Cheddar" rule.**
  An over-broad parent is nutritionally useless: this database's cheeses run
  from 82 kcal (`Cheese, cottage, NFS`) to over 400. I propose Red Leicester and
  Double Gloucester → `Cheese, cheddar` because they are cheddar-process cheeses
  with the same composition, and I refuse Wensleydale, Caerphilly and
  Lancashire, which are lower-fat crumbly territorials.
- **`muesli` → granola.** Granola is baked with oil and syrup; muesli is not.
  The energy gap is 30–40% and it is exactly the direction that flatters the
  user. Report the gap, do not paper it.
- **`neeps` → `Turnip, raw`.** In Scotland "neeps" and often "turnip" mean
  swede/rutabaga (37 kcal), not the white turnip (28 kcal) USDA calls turnip.
  `turnip swede` currently probes `weak 0.412 Turnip, raw`. I propose
  `swede` → `Rutabaga, raw` (high) and explicitly **decline** to touch `turnip`,
  because for an English user it does mean the white turnip and remapping it
  would break the majority case to fix the minority one.
- **`cottage pie` → `Shepherd's pie` as a synonym.** Proposed as a
  `nutritional_fallback` only. The row is a real dish with a real profile and
  cottage pie is close to it, but they are not the same food and the card must
  keep saying which row it used.
- **`gravlax` → `Fish, salmon, chinook, smoked, (lox)`.** Proposed at medium.
  Lox is brine-cured and gravlax is salt-and-sugar-cured with dill; macros are
  close, the sugar and sodium figures are not identical. Fallback, not identity.
- **`rakfisk`, `surströmming`, `hákarl`, `lutefisk`.** No neighbour exists and I
  will not invent one from a fresh-fish row: lye-treatment and long fermentation
  change water, protein and sodium substantially and in directions I cannot
  bound. Report as gaps.
- **`paneer` → `mozzarella`-shaped mappings generally.** Not in my domain, but
  the same reasoning kills `quark` → `Cheese, cream` (342 kcal vs quark's ~70)
  and `skyr` → `Yogurt, whole milk`. Where I propose a dairy fallback I have
  matched it on fat basis, not on culture.

---

## 5. One mechanism finding, outside the food-knowledge remit

`search_foods` orders by `sim + ts_rank` (plus precedence as tie-break) but the
verdict floors are applied to `sim` of whichever row that ordering surfaced.
The two disagree in practice:

```
## cauliflower cheese weak
    0.3   Broccoli salad with cauliflower, cheese, bacon bits, and dressing   <- head, sets the verdict
    0.545 Cauliflower, raw
    0.545 Cauliflower, raw
    0.5   Fried cauliflower

## roast chicken auto
    0.65  Chicken, chicken roll, roasted     <- head, 0.65 -> auto
    0.361 Chicken, roasting, meat only, cooked, roasted
    0.419 Chicken, roasting, meat only, raw   <- higher sim than the row above it
```

`cauliflower cheese` is declared `weak` while the list contains a 0.545, and the
`roast chicken` list is not monotone in `sim` at all. Whatever is decided about
thresholds, the number the threshold is compared against should be the number the
list is ordered by. Flagged for whoever picks up RECONCILED §3.3.

---

## 6. Coverage

994 terms. British and Irish dishes (114), British-vs-American ingredient names
and spellings (115), German/Austrian/Swiss (140), Dutch and Nordic (140),
defining ingredients of the dishes above (137 + 97), everyday British composite
foods and confectionery (125), and preparation/cut variants (126).

Every dish named in the brief was probed together with its signature
ingredient. Where the dish is absent and the ingredient is also absent —
haggis and sheep's pluck, spätzle and any egg-noodle-dough row, surströmming
and any fermented-herring row — that is recorded as an entity gap with the
ingredient search pasted. Where the dish is absent and the ingredient is
present but unreachable — black pudding and `Blood sausage`, wiener schnitzel
and `Veal, ..., pan-fried, breaded`, fish fingers and `Fish, stick` — that is a
reachability gap and is the more valuable finding.
