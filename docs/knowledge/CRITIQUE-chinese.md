# Critique — AUDIT-chinese.md

Adversarial review. 28 Aug 2026. Read-only on the database; every re-probe below
was run with `scripts/probe_knowledge.py` at HEAD `74c3921`, and every USDA
figure is quoted from a `SELECT` against `food_nutrient`.

Bottom line: the arithmetic in this audit is honest and the entity gaps are real,
but five claimed dangerous auto-matches do not happen in production, one proposed
target row is empty, and the ranking argument it is built on was replaced by
`71e62d1` after it was written.

---

## 0. Headline: three of the seven headline `auto`s do not happen

The audit's §0 lists seven `auto` verdicts as putting "a materially wrong row
into the log with no model consulted". That is a probe verdict, and the probe
measures `db.search_foods` alone. `resolve_items` then filters the candidate
list through `inverts_meaning`, `state_conflicts`, `unrequested_qualifier` and
`label_absent` before taking anything.

I replayed the *real* decision — `parse._candidates` (pooled, limit 5,
re-sorted) followed by the exact `auto = next(...)` predicate from
`resolve_items` — for every claimed auto in the document.

**Three of the seven headline cases escalate to the model tier in production,
which is the system working.** Two more of §1.8's nine "smaller autos" do too.

| audit claim | production | blocked by |
|---|---|---|
| `rapeseed oil` → `Oil, grapeseed` | **escalates** | `unrequested_qualifier: grapeseed` |
| `bang bang chicken` → `Chicken, back` | **escalates** | `unrequested_qualifier: back` |
| `pickled cabbage fish` → `Cabbage, red, pickled` | **escalates** | `unrequested_qualifier: red` (and `green` on the runner-up; `Fish, pickled` survives the guards but is 0.619, below the 0.62 gate) |
| `mixed vegetables` → `Mixed vegetable juice` | **escalates** | `unrequested_qualifier: Mixed vegetable juice` |
| `steamed fish` → `Fish, cod, steamed` | **escalates** | `unrequested_qualifier: cod` (every candidate names a species) |
| `glutinous rice` → `Flour, rice, glutinous` | auto, confirmed | — |
| `beef in black bean sauce` → `Black bean sauce` | auto, confirmed | — |
| `sweet potato` → `Pie, sweet potato` | auto, confirmed | — |
| `pumpkin` → `Pie, pumpkin` | auto, confirmed | — |
| `seaweed` → `Soup, seaweed` | auto, confirmed | — |
| `ginger` → `Tea, ginger` | auto, confirmed | — |
| `water chestnut flour` → `Flour, chestnut` | auto, confirmed | — |
| `custard bun` → `Custard` | auto, confirmed | — |
| `shrimp with eggs` → `Egg roll, with shrimp` | auto, confirmed | — |
| `red bean soup` → `Soup, bean` | auto, confirmed | — |
| `chilli garlic sauce` → `Garlic sauce` | auto, confirmed | — |
| `napa cabbage` → `Cabbage, napa, cooked` | auto, confirmed | — |
| `sweet soy sauce` → `Soy sauce` | auto, confirmed | — |
| `chinese cabbage` → `Cabbage, Chinese, raw` | auto, confirmed | — |
| `rice noodles` → `Rice noodles, dry` | auto, confirmed | — |

Note the shape of what the guards catch and what they miss. `unrequested_qualifier`
catches every case where the wrong row is the *right food narrowed by a word the
user never said* (`grapeseed`, `back`, `red`, `cod`). It is structurally blind to
the case where the wrong row is a **different food whose name contains the query
as a prefix** — `Pie, sweet potato`, `Pie, pumpkin`, `Soup, bean`, `Custard`,
`Tea, ginger`, `Soup, seaweed`, `Flour, rice, glutinous`, `Black bean sauce`,
`Garlic sauce`. In every one of those, segment 0 shares a word with the query and
adds only a word the query *also* effectively contains, or the added word sits in
segment 0 as the head noun (`Pie`, `Soup`, `Tea`, `Flour`) and the loop's `i == 0`
branch requires `words & q` **and** `extra` — which is satisfied, so it should
fire… except it does not, because for `Pie, sweet potato` segment 0 is `Pie`
alone: `words = {"pie"}`, `words & q` is empty, so the `i == 0` branch skips it,
and segment 1 (`sweet potato`) is fully covered by the query. **The USDA
inversion `Noun, food` defeats `unrequested_qualifier` entirely.** That is the
single most useful generalisation in this domain and the audit does not state it.

The replay used `search_terms=""`. That is the conservative case: adding the
model's phrase widens the query word set, which can only make
`unrequested_qualifier` *less* likely to fire, and widens the candidate pool.
For the five blocked cases the blocking word (`grapeseed`, `back`, `red`, `cod`,
`juice`) is one no plausible `search_terms` for that dish contains, so the block
is robust. Where the model *would* fabricate the word — the turkey/`deli` failure
in CLAUDE.md — the block is not robust, and that is a known upstream problem, not
a correction to this audit.

---

## 1. Nutritional claims: what I verified, and what is off

I re-pulled every figure the audit quotes. **The arithmetic is honest almost
everywhere.** Verified per 100 g, `SELECT` against `food_nutrient`:

| audit claim | verified |
|---|---|
| `Flour, rice, glutinous` 368 kcal / 80.1 carb | 368 / 80.1 ✔ |
| `Rice, white, cooked, glutinous` 96 kcal | 96 / 2.0 P / 21.0 C ✔ (3.8× confirmed) |
| `Black bean sauce` 168 kcal / 6.3 P | 168 / 6.3 ✔ |
| `Pie, sweet potato` 269 vs `Sweet potato, NFS` 115 | 269 / 115 ✔ |
| `Pie, pumpkin` 249 vs `Pumpkin, raw` 26 | 249 / 26 ✔ |
| canola ~9% ALA, ~63% oleic; grapeseed ~70% linoleic, no omega-3 | 172336: MUFA 63.3, ALA 9.1; 171028: PUFA 18:2 69.6, **no 1404 row at all** ✔ |
| `Chicken, back` 298 / 25.7 / 20.8 | ✔ |
| `Garlic sauce` 683 kcal | 683 / 74.0 g fat ✔ |
| sesame paste 170191 Ca **960**, Fe 19.2 vs `Tahini` Ca **116**, Fe 7.0 | ✔ exactly. 8.3× calcium, 2.7× iron |
| whole tofu table (§2.9), 11× protein spread | every row ✔, including the 172475 / 172448 2× discrepancy |
| `Tofu, salted and fermented (fuyu)` Na ~2,900 | 2873 ✔ |
| FNDDS `Cabbage, Chinese, raw` numerically identical to pak-choi | 13/1.5/0.2/2.2/Na 65/Ca 105 both ✔; pe-tsai 16/1.2/Ca 77 ✔ |
| `%prawn%`, `%daikon%`, `%konjac%`, `%shirataki%`, `%wood ear%` → 0 rows | ✔ all zero |
| `%rapeseed%` → exactly one row, the grapeseed one | ✔ — and the mechanism is that "g-**rapeseed**" contains it as a substring, which the audit does not say and which is the whole joke |

### 1.1 The one factual error in a proposed target: `748278` is an empty row

§1.4 names the canola targets as "`Oil, canola` at **748278** (Foundation),
**172336** (SR Legacy) and `Canola oil` at **2710188** (FNDDS)", Foundation
first — Foundation is precedence 1, above SR Legacy, so a reader building the
mapping takes 748278.

**748278 has no energy figure and no macronutrients.** It carries 38
`food_nutrient` rows and every one of them is a fatty acid or a fatty-acid
total: no 1008, no 2047, no 2048, no 1003, no 1004, no 1005.

```
1258 Fatty acids, total saturated        6.61 G
1292 Fatty acids, total monounsaturated 62.60 G
1293 Fatty acids, total polyunsaturated 25.30 G
1404 PUFA 18:3 n-3 c,c,c (ALA)           7.45 G
```

`db.search_foods` already knows this — it computes `has_energy` and the comment
beside it says a row with macros and no energy "is not a lower-quality
candidate, it is an unusable one". A mapping pointed at 748278 would log
frying oil at **zero calories**, silently, and invariant 6 ("missing nutrients
are skipped, never zeroed") means the day's energy would simply be short with
nothing raising. The usable rows are **172336** (SR Legacy, 884 kcal, 102
nutrients) and **2710188** (FNDDS, 900 kcal, 65 nutrients). Any encoded mapping
must name one of those two and must not name 748278.

Note also the audit's own §1.4 ALA figure: it says "~9%", the row says 7.45 for
Foundation and 9.1 for SR Legacy. It quoted the SR number while listing
Foundation as the first target — a small sign that the two rows were not
actually opened.

---

## 2. Culinary errors in the audit itself

### 2.1 *Di san xian* contains no sweet potato and no pumpkin

§1.3 justifies the sweet-potato and pumpkin findings with: "sweet potato and
pumpkin are the body of *di san xian*, *ba si di gua*, and every claypot."

地三鲜 *di san xian* is **potato, aubergine and green pepper** (土豆 / 茄子 /
青椒). It contains neither sweet potato nor pumpkin. 拔丝地瓜 *ba si di gua* is
candied sweet potato and is correct. The finding survives — `Pie, sweet potato`
at 269 kcal against `Sweet potato, NFS` at 115 is real and it is a production
auto — but the dish named to carry it is the wrong dish, and it is named twice
(§2.5 repeats "di san xian's cousins" for wood ear, where it is at least
hedged). This is the domain's own version of the bresaola trap: a competent
cook reading §1.3 would stop trusting the section.

### 2.2 `kecap manis` is Indonesian, and the number quoted is Indonesian

§5 justifies the `sweet soy sauce` → `Soy sauce` auto with "kecap manis is ~50%
sugar and ~250 kcal / 100 g against 53". The auto is real and the direction is
right. But in a *Chinese* audit the referent for 甜酱油 is the Sichuan reduced
soy of dan dan mian and liangfen — soy sauce simmered with brown sugar and
spices, typically 20–30% sugar, not 50%. Quoting kecap manis's figure
overstates the error by roughly double for the food this domain actually means.
The finding should be `medium` confidence with a range, not a single number
lifted from another cuisine.

### 2.3 `fuyu` is probably not "the Japanese reading"

§2.6: "腐乳 is *furu* in Mandarin and *fuyu* in Japanese; USDA transliterated the
Japanese." 腐乳 in Japanese is normally read *fu-nyū*; the Okinawan product is
豆腐餻 *tōfuyō*. "fuyu" is more plausibly a loose romanisation of the Mandarin
than a Japanese reading. The *actionable* half of §2.6 is untouched and correct:
`furu` returns nothing, `fermented tofu` reaches 174280 at 0.536, and 174280 is
the right row at **2873 mg Na / 100 g** (verified). Only the etymology is shaky,
and it is stated as fact.

### 2.4 `century egg` — "the alkaline cure changes little nutritionally"

§3 files the duck-egg row as "a defensible fallback" on that reasoning. The cure
is salt *and* alkali: pidan runs several hundred to ~1,000 mg Na / 100 g against
~146 for a fresh duck egg. That is the same sodium argument the audit itself
makes correctly for `furu` in §6 and for `doubanjiang` in §3, applied
inconsistently here. Downgrade to `medium`, and say the fallback loses the salt.

---

## 3. Harm ranking: §0 is not in descending order of harm

§0 says "in descending order of harm". Verified per 100 g, it is not, and two of
the corrections point the same way — the cases that *do* survive the guards are
under-ranked relative to the cases that do not.

- **`seaweed` → `Soup, seaweed` is ranked 5th and is nearly harmless.**
  `Soup, seaweed` 37 kcal / 3.7 P / Na 324; `Seaweed, raw` 41 kcal / 3.5 P /
  Na 384. **A 10% energy difference.** It is a genuine and interesting
  *methodological* finding — an exact float tie decided by nothing — but as a
  nutritional harm it belongs nowhere near a 3.8× energy error. Placing it above
  `chilli garlic sauce` (683 kcal vs ~70, ~9×, and a confirmed production auto)
  inverts the ranking by roughly a factor of ninety.

- **`custard bun` → `Custard` is filed under "smaller autos".** `Custard` is
  97 kcal / 10.9 g sugar. A 奶黃包 is ~250–300 kcal / 100 g. That is a ~3×
  *undercount* on a dim-sum staple, comparable to the headline glutinous-rice
  case, and it survives every guard.

- **`red bean soup` → `Soup, bean`: the audit names the wrong harm.** It says
  "savoury; hong dou tang is a dessert". On energy the two are close — `Soup,
  bean` is 67 kcal and 紅豆湯 is ~70–90. The actual damage is **sugar 1.1 g vs
  ~15 g** and **Na 244 vs ~0**: a 250 g bowl loses ~35 g of sugar, close to a
  whole day's ceiling, invisibly. Right case, wrong reason, and the reason is
  the part a mapping would encode.

- **`water chestnut flour` → `Flour, chestnut` is culturally wrong and
  nutritionally mild.** Verified: `Flour, chestnut` 385 kcal / 80.5 C / 5.3 P /
  8.7 fibre; 馬蹄粉 is ~380 kcal / ~90 C / ~0 P / ~0 fibre. The energy is within
  2%. The real error is +5 g protein and +8.7 g fibre per 100 g on an ingredient
  used at 30–50 g. The audit's `culturally_incorrect_mapping` label is right and
  its placement in "less costly" is right; its framing ("a different plant
  family", 5 g protein, 8 g fibre) implies more damage than the numbers carry.

---

## 4. Superseded: the whole `covers` argument moved under the audit

The audit is explicit that it ran at `d359db5`, where `covers` was a primary
sort key. **`71e62d1` replaced that with a multiplicative boost** —
`(similarity + ts_rank) * 1.35 when covered` — and the commit message says why
the key form was abandoned. Four of the audit's claims do not survive the
change. Re-probed at HEAD `74c3921`:

- **§2.1's headline example is gone.** `tamari` is now `ask 0.600 Tamarind`,
  with `Soy sauce made from soy (tamari)` at **rank 2**, not rank 1. The audit's
  argument — "the correct row now leads … the verdict and the ranking now
  disagree" — no longer holds for the case it is built on. The *outcome* is
  better than the audit reports (it escalates with the correct row on the list
  rather than being written off as `weak`), but the stated mechanism is wrong.
- **`squid` likewise.** Head is now `Squirrel` at 0.364; `Mollusks, squid, mixed
  species, raw` sits at rank 2 at 0.194. The audit's "correct, rank 1" annotation
  is false at HEAD.
- **`dark soy sauce` is now an `auto`, not a `weak`.** It resolves `auto 0.643 →
  Soy sauce`. §5 praises the soy-sauce family's `ask` verdicts as "the system
  working" and files `dark soy sauce → a pork-and-rice FNDDS dish" as one of the
  two indefensible cases. Neither is true now: the pork-and-rice row has fallen
  to rank 2 at 0.173, and the collapse onto plain `Soy sauce` that §5 calls
  defensible is happening with no model consulted.
- **§2.10 survives**, and is the audit's best mechanical finding. `dried scallop`
  still heads on `Potato, scalloped, from dry mix` (0.294) above `Scallops,
  fried` (0.526) at HEAD, via English stemming *dried*→`dri`, *dry*→`dri`,
  *scalloped*→`scallop`. Attribute it to the covers **boost**, not to
  `covers DESC`.

Pattern 2 of §7 ("the `covers DESC` key of `d359db5` … the weak floor should now
read rank") should be rewritten or struck. Its recommendation — have the weak
floor read rank instead of `sim` — was addressed by 71e62d1 taking a different
route, and following it now would layer a second fix on a solved problem.

---

## 5. What the audit missed

741 terms, and the produce aisle is almost absent. `grep -ci` over
AUDIT-chinese.md returns **zero** for: jujube, red date, rice cake, nian gao,
oyster sauce, hoisin, bamboo, lotus, bitter melon, shiitake, goji, pork belly,
brisket, lychee, chinese broccoli, gai lan, pak choi, water chestnuts (the
vegetable, as opposed to its flour), sesame oil. The document is thorough on
dishes, condiments, tofu forms, noodle forms and romanisation, and thin on the
vegetables, fruit, mushrooms and cured goods that make up most of the mass on a
Chinese plate. Three of the gaps are production autos with real errors.

### 5.1 `jujube` → `Jujube, raw` — 3.6×, and USDA has the right row

```
auto  jujube      0.636  Jujube, raw               <- taken, survives all guards
weak  red dates   0.364  Date                      <- a different fruit entirely
```

| row | fdc_id | kcal | protein | carb |
|---|---|---|---|---|
| `Jujube, raw` (taken) | 168151 | **79** | 1.2 | 20.2 |
| `Jujube, Chinese, fresh, dried` | 168152 | **281** | 4.7 | 72.5 |

紅棗 is eaten **dried** — in soups, congee, braises, tea. USDA carries the row
and names it *Chinese*, and the query for it loses to the fresh-fruit row at
0.636, which is an auto that writes a permanent alias. **3.6× undercount.** The
English name `red dates` is worse: it reaches `Date` (*Phoenix dactylifera*), a
different genus, at 0.364.

This is the audit's own §1.1 dry-versus-fresh pattern in a food it never
probed — and §7's pattern 5 lists five such foods without it.

### 5.2 `rice cake` → the puffed cracker, at similarity 1.000

```
auto  rice cake  1.000  Rice cake (2708162)
none  nian gao   -      (nothing)
```

`Rice cake` (2708162, FNDDS) is **392 kcal / 7.1 P / 81.1 C / Na 71** — and it
is numerically identical, to the decimal, to SR Legacy 168107 `Rice cake,
cracker (include hain mini rice cakes)`. It is the puffed snack. 年糕 — Shanghai
rice cake, 炒年糕, the whole Ningbo/Shanghai staple — is a chewy glutinous batons
at roughly 150–190 kcal / 100 g as eaten. **A 2–2.6× overcount at similarity
1.000**, which means no threshold anywhere can ever save it, no guard fires
(single-segment description, every query word present), and `nian gao` returns
nothing so there is no other way in. This is a worse case than five of the
audit's seven headline entries, because 1.000 admits no remedy short of a
synonym.

### 5.3 `water chestnuts` → `Chestnuts` — the audit found this trap and probed
only the flour

§1.8 correctly identifies *Eleocharis dulcis* vs *Castanea* as a
`culturally_incorrect_mapping` for `water chestnut flour`. The whole vegetable
was never probed, and it is worse:

```
auto  water chestnuts  0.625  Chestnuts (2707499)   <- survives all guards
```

| row | fdc_id | kcal | protein | carb |
|---|---|---|---|---|
| `Chestnuts` (taken) | 2707499 | **245** | 3.2 | 53.0 |
| `Waterchestnuts, chinese, (matai), raw` | 170066 | **97** | 1.4 | 23.9 |
| `Water Chesnut` (FNDDS, note the typo) | 2710003 | 78 | 1.4 | 19.2 |

**2.5–3.1× overcount**, on an ingredient used at 50–100 g in a stir-fry rather
than the 5 g of starch the flour case concerns. `unrequested_qualifier` cannot
fire — `Chestnuts` is one segment and it shares "chestnuts" with the query,
adding nothing. `label_absent` cannot fire for the same reason. Note also the
FNDDS row's misspelling, `Water Chesnut`, which is why it scores 0.522 rather
than higher.

### 5.4 Smaller, and honestly smaller

Reported so the next audit does not have to re-probe them. All are production
autos that survive the guards, all are the *right food* on the wrong
preparation, and none is worth a mapping on its own:

```
auto  bean sprouts      0.765  Bean sprouts, raw       (cooked row at 0.650)
auto  bamboo shoots     0.778  Bamboo shoots, raw      (cooked row at 0.667)
auto  chinese broccoli  0.810  Broccoli, chinese, raw  (cooked row at 0.739)
auto  lotus root        0.786  Lotus root, raw         (cooked row at 0.611)
auto  bitter melon      0.650  Bitter melon, cooked    (only row returned)
auto  winter melon      0.650  Winter melon, cooked    (only row returned)
```

Each is decided by whichever preparation USDA happened to name, and each flips
correctly the moment the model declares a `state` — I verified that
`state_conflicts` sends `chinese cabbage` (state `cooked`) and `napa cabbage`
(state `raw`) to the model tier. That is the guard working, and it is the reason
these are not findings.

### 5.5 Reachability gaps the audit did not list

Verified zero-row or effectively-unreachable, none mentioned in the audit:

```
none  gai lan / choy sum / gai choy / yau choy   -    (all zero rows)
none  mange tout / mooncake / mantou / guotie / jianbing / malatang / ho fun
none  nori                -                            (`Seaweed, laver, raw` exists)
weak  pak choi     0.346  Cabbage, chinese (pak-choi), raw   <- the word is IN the row
weak  spring onion 0.240  Onions, spring or scallions (...), raw  <- likewise
weak  chow fun     0.231  Chow fun noodles with vegetables, meatless <- likewise
weak  potsticker   0.196  Potsticker or wonton, pork and vegetable, frozen <- likewise
weak  chilli oil   0.333  Corn oil                    (`chili oil` -> `Chili, NFS`)
weak  prawn toast  0.333  Melba toast
weak  pork floss   0.333  Pork, NFS
weak  mooli        0.333  Moose
```

`pak choi`, `spring onion`, `chow fun` and `potsticker` are the *same* defect the
audit describes for `tamari` in §2.1 — the query's exact word is in the row's
description and the row is still below the weak floor — and they are better
examples than two of the six the audit chose, because they reproduce at HEAD.
`mooli` → `Moose` is `daikon` (§2.2) under its third English name.

The `-ai` "Mai Tai" attractor of §4 has a sibling worth naming: `singapore
noodles` → `Singapore Sling` (0.455). It is the same failure — a cocktail row
catching a Cantonese/Southeast-Asian place name.

---

## 6. What I upheld without reservation

So the corrections above are read in proportion. These are correct, verified,
and I would encode them as the audit states:

- §5's `sesame paste` ≠ `Tahini` finding. **960 mg vs 116 mg calcium**, 19.2 vs
  7.0 mg iron, confirmed to the decimal. The unhulled/hulled explanation is
  correct, the current accidental behaviour is correct, and making it deliberate
  is the single most valuable proposal in the document.
- §2.9's tofu table, every row. The 172475 (17.3 g) / 172448 (9.0 g) "two rows
  called firm tofu differing 2×" observation is real, and the conclusion — any
  tofu mapping is `medium` at best and must say so — is right.
- §5's `Duck, Peking` reading: 154 kcal / 5.3 g protein / 6.5 g carb is the
  FNDDS composite including pancake, it is the right row for the dish, and
  recording it as *not* a bug was the correct call.
- §6's whole refusal list. `hot pot`, `dim sum`, `chinese food`, `XO sauce`,
  `five spice → curry powder`, `star anise → anise seed`, `conpoy`. Each
  argument is sound; `star anise` (*Illicium verum*, Schisandraceae, against
  *Pimpinella anisum*, Apiaceae) is exactly the family-level error the brief
  warns about, and refusing a nutritionally irrelevant mapping to avoid setting
  the precedent is the right instinct.
- §3's entity gaps. `%prawn%`, `%daikon%`, `%konjac%`, `%shirataki%` and
  `%wood ear%` all return **0 rows**, verified. `prawn` is the highest-value
  one-line fix in the domain and the audit is right to say so.
- §2.5's hazard note on `Fungi, Cloud ears, dried` — mapping the synonym without
  a preparation guard would overstate a rehydrated portion ~5×. Correct, and the
  same note should be attached to §5.1's jujube mapping above.

---

## 7. The generalisation the audit reached for and missed

§7 pattern 1 says "every wrong `auto` in this domain is a short-description row
winning", and cites RECONCILED §1's length effect. That is true but not
actionable — it names a statistical tendency, and the resolver already has three
guards that act on structure rather than on length.

The sharper statement, which falls straight out of the guard replay:

> **`unrequested_qualifier` catches the wrong row that is the right food narrowed
> by a word the user never said. It is structurally blind to the wrong row that
> is a different food whose description *contains* the query.**

The five cases it catches are `grapeseed`, `back`, `red`, `cod`, `juice` — all
narrowing qualifiers. The fifteen it misses are `Pie, sweet potato`, `Pie,
pumpkin`, `Soup, bean`, `Soup, seaweed`, `Tea, ginger`, `Custard`, `Flour, rice,
glutinous`, `Flour, chestnut`, `Black bean sauce`, `Garlic sauce`, `Chestnuts`,
`Rice cake`, `Jujube, raw` — and the reason is one line of the guard. USDA's
inversion puts the *category* in segment 0 alone:

```python
for i, seg in enumerate(description.split(",")):
    ...
    if i == 0:
        if (words & q) and extra:   # `Pie` alone: words & q is empty -> skip
            return seg.strip()
        continue
```

For `Pie, sweet potato` against query `sweet potato`, segment 0 is `{"pie"}`,
which shares nothing with the query, so the `i == 0` branch declines to judge it
— by design, because a name sharing nothing with the query is meant to be caught
by *similarity* instead. But similarity is exactly what the length effect
defeats. So the two mechanisms have a hole precisely where they meet: **a short
category noun in segment 0, with the user's whole query as segment 1.**

That is a testable, mechanical rule, and every one of the fifteen surviving
autos in this domain fits it. Whether it should be closed — and it would need a
whitelist, since `Rice noodles, dry` and `Oil, canola` have the same shape and
are right — is a resolver question, not a knowledge-audit question. But it
belongs in RECONCILED.md, and "short descriptions win" does not, because nothing
can be built on it.
