# Knowledge audit — Chinese cuisine

26 Aug 2026. Probe: `scripts/probe_knowledge.py` at commit `d359db5`
(`nutrai/db.py` gained the `covers DESC` primary sort key *during* this audit,
in `d359db5`; every number below was re-measured against that HEAD in one run
so the whole set is internally consistent). Database read-only, `SELECT` only.

**741 terms probed** across regional dishes, dim sum, ingredients, condiments,
tofu forms, noodle forms, pinyin / Cantonese romanisation / English menu names.

    none = 193 (26%)   weak = 283 (38%)   ask = 155 (21%)   auto = 110 (15%)

Full probe output: `scripts/probe_knowledge.py --file` over the 741-line list,
reproduced verbatim in the tables below for every case discussed.

---

## 0. The headline

Six `auto` verdicts in this domain put a materially wrong row into the log with
no model consulted and cache an alias that is never re-checked. In descending
order of harm:

```
auto  glutinous rice           0.714  Flour, rice, glutinous          (368 kcal)
                                      vs Rice, white, cooked, glutinous (96 kcal)
auto  beef in black bean sauce 0.727  Black bean sauce                (6.3 g protein)
auto  sweet potato             0.812  Pie, sweet potato               (269 kcal)
                                      vs Sweet potato, NFS             (115 kcal)
auto  rapeseed oil             0.688  Oil, grapeseed        (canola exists, unreachable)
auto  seaweed                  0.667  Soup, seaweed         (Seaweed, raw ties at 0.667)
auto  bang bang chicken        0.625  Chicken, back
auto  pickled cabbage fish     0.667  Cabbage, red, pickled (a fish dish, no fish)
```

Three more are wrong but less costly: `ginger → Tea, ginger` (0.636),
`mixed vegetables → Mixed vegetable juice` (0.625),
`water chestnut flour → Flour, chestnut` (0.714).

Everything else in this document is §1's length effect wearing Chinese clothes.

---

## 1. Wrong-confident matches, with the numbers

### 1.1 `glutinous rice` → `Flour, rice, glutinous`

```
== glutinous rice auto
    0.714 Flour, rice, glutinous | foundation_food
    0.536 Rice, white, cooked, glutinous | survey_fndds_food
    0.500 Cake made with glutinous rice | survey_fndds_food
    0.405 Rice, white, glutinous, unenriched, uncooked | sr_legacy_food
    0.405 Rice, white, glutinous, unenriched, cooked | sr_legacy_food
```

| row | kcal/100 g | carb |
|---|---|---|
| `Flour, rice, glutinous` (taken) | 368 | 80.1 |
| `Rice, white, cooked, glutinous` (2708422, right) | 96 | 21.0 |

**3.8×.** A 200 g bowl of sticky rice — zongzi, lo mai gai, tang yuan, the
filling of every sticky-rice dish in the domain — logs as 736 kcal instead of
192. It is silent, it passes the Atwater check (the flour row is internally
consistent), and the alias is written once and reused for ever.

The correct row is *on the list, at rank 2*. It loses because the flour row's
description is four words and the rice row's is five with two of them absent
from the query. This is §1 exactly.

`glutinous rice flour` correctly auto-matches the same flour row at 1.000, so
the two queries — which differ by a whole processing step and 3.8× the energy —
land on one row.

### 1.2 `beef in black bean sauce` → `Black bean sauce`

```
== beef in black bean sauce auto
    0.727 Black bean sauce | survey_fndds_food     (168 kcal, 6.3 g protein)
    0.462 Black bean salad | survey_fndds_food
    0.333 Barbecue beef, no sauce | survey_fndds_food
    0.321 Black beans, NFS | survey_fndds_food
```

A main course resolves to its condiment. 300 g logs 19 g protein where the beef
alone would carry ~50 g. `chicken in black bean sauce` escapes only by scoring
0.593 — six thousandths below the gate — and escalates. The two queries differ
in nothing that matters and get opposite treatment.

Category: `ingredient_vs_dish_ambiguity`. Note the direction: the usual worry is
a dish standing in for an ingredient; here the *sauce* stands in for the dish,
which is worse because it silently deletes the protein.

### 1.3 `sweet potato` → `Pie, sweet potato`, `pumpkin` → `Pie, pumpkin`

```
auto  sweet potato   0.812  Pie, sweet potato   (269 kcal)   vs Sweet potato, NFS 115
auto  pumpkin        0.727  Pie, pumpkin        (249 kcal)   vs Pumpkin, raw       26
ask   carrot         0.500  Muffin, carrot
ask   onion          0.500  Bread, onion
ask   zucchini       0.600  Bread, zucchini
```

A short vegetable name is a *prefix* of a longer dessert name, and the dessert
row is shorter overall than `Sweet potato, NFS`… no: `Pie, sweet potato` (17
chars) beats `Sweet potato, NFS` (17 chars) on trigram because the query's
trigrams cover a larger fraction of `Pie, sweet potato`'s set once the comma
boundary is counted. Whatever the mechanism, the ranking prefers the baked good
for five of the commonest vegetables in the domain (sweet potato and pumpkin
are the body of *di san xian*, *ba si di gua*, and every claypot).

The `carrot`/`onion`/`zucchini` cases escalate, so they are not defects by the
audit's rule — but the candidate list handed to the model is headed by a muffin
and a loaf of bread, which is the exception the rule names.

### 1.4 `rapeseed oil` → `Oil, grapeseed`

```
== rapeseed oil auto
    0.688 Oil, grapeseed | sr_legacy_food
    0.389 Oil, teaseed | sr_legacy_food
    0.368 Flaxseed oil | survey_fndds_food
    0.350 Oil, poppyseed | sr_legacy_food
```

USDA holds `Oil, canola` at **748278** (Foundation), **172336** (SR Legacy) and
`Canola oil` at **2710188** (FNDDS). Rapeseed oil *is* canola oil — the same
plant, *Brassica napus*; "canola" is the trade name coined in Canada for the
low-erucic cultivar and "rapeseed" is the British and Chinese-market word for
it (菜籽油, the default frying oil in Sichuan and Hunan cooking).

Energy is the same to within rounding, so nothing raises. The fatty-acid
profile is not: canola is ~9% α-linolenic and ~63% oleic; grapeseed is ~70%
linoleic and essentially no omega-3. A user tracking fat quality gets a
confidently wrong answer for the single most-used oil in half this cuisine.

`% rapeseed` returns exactly one row in the whole database — the grapeseed one.
The right answer is not merely mis-ranked, it is *unreachable by that word*.

### 1.5 `seaweed` → `Soup, seaweed` — an exact tie, decided by nothing

```
== seaweed auto
    0.667 Soup, seaweed | survey_fndds_food     <- taken
    0.667 Seaweed, raw | survey_fndds_food      <- 2709805, the ingredient
    0.615 Seaweed, dried | survey_fndds_food
    0.533 Seaweed, pickled | survey_fndds_food
```

An **exact float tie at 0.667**, broken by the trailing keys, and the soup won.
RECONCILED §D1 says precedence "only breaks exact float ties, which do not
occur". They occur. Here it decides between an ingredient and a dish, and the
system has no opinion about which it picked.

### 1.6 `bang bang chicken` → `Chicken, back`

```
== bang bang chicken auto
    0.625 Chicken, back | survey_fndds_food   (298 kcal, 25.7 protein, 20.8 fat)
    0.500 Barbecue chicken | survey_fndds_food
    0.474 Orange chicken | survey_fndds_food
    0.471 Fat, chicken | sr_legacy_food
    0.444 Chicken skin | survey_fndds_food
```

Bang bang ji is cold poached breast, shredded, under a sesame-and-chilli
dressing. `Chicken, back` is the bony, skin-heavy carcass cut — 298 kcal
against ~165 for poached breast, and the dressing (the entire point of the
dish, and most of its fat) is absent either way. The candidate list contains no
correct answer at all; the failure is that one of them was taken anyway.

The same head appears for `gong bao chicken` (0.500, ask — fine) and
`beggar chicken` (0.474, ask — fine). `Chicken, back` is a short-description
attractor for any two-word-modifier + "chicken" query in this cuisine.

### 1.7 `pickled cabbage fish` → `Cabbage, red, pickled`

```
== pickled cabbage fish auto
    0.667 Cabbage, red, pickled | survey_fndds_food
    0.619 Fish, pickled | survey_fndds_food
    0.593 Cabbage, green, pickled | survey_fndds_food
```

*Suan cai yu* is a Sichuan fish stew. The auto-match logs it as red pickled
cabbage: no fish, no protein, no oil. Every candidate is wrong; one was taken.

### 1.8 Smaller autos, same shape

```
auto  ginger                0.636  Tea, ginger      (1 kcal)  vs Ginger root, raw 80
auto  mixed vegetables      0.625  Mixed vegetable juice (28 kcal, a drink)
auto  water chestnut flour  0.714  Flour, chestnut  (Castanea nut flour)
                                   vs Waterchestnuts, chinese, (matai), raw @ 0.317
auto  custard bun           0.667  Custard          (the bun is deleted)
auto  shrimp with eggs      0.652  Egg roll, with shrimp
auto  red bean soup         0.714  Soup, bean       (savoury; hong dou tang is a dessert)
auto  chilli garlic sauce   0.650  Garlic sauce     (683 kcal/100 g — an oil emulsion)
auto  napa cabbage          0.684  Cabbage, napa, cooked   (unqualified query → cooked row)
auto  steamed fish          0.765  Fish, cod, steamed      (species invented)
```

`chilli garlic sauce` is the sleeper here: FNDDS `Garlic sauce` is 683 kcal /
100 g — an oil-and-garlic emulsion — while 蒜蓉辣椒醬 is a water-based chilli
condiment at roughly 70 kcal. A ~9× overcount, auto-matched.

`water chestnut flour` is worth separating out: 马蹄粉 is the starch of
*Eleocharis dulcis*, a near-pure carbohydrate used to set 馬蹄糕. `Flour,
chestnut` is milled *Castanea* nuts — 5 g protein, 8 g fibre, a different plant
family. `culturally_incorrect_mapping`, taken at 0.714.

---

## 2. Reachability gaps — USDA has the row, the query cannot reach it

These are the valuable ones. Each was checked with a `%description%` search
before being filed.

### 2.1 `tamari` — the word is *in* the row and it still loses

```
== tamari weak
    0.269 Soy sauce made from soy (tamari) | sr_legacy_food   <- rank 1 on `covers`
    0.600 Tamarind | survey_fndds_food                        <- higher sim
    0.400 Tamarinds, raw | sr_legacy_food
    0.400 Tamarind drink | survey_fndds_food
    0.333 Candies, Tamarind | sr_legacy_food
```

The `covers DESC` key added in `d359db5` rescues the ordering — the correct row
now leads — but `sim` is what `AUTO_MATCH_SIMILARITY` and
`WEAK_MATCH_SIMILARITY` read, and 0.269 is below the weak floor. So the probe
reports `weak`: "the right answer was probably never on the list", when the
right answer is sitting at position 1. **The verdict and the ranking now
disagree**, which is a general consequence of `d359db5` and shows up all over
this domain:

```
weak  squid       0.194  Mollusks, squid, mixed species, raw     <- correct, rank 1
weak  scallion    0.160  Onions, spring or scallions (...), raw  <- correct, rank 1
weak  sriracha    0.375  Sauce, hot chile, sriracha              <- correct, rank 1
weak  kelp        0.294  Seaweed, kelp, raw                      <- correct, rank 1
weak  suet        0.119  Beef, variety meats and by-products, suet, raw
weak  cellophane noodles 0.317 Noodles, chinese, cellophane or long rice (mung
                              beans), dehydrated                 <- correct, rank 1
```

Six correct heads reported as `weak`. Whatever consumes the weak floor should be
reading rank, not `sim`, or these get treated as "USDA does not have it".

### 2.2 `daikon` — nothing at all, for a row that exists four times

```
none  daikon        -      (nothing)
ask   chinese radish 0.467 Radish
none  luo bo        -      (nothing)
```

```sql
168451 | Radishes, oriental, raw
168452 | Radishes, oriental, cooked, boiled, drained, without salt
170122 | Radishes, oriental, cooked, boiled, drained, with salt
168453 | Radishes, oriental, dried
```

"Daikon" is the ordinary English word for this vegetable on every packet sold in
the West, and it returns zero rows. `chinese radish` reaches only FNDDS
`Radish` — the small red salad radish, a different plant with 4× the
peppery-compound content and half the water. Turnip cake (蘿蔔糕), *luo bo si
bing*, every braise and every hotpot uses this.

### 2.3 `prawn` — zero rows in the entire database

```
none  prawn         -      (nothing)
none  king prawn    -      (nothing)
none  prawns        -      (nothing)
weak  prawn cracker 0.421  Cracker, meal
ask   prawn crackers 0.474 Crackers, NFS
weak  king prawn chow mein 0.345 Noodles, chow mein
```

```sql
SELECT fdc_id, description FROM food WHERE description ILIKE '%prawn%';
-- 0 rows
```

while `Crustaceans, shrimp, cooked` (175180), `Crustaceans, shrimp, raw`
(175179) and a dozen more exist. Every British and Australian Chinese menu says
"king prawn". This is the single highest-traffic synonym gap in the domain and
it is a one-line fix.

### 2.4 `minced pork` / `pork mince` → Spam

```
== minced pork weak
    0.207 Luncheon meat, pork with ham, minced, canned, includes Spam (Hormel)
    0.203 Luncheon meat, pork and chicken, minced, canned, includes Spam Lite
    0.129 Luncheon meat, pork, ham, and chicken, minced, canned, ... SPAM, 25% less sodium
    0.438 Ham, minced
    0.312 Pork, NFS
auto  ground pork   1.000  Pork, ground
```

`Pork, ground` (2705863) is reached perfectly by the American word and not at
all by the British one. Mapo tofu, zhajiangmian, dan dan mian, lion's head,
every dumpling filling — minced pork is the most-used meat in this cuisine and
the `covers` key actively promotes Spam, because "minced" and "pork" both
appear in the Spam description.

### 2.5 `wood ear` / `black fungus` — one row, unreachable by its common name

```
none  wood ear             -      (nothing)
weak  wood ear mushroom    0.435  Mushroom, enoki
weak  black fungus         0.333  Bread, black
none  mu er                -      (nothing)
weak  cloud ear            0.375  Fungi, Cloud ears, dried
ask   cloud ear fungus     0.481  Fungi, Cloud ears, dried
```

```sql
SELECT fdc_id, description FROM food WHERE description ILIKE '%fungi%';
-- 168581 | Fungi, Cloud ears, dried | sr_legacy_food     (the only one)
```

USDA's single *Auricularia* row is named "Cloud ears". "Wood ear" is the same
genus and the name used on nine packets in ten; it returns nothing, and
"wood ear mushroom" lands on enoki. Standard in yu xiang rou si, hot and sour
soup, mu shu, and di san xian's cousins.

**Hazard to carry with the mapping:** the row is the *dried* form at 284 kcal /
100 g. Wood ear is eaten rehydrated at roughly 10× the mass. A synonym that
points a rehydrated 50 g portion at the dried row overstates by ~5×. The
mapping is right; it needs the same preparation-state guard `state_conflicts`
already applies.

### 2.6 `furu` — `fuyu` is in the database under its Japanese reading

```
ask   fermented tofu      0.536  Tofu, salted and fermented (fuyu)   (174280)
none  furu                -      (nothing)
weak  fermented bean curd 0.320  Soybean curd
```

腐乳 is *furu* in Mandarin and *fuyu* in Japanese; USDA transliterated the
Japanese. The Mandarin spelling — the one a person cooking Chinese food types —
reaches nothing.

### 2.7 Mung-bean and rice noodles

```
weak  cellophane noodles  0.317  Noodles, chinese, cellophane or long rice (mung
                                 beans), dehydrated                    (174258, correct)
weak  mung bean noodles   0.378  Long rice noodles, made from mung beans, cooked
                                                                       (2708355, correct)
weak  glass noodles       0.381  Noodles, cooked          (wheat — wrong)
none  fensi               -      (nothing)
none  bean thread         -      (nothing)
weak  rice vermicelli     0.319  Rice and vermicelli mix, rice pilaf flavor, unprepared
auto  rice noodles        0.765  Rice noodles, dry
```

Two correct rows exist and are reachable by two of six names for the same
thing. `rice vermicelli` — 米粉, the noodle of Singapore noodles and Fujian
cooking — lands on a boxed American pilaf mix.

Note the dry/cooked split in the correct rows themselves: 351 kcal dehydrated
against 84 cooked, a 4× hazard identical to §1.1.

### 2.8 `mapo tofu` returns exactly one candidate

```
== mapo tofu weak
    0.312 Tofu, fried | sr_legacy_food      <- the only row returned
none  ma po tofu    -   (nothing)
none  mapo doufu    -   (nothing)
none  麻婆豆腐        -   (nothing)
```

FNDDS carries three composites that are structurally this dish and none of them
is retrieved:

```sql
2706770 | Pork, tofu, and vegetables, excluding carrots, broccoli, and
          dark-green leafy; no potatoes, soy-based sauce
2706760 | Pork, tofu, and vegetables including carrots, ...; soy-based sauce
2707477 | Tofu and vegetables excluding ...; with soy-based sauce
```

`Tofu, fried` is 270 kcal / 18.8 g protein — deep-fried tofu puffs, not the
silken cubes of the dish. The composite rows are unreachable because their
descriptions are 90+ characters and the query is nine.

### 2.9 Tofu forms do not collapse in USDA — but the query collapses them

USDA is unusually good here. Protein per 100 g across the rows that exist:

| row | fdc_id | kcal | protein |
|---|---|---|---|
| `Tofu, dried-frozen (koyadofu)` | 172450 | 477 | **52.5** |
| `Tofu, fried` | 172451 | 270 | 18.8 |
| `Tofu, raw, firm, prepared with calcium sulfate` | 172475 | 144 | **17.3** |
| `Tofu, hard, prepared with nigari` | 174291 | 145 | 12.7 |
| `Tofu, extra firm, prepared with nigari` | 174290 | 83 | 10.0 |
| `Tofu, firm, prepared with calcium sulfate and magnesium chloride (nigari)` | 172448 | 78 | **9.0** |
| `Tofu, salted and fermented (fuyu)` | 174280 | 116 | 8.9 |
| `Tofu, soft, ... (nigari)` / `Soybean curd` | 172449 / 2707435 | 61 | 7.2 |
| `MORI-NU, Tofu, silken, firm` | 172461 | 62 | 6.9 |
| `MORI-NU, Tofu, silken, soft` | 174292 | 55 | **4.8** |

**11× spread in protein density.** And the query cannot reach the top half:

```
== firm tofu weak
    0.400 MORI-NU, Tofu, silken, firm | sr_legacy_food      (6.9 g protein)
    0.345 HOUSE FOODS Premium Firm Tofu | sr_legacy_food
    0.333 Vitasoy USA Azumaya, Firm Tofu | sr_legacy_food
    0.333 MORI-NU, Tofu, silken, lite firm | sr_legacy_food
    0.323 MORI-NU, Tofu, silken, extra firm | sr_legacy_food
    0.312 Vitasoy USA, Nasoya Lite Firm Tofu | sr_legacy_food
```

Neither non-brand block-tofu row (172475 at 17.3 g, 172448 at 9.0 g) appears in
the top six. Ten brand rows crowd them out because a brand name is short and a
USDA qualifier list is long — RECONCILED §3.2's brand-token length penalty
running in reverse. `firm tofu` versus the row it should get is a **2.5×
protein error**.

Also note USDA's own inconsistency: **172475 "raw, firm" is 17.3 g protein and
172448 "firm … nigari" is 9.0 g.** Two rows called firm tofu differing 2×. Any
mapping here is `medium` at best and must say so.

```
ask   silken tofu      0.500  MORI-NU, Tofu, silken, soft
ask   extra firm tofu  0.516  MORI-NU, Tofu, silken, extra firm
weak  pressed tofu     0.333  Tofu, fried
none  block tofu       -      (nothing)
weak  cotton tofu      0.412  Candy, cotton
weak  dried tofu       0.440  Tofu, dried-frozen (koyadofu)
```

`extra firm tofu` → MORI-NU *silken* extra firm (7.4 g) while
`Tofu, extra firm, prepared with nigari` (10.0 g) exists. `silken`, a
partitioning qualifier in RECONCILED §3.1's sense, is being *added* by the
match rather than checked.

### 2.10 `dried scallop` → scalloped potatoes, via the new `covers` key

```
== dried scallop weak
    0.294 Potato, scalloped, from dry mix | survey_fndds_food
    0.244 Potatoes, scalloped, dry mix, unprepared | sr_legacy_food
    0.233 Potato, scalloped, from dry mix, with meat | survey_fndds_food
    0.154 Potatoes, scalloped, dry mix, prepared with water, whole milk and butter
    0.526 Scallops, fried | survey_fndds_food
```

English stemming folds *dried* → `dri` and *dry* → `dri`, and *scalloped* →
`scallop`. So "Potato, scalloped, from dry mix" **covers** the query "dried
scallop" and is promoted above `Scallops, fried` (0.526) by the `covers DESC`
key. This is `d359db5` making a case worse, and it is worth recording because
the commit's own argument — coverage as a key, not a tie-break — is otherwise
sound.

Same mechanism, same domain: `dark soy sauce` → 0.173 `Pork, rice, and
vegetables excluding carrots, broccoli, and **dark**-green leafy; **soy**-based
**sauce**`.

---

## 3. Entity gaps — USDA genuinely has nothing

Searched by name, by ingredient and by category before filing.

| term | probe | nearest by category | verdict |
|---|---|---|---|
| `sichuan peppercorn`, `huajiao` | none / `weak 0.400 Pepper steak` | `%zanthoxylum%` → 0 rows; `%prickly ash%` → 0 rows | real gap, nutritionally negligible (2–3 g/dish) |
| `star anise` | `weak 0.333 Spices, anise seed` | `%anise%` → `Spices, anise seed` only | real gap. *Illicium verum* vs *Pimpinella anisum* — different family. Do **not** map. |
| `doubanjiang`, `douchi`, `laoganma`, `tianmianjiang`, `XO sauce` | none / weak | `%bean paste%` → `Bean paste, sweetened` (a *sweet* red-bean paste, not a chilli paste) | real gap. Sodium-dense (doubanjiang ~4,000 mg Na/100 g) and unrepresented. |
| `char siu`, `cha siu`, `chashao` | none | `Barbecue pork, no sauce` (2706400, 249 kcal / 24.8 P / 15.9 F) | dish gap; the neighbour is a fair *approximation*, see §5 |
| `har gow`, `siu mai`, `xiao long bao`, `cheung fun`, `lo mai gai` | none / `siu mai → 0.364 Mai Tai` | `Dumpling, no meat`, `Wonton, dumpling or pot sticker, steamed`, `Potsticker or wonton, pork and vegetable, frozen` | wrapper material differs (wheat starch vs wheat flour), fillings differ; decompose rather than map |
| `hot pot`, `huo guo`, `mala hot pot` | none | — | genuinely unmappable, see §6 |
| `chinese sausage`, `lap cheong` | `weak 0.414 Beef sausage with cheese` | `%sausage%` → nothing cured-sweet-pork | real gap. Lap cheong is ~500 kcal / 100 g, ~40 g fat, ~10 g sugar — no USDA sausage resembles it. |
| `century egg`, `pidan`, `thousand year egg` | none | `Egg, duck, whole, fresh, raw` | real gap; alkaline cure changes little nutritionally, so the duck-egg row is a defensible fallback |
| `msg`, `monosodium glutamate` | none | — | real gap. ~12% sodium by mass; a sodium-tracking user cannot record it at all. |
| `potato starch`, `tapioca starch`, `sweet potato starch`, `wheat starch`, `mung bean starch` | all weak, onto a gluten-free bread roll | `%starch%` → only `Cornstarch` (169698) | real gap; all are ~381 kcal / ~91 g carb like cornstarch |
| `lily bud`, `golden needles` | none | `%lily%` → three unrelated rows (pond lily, sesbania blossoms) | real gap, negligible mass |
| `shirataki`, `konjac` | none | `%konjac%`, `%shirataki%` → 0 rows | real gap; matters because shirataki is ~10 kcal/100 g and any substitute overstates hugely |
| `yuba`, `tofu skin`, `fu zhu`, `bean curd sticks` | none / `weak 0.312 Tofu, fried` | `Tofu, dried-frozen (koyadofu)` 477 kcal / 52.5 g protein | dried yuba is ~460 kcal / 52 g protein — a genuinely close fallback, see §5 |
| `stinky tofu`, `chou doufu` | none | firm tofu rows | real gap; fermentation changes little, medium fallback |
| `aubergine`, `courgette` | none | `Eggplant, raw` exists | not an entity gap — a **synonym** gap, see §5 |
| `pomelo`, `hawthorn`, `haw flakes`, `gingko nut`, `osmanthus`, `perilla`, `kabocha` | none | — | real gaps, low traffic |

---

## 4. Romanisation and menu-name coverage

Systematic result: **pinyin loses, English wins, Cantonese loses hardest.**

| dish | pinyin | Cantonese | English menu name |
|---|---|---|---|
| 宮保雞丁 | `gongbao jiding` none · `gong bao chicken` ask 0.500 (`Chicken, back`) | — | **`kung pao chicken` auto 1.000** ✔ |
| 叉燒 | `chashao` none | `char siu` none · `cha siu` none · `siu yuk` none | `BBQ pork` weak 0.429 (`Pork, belly`) · `chinese barbecue pork` ask 0.452 ✔-ish |
| 北京烤鴨 | — | — | **`peking duck` auto 1.000** (`Duck, Peking`, a true FNDDS composite: 154 kcal, 5.3 P, 6.5 C — pancake included) ✔ ; `beijing duck` weak 0.389 ✗ |
| 餛飩 | `huntun` none | `won ton` weak 0.357 | **`wonton` ask 0.583**, `wonton soup` auto 1.000 ✔ |
| 粥 | `zhou` none · `jook` none | `teochew porridge` none | **`congee` auto 1.000** ✔ |
| 麻婆豆腐 | `mapo doufu` none · `ma po tofu` none | — | `mapo tofu` weak 0.312 ✗ |
| 炸醬麵 | `zhajiangmian` none · `zha jiang mian` none | — | `noodles with soybean paste` weak 0.394 ✗ |
| 擔擔麵 | `dan dan mian` none | — | `dan dan noodles` ask 0.450 (`Rice noodles, dry` — wrong material, dan dan is wheat) |
| 地三鮮 | `di san xian` none | — | `three treasures of the earth` none |
| 回鍋肉 | `hui guo rou` none | — | `twice cooked pork` weak 0.429 (`Bratwurst, pork, cooked`) ✗ |
| 水煮魚 | `shui zhu yu` none | — | `water boiled fish` weak 0.302 ✗ |
| 魚香茄子 | `yu xiang qiezi` none | — | `fish fragrant eggplant` ask 0.458 (`Fried eggplant` — actually reasonable) |

**Not one pinyin string in the domain resolved to anything.** 麻婆豆腐 in Han
characters returns nothing, as expected. Cantonese romanisation is equally
dead: `siu mai` → `Mai Tai` (0.364), `lo mai gai` → `Mai Tai` (0.308),
`maotai` → `Mai Tai` (0.400). The "Mai Tai" attractor catches every
Cantonese-romanised syllable ending in *-ai*.

Where an English menu name exists in FNDDS the system is genuinely good:
`kung pao chicken`, `kung pao shrimp`, `hunan beef`, `orange chicken`,
`general tso chicken`, `sesame chicken`, `beef and broccoli`,
`sweet and sour pork`, `egg drop soup`, `hot and sour soup`, `lo mein`,
`congee`, `bao bun`, `shrimp toast`, `shrimp chips`, `bubble tea`,
`chicken feet`, `abalone`, `tripe` all auto-match correctly at 0.63–1.00.

That is the shape of it: **USDA has decent American-Chinese-restaurant
vocabulary and almost no Chinese vocabulary**, and the resolver has no bridge
between the two.

---

## 5. Ingredient tests the brief asked for specifically

### Light vs dark soy sauce — USDA does not distinguish, and the queries diverge

```
ask   light soy sauce    0.600  Soy sauce
weak  dark soy sauce     0.173  Pork, rice, and vegetables excluding carrots,
                                broccoli, and dark-green leafy; soy-based sauce
ask   dark soya sauce    0.500  Soy sauce
auto  sweet soy sauce    0.643  Soy sauce
ask   thick soy sauce    0.600  Soy sauce
ask   superior soy sauce 0.529  Soy sauce
```

Sodium across every soy row in the database:

| row | Na mg/100 g | kcal |
|---|---|---|
| `Soy sauce made from hydrolyzed vegetable protein` | 6820 | 60 |
| `Soy sauce made from soy (tamari)` | 5586 | 60 |
| `Soy sauce` / `... soy and wheat (shoyu)` | 5493 | 53 |
| `Soy sauce, reduced sodium` | 3598 | 57 |

**There is no light/dark row.** Real 生抽 is ~6,000 mg Na/100 g; real 老抽 is
lower in sodium and carries molasses/caramel, so it is sweeter and darker at
similar salt. Collapsing both to 5,493 is a *defensible* approximation and the
`ask` verdicts are the system working. Two things are not defensible:
`dark soy sauce` scoring 0.173 onto a pork-and-rice FNDDS dish (§2.10), and
`sweet soy sauce` **auto**-matching plain soy sauce — kecap manis is ~50%
sugar and ~250 kcal / 100 g against 53.

### Sesame paste vs tahini — measurably different, and the difference is calcium

```
ask   sesame paste          0.542  Seeds, sesame butter, paste
weak  chinese sesame paste  0.406  Seeds, sesame butter, paste
auto  tahini                1.000  Tahini
none  zhi ma jiang          -      (nothing)
```

| row | kcal | protein | fat | **calcium mg** | iron mg |
|---|---|---|---|---|---|
| `Seeds, sesame butter, paste` (170191) | 586 | 18.1 | 50.9 | **960** | 19.2 |
| `Tahini` (FNDDS) | 697 | 19.7 | 62.4 | **116** | 7.0 |
| `Seeds, sesame butter, tahini, from roasted and toasted kernels` | 595 | 17.0 | 53.8 | 426 | 8.9 |

**8× calcium, 2.7× iron.** Chinese 芝麻醬 is ground from *unhulled* roasted
sesame; tahini is from hulled kernels, and the hull is where the calcium is. So
"sesame paste → tahini", which is the obvious mapping and the one a naive
system would make, is an 8× calcium error on the single ingredient that carries
dan dan mian, cold sesame noodles and hot pot dipping sauce.

Current behaviour gets this right *by accident*: both `sesame paste` and
`chinese sesame paste` head on `Seeds, sesame butter, paste`. It should be made
deliberate, and `tahini` should be explicitly rejected as the target.

### `Duck, Peking` is the dish, not the bird — and it is correct

```
auto  peking duck        1.000  Duck, Peking
auto  peking roast duck  0.667  Duck, Peking
weak  beijing duck       0.389  Duck, Peking
```

`Duck, Peking` (2706141) is 154 kcal / 5.32 g protein / 11.76 g fat / 6.47 g
carbohydrate / 287 mg Na. The carbohydrate and the low protein give it away: it
is the FNDDS *composite* — duck with pancake and sauce — not the meat. That is
the right row for the dish, and the auto-match is correct. Recorded here
because 5.3 g protein looks like an obvious bug and is not.

`beijing duck`, the same dish under the modern romanisation, misses.

### `Chinese cabbage` is genuinely ambiguous and must not be encoded

```
auto  chinese cabbage  0.789  Cabbage, Chinese, raw     (FNDDS 2709774)
auto  napa cabbage     0.684  Cabbage, napa, cooked     (SR 168572)
none  wombok           -      (nothing)
```

| row | kcal | protein | vit C mg | Ca mg |
|---|---|---|---|---|
| FNDDS `Cabbage, Chinese, raw` | 13 | 1.5 | 45.0 | 105 |
| SR `Cabbage, chinese (pak-choi), raw` | 13 | 1.5 | 45.0 | 105 |
| SR `Cabbage, chinese (pe-tsai), raw` | 16 | 1.2 | 27.0 | 77 |

FNDDS's "Chinese cabbage" is numerically **identical to pak-choi** — so FNDDS
means bok choy. But in British and Australian English "Chinese cabbage" (and
"wombok") means *napa* = pe-tsai. The two differ 1.7× in vitamin C and 1.4× in
calcium. Whichever way you encode it you are wrong for half the users. See §6.

---

## 6. Deliberately not encoding

Judged as important as what is proposed.

- **`hot pot` → anything.** A cooking method, not a food. Its composition is
  whatever went into it. Any row is a fabrication; the correct behaviour is the
  current `none` and a decomposition prompt.
- **`chinese cabbage` → either cabbage row.** §5. The term is regionally
  ambiguous between two real vegetables with different nutrient profiles. An
  automatic mapping picks a side silently. This should ask.
- **`sesame paste` → `Tahini`.** 8× calcium error (§5). The most tempting
  mapping in the domain and the wrong one.
- **`star anise` → `Spices, anise seed`.** Different genus, different family,
  different compound. Also nutritionally irrelevant at 1 g/dish, so the mapping
  buys nothing and risks a `culturally_incorrect_mapping` precedent.
- **`conpoy` / `dried scallop` → `Mollusks, scallop, cooked, steamed`.** 3×
  mass error in the dried direction, and conpoy is used at 5 g. Not worth it.
- **`dim sum` → a parent category.** "Dim sum" spans har gow (~90 kcal/100 g)
  to lo mai gai (~200) to egg tart (~300). A parent category here is
  `overly_broad_mapping` in the brief's exact sense.
- **`chinese food` / `chinese takeaway` / `chinese takeout`.** Same argument,
  larger. Currently `weak → Chinese pancake`, which is at least visibly absurd.
- **`XO sauce` → `Soy sauce`** (current `ask 0.500`). XO is dried scallop,
  dried shrimp, ham and chilli in oil — ~600 kcal/100 g against 53. The
  candidate list is nonsense; escalating is right; encoding a synonym would be
  worse than nothing.
- **`furu` → firm tofu.** Fermented bean curd is 8.9 g protein and, critically,
  ~2,900 mg Na/100 g in reality. `Tofu, salted and fermented (fuyu)` exists and
  is the right target (§2.6); a generic-tofu fallback would lose the salt.
- **`five spice powder` → `Spices, curry powder`** (current `ask 0.462`).
  Different spice set entirely; both are nutritionally negligible, so the
  mapping has no upside and encodes a cultural error.

---

## 7. Patterns

1. **Every wrong `auto` in this domain is a short-description row winning.**
   `Soup, seaweed`, `Chicken, back`, `Pie, sweet potato`, `Black bean sauce`,
   `Tea, ginger`, `Oil, grapeseed`, `Flour, rice, glutinous` — all short, all
   beating a longer correct row that was on the list. RECONCILED §1, verbatim.

2. **The `covers DESC` key of `d359db5` fixes ordering and leaves `sim`
   untouched**, so six correct heads in this domain are reported `weak`
   (§2.1). It also creates two new failures through English stemming —
   `dried scallop` → scalloped potatoes, `dark soy sauce` → a pork-and-rice
   dish (§2.10). Net positive, but the weak floor should now read rank.

3. **Brand rows out-rank USDA rows for tofu** (§2.9) — ten MORI-NU / Vitasoy /
   HOUSE FOODS rows crowd the block-tofu entries out of the top six. This is
   RECONCILED §3.2's brand-token argument running the other way: brand names
   are *short*, so brand rows win on length just as everything else does.

4. **The pinyin/English asymmetry is total.** 0 of ~45 pinyin strings resolved;
   the English menu names that FNDDS happens to carry resolve at 0.63–1.00.
   There is no partial credit in between.

5. **Dry-versus-cooked is the second-largest hazard after identity**, and it is
   invisible: glutinous rice 3.8×, cellophane noodles 4.2×, wood ear ~5×,
   dried yuba ~5×, dried scallop 3×. Every one of these foods is *sold* dry and
   *eaten* wet, and USDA carries both rows.
