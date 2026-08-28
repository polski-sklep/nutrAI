# CRITIQUE-southeast-asian

28 Aug 2026. Critic pass over `docs/knowledge/AUDIT-southeast-asian.md`
(1,754 lines, 411 terms, 36 findings F1-F36, proposals P1-P3).

Method: every disputed claim re-probed with `scripts/probe_knowledge.py`;
every nutritional claim re-checked against `food_nutrient` with a read-only
SELECT; every claimed dangerous `auto` re-run through the real
`state_conflicts` / `unrequested_qualifier` / `label_absent` guards in
`nutrai/llm/parse.py`.

Written incrementally. Status: IN PROGRESS.

## Summary of the verdict

The audit is unusually good on *absence*: the 48% `none` figure, the Filipino
77%, the entity gaps (F8 sambal/shrimp paste, F15, F20, F28) all re-probe
exactly as written and the botanical reasoning in F16 (ube ≠ taro) and F22
(water spinach ≠ spinach) is correct and is the domain's version of the
halloumi trap. F36 is the best single finding in the file and I confirm it.

Where it is weak is on *state*, on its own guard methodology, and on the
confidence column of P2. Six proposals pin a **dry** or **prepared-dish** row at
`high` while the same document files a 3x dry-vs-cooked error (F25) as its
flagship harm. And the guard check covers only 24 of the 54 `auto` verdicts it
found — 30 were never run through the guards at all, including two that turn out
to be live wrong-confident matches.

## Confirmed — re-measured and upheld

Guard replay used `nutrai.llm.parse.inverts_meaning / state_conflicts /
unrequested_qualifier / label_absent` against live `db.search_foods`.

| finding | probe | guards | verdict |
|---|---|---|---|
| F1 coconut milk -> 2705413 (31 kcal) | 1.000 | SURVIVES | **upheld** |
| F2 coconut cream -> 2708006 Pie (297 kcal) | 0.765 | SURVIVES | **upheld** |
| F4 sweet soy sauce -> 2707442 Soy sauce | 0.643 | SURVIVES | **upheld** |
| F6 ginger -> 2710507 Tea, ginger (1 kcal) | 0.636 | SURVIVES | **upheld** |
| F25 brown rice -> 1104812 Flour, rice, brown | 0.647 | SURVIVES | **upheld** |
| F36 roasted peanuts -> 2707520 honey roasted | 0.727 | SURVIVES | **upheld** |

Nutrient figures re-pulled per 100 g and every one the audit quotes is correct:

```
 2705413 Coconut milk                  kcal=31   fat=2.08  carb=2.92  Ca=188
 2707568 Coconut milk, used in cooking kcal=230  fat=23.84 carb=5.54  Ca=16
  170173 Nuts, coconut milk, canned    kcal=197  fat=21.33 carb=2.81
 2708006 Pie, coconut cream            kcal=297  fat=17.83 carb=31.96 sug=18.66
  170580 Nuts, coconut cream, raw      kcal=330  fat=34.68 carb=6.65
 2707571 Coconut cream, cnd, sweetened kcal=357  fat=16.31 carb=53.21 sug=51.5
 1104812 Flour, rice, brown            kcal=365  prot=7.19 carb=75.5
 2708414 Rice, brown, cooked           kcal=123  prot=2.43 carb=25.76
 2707442 Soy sauce                     kcal=53   Na=5493
 2710507 Tea, ginger                   kcal=1    (an infusion, not a rhizome)
 2707515 Peanuts, roasted, salted      kcal=599  prot=28.03 carb=15.26 sug=4.18
 2707520 Peanuts, honey roasted        kcal=574  prot=20.70 carb=30.02 sug=16.14
```

Two small corrections inside the confirmations:

- F6 understates itself. `Tea, ginger` is **1 kcal/100 g**, not merely a wrong
  row — it is an infusion. Ginger in a rendang or a pho broth logs as
  approximately nothing at all, so the error is not a mis-estimate, it is a
  silent deletion of the ingredient. The audit never quotes the figure.
- F2's mechanism note is right but incomplete. The audit blames
  `unrequested_qualifier` only inspecting segments after the first. True, but
  `label_absent` also cannot fire — "coconut" and "cream" are both present in
  `Pie, coconut cream`. Two guards are blind here, not one.

## The methodological error at the centre of the guard check

The audit's guard check says it ran the domain's autos "read-only; bare user
label, no model `search_terms`, `state` unset — the honest worst case for a
typed message". **`state` unset is not a worst case, it is an impossible case.**

`nutrai/llm/schemas.py:69` lists `state` in `required`, with the enum
`["raw","cooked","dry","as_sold","unknown"]`. Every item that reaches
`resolve_items` carries one of those five. Running the guards with `state=None`
turns `state_conflicts` off entirely — `_STATE_EXCLUDES.get(None)` returns
nothing and the function returns `None` before it looks at the description. So
the audit's table measures a resolver with one of its three guards disabled.

The direction of the error is not uniform, which is why it matters:

- **`state_conflicts` is understated.** Re-run with the state a model would
  actually emit, four of the table's SURVIVES entries change behaviour:

```
chinese broccoli  state=cooked  0.810 Broccoli, chinese, raw  BLOCK state:raw
                                0.739 Broccoli, chinese, cooked  -> AUTO (better row)
chinese cabbage   state=cooked  0.789 Cabbage, Chinese, raw   BLOCK -> escalates
napa cabbage      state=raw     0.684 Cabbage, napa, cooked   BLOCK -> escalates
chicken thigh
  skinless        state=cooked  0.697 Chicken, thigh, ...raw  BLOCK -> escalates
```

- **`unrequested_qualifier` is overstated.** It is called with
  `asked_for = f"{label} {it.get('search_terms') or ''}"` (parse.py:688), not
  with the bare label. A longer query means a larger `q`, which means *fewer*
  blocks. Every "BLOCK:qual escalates" row in the audit's table is measured
  against the strictest possible query. Re-run with the search_terms a model
  would write, `condensed milk` flips:

```
condensed milk  st='milk, condensed, sweetened'
    0.625 Milk, condensed, sweetened  SURVIVES  -> AUTO
```

  Harmless here (condensed milk does mean sweetened), but it shows the table's
  block column is not load-bearing. F33's withdrawal survives the correction —
  `rice flour` with `search_terms='rice flour, white'` still blocks on `brown` —
  so the retraction stands; its stated reasoning does not.

None of this overturns F1/F2/F4/F6/F25/F36. Those six survive every combination
of state and search_terms I could construct, which is why I mark them upheld
above rather than merely reproduced.

## Overturned — mappings that would log a materially wrong number

### O1 — P2 pins the **dry** noodle row at `high`, in a document whose flagship finding is a dry-vs-cooked error

Seven proposal lines point at `174258 Noodles, chinese, cellophane or long rice
(mung beans), dehydrated`, and one at `Rice noodles, dry`:

```
sotanghon / glass noodles / cellophane noodles / mung bean noodles /
bean thread noodles / woon sen / mien   -> 174258   | high
bihon                                   -> Rice noodles, dry | high
```

Measured:

```
  174258 Noodles, chinese, cellophane ... dehydrated  kcal=351  carb=86.09
 2708355 Long rice noodles, mung beans, cooked        kcal=84   carb=20.66   (4.2x)
  169742 Rice noodles, dry                            kcal=364  carb=80.18
  168914 Rice noodles, cooked                         kcal=108  carb=24.01   (3.4x)
```

A plate of yum woon sen, sotanghon guisado or pancit bihon is weighed cooked.
Pinning the dehydrated row is a **4.2x** error — larger than F25's 3x, which the
audit calls "a 3x staple error" and files as its own headline. The same document
proposes `brown rice -> 2708414 Rice, brown, **cooked**` and then proposes the
dry row for every noodle, with no sentence acknowledging the inconsistency.

Worse, the resolver already gets this right unaided when state is supplied:

```
== 'rice noodles'  st='rice noodles, cooked'  state=cooked
   0.765 Rice noodles, dry     BLOCK state:dry
   0.650 Rice noodles, cooked  SURVIVES   -> AUTO -> Rice noodles, cooked
```

So P2's `bihon -> Rice noodles, dry` would make a synonym layer *worse* than the
shipped resolver on the commonest case. Overturned: propose the pair and let the
model tier or `state_conflicts` choose, exactly as the audit itself argues for
brown rice ("the encoding should block the flour rather than pin one cooked row").

### O2 — `squid -> Calamari, cooked` maps an ingredient onto a fried preparation

```
squid / sotong / pusit / pla muek | synonym | 2706333 Calamari, cooked | high
```

```
  174223 Mollusks, squid, mixed species, raw     kcal=92   prot=15.58 fat=1.38
  171982 Mollusks, squid, cooked, fried          kcal=175  prot=17.94 fat=7.48
 2706333 Calamari, cooked                        kcal=155  prot=19.36 fat=6.25
 2706334 Calamari, fried                         kcal=234  prot=13.76 fat=13.22
```

*Calamari* is not the English for *squid*; it is the name of a **fried
preparation**, and FNDDS's numbers say so — 6.25 g fat where the raw mollusc has
1.38, a **4.5x** fat multiplier, and `Calamari, cooked` sits within 12% of
`squid, cooked, fried`. Sambal sotong, adobong pusit and pla muek pao are not
battered. The audit itself lists `174223 Mollusks, squid, mixed species, raw` in
F31's own evidence block and then proposes the calamari row anyway.

This is the domain's bresaola: a name that reads as a translation and is actually
a different preparation. Repoint to `174223` (raw) / `171982` (fried) and let
state choose; `high` is defensible only on the identity, not on the row.

### O3 — `ikan bilis -> Fish, anchovy, canned in oil` contradicts its own rationale

```
ikan bilis / dried anchovies | synonym | 174183 Fish, anchovy, canned | medium
```

The rationale calls ikan bilis "a serious sodium and **calcium** source". The
proposed row:

```
  174183 Fish, anchovy, european, canned in oil, drained solids
         kcal=210  prot=28.89  fat=9.71  Na=3668  Ca=232
```

Dried whole anchovy is eaten bones-and-all and runs roughly 1,500–2,000 mg
calcium per 100 g; the proposed row carries **232**, about one-eighth, because
canned fillets are boned. It is also oil-packed, so the fat is a packing medium
the dried product does not have. Dried-vs-preserved is the exact trap the brief
names. Reject, or demote to `low` with the deficit stated. `anchovies -> Fish,
anchovy` (a reachability fix on the plural, F32) is unaffected and stands.

### O4 — the coconut milk targets are the wrong way round

```
coconut milk / santan / gata / kati | -> 2707568 (230 kcal) | high
tinned coconut milk                 | -> 170173  (197 kcal) | high
```

`santan`, `gata` and `kati` are, in ordinary home cooking today, the **tinned**
product; `2707568 Coconut milk, used in cooking` is byte-identical to
`170172 Nuts, coconut milk, raw` (230/2.29/23.84/5.54 — the freshly pressed
first extraction). The audit assigns the fresh-press figure to the native words
and the tinned figure to the English phrase that says "tinned". Swap them, or
collapse to 170173. A 17% overstatement, so a correction rather than a defect —
but it is backwards, and the layer will be read literally.

## Downgraded — culturally right, confidence inflated or target over-broad

**D1 — `krupuk` / `kerupuk` -> Shrimp chips, `high` -> `medium`.** *Krupuk* is a
family, not a food. *Krupuk udang* is the prawn cracker; *krupuk putih*,
*krupuk kampung* and *emping* (melinjo nut) contain no shrimp at all and are
plain fried starch. `prawn cracker`/`prawn crackers` -> `2708246 Shrimp chips`
is a clean `high` and I uphold it. Bare `krupuk` is over-broad in the
halloumi-to-cheese sense the brief names — and unlike halloumi the products
differ in protein (17.9 g fat / 571 mg Na for the shrimp version against a
near-pure starch cracker).

**D2 — `calamansi` -> `Lime, raw`, `high` synonym -> `medium`
nutritional_fallback.** Calamansi is *Citrus × microcarpa*, a kumquat-mandarin
hybrid, not *Citrus aurantiifolia*. For the 5 ml squeeze that is the actual use
this is immaterial and the fallback is fine; calling it a `synonym` at `high`
asserts an identity that is false, and the audit's own F17 correctly describes
it as "a citrus fruit". Same relation-word problem as O2. Note the audit
proposes both `calamansi` and `kalamansi` but its probe only ever tested
`calamansi` and `kalamansi juice`; `kalamansi` bare returns `none`.

**D3 — the four `adobo` surfaces onto one row, `high` -> `medium`.**
`adobo`, `chicken adobo`, `pork adobo` and `adobong manok` all point at
`2708958`. Pork adobo is usually belly or shoulder and chicken adobo is thigh;
folding them erases the fat difference, and USDA has no second row to split
them onto — which is an argument for escalating, not for asserting. Also worth
recording because I checked it and it is *not* the problem it looks like: the
row is named "Adobo, with rice" but carries **8.86 g carbohydrate per 100 g**,
far below cooked rice's ~28, so it is meat-weighted and a user logging adobo
plus a separate rice portion will not double-count. The name misdescribes the
row in the opposite direction.

**D4 — the basil group: right answer, wrong reason, non-existent target.**
P3 says "all cultivars of *Ocimum* are the same leaf herb". Holy basil
(*O. tenuiflorum*) is a different **species** from sweet and Thai basil
(*O. basilicum*), not a cultivar of it. The nutritional conclusion survives —
these are 5-10 g garnishes and the difference is aromatic — so `high` stands,
but the stated reasoning is wrong and should not be encoded as the rationale.
Separately, the proposed target string `Basil, fresh` does not exist; the row is
`Basil, raw`. Same defect in `tahu | synonym | Tofu (raw, firm)` — there is no
`Tofu, raw, firm`; the rows are `Tofu, raw, regular` and `MORI-NU, Tofu, silken,
firm`. Two proposals name rows that are not in the database.

**D5 — `pho` bare -> "with meat", `high` -> `medium`.** `pho bo`, `pho ga` ->
with-meat and `pho chay` -> no-meat are exactly right and the audit is correct
that this is the one place USDA's split matches the native vocabulary. Bare
`pho` defaulting to with-meat is a guess about the eater, not about the word.
The difference is 37 vs 77 kcal per 100 g over a ~700 g bowl — 280 kcal on a
coin toss. Escalate instead.

**D6 — `bitter gourd` / `ampalaya` / `pare` -> `Balsam-pear ... raw`, note the
state.** Correct food, correct genus, and `pare` is right for Indonesian. But
ampalaya is never eaten raw (ginisang ampalaya, pad ma-ra); pinning the raw row
in a synonym layer is the O1 shape in miniature. `bitter melon` already autos
onto `Bitter melon, cooked` and survives the guards, so the cooked row is
reachable.

**D7 — `gula melaka` and `jaggery` were proposed without ever being probed.**
P3 lists `gula melaka | nutritional_fallback | Sugars, granulated | medium`, and
`gula melaka` appears nowhere in the 411 probe lines. I probed it: `none`.
(`jaggery`, its South Asian cognate, is also `none`.) The proposal happens to be
right; it is not evidenced, and in a document this careful about measurement
that is a lapse worth naming.

**D8 — the guard table conflates harmful survivors with correct ones.** Seventeen
rows are labelled "SURVIVES AUTO" with no column separating them. Six are the
defects (coconut milk, coconut cream, brown rice, sweet soy sauce, dark soy
sauce, ginger) and eleven — jackfruit, shrimp, garlic, bean sprouts, bamboo
shoots, chinese broccoli, white pepper, curry powder, tempe, bitter melon,
peanut brittle — are the resolver getting it **right** with no model spend. The
table reads as seventeen risks. It is six.

## Missed — foods this domain eats that the audit never probed

163 further terms probed. The eight below are the ones that matter, each with
probe output and, where it is an `auto`, a guard replay under a realistic
`state` and `search_terms`.

### M1 — `glutinous rice` is a live wrong auto, and the audit walked past it

```
auto  glutinous rice                     0.714  Flour, rice, glutinous

== 'glutinous rice'  st='rice, glutinous, cooked'  state=cooked
   0.714 Flour, rice, glutinous  SURVIVES   -> AUTO -> Flour, rice, glutinous
```

```
 1104867 Flour, rice, glutinous               kcal=358  prot=6.69  carb=80.1
 2708422 Rice, white, cooked, glutinous       (exists)
  169711 Rice, white, glutinous, unenriched, cooked  (exists)
```

The audit *prints this line* in Batch 1 and then, in F25, hands it to the
Chinese audit — "the same defect the Chinese audit filed for `glutinous rice`".
That is a filing decision, not a measurement, and it is wrong for this domain:
**glutinous rice is the everyday staple grain of Laos, Isan and northern
Thailand**, eaten at most meals, and it is the basis of khao niao mamuang, xoi,
suman and kanom. It is a bigger daily error here than brown rice.

Note `state_conflicts` cannot save it: `Flour, rice, glutinous` contains no
state word, so a declared `cooked` does not contradict it. Two correct cooked
rows exist and neither is reachable. This deserved its own finding at the same
weight as F25, with `sticky rice` (weak 0.375 `Soup, rice`) and `khao niao` as
its synonyms.

### M2 — `coconut milk powder` is F1 with a 21x multiplier, and `light coconut milk` a 3x

```
auto  coconut milk powder                0.650  Coconut milk
auto  light coconut milk                 0.684  Coconut milk

== 'coconut milk powder'  st='coconut milk powder, dried' state=dry
   0.650 Coconut milk  SURVIVES  -> AUTO -> Coconut milk [2705413]
== 'light coconut milk'  st='coconut milk, light, canned' state=as_sold
   0.684 Coconut milk  SURVIVES  -> AUTO -> Coconut milk [2705413]
```

F1 tested the two words and stopped. The powder (Kara, Maggi santan powder — the
ordinary form in Malaysian and Filipino home cooking) is a dried product around
650 kcal/100 g resolving onto a 31 kcal beverage. `state='dry'` does not help:
`Coconut milk` names no state. Both auto, both cache an alias, and any fix to F1
that keys on the exact string `coconut milk` will leave both standing.

### M3 — `green beans` reproduces F36 at 5.6x, on a vegetable this cuisine eats daily

```
== 'green beans'  st='green beans, boiled'  state=cooked
   0.750 Green beans, raw     BLOCK state:raw
   0.667 Fried green beans    SURVIVES   -> AUTO -> Fried green beans
```

```
 2709769 Green beans, raw      kcal=40   fat=0.28  carb=7.41  Na=0
 2709869 Fried green beans     kcal=223  fat=12.86 carb=22.86 Na=314
```

F36 is the audit's best finding — "blocking the head can promote something
worse" — and it rests on one case where the harm is 10 g of peanuts. Here the
same mechanism, driven by `state_conflicts` rather than
`unrequested_qualifier`, promotes a **5.6x** row for adobong sitaw, pad prik
king, sayur lodeh and gulai. This is the evidence F36 needed and did not have,
and it shows the mechanism is not specific to one guard.

### M4 — `sriracha` cannot reach the row named sriracha

```
weak  sriracha                           0.375  Sauce, hot chile, sriracha
```

`ILIKE %sriracha%` -> three rows, one of them `171186 Sauce, hot chile,
sriracha`. Below the weak floor, so the model tier is not even handed the list.
This is F9's exact shape (a perfect substring losing to description length) on
the single most-used chilli condiment of the domain in Western kitchens, and it
is untested in 411 terms. Note the audit *did* surface `171187 ... CHA! BY TEXAS
PETE` as the bad neighbour for `pete` in Batch 5 and did not follow the thread.

### M5 — `daikon` returns nothing while USDA carries it under `Radishes, oriental`

```
none  daikon                             -      (nothing)
auto  oriental radish                    0.714  Radishes, oriental, raw
weak  mooli                              0.333  Moose
```

`ILIKE %daikon%` -> 0 rows; `168451/168452/168453 Radishes, oriental,
raw/cooked/dried` is daikon. F12 searched "by ingredient (fish sauce, lime,
sugar, vinegar, **daikon**, carrot)" and concluded there was a gap, but the
correct row is right there under USDA's name for it. This is the purest F30
(prawn/shrimp) case in the domain and the audit filed it as an entity gap
instead. `mooli`, the British greengrocer name, reaches **`Moose`** — the same
near-collision shape as F17/F18/F31 and a better example than any of them.

### M6 — `scallion` scores 0.160 against the row that contains the word

```
weak  spring onion    0.240  Onions, spring or scallions (includes tops and bulb), raw
weak  scallion        0.160  Onions, spring or scallions (includes tops and bulb), raw
weak  mint leaves     0.333  Taro leaves, raw
```

0.160 is the second-lowest score anywhere in either document (only F18's `laing`
at 0.059 is worse) and the row literally contains "scallions". Spring onion is
in pho, nasi goreng, adobo, laksa and every fried rice in the domain.
`2727585 Green onion, (scallion), bulb and greens, root removed, raw` also
exists and is also unreachable. `mint leaves` -> **`Taro leaves, raw`** is a
bonus: mint is the defining herb of bun cha and goi cuon.

### M7 — `rice vermicelli` reaches a Rice-A-Roni box, and the audit printed it without filing it

```
weak  rice vermicelli  0.319  Rice and vermicelli mix, rice pilaf flavor, unprepared
weak  vermicelli       0.440  Vermicelli, made from soy
none  bihun            -      (nothing)
```

This exact line appears in the audit's Batch 2 and is never mentioned again — no
finding, no proposal, though `bihon` (the same noodle, Filipino spelling)
appears in P2 with no finding reference. `ILIKE %vermicelli%` -> seven rows,
five of them boxed American pilaf mixes and two of them **soy** noodles. Rice
vermicelli is the noodle of bun, pancit bihon, laksa and mohinga; there is no
correct row and the head of its candidate list is a seasoned pilaf mix. That is
an entity gap of the F15 class, unfiled.

### M8 — `tapioca flour` 0.189 and `pork mince` 0.169: the ranker returning anything

```
weak  tapioca flour  0.189  Rolls, gluten-free, white, made with brown rice flour, tapioca starch, and sorghum flour
weak  pork mince     0.169  Luncheon meat, pork with ham, minced, canned, includes Spam (Hormel)
ask   minced pork    0.438  Ham, minced
auto  ground pork    1.000  Pork, ground
```

The audit filed `tapioca starch` at 0.203 against the same gluten-free roll in
Batch 2 and drew no conclusion. `pork mince` — the British and Australian word
order, and the meat in bun cha, larb moo, sisig and lumpia — reaches **Spam**,
while the American `ground pork` autos at 1.000 onto the right row. Another pure
F30-shape synonym gap, and one where the wrong neighbour is a cured, salted,
canned product.

## Notes on method

Guard replay script and the nutrient dump are in the session scratchpad, not in
the repo. Everything above is reproducible with:

```
.venv/bin/python scripts/probe_knowledge.py "glutinous rice" "coconut milk powder" \
    sriracha daikon scallion "rice vermicelli" "pork mince" mooli
```

and, for the guard replay, `inverts_meaning` / `state_conflicts` /
`unrequested_qualifier` / `label_absent` from `nutrai/llm/parse.py` applied over
`db.search_foods(label)` with `asked_for = f"{label} {search_terms}"` — the same
expression `resolve_items` builds at parse.py:688.

No database writes. No files under `nutrai/`, `tests/`, `sql/` or `scripts/`
were modified.

Status: COMPLETE.
