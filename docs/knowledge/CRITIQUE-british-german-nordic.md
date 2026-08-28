# Critique — AUDIT-british-german-nordic.md

Written 28 Aug 2026 by a second agent who did not write the audit. Read-only
against the live database. Every claim below is either probe output, guard
replay, or a `SELECT` quoted per 100 g.

## Method note — how the guard replay was done

`scripts/probe_knowledge.py` calls `db.search_foods(label)` for the **user's
label alone**. Production does two further things the probe does not:

1. `parse._candidates` searches the *model's* `search_terms` as well as the
   label (and the dish name on a one-item meal), pools the five results of each
   query, and ranks by the best score **any** query achieved.
2. `resolve_items` then filters with `inverts_meaning`, `state_conflicts`,
   `unrequested_qualifier` and `label_absent`, and auto-takes **the best
   candidate that survives all four**, not the head.

I replayed both. Two scratch scripts, neither in the repo:
`guardcheck.py` (label only, guards applied) and `guard2.py` (full
`_candidates` with a plausible model `search_terms`, then guards).

The `search_terms` I supplied are the USDA-style phrases `PARSE_SYSTEM` asks
the model to write (e.g. `rapeseed oil` -> `"Oil, rapeseed, canola"`). This is
a dependency, and I state it: where the model does not know the food at all
(haggis, surströmming, karjalanpiirakka) the search_terms cannot rescue it, and
the audit's gap findings there stand. But for every dialect-synonym case the
audit files as "zero reachability", the model writing the American word is the
*expected* case, not a charitable one — it is the mechanism the 25 Aug turkey
incident showed is already firing.

---

## 1. The guard check — five of nine claimed dangerous auto-matches do not survive

The audit's §1 is titled "Wrong-confident matches (`auto` onto a semantically
wrong row)" and is presented as production behaviour. It is probe behaviour.

| audit claim | label only + guards | full `_candidates` + guards | verdict |
|---|---|---|---|
| §1.1 `scotch egg` -> `Scotch` | AUTO 2710701 | AUTO 2710701 | **UPHELD** |
| §1.1 `scotch pie` -> `Scotch` | AUTO 2710701 | AUTO 2710701 | **UPHELD** |
| §1.1 `scotch broth`, `scotch pancake` | `ask` (0.538 / 0.467) | escalates | **OVERTURNED** — never was an auto; the audit files an `ask` under "wrong-confident" |
| §1.2 `oatmeal` -> `Pie, oatmeal` | AUTO 2708016 | AUTO 2708016 | **UPHELD** |
| §1.3 `rapeseed oil` -> `Oil, grapeseed` | blocked `qual:grapeseed` | blocked; canola rows surface at 0.550 | **OVERTURNED** |
| §1.4 `jam sandwich` -> `Spam sandwich` | blocked `qual:Spam sandwich` | blocked | **OVERTURNED** |
| §1.5 `bacon sandwich` -> `Bacon biscuit sandwich` | blocked `qual:Bacon biscuit sandwich` | blocked | **OVERTURNED** |
| §1.5 `sausage sandwich` -> `Sausage biscuit sandwich` | blocked `qual:Sausage biscuit sandwich` | blocked | **OVERTURNED** |
| §1.6 `roast chicken` -> `Chicken, chicken roll, roasted` | AUTO 2706087 | AUTO 2706087 | **UPHELD, and worse than stated — see §2** |
| §1.7 `brown bread` -> `Bread, Boston Brown` | AUTO 2707847 | AUTO **2707709 `Bread, whole wheat`** (0.762) | **OVERTURNED** |
| §1.8 `biscuit` -> `KFC, biscuit` | AUTO 170339 | AUTO 170339 | **UPHELD** |

Guard replay, verbatim:

```
=== 'rapeseed oil' search_terms='Oil, rapeseed, canola' state=as_sold
  0.688  171028 Oil, grapeseed        BLOCKED qual:grapeseed
  0.550  748278 Oil, canola           BLOCKED below-gate
  0.550  172336 Oil, canola           BLOCKED below-gate
  0.550 2710188 Canola oil            BLOCKED below-gate
  -> escalates to model
```

```
=== 'jam sandwich' search_terms='Sandwich, jam, white bread'
  0.667 2709138 Jelly sandwich, on white bread   BLOCKED qual:Jelly sandwich
  0.625 2707055 Spam sandwich                    BLOCKED qual:Spam sandwich
  -> escalates to model
```

`unrequested_qualifier` catches all four for the same structural reason: a
first segment that echoes the query's word and adds one (`Spam` to `sandwich`,
`grapeseed` to `oil`) is exactly the case that guard was written for. The audit
had the guard-check instruction available and did not run it.

**§1.7 is the most consequential overturn.** The audit asserts "`Bread, whole
wheat` (2707709, 254 kcal) is **not on the list**". It is not on the *probe's*
list, because the probe searched only the word `brown bread`. Once the model's
`search_terms` are pooled in, 2707709 leads at 0.762 and is auto-taken:

```
=== 'brown bread' search_terms='Bread, whole wheat, wholemeal'
  0.762 2707709 Bread, whole wheat     AUTO-TAKEN
  0.625 2707847 Bread, Boston Brown    ok
  -> AUTO 2707709 Bread, whole wheat
```

So the production behaviour is *correct*, and the audit reports it as a
274-kcal molasses-bread error.

Three claimed autos survive everything and are real, undiluted findings:
`scotch egg` / `scotch pie`, `oatmeal`, `biscuit`. Those are the audit's
genuine contribution and I would raise, not lower, their priority.

---

## 2. A guard pathology the audit did not see: `label_absent` blocks the *right* row

Two of the surviving autos are worse than the audit describes, and for the same
reason. `label_absent` and `unrequested_qualifier` disqualify the correct row
while the wrong one passes, so the guards do not merely fail to help — they
select the error.

**`roast chicken` (§1.6).** With the model's `search_terms`, the correct row
leads the list at 0.743 and is thrown out:

```
=== 'roast chicken' search_terms='Chicken, roasted, meat only' state=cooked
  0.743  172395 Chicken, roasting, meat only, cooked, roasted   BLOCKED qual:roasting
  0.650  173639 Chicken, roasting, dark meat, ... cooked        BLOCKED qual:roasting
  0.650 2706087 Chicken, chicken roll, roasted                  AUTO-TAKEN
  -> AUTO 2706087 Chicken, chicken roll, roasted
```

`roasting` in `Chicken, roasting` is a *class of bird*, not a qualifier, and
the guard reads it as one. Meanwhile `Chicken, chicken roll, roasted` survives
because its second segment repeats the query's own word (`chicken`), which the
guard's `words & q` test treats as narrowing rather than as a different food.
Sodium: 499 mg per 100 g for the roll, 75 mg for 172395 — a **6.6x** sodium
error on top of the pressed-loaf identity error. The audit reports the wrong
row and never notices that the guard is what removed the right one.

**`jelly` — the audit's largest miss, same pathology.** See §4.

---

## 3. Errors of culinary fact and of nutritional defensibility

### 3.1 `bovril` -> `Yeast extract spread` is wrong. Bovril is beef extract.

§3: "**marmite / vegemite / bovril** — `none`, but `Yeast extract spread`
probes `auto 0.667`. That one is a clean synonym."

Marmite and Vegemite are yeast extracts. **Bovril is a beef extract paste.**
It was briefly reformulated as yeast extract in 2004 and reverted to beef in
2006; the product sold today is beef. This is precisely the bresaola-is-beef
class of error the brief names, arriving in the opposite direction.

Two mitigations I record honestly: the database has no beef-extract row at all
(`ilike '%beef extract%'` returns nothing — only `Roast beef spread` 174597),
and the two products are nutritionally closer than the identity error suggests
(`Yeast extract spread` 167717: 185 kcal, 23.9 g protein, 0.9 g fat, 20.4 g
carbohydrate, **3,380 mg sodium**). So the damage is a confidence and
provenance error rather than a large number error. The fix is to split the
line: marmite/vegemite high, bovril a declared gap.

It also matters that this never fires in production anyway — `label_absent`
blocks both:

```
=== 'marmite' search_terms='Yeast extract spread'
  1.000  167717 Yeast extract spread   BLOCKED label_absent
  -> escalates to model
```

### 3.2 `black pudding` -> `Blood sausage` is Blutwurst, not black pudding

§2.1 files `blutwurst` and `black pudding` on one line pointing at
`Blood sausage` 171618, and §6 calls it "a reachability gap and ... the more
valuable finding". They are not the same food. British black pudding is
one-fifth to one-third cereal — oatmeal or barley — and German Blutwurst is
meat and fat.

```
171618 Blood sausage   379 kcal | 14.6 protein | 34.5 fat | 1.29 carb | 680 Na
```

UK black pudding runs roughly 290 kcal, 22 g fat and 15 g carbohydrate. The row
overstates fat by about 55% and reports essentially **zero carbohydrate for a
food that is a sixth cereal**. `blutwurst` -> `Blood sausage` is high
confidence; `black pudding` -> `Blood sausage` is a nutritional fallback at
medium at best, and the audit should have separated them.

### 3.3 `gherkin` -> `Pickles, cucumber, dill or kosher dill` is variant-dependent and unflagged

The audit gives this line no discussion. The sweet/sour split is a 7.6x energy
error and a 17x sugar error:

```
168558 Pickles, cucumber, dill or kosher dill                  12 kcal | 1.07 sugar |  809 Na
169379 Pickles, cucumber, sour                                 11 kcal | 1.06 sugar | 1208 Na
169378 Pickles, cucumber, sweet (incl. bread and butter)       91 kcal | 18.27 sugar | 457 Na
```

British "pickled gherkins" are usually a sour vinegar pickle, so dill is the
better default — but German *Gewürzgurken* and Dutch *zoetzure augurken* are
sweetened, and this audit's domain explicitly includes them. Confidence should
be medium with the sweet row named, not an unannotated row in a table of clean
synonyms.

### 3.4 `quark` -> `Cheese, cottage, dry curd`: right shape, wrong sodium, and fat-grade unstated

```
2705753 Cheese, cottage, dry curd   72 kcal | 10.3 protein | 0.29 fat | 6.66 carb | 372 Na
```

German *Magerquark* is roughly 67 kcal, 12 g protein, 0.2 g fat, 4 g
carbohydrate and **about 40 mg sodium**. The FNDDS row carries 372 mg — near
enough **9x** — and sodium is a targeted nutrient. The audit says "a fallback,
not a synonym", which is right, but it never names the number that makes it a
fallback, and it does not mention that quark is sold at 20% and 40% fat grades
(Sahnequark is ~160 kcal), so "quark" unqualified is not one food.

### 3.5 §4's cheese refusal overlooks the row that solves it

§4 refuses "Wensleydale, Caerphilly and Lancashire, which are lower-fat crumbly
territorials" and offers them nothing. `Cheese, cheshire` exists and is the
crumbly territorial neighbour:

```
173415 Cheese, cheshire  387 kcal | 23.4 protein | 30.6 fat | 700 Na
328637 Cheese, cheddar   409 kcal | 23.3 protein | 34.0 fat | 654 Na
```

`lancashire cheese` already probes `ask 0.550 Cheese, cheshire`. The refusal is
defensible; declining to mention the obvious neighbour, having looked, is not.
Also, "lower-fat" overstates the gap — Wensleydale is ~31 g fat against
cheddar's 34, about 9%, not a different class.

### 3.6 Smaller corrections

- §1.3 quotes grapeseed at "69.9 g linoleic". It is **69.6**; MUFA 16.1 is
  right. Canola verified: 63.28 MUFA, 19.00 linoleic, **9.14 ALA**. The
  audit's chemistry is otherwise correct and rapeseed-is-canola is right.
- §1.3 says "Both are 884 kcal". True of 171028 and 172336; the FNDDS
  `Canola oil` 2710188 is **900**, and `Oil, canola` 748278 (Foundation) has
  no nutrients at all, so it is filtered as an unusable row.
- §1.2's arithmetic checks out: `Pie, oatmeal` 396 kcal, `Oatmeal, NFS` 76.
- §1.1's `Scotch` figures check out: 2710701, 231 kcal, 0 protein / 0 fat /
  0 carbohydrate.
- §0's reachability table checks out where I tested it: 0 rows contain
  `yoghurt`, 153 contain `yogurt`; 0 contain `prawn`, 69 contain `shrimp`; 0
  contain `schnitzel`; 1 contains `lingenberry` and 0 `lingonberry`.
- §3 on marzipan reverses the ratio. Almond paste is the *higher*-almond
  product; finished marzipan carries more sugar. `Almond paste` 2707535 is 458
  kcal with 36.3 g sugar. The conclusion — do not map it — is right anyway.
- §2.4's claim that FNDDS `Shepherd's pie` is beef is not checkable from this
  database (no ingredient tables). It is plausible and it is asserted as fact.

---

## 4. What the audit missed. 994 terms, and `jelly` was not one of them.

### 4.1 `jelly` — a surviving auto-match, 4.4x energy, and it is not variant-dependent

British *jelly* is a gelatin dessert. USDA `Jelly` is a fruit spread. The label
matches the description exactly, so every guard passes, and the correct row is
disqualified by `label_absent` for not containing the word the user typed:

```
=== 'jelly' search_terms='Gelatin dessert, prepared' state=as_sold
  1.000 2710300 Jelly              AUTO-TAKEN
  0.640 2710310 Gelatin dessert    BLOCKED label_absent
  -> AUTO 2710300 Jelly
```

```
2710300 Jelly              266 kcal | 0.15 protein | 0.02 fat | 69.95 carb | 51.22 sugar
2710310 Gelatin dessert     60 kcal | 1.22 protein | 0.00 fat | 14.19 carb | 13.49 sugar
```

**4.4x energy and 3.8x sugar**, taken with no model consulted, and an alias
written that is never re-checked. This is strictly worse than the audit's §1.4
`jam sandwich` — which the guards block — and it is the same class of error
the audit's §1.8 `biscuit` entry describes, except that `jelly` is *not*
genuinely two-sided for a British user: a British user typing "jelly" means the
dessert essentially always, and says "jam" for the spread.

It is worth noting explicitly that the audit's §1.4 and this case are mirror
images. It found the harmless one and missed the damaging one.

### 4.2 `pudding rice` — surviving auto, ~3x

```
=== 'pudding rice' search_terms='Rice, white, short grain, raw' state=raw
  1.000 2705685 Pudding, rice                             AUTO-TAKEN   (108 kcal, cooked dessert)
  0.722  168931 Rice, white, short-grain, raw, unenriched  ok          (~358 kcal, the dry grain)
  -> AUTO 2705685 Pudding, rice
```

Note the shape: the correct row survives every guard and is simply ranked
second. Even `state: raw` does not save it, because `Pudding, rice` asserts no
state and `state_conflicts` correctly declines to block a silent description.
Lower frequency than `jelly`, same mechanism.

### 4.3 Dialect and orthography entries the §2.1/§2.3 tables omit

Every one probed; verdicts are the probe's, on the user's own word.

| term | probe | the collision the audit did not name |
|---|---|---|
| `jelly` | `auto 1.000 Jelly` | dessert vs fruit spread — §4.1 |
| `chips` | `ask 0.600 Soy chips` | UK chips are fries (~160 kcal) — `Potato chips, NFS` is **532** |
| `crisps` | `weak 0.357 Crisp, peach` | the other half of the same collision |
| `liquorice` | `weak 0.316 Candy, licorice` | pure UK/US spelling, identical to the audit's own `yoghurt` case |
| `linseed` / `linseeds` | `none` / `none` | `Seeds, flaxseed` 169414; `flaxseed` probes `auto 0.692`. A clean synonym, and Leinsamen is a staple in this domain |
| `semi skimmed milk` | `weak 0.346 Milk, fat free (skim)` | 34 kcal / 0.08 g fat against `Milk, reduced fat (2%)` at 50 / 1.90 — the default British milk |
| `gammon`, `rasher` | `none` | the audit spends §2.5 on bacon cuts and omits both |
| `quorn` | `none` | ubiquitous British protein; also the one food where `inverts_meaning` matters |
| `coriander` | `ask 0.476 Spices, coriander seed` | UK coriander is the leaf: 23 kcal vs the seed's **298**, and 17.8 g fat vs 0.52 |
| `paprika` | `ask 0.533 Spices, paprika` | German *Paprika* is the bell pepper, not the spice (282 kcal) |
| `marrow` | `weak 0.184 Caribou, bone marrow, raw` | vegetable marrow against bone marrow |
| `mince` | `weak 0.417 Ham, minced` | UK mince is ground beef |

`chips`, `crisps`, `coriander` and `paprika` all currently escalate, so they are
findings about the mapping table rather than about live damage. `jelly` is live
damage. `linseed`, `liquorice` and `semi skimmed milk` are cheap, safe,
unambiguous additions the audit's own §2.1 criteria would have accepted had it
probed them.

### 4.4 Things that work, which the audit's method would have called broken

Worth recording so nobody "fixes" them:

- `welsh rarebit`, `sauerkraut`, `kohlrabi`, `soda bread`, `smoked salmon`,
  `rye crispbread`, `kefir`, `worcestershire sauce`, `trifle`, `custard`,
  `frankfurter` all auto-match correctly.
- `pumpernickel` probes `auto 0.722 Roll, pumpernickel`, which looks like a
  §1-class error and is not: `Roll, pumpernickel` 2707767 and
  `Bread, pumpernickel` 174918 carry **identical** figures (250 kcal, 8.7
  protein, 3.1 fat, 47.5 carb, 6.5 fibre, 596 Na). With search_terms the bread
  row leads at 1.000 anyway.
- `danish pastry` probes `auto 0.667 Danish pastry, cheese`; in production
  `unrequested_qualifier` blocks it and it escalates.

---

## 5. The methodological point that runs under everything

§5 of the audit is correct and understated. `db.search_foods` orders by
`(similarity + ts_rank) * covers_boost`, then energy-presence, then precedence
— but `probe_knowledge.verdict()` reads `sim` **of whichever row that ordering
surfaced**. So the probe's own `none`/`weak`/`ask`/`auto` labels are not a
function of the list's best similarity, and the headline distribution
(`none=35% weak=34% ask=17% auto=14%`) inherits that.

Production does not have this defect in the same place: `resolve_items` scans
the whole candidate list for the best row clearing `AUTO_MATCH_SIMILARITY` that
survives the guards, rather than testing the head. So §5's example
(`cauliflower cheese` declared `weak` while the list holds a 0.545) does not
change what production does — 0.545 is below the gate either way. The defect is
real; it is a defect of the audit's instrument more than of the resolver.

The larger instrument problem is the one in this critique's method note: the
probe searches one string, `_candidates` searches three or more. Every §2.1
"zero reachability" row is zero-reachability *for the user's own word*, and in
production the model's `search_terms` retrieve the right row and `label_absent`
then correctly prevents a silent auto-match:

```
=== 'gherkins' search_terms='Pickles, cucumber, dill'
  0.710  168558 Pickles, cucumber, dill or kosher dill   BLOCKED label_absent
  -> escalates to model

=== 'emmental' search_terms='Cheese, Swiss'
  1.000 2705735 Cheese, Swiss                            BLOCKED label_absent
  -> escalates to model

=== 'streaky bacon' search_terms='Pork, cured, bacon, cooked'
  0.917  167914 Pork, cured, bacon, cooked, baked        AUTO-TAKEN
```

That last one overturns §2.5's central claim ("neither reaches its own row,
both reach a vegetarian product"). `back bacon` likewise auto-matches
`Canadian bacon, cooked` 2705884 at 1.000. The 3.75x split the audit calls "worth
more than any single dish mapping in this audit" is, in production, already
resolved correctly.

**None of this makes the synonym mappings worthless.** An escalation costs a
model call, and a model call is a probabilistic answer where a mapping is a
fixed one. But the audit sells §2.1 as damage and it is mostly cost, and the
distinction decides what gets built first. What deserves building first is the
short list that survives the guards: `scotch egg` / `scotch pie`, `oatmeal`,
`biscuit`, `roast chicken`, and — the audit's own criteria applied to a term it
did not probe — `jelly`.
