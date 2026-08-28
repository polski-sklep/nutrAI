# CRITIQUE-taxonomy-fallback

28 Aug 2026. Adversarial review of `AUDIT-taxonomy-fallback.md`. I did not write
that file. Every claim below was re-probed or re-measured; where I uphold the
auditor I say so, and where I overturn I quote the number.

Method: `scripts/probe_knowledge.py` for verdicts, read-only `SELECT` against
`food_nutrient` for figures, and a scratchpad re-implementation of the shipped
guards (`inverts_meaning`, `state_conflicts`, `unrequested_qualifier`,
`label_absent` imported from `nutrai.llm.parse`, not re-typed) for the guard
check.

_Sections appended as work proceeds._

## 1. The guard check, redone with `search_terms` present — three corrections

The auditor's guard harness fed the guards the **label alone**. Production does
not: `_candidates` pools `search_terms` *and* the label, and
`unrequested_qualifier`/`inverts_meaning` are handed
`asked_for = f"{label} {search_terms}"`. Re-running with a plausible
`search_terms` moves three of the audit's headline results.

### 1a. `salmon` → `Salmon salad` — UPHELD, but only when the state is `cooked`

```
'salmon'  state=None    search_terms='Fish, salmon, Atlantic, farmed, cooked'
   0.786  Fish, salmon, Atlantic, farmed, cooked, dry heat   BLOCKED:qualifier
   0.730  Fish, salmon, Atlantic, farmed, raw                SURVIVES
   0.700  Salmon salad                                       SURVIVES
   -> effective = AUTO Fish, salmon, Atlantic, farmed, raw

'salmon'  state='cooked' search_terms='Fish, salmon, Atlantic, farmed, cooked'
   0.786  Fish, salmon, Atlantic, farmed, cooked, dry heat   BLOCKED:qualifier
   0.730  Fish, salmon, Atlantic, farmed, raw                BLOCKED:state
   0.700  Salmon salad                                       SURVIVES
   -> effective = AUTO Salmon salad
```

So the finding is real but the audit states it too broadly. Unstated or raw
state, the correct farmed-Atlantic row outranks the salad and takes the match.
Declare the state honestly — `cooked`, which is what anyone eating salmon would
log — and `state_conflicts` removes the only row standing between the user and
the mayonnaise. **The guard that exists creates the failure**, which is a
sharper statement than the audit's.

### 1b. The audit gives the wrong mechanism for `Salmon salad`

> "`Salmon salad` is a single unpunctuated segment, so `unrequested_qualifier`
> has nothing after a comma to inspect at all."

False. The `i == 0` branch does inspect the head segment. The real mechanism is
that **`salad` sits in `_QUALIFIER_STOP`** — added for `Oil, olive, salad or
cooking` — so the head reduces to `{salmon}`, `extra` is empty and the branch
cannot fire:

```
unrequested_qualifier('salmon',       'Salmon salad')  = None
unrequested_qualifier('chicken',      'Chicken salad') = None
unrequested_qualifier('tuna',         'Tuna salad')    = None
unrequested_qualifier('egg',          'Salad, egg')    = None
```

This also falsifies the comment shipped in `parse.py` beside `_QUALIFIER_STOP`:
"Only ever a later segment; a first segment like `Chicken salad` is still
judged as a name." It is not. Every `X salad` row in FNDDS is auto-matchable by
`X`. That is a one-line fix (drop `salad` from the stoplist and exempt only the
literal `salad or cooking` usage), and the audit's proposed "fifth guard" is
not needed for this third of its evidence.

### 1c. NEW — `label_absent` blocks the *correct* row on every `-y/-ies` plural

This is the mechanism the audit missed, and it is the one that makes the pie
results dangerous rather than merely possible. `label_absent` prefix-matches to
stand in for stemming, and `y -> ies` defeats it:

```
label_absent('strawberry', 'Strawberries, raw')     = True    <- correct row BLOCKED
label_absent('strawberry', 'Pie, strawberry')       = False   <- pie SURVIVES
label_absent('cherry',     'Cherries, sweet, raw')  = True
label_absent('cherry',     'Pie, cherry')           = False
label_absent('blueberry',  'Blueberries, raw')      = True
label_absent('raspberry',  'Raspberries, raw')      = True
label_absent('pastry',     'Pastries')              = True
label_absent('patty',      'Patties')               = True
(for contrast: 'potato'/'Potatoes, raw' = False, 'brownie'/'brownies' = False)
```

Measured end to end, with a `search_terms` the model would plausibly write:

```
'strawberry' state=None  search_terms='strawberries, fresh'
   0.733  Pie, strawberry       SURVIVES
   0.625  Strawberries, frozen  BLOCKED:qualifier,label_absent
   0.591  Strawberries, raw     BLOCKED:label_absent
   -> effective = AUTO Pie, strawberry

'strawberry' state='raw' search_terms='Strawberries, raw'
   1.000  Strawberries, raw     BLOCKED:label_absent   (x5, duplicate rows)
   -> effective = escalates
```

The guard written to stop `brownie -> Pie, chocolate creme` **selects for the
pie** on this whole family: the dish row keeps the singular the user typed, the
fruit row pluralises it. The audit's "highest-value finding" is right about the
outcome and wrong about the cause, and the cheapest fix is a `-y/-ies` rule in
`label_absent`, not a new guard.

### 1d. `sweet potato` and `brown rice` — UPHELD and worse than reported

Adding `search_terms` does not save either; it makes both clearer, because the
correct rows are the ones the guards disqualify:

```
'sweet potato' state='cooked' search_terms='Sweet potato, cooked, baked'
   0.812  Pie, sweet potato                                 SURVIVES
   0.765  Sweet potato, NFS                                 SURVIVES
   -> effective = AUTO Pie, sweet potato
'sweet potato' state=None search_terms='Sweet potato, cooked, baked in skin, without salt'
   0.875  Sweet potato, cooked, baked in skin, flesh, ...   BLOCKED:qualifier ("flesh")
   0.812  Pie, sweet potato                                 SURVIVES
   -> effective = AUTO Pie, sweet potato

'brown rice' state='cooked' search_terms='Rice, brown, cooked'
   0.647  Flour, rice, brown                                SURVIVES
   0.600  Rice, brown, cooked, no added fat                 BLOCKED:qualifier
   0.581  Rice, brown, cooked, NS as to fat                 BLOCKED:qualifier
   -> effective = AUTO Flour, rice, brown
```

The right sweet-potato row scores **0.875, higher than the pie**, and is thrown
out for the word "flesh". Note `Sweet potato, NFS` also survives at 0.765 — one
rank below the pie. A tie-break that preferred the shorter/`NFS` row over a
dish head would fix this case without any new guard.

## 2. Culinary and nutritional errors in the audit's own proposals

### 2a. OVERTURN — `emmental -> Cheese, gruyere` ignores the row that *is* emmental

Batch 9 proposes "comté, emmental, raclette → `Cheese, gruyere` — Alpine
cooked-curd, the closest make and within 5% on every line". `Cheese, swiss`
exists and Swiss cheese in USDA **is** Emmental:

```
171251 Cheese, swiss    kcal=393  prot=26.96 fat=30.99 satfat=18.23 Ca=890  Na=187
171242 Cheese, gruyere  kcal=413  prot=29.81 fat=32.34 satfat=18.91 Ca=1011 Na=714
```

"Within 5% on every line" is false on the line that matters: **sodium 187 vs
714, a factor of 3.8.** Emmental's low salt is one of its defining properties.
On a 40 g portion the proposed mapping invents 211 mg of sodium against 75 mg.
The mapping is not a fallback at all — it is a substitution away from an exact
identity. `emmental / emmentaler → Cheese, swiss` (high). `comté` and
`raclette` → `Cheese, gruyere` stand.

### 2b. OVERTURN — bresaola is beef, and the audit files it under cured pork

Batch 1 is titled "cured and salted pork" and includes `bresaola` in it, then
places it in the cut taxonomy as "loin (lonza/coppa/bresaola territory) under
10 g [fat]". Bresaola is air-dried **beef** silverside/eye of round. The audit
never proposes a target for it, while the correct one sits four lines above in
its own probe output:

```
170604 Beef, cured, dried   kcal=153 prot=31.1 fat=1.94 Na=2790
```

Real bresaola is ~150 kcal, 32 g protein, 2 g fat — an almost exact match on
macros, ~1.6x high on sodium. **`bresaola → Beef, cured, dried` (high on
macros, medium on sodium)** is the single best unclaimed mapping in batch 1,
and the audit missed it because it had put the food in the wrong animal.

### 2c. OVERTURN — coppa/capocollo is not a loin

Same sentence: "loin (lonza/coppa/bresaola territory) under 10 g". `Lonza` is
loin. **`Coppa`/`capocollo` is the neck and shoulder collar muscle**, marbled by
definition — 25–30 g fat per 100 g, roughly 320–380 kcal. Building any fallback
on "under 10 g fat" for coppa understates its energy by about 2x. Coppa belongs
in the belly/jowl half of the audit's own cut axis, not the loin half.

### 2d. INTERNAL CONTRADICTION — the dried-chilli chain the audit proposes, it then refutes

Batch 5 proposes:

> the correct parent chain runs `ancho / guajillo / gochugaru / bird's eye,
> dried → Spices, chili powder`

and three paragraphs later:

> `Spices, chili powder` carries **2867 mg sodium** (it is a blend with salt)
> ... For pure ground chillies the honest target is `Spices, paprika` or
> `Spices, pepper, red or cayenne`, not `Spices, chili powder`.

Gochugaru is pure ground chilli with no salt; ancho and guajillo are whole
dried pods. Every member of the proposed chain is exactly the "pure ground
chilli" case the later paragraph excludes. The chain as written imports 2.9 g
of sodium per 100 g. **Only the second statement should survive.**

### 2e. DOWNGRADE — `schmaltz → Fat, chicken` is not "a pure synonym"

Correct for Yiddish/Ashkenazi *schmaltz*. German **`Schmalz`** and Polish
**`smalec`** are rendered *pork* lard — `Griebenschmalz` is lard with
cracklings. `Fat, chicken` is 900 kcal / 29.8 g satfat / 85 mg chol; `Lard` is
902 / 39.2 / 95. Energy is identical, saturated fat is 32% out and the food is
a different animal. In a diary that already logs `salo`, `slanina`, `żurek` and
`kotlet schabowy`, the German reading is at least as likely as the Yiddish one.
**Medium, and it should ask rather than auto.**

### 2f. DOWNGRADE — the fresh-cheese "no row" bucket is the over-breadth the audit condemns

Batch 2's table puts `twaróg, quark, fromage blanc, skyr, labneh` on one line
("acid, drained, **unsalted**"). Three problems:

* **Skyr** is made from skimmed milk: ~63 kcal, 11 g protein, 0.2 g fat.
  **Labneh** is strained *whole-milk* yogurt: ~230–250 kcal, 20–24 g fat — and
  it is conventionally **salted**, so "unsalted" is wrong for it.
  That is a 4x energy spread inside one proposed family, in a file whose whole
  argument is that a 72–310 kcal `fresh cheese` parent "is nutritionally empty
  and must not be encoded". The same objection applies to its own line.
* **Twaróg** is sold in three legally distinct fat grades (chudy ~90 kcal,
  półtłusty ~130, tłusty ~175). A single mapping cannot be high confidence.
* **Chhena is not pressed.** The table lists "paneer, chhena — acid, pressed".
  Chhena is the drained, *unpressed* curd; paneer is chhena pressed. Minor for
  numbers, but it is the make distinction the table claims to be organised by.

### 2g. DOWNGRADE — "the highest-confidence proposals in this audit" are variant-dependent

`manchego → Cheese, gouda` (356 kcal, 27.4 g fat): manchego is sheep's milk and
runs ~390–420 kcal with ~33 g fat. That is 10–15% under on energy and ~20%
under on fat. `stilton → Cheese, blue` (353 / 28.7) is the same size of error —
Stilton is ~410 / 35. `wensleydale → Cheese, cheddar` is called "literally the
same make"; it is not (Wensleydale is not cheddared, it is a crumbly moist
territorial). `pecorino romano → Cheese, romano` is good on macros but the USDA
Romano rows are cow's-milk Romano at 1433 mg Na against a real Pecorino Romano
nearer 1600–1800.

None of these are bad mappings. They are **medium**, and the audit's claim that
they are "beyond dispute" because "make fixes composition" is exactly the
reasoning it rejects for the fresh cheeses. `parmigiano reggiano → Cheese,
parmesan, hard`, `gorgonzola → Cheese, blue` and `red leicester / double
gloucester → Cheese, cheddar` are the ones that genuinely are high.

### 2h. UPHELD — the `Cheese, paneer` row really is unusable

Verified directly on `food_nutrient` for 2705740: carbohydrate (1005) = 22.46,
and **sugars (1063) = 23.33** — sugar exceeding total carbohydrate, as claimed.
1063 is folded to 2000 by `nutrient.canonical_id`, so it does reach the day
total and the ceiling. The audit's refusal to use this row for anything,
including paneer itself, is correct and is the most useful single call in the
file.

### 2i. Structural — the promised conclusions section does not exist

The header says "Findings, proposals and rejections are at the end of the file,
after the ten batch sections." The file ends with batch 11. There is no
consolidated proposal table, no confidence column, and batches 1, 5, 6, 7 and
10 end without an explicit proposal list at all — the mappings have to be dug
out of prose. For a file whose output is meant to be a knowledge layer, that is
a real gap.

## 3. What the audit missed — probed, guard-checked, worse than anything in it

### 3a. `chicken` auto-matches `Fat, chicken`, and no `search_terms` saves it

The audit devotes batch 4 to animal fats and never probes the bare word.

```
$ probe_knowledge.py chicken
auto  chicken                            0.667  Fat, chicken

guard harness, label only:
   0.667  Fat, chicken     SURVIVES        -> AUTO
   0.615  Chicken skin / Chicken, tail / Chicken, back / Chicken feet   BLOCKED:qualifier

guard harness, state='cooked', search_terms='Chicken, breast, meat only, cooked, roasted':
   0.756  Chicken, roasting, meat only, cooked, roasted                 BLOCKED:qualifier
   0.725  Chicken, broilers or fryers, breast, meat only, cooked, roast BLOCKED:qualifier
   0.674  Chicken, roasting, dark meat, meat only, cooked, roasted      BLOCKED:qualifier
   0.667  Fat, chicken                                                  SURVIVES
   -> effective = AUTO Fat, chicken
```

Measured:

```
173564 Fat, chicken   kcal=900  prot=0     fat=99.8  satfat=29.8  chol=85
       chicken breast, meat only, roasted   kcal≈165  prot≈31  fat≈3.6
```

A 200 g portion labelled `chicken` is booked as **1800 kcal and 0 g protein**
instead of ~330 kcal and 62 g. Every legitimate chicken row is disqualified by
`unrequested_qualifier` for carrying `broilers`/`roasting`/`breast`/`dark meat`,
while `Fat, chicken` survives because its head segment (`Fat`) shares no word
with the query and is therefore skipped, and its only other segment is the
query word itself. **The guards do not merely fail to catch this; they clear
the field for it.** Then it writes an alias that is never re-checked.

`beef`, `pork` and `goose` were checked the same way and all escalate safely
(`Beef, NFS` 0.556, `Pork, NFS` 0.556, `Fat, goose` 0.600 — all under the
gate). `chicken` is uniquely exposed because `Fat, chicken` is the only rendered
fat whose short description scores over 0.62 against its bare animal name. This
is a one-row problem with a one-line fix and it is the highest-severity result I
found in this domain.

### 3b. `arrowroot` auto-matches the tuber when the food is the starch

Present in the audit's own batch 6 probe block, reported as a clean auto with
no comment — the exact shape of its `brown rice → Flour, rice, brown` finding,
inverted.

```
auto  arrowroot   0.714  Arrowroot, raw
guard harness, search_terms='arrowroot, ground':
   0.714  Arrowroot, raw     SURVIVES     -> AUTO
   0.625  Arrowroot flour    BLOCKED:qualifier

168490 Arrowroot, raw    kcal=65   prot=4.24 carb=13.39   <- the tropical tuber
170684 Arrowroot flour   kcal=357  prot=0.3  carb=88.15   <- what a kitchen means
```

**5.5x on energy, 6.6x on carbohydrate**, and the correct row is disqualified
while the wrong one survives. Nobody logs raw *Maranta* tuber; "arrowroot" in a
recipe is the thickener.

### 3c. `coriander` — the audit found the fenugreek leaf/seed trap and stopped there

```
ask   coriander          0.476  Spices, coriander seed
weak  fresh coriander    0.370  Spices, coriander seed

169997 Coriander (cilantro) leaves, raw  kcal=23   fat=0.52  fib=2.8   Fe=1.77   vitK=310
170922 Spices, coriander seed            kcal=298  fat=17.77 fib=41.9  Fe=16.32  vitK=0
```

**13x energy, 9x iron, 15x fibre**, and in British English `coriander`
unqualified *always* means the leaf. The correct row exists (`cilantro` already
auto-matches at 0.692) but is blocked by `unrequested_qualifier` for the
parenthesised "(cilantro)". `coriander → Coriander (cilantro) leaves, raw` is a
clean high-confidence synonym the audit did not propose, and it is the same
finding as its own `fenugreek leaves → Spices, fenugreek seed`, one batch over.

### 3d. British and Polish entity gaps the audit did not probe

It audited British *dairy* grades and the `chilli`/`chili` spelling and left the
rest of the same vocabulary untested. All of these have exact USDA rows:

```
none  aubergine        -> 169228 Eggplant, raw                          (25 kcal)
none  courgette        -> 169291 Squash, summer, zucchini, incl skin, raw (17 kcal)
none  swede            -> 168454 Rutabagas, raw                         (37 kcal)
none  mangetout        -> snow pea rows exist under "Peas, edible-podded"
none  prawns           -> the shrimp rows
none  gammon           -> the cured-ham rows
none  sultanas         -> the raisin rows
weak  yoghurt   0.357  Yogurt, NFS      <- the same one-character orthography
none  natural yoghurt  -                   finding the audit made for `chilli`
weak  greek yoghurt 0.423 Yogurt, Greek, with oats
weak  cornflour 0.333  Flour, coconut   <- UK cornflour IS 169698 Cornstarch
                                           (381 kcal, 91 g carb); `Flour, coconut`
                                           is 21 g protein and 39 g fibre
none  porcini / kasza manna / smalec / biały ser
```

`yoghurt` is the finding to take seriously: the audit's `chilli` result is
presented as a one-off belonging to the normalisation layer, and it is not one
character in one family — it is the whole British spelling set, and `yoghurt`
is a word this diary will see constantly.

### 3e. `molokhia`, `plaice`, `hake` and `sprats` are `none` with an obvious target unproposed

The audit records these as gaps and proposes nothing. Three of the four have a
row:

```
168419 Jute, potherb, raw    kcal=34 prot=4.65 fat=0.25 Ca=208 Fe=4.76 vitA_RAE=278
```
is molokhia/mulukhiyah exactly, and it is a much better answer than the FNDDS
composite the audit reports (`Bitter melon, horseradish, jute, or radish
leaves, cooked`, 56 kcal / 2.74 g fat — cooked with added fat, Ca 41 against
208, a 5x calcium loss).

```
174196 Fish, flatfish (flounder and sole species), raw   kcal=70 prot=12.41 fat=1.93
```
covers `plaice`, `sole`, `lemon sole` and `dab` — plaice is a flatfish and this
row is the species group. `hake` and `sprat` genuinely have no row: hake is a
lean gadoid and `Fish, cod, Atlantic, raw` is defensible; sprats are brisling
and the sardine row is defensible, with the caveat the audit itself raises
about canned-with-bones calcium.

### 3f. A fourth `Pie,` inversion, and a fish becomes a dessert

```
weak  lemon sole   0.400  Pie, lemon
```

Below the gate, so it escalates — but it joins `Pie, sweet potato`,
`Pie, lemon` (preserved lemon) and `Salmon salad` and shows the shape is not
confined to produce.

## 4. Verdict

48 claims and proposals examined: **33 upheld, 9 downgraded, 6 overturned.**

The audit's core method is sound and its central judgements — refuse a parent
for `fish`, `offal`, `leafy green`, `fresh cheese` and `animal fat`; never use
the `Cheese, paneer` row; never map gochujang, harissa or sambal onto anything
— all survive re-measurement. It is also the only audit in this set that ran the
shipped guards rather than trusting the probe, and that discipline was right.

Where it fails, it fails in three consistent ways.

1. **It ran the guards with the label alone.** Production pools `search_terms`
   into the candidate list and into `asked_for`. That changes three headline
   results: `salmon → Salmon salad` needs `state='cooked'` to fire (and then
   fires *because* `state_conflicts` removes the correct row), `strawberry`
   depends on what the model writes, and `sweet potato` and `brown rice` become
   worse, not better, because the correct rows score *higher* and are thrown out
   by `unrequested_qualifier`.

2. **It got two mechanisms wrong.** `Salmon salad` is not unguarded for want of
   a comma — the `i == 0` branch does inspect the head; it is unguarded because
   `salad` is a `_QUALIFIER_STOP` word, which also falsifies the comment shipped
   beside that stoplist. And the pie family is dangerous not because the guard
   is blind to a dish head but because `label_absent` prefix-stemming fails on
   `-y/-ies`, blocking `Strawberries, raw` while leaving `Pie, strawberry`
   untouched. Both are one-line fixes; the audit's proposed fifth guard is not
   needed for either.

3. **Confidence is inflated on the cheese proposals and one culinary family is
   simply misfiled.** Bresaola is beef and sits in a batch titled "cured pork",
   with `Beef, cured, dried` unproposed four lines above it in its own probe
   output; coppa is a neck collar, not a loin; `Cheese, swiss` is emmental and
   the audit routes emmental to gruyère at 3.8x the sodium.

And it missed the worst case in the domain. **`chicken` auto-matches
`Fat, chicken` at 0.667 and survives every guard with correct `search_terms` and
a correct state**, because the guards disqualify all five real chicken rows and
leave the rendered fat standing: 900 kcal and zero protein per 100 g, cached as
an alias forever. `arrowroot → Arrowroot, raw` (the tuber, 65 kcal, against
`Arrowroot flour` at 357) is the same shape, sitting unremarked in the audit's
own batch 6 probe output.
