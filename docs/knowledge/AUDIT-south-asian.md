# Knowledge audit — South Asian

26 Aug 2026. Domain: Indian (Punjabi, Bengali, Gujarati, Kerala, Tamil,
Hyderabadi, Goan, Kashmiri, Rajasthani, Odia), Pakistani, Bangladeshi, Sri
Lankan, Nepali. Dishes, ingredients, aliases, regional names and
transliteration variants.

Method: `scripts/probe_knowledge.py` on **1,026 distinct terms**, batched
through `--file`. Every claim below is pasted probe output or a `SELECT`
against the live database. No writes. The integration suite was not run.

```
ask=136 (13%)  auto=110 (11%)  none=477 (46%)  weak=303 (30%)
```

---

## 0. The shape of the corpus

The entire South Asian knowledge in this database is **41 FNDDS rows** plus a
handful of SR Legacy ingredient rows. That is the ceiling on what any
reachability fix can recover.

```
2705700 Barfi or Burfi, Indian dessert     2707431 Lentil curry
2706388 Beef curry                          2707432 Lentil curry with rice
2706389 Beef curry with rice                2710066 Pakora
2706538 Biryani with chicken                2709631 Palak Paneer
2706490 Biryani with meat                   2707429 Papad, grilled or broiled
2708985 Biryani with vegetables             2707430 Sambar, vegetable stew
2707713 Bread, chappatti or roti            2708730 Samosa
2707613 Bread, naan                         2709128 Upma
2707715 Bread, paratha                      2709130 Vada
2707714 Bread, puri                         2710067 Vegetable curry
2709632 Channa Saag                         2710178 Curry sauce
2705740 Cheese, paneer                      2709309 Chutney
2706437 Chicken curry                       2708347 Dosa, plain
2705686 Firni, Indian pudding               2709129 Dosa, with filling
2706460 Fish curry                          2708346 Idli
2710351 Ladoo, round ball                   2707427 Dal
2710168 Ghee, clarified butter
+ SR Legacy: 171314 Butter, Clarified butter (ghee) · 174288 Chickpea flour
  (besan) · 168106 Papad · 171844/174075 Bread, chapati or roti · 171845/174077
  Bread, naan · 174076 Bread, paratha
```

Confirmed **zero rows** anywhere in `food` for: `halva|halwa`, `kheer`,
`raita`, `lassi`, `jaggery`, `asafo(etida)`, `curry leaf|curry leaves`,
`kokum`, `amchur`, `nigella`, `ajwain|carom`. Those are genuine entity gaps.

---

## 1. The flagship: `paneer` auto-matches a spinach dish

```
auto  paneer
        0.636  Palak Paneer      [survey_fndds_food]
        0.500  Cheese, paneer    [survey_fndds_food]
```

The correct row is **rank 2 on the same list** and is never consulted, because
the head cleared `AUTO_MATCH_SIMILARITY = 0.62`. None of the three guards can
fire: `label_absent` passes (the word "paneer" *is* in "Palak Paneer"),
`unrequested_qualifier` inspects only comma segments and "Palak Paneer" has
none, `state_conflicts` has nothing to contradict.

```
Cheese, paneer   299 kcal   15.9 g protein   15.5 g fat
Palak Paneer     101 kcal    5.4 g protein    7.0 g fat
```

A 3× energy understatement and a 3× protein understatement on the single most
logged South Asian ingredient — silent, and `upsert_alias` caches it forever
with no command that can repoint it. Every phrasing a cook actually uses lands
on the dish rather than the cheese:

```
ask   paneer raw          0.467  Palak Paneer
weak  paneer fried        0.412  Palak Paneer
weak  fried paneer        0.412  Palak Paneer
weak  paneer tikka        0.412  Palak Paneer
weak  shahi paneer        0.412  Palak Paneer
weak  matar paneer        0.412  Palak Paneer
weak  kadai paneer        0.412  Palak Paneer
weak  paneer tikka masala 0.348  Palak Paneer
weak  saag paneer         0.438  Palak Paneer
weak  paneer curry        0.421  Cheese, paneer
```

Only two phrasings reach the cheese, and nobody types them:

```
auto  paneer cheese          1.000  Cheese, paneer
auto  paneer indian cheese   0.667  Cheese, paneer
```

`panir` returns **nothing at all**.

---

## 2. Wrong-confident matches (`auto` onto a semantically wrong row)

Worst class: silent, and it writes an alias that is never re-checked.

| Query | Auto-matched | sim | Should be | Cost |
|---|---|---|---|---|
| `paneer` | `Palak Paneer` | 0.636 | `Cheese, paneer` | 299→101 kcal, 15.9→5.4 g protein |
| `almond` | `Oil, almond` | 0.636 | `Almonds, NFS` | 598→884 kcal, **21→0 g protein**, 52→100 g fat |
| `walnut` | `Oil, walnut` | 0.636 | `Nuts, walnuts, english` | same shape |
| `white rice cooked` | `Rice, white, cooked, glutinous` | 0.643 | `Rice, cooked, NFS` | 129→96 kcal on the largest-mass item of the meal |
| `coconut cream` | `Pie, coconut cream` | 0.765 | `Coconut cream, canned, sweetened` | a dessert pie for a curry base |
| `cucumber raita` | `Cucumber, raw` | 0.647 | (no raita row) | 16 kcal for a yogurt dish |
| `tamarind rice` | `Tamarind` | 0.643 | (no puliyodarai row) | fruit pulp for a rice dish |
| `milk rice` (kiribath) | `Rice milk` | 1.000 | (no kiribath row) | 47 kcal beverage for a coconut rice |
| `ginger` | `Tea, ginger` | 0.636 | `Ginger root, raw` | 1 kcal/100 g |
| `spinach cooked` | `Malabar spinach, cooked` | 0.652 | `Spinach, NS as to form, cooked` | different species; 23 vs 59 kcal |
| `yogurt plain` | `Yogurt, plain, nonfat` | 0.650 | `Yogurt, plain, whole milk` | dahi is whole-milk; 50/0.1 g fat vs 78/4.5 |

Candidate lists, verbatim:

```
auto  almond
        0.636  Oil, almond
        0.636  Almond oil
        0.538  Flour, almond
        0.538  Almond paste
        0.500  Cookie, almond
        0.500  Almond butter
auto  ginger
        0.636  Tea, ginger
        0.467  Ginger root, raw
        0.350  Spices, ginger, ground
auto  coconut cream
        0.765  Pie, coconut cream
        0.481  Coconut cream, canned, sweetened
auto  milk rice
        1.000  Rice milk
        0.455  Rice, cooked, with milk
```

`milk rice` scoring 1.000 against `Rice milk` is the length mechanism at its
purest: trigram similarity is word-order blind, and the two-word query is a
permutation of the two-word description, so it is a *perfect* match to the
opposite food.

`almond` and `walnut` are not South-Asian-specific defects, but badam and
akhrot are load-bearing in korma, kheer, halwa and thandai, so this domain
walks into them constantly. Logging 30 g of almonds in a korma as 265 kcal of
pure oil with **zero protein** is exactly the failure mode invariant 1 exists
to prevent, arriving through the resolver instead of the model.

---

## 3. Reachability gaps — the right row exists and the name cannot reach it

### 3.1 The named word is *inside* the description and still loses

The RECONCILED §1 mechanism, in its purest South Asian form. In each case the
description literally contains the user's word.

```
weak  ghee     0.227  Butter, Clarified butter (ghee)   [sr_legacy]
                0.227  Ghee, clarified butter            [fndds]
auto  clarified butter        0.773  Butter, Clarified butter (ghee)
```

Ghee is the defining fat of the entire cuisine. The query `ghee` scores 0.227
against **two** rows that both spell it out, while the English paraphrase a
South Asian cook would never type auto-matches at 0.773. `desi ghee` and `ghi`
return nothing at all.

```
weak  besan    0.286  Chickpea flour (besan)
auto  chickpea flour   0.714  Chickpea flour (besan)

weak  chapati  0.170  Bread, chapati or roti, plain, commercially prepared
                0.136  Bread, chapati or roti, whole wheat, ...
weak  roti     0.217  Bread, chappatti or roti
                0.106  Bread, chapati or roti, plain, commercially prepared
ask   roti bread     0.478  Bread, chappatti or roti
ask   chapatti bread 0.583  Bread, chappatti or roti

weak  barfi    0.222  Barfi or Burfi, Indian dessert
weak  burfi    0.222  Barfi or Burfi, Indian dessert
auto  barfi indian dessert   0.778  Barfi or Burfi, Indian dessert

weak  firni    0.286  Firni, Indian pudding
auto  firni pudding          0.667  Firni, Indian pudding

weak  sambar   0.333  Sambar, vegetable stew
auto  sambar vegetable stew  1.000  Sambar, vegetable stew

weak  ladoo    0.353  Ladoo, round ball
auto  ladoo ball             0.647  Ladoo, round ball

weak  pigeon pea   0.243  Pigeon peas (red gram), mature seeds, raw
weak  bengal gram  0.316  Chickpeas, (garbanzo beans, bengal gram), dry
weak  mungo beans  0.429  Mungo beans, mature seeds, raw
weak  towelgourd   0.407  Gourd, dishcloth (towelgourd), raw
weak  chickpeas cooked  0.239  Chickpeas (garbanzo beans, bengal gram), mature
                                seeds, cooked, boiled, with salt
weak  naan plain   0.220  Bread, naan, plain, commercially prepared, refrigerated
```

Note the shape: in **every** one of these, adding a redundant English word the
user did not say ("bread", "pudding", "ball", "vegetable stew", "indian
dessert") moves the same row from `weak` to `auto`. The score is measuring
description length, not correctness — exactly r = −0.87 to −0.94.

These are all recoverable (`weak` still reaches the model tier with the right
row at the head), but the resolver's own confidence signal says "the right
answer is probably absent" while the right answer is ranked first.

### 3.2 Terminal reachability gaps — verdict `none`, and USDA has the row

These never reach the model tier at all. `plainto_tsquery` is AND over every
word and the trigram `%` operator's default 0.3 floor is not met, so
`_candidates` returns an empty list and the item is simply unresolved.

| Query | Verdict | Row that exists and was never returned |
|---|---|---|
| `masala dosa` | none | `2709129 Dosa, with filling` |
| `chana masala`, `chole` | none | `2709632 Channa Saag` (nearest), `Chickpeas, NFS` |
| `biriyani`, `briyani`, `biriani`, `birayani`, `byriani` | none | `2706490 Biryani with meat` etc. |
| `ridge gourd`, `turai`, `luffa` | none / `Turtle` 0.300 | `168414 Gourd, dishcloth (towelgourd), raw` |
| `bottle gourd`, `lauki` | none / `Lau lau` 0.429 | `169232 Gourd, white-flowered (calabash), raw` |
| `karela` | none | `168393 Balsam-pear (bitter gourd), pods, raw` |
| `moringa`, `moringa pods`, `moringa leaves` | none | `170483 Drumstick pods, raw`, `168416 Drumstick leaves, raw` |
| `prawn`, `prawns`, `king prawn`, `tiger prawn` | none | `2706360 Shrimp, NFS` |
| `urad`, `kala chana`, `kabuli chana`, `lobia` | none | `174259 Mungo beans…`, `173756 Chickpeas…` |
| `atta`, `maida`, `sooji`, `suji`, `bajra`, `jowar`, `ragi` | none | `Wheat flour, whole-grain`, `Semolina`, `Millet`, `Flour, sorghum` |
| `pappadam` / `poori` / `rotee` / `dhaal` | weak / none | `Papad`, `Bread, puri`, `Bread, chappatti or roti`, `Dal` |
| `mutton biriyani` | none | `Biryani with meat` |
| `dahi`, `dahee`, `doi` | none | `Yogurt, plain, whole milk` |
| `methi`, `kasuri methi` | none | `171324 Spices, fenugreek seed` (seed only — see §5) |

`prawn` is the one that surprised me most. It is the standard word for shrimp
in Indian, Pakistani, Sri Lankan and Bangladeshi English — not a regional
curiosity — and every form of it returns literally nothing while `shrimp`
auto-matches at 0.636.

The five biryani misspellings returning `none` while `biryani` itself returns
a candidate list is the transliteration failure in its cleanest form: there is
no canonical Latin spelling of a Devanagari or Urdu word, so the *user* has no
way to know which of five equally correct spellings the database happens to
hold.

---

## 4. Every named dal collapses onto one generic row

The task asked whether dals are distinguished. **They are not, and each one has
its own USDA row.**

```
weak  urad dal     0.444  Dal
weak  toor dal     0.444  Dal
ask   tur dal      0.500  Dal
weak  arhar dal    0.400  Dal
weak  moong dal    0.400  Dal
weak  mung dal     0.444  Dal
weak  masoor dal   0.364  Dal
weak  chana dal    0.400  Dal
weak  yellow dal   0.364  Dal
weak  dal makhani  0.333  Dal
weak  dal tadka    0.400  Dal
weak  nepali dal   0.364  Dal
auto  dal          1.000  Dal
```

The rows that exist and are never returned for these queries:

```
Dal (FNDDS, cooked dish)                       145 kcal  8.6 g prot  7.5 g fibre
Mungo beans, mature seeds, raw   (urad)        341       25.2        18.3
Mung beans, mature seeds, raw    (moong)       347       23.9        16.3
Lentils, pink or red, raw        (masoor)      358       23.9        10.8
Pigeon peas (red gram), raw      (toor/arhar)  343       21.7        15.0
Chickpeas (…bengal gram), raw    (chana)       378       20.5        12.2
```

Two separate errors ride together here. The **identity** error: masoor at
10.8 g fibre and urad at 18.3 g are a 70% spread, and folding them into one
row erases it. The **state** error: `Dal` is a cooked dish and the specific
rows are dry seeds, a 2.4× energy difference, so any fix that points a dal name
at a raw row without also fixing state makes things worse, not better.

`dalchini` (cinnamon) resolving to `Dal` at 0.300 is the same collapse read
backwards — a three-letter substring is enough to pull an unrelated spice into
the lentil row.

---

## 5. `curry leaf` — the classic conflation, measured

USDA has **no** curry leaf row (`SELECT … WHERE description ~* 'curry leaf|curry
leaves'` → 0 rows). What the query returns instead:

```
ask   curry leaf
        0.500  Lentil curry
        0.375  Beef curry
        0.375  Fish curry
        0.353  Curry sauce
        0.333  Chicken curry
        0.308  Lentil curry with rice
weak  curry leaves       0.444  Lentil curry
weak  curry leaf fresh   0.400  Fish curry
weak  fresh curry leaves  0.364  Fish curry
auto  curry powder       0.650  Spices, curry powder
```

This is a `none`/`weak` situation *dressed as* an `ask`. Every candidate is a
composite curry **dish**; there is no leaf, no herb, no spice on the list. If
the model tier picks any of them, ten curry leaves (about 1 g) become a portion
of lentil curry. The brief's exception applies: the candidate list itself is
nonsense, so the `ask` is a defect and not the system working.

The right answer is that curry leaf is a **garnish aromatic used at ~1 g and
discarded or eaten whole**, and the honest handling is to omit it, not to
approximate it onto a curry dish. `curry powder` correctly reaching `Spices,
curry powder` while `curry leaf` reaches six curry dishes is the conflation in
one screen.

Related, and a real preparation mismatch rather than a naming one:

```
weak  fenugreek leaves   0.407  Spices, fenugreek seed
weak  fenugreek leaf     0.385  Spices, fenugreek seed
auto  fenugreek seed     0.714  Spices, fenugreek seed
```

Methi leaves (a green, eaten by the bunch in methi paratha or aloo methi) and
methi seeds (a bitter spice used by the teaspoon) are entirely different foods.
USDA holds only the seed. Pointing `methi` at the seed row would let 150 g of
methi greens be scored as 150 g of fenugreek seed.

---

## 6. Nonsense candidate heads (comedy, but they are what the model is shown)

```
ask   paya            0.455  Papaya, raw          (trotters → fruit)
weak  poha            0.128  Groundcherries, (cape-gooseberries or poha), raw
weak  misal           0.375  Miso
weak  hoppers         0.333  Peppers, hot, raw
weak  malai           0.333  Marmalade
weak  rava            0.364  Guava, raw
weak  maida           0.300  Mai Tai
weak  arbi            0.083  ARBY'S, roast beef sandwich, classic
weak  laung           0.429  Lau lau
weak  lauki           0.429  Lau lau
weak  mooli           0.333  Moose
weak  nachni          0.308  Nachos, NFS
weak  groundnut       0.429  Groundhog
weak  turai           0.300  Turtle
weak  jamun           0.429  Jam
ask   ber             0.500  Beer
weak  chai            0.333  SILK Chai, soymilk
weak  mishti          0.333  Miso
weak  churma          0.364  Churros
weak  ker sangri      0.353  Sangria, red
weak  boiled egg indian  0.368  Squash, Indian, cooked, boiled (Navajo)
ask   goat mince      0.500  Goat milk
ask   mustard fish    0.615  Mustard
```

`poha` at 0.128 against a Hawaiian gooseberry is the funniest and also the most
instructive: the USDA row happens to carry "poha" as a regional synonym for
*Physalis peruviana*, so a homonym in a parenthetical outranks the flattened
rice the user meant, which USDA does not hold at all.

`Squash, Indian, cooked, boiled (Navajo)` matching `boiled egg indian` is worth
naming separately — SR Legacy's "(Navajo)" and "(Northern Plains Indians)" rows
mean *Native American*, and the token `indian` is a live trap for anyone who
disambiguates a South Asian dish by writing "indian" after it. Thirty-four
such rows exist in `food`.

---

## 7. Entity gaps — searched by ingredient and by category, nothing near

For each of these I searched the description text by name **and** by the
composing ingredient and category, and pasted the result. These are real
absences, not reachability failures.

- **halwa / halva / halvah** — `~* 'halva|halvah|halwa'` → **0 rows**. Nearest
  by composition (`sooji halwa` = semolina + ghee + sugar) is `Semolina,
  enriched` + `Butter, Clarified butter (ghee)` as an ingredient list. There is
  no cooked-sweet row of any kind that resembles it. `carrot halwa` currently
  reaches `Muffin, carrot` at 0.350.
- **kheer / payasam** — `~* 'kheer|rice pudding'` → 1 row, `Restaurant, Latino,
  arroz con leche (rice pudding)`. That is a genuine near neighbour by
  composition (rice, whole milk, sugar) and is unreachable from either word:
  `kheer` → none, `payasam` → `Papayas, raw` 0.333. `Firni, Indian pudding`
  (144 kcal) is the closer neighbour — firni is the same dish made with ground
  rice — and is reachable only as `firni pudding` / `indian pudding`.
- **raita** — `~* 'raita'` → **0 rows**. Composition is `Yogurt, plain, whole
  milk` + `Cucumber, raw`, both present. Currently `cucumber raita` auto-matches
  the cucumber alone and drops the yogurt entirely (§2).
- **lassi / chaas** — `~* 'lassi'` → 0 rows. `Buttermilk` auto-matches at 1.000
  and is the honest neighbour for salted lassi/chaas; sweet and mango lassi have
  no neighbour that carries their sugar.
- **jaggery / gur / nolen gur / palm jaggery** — `~* 'jaggery|palm sugar'` → 0
  rows. `Molasses` exists and is the nearest by process (unrefined cane
  concentrate) but not by composition — jaggery is ~10% moisture solid sucrose
  at ~383 kcal, molasses is a syrup at ~290. Reported as an entity gap with a
  low-confidence neighbour, not as a mapping.
- **asafoetida / hing** — 0 rows. Used at ~0.1 g. Correct handling is omission.
- **kokum, amchur, ajwain, kalonji/nigella, kasundi** — 0 rows each. All
  sub-gram spices; omission is right.
- **kulfi, falooda, rasgulla, gulab jamun, jalebi, mysore pak, sandesh,
  rasmalai, peda, soan papdi** — 0 rows. The only Indian sweets USDA holds are
  `Barfi or Burfi`, `Ladoo, round ball` and `Firni`.
- **Sri Lankan corpus is empty.** `lamprais`, `hoppers`, `string hoppers`,
  `kottu roti`, `pol sambol`, `kiribath`, `watalappan`, `ambul thiyal`, `seeni
  sambol` — every one `none` or nonsense. Searched `~* 'sri lanka'` → 0 rows.
- **Nepali corpus is empty.** `momo`, `momos`, `dal bhat`, `gundruk`, `sel
  roti`, `thukpa`, `sukuti`, `chatamari`, `yomari`, `juju dhau` — all `none`.
  `Wonton, dumpling or pot sticker, steamed` (reached only by `steamed
  dumpling`, 0.459) is the honest neighbour for momo; `Bamboo shoots, cooked`
  is a real match for the *tama* in aloo tama.
- **Bengali fish** — `ilish/hilsa`, `rohu`, `katla`, `pabda`, `bhetki`,
  `magur`, `chital`: all `none`. Searched `~* 'carp|tilapia|mackerel|pomfret'`.
  `Fish, carp` (FNDDS) and `Fish, carp, raw` exist and are a defensible
  neighbour for rohu and katla, both of which *are* carps (Labeo rohita, Catla
  catla are Cyprinidae). Hilsa is a shad and its nearest neighbour by fat
  profile is `Fish, mackerel, Atlantic` — that one I am flagging as medium.
- **Vanaspati** (hydrogenated vegetable fat, still widely used in Pakistan and
  in Indian commercial sweets) — `none`. Nutritionally distinct from ghee
  because of trans fat, and USDA's shortening rows are a poor proxy for the
  Indian product. Reported, not mapped.

---

## 8. Deliberately rejected

Encoding these would be worse than leaving the gap.

- **`paneer → Cheese, NFS` or `paneer → mozzarella`.** `indian cheese` already
  reaches `Cheese, NFS` at 0.389 and it is nearly useless: "cheese" spans 300 to
  400 kcal and 0 to 35 g fat. `Cheese, paneer` exists, so any parent-category
  mapping here is strictly worse than fixing reachability. Mozzarella is the
  culturally wrong version of the same error — paneer is acid-set and
  non-melting, mozzarella is rennet-set and pasta filata.
- **`dahi → Yogurt, plain, nonfat`.** Nonfat is the American default and the
  wrong one: dahi is set from whole buffalo or cow milk. `Yogurt, plain, whole
  milk` is the correct target; the nonfat row is what the ranking currently
  hands you (`yogurt plain` → auto 0.650 nonfat) and encoding it would make the
  accident permanent.
- **`ragi → Millet` / `ragi flour → Flour, rye`.** `ragi flour` currently reaches
  `Flour, rye` at 0.500, which is simply a different grain. `Millet flour` is
  Panicum miliaceum; ragi is Eleusine coracana and carries roughly 3× the
  calcium that is the *reason* people eat it. Proposing `finger millet → Millet`
  at medium is defensible for energy and macros; proposing it as a synonym is
  not, and no mapping should be made that implies the calcium figure transfers.
- **`jaggery → Molasses`.** Same process family, different physical form and
  ~30% different energy density per gram. A person weighing 20 g of jaggery
  would get a syrup's figures. Leave it as an entity gap; `/food` with a label
  is the right route.
- **`biryani → Rice, cooked, NFS`.** Biryani is 145 kcal/100 g at 6.8 g fat;
  plain rice is 129 at 0.3. The fat is the whole difference and a rice fallback
  erases it. `Biryani with meat/chicken/vegetables` all exist — this is a
  spelling problem, not a missing-food problem.
- **`halwa → Semolina` or `kheer → Rice, cooked`.** Both would drop the ghee and
  the sugar, which is most of the energy. A dish-ingredient decomposition is the
  only honest route, and it must include the fat.
- **`hoppers → Bread, naan`, `dosa → pancake`, `idli → steamed bun`.** All
  fermented-batter South Asian breads; none of the Western neighbours share the
  fermentation, the flour, or the fat. `Dosa, plain` and `Idli` exist; hoppers
  do not, and inventing a bread neighbour for them is guesswork.
- **`prawn → Crustaceans, shrimp, cooked` at high confidence for the *state*.**
  The synonym prawn→shrimp is high confidence. Which shrimp row is not: `Shrimp,
  NFS` (146 kcal, cooked) versus the raw rows is a state decision, and the
  synonym should point at the same NFS row `shrimp` itself reaches so the
  existing state machinery still applies.
- **`curry leaf → any curry row`.** Stated at length in §5. Omission is correct.
- **`mutton → Lamb`.** In South Asia mutton means **goat**, not sheep. `Goat`
  (FNDDS, 142 kcal, 26.9 g protein) and `Game meat, goat, raw` both exist.
  Mapping mutton to lamb is the culturally incorrect mapping this audit is
  supposed to catch — lamb is 60% fattier. But it is region-conditional (British
  English "mutton" *is* adult sheep), so I am proposing it at medium and as a
  fallback, not a synonym.

---

## 9. What I would fix first, in order

1. **`paneer`.** One alias, 3× error, most-logged ingredient in the domain.
2. **The `auto` band generally.** Eleven of 110 autos in this domain are onto a
   semantically wrong row, and every one caches. `almond → Oil, almond` and
   `white rice cooked → glutinous` are not South Asian bugs but they land here
   hardest.
3. **`prawn`.** Zero cost, zero ambiguity, currently returns nothing.
4. **Transliteration.** Five biryani spellings, `panir`, `idly`, `pakoda`,
   `poori`, `pappadam`, `dhaal`, `chappati` — all reach nothing or scrape a
   weak floor while the row sits there.
5. **The dal family**, but only together with a state decision (§4).
6. **`ghee`, `besan`, `roti`, `chapati`, `sambar`, `barfi`, `firni`, `ladoo`** —
   the rows that contain the user's own word and score under 0.30 against it.
   These are §1 of RECONCILED, and no per-term alias fixes the mechanism; they
   are listed as synonyms here because that is the only lever this audit has.
