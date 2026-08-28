# CRITIQUE-south-america

28 Aug 2026. Adversarial review of `docs/knowledge/AUDIT-south-america.md`.
Read-only throughout: every SQL statement below is a `SELECT`, every probe is
`scripts/probe_knowledge.py`. I did not write the audit and I am not here to
agree with it.

Status: COMPLETE.

## Summary of the review

The audit is honest about its measurements: I re-ran every probe I disputed and
the numbers reproduce **exactly** (`sweet potato` 0.812, `arepa` 0.353,
`palmito` 0.308, `bife de chorizo` 0.500, `feijoada` 0.429, `couve` nothing).
Nothing in it is fabricated, and the domain-shape conclusion — 75% of a South
American vocabulary returns an empty candidate list — stands.

What is wrong is in the **proposals**, not the probes. Two of the
"high confidence — safe to encode automatically" rows are nutritionally worse
than the failure they were written to fix, one is a 36x sodium error, and the
guard analysis is materially incomplete in the audit's own favour.

---

# 1. The guard check

`resolve_items` applies `inverts_meaning`, `state_conflicts`,
`unrequested_qualifier` and `label_absent` to every candidate before an
auto-match. The probe measures `db.search_foods` alone, so a probe verdict of
`auto` is not yet a production defect. I ran the four real guard functions from
`nutrai/llm/parse.py` over every wrong-confident match the audit claims.

| audit claim | probe verdict | guards | reality in production |
|---|---|---|---|
| SA-43 `sweet potato` -> `Pie, sweet potato` 0.812 | auto | **none fire** | **CONFIRMED — auto-matches, alias cached** |
| SA-44 `brown rice` -> `Flour, rice, brown` 0.647 | auto | **none fire** | **CONFIRMED — auto-matches, alias cached** |
| SA-47 `white rice cooked` -> `Rice, white, cooked, glutinous` 0.643 | auto | `unrequested_qualifier` -> "glutinous" | **OVERTURNED — already blocked; escalates to the model tier, which is the system working** |
| SA-25 `bife de chorizo` -> `Chorizo` 0.500 | **ask** | (n/a, below gate) | escalates today; the risk is hypothetical and belongs to a future synonym table |
| SA-35 `arepa` -> `Arepa Dominicana` 0.353 | **weak** | `unrequested_qualifier` -> "Arepa Dominicana" | double-blocked; never an auto |
| SA-49 `palmito` -> `Oil, palm` 0.308 | **weak** | none fire | below the gate; not an auto |
| SA-27 `morcilla` -> `Mortadella` 0.333 | weak | `label_absent` | double-blocked |
| SA-7 `feijoada` -> `Feijoa, raw` 0.429 | weak | `state_conflicts` -> "raw" | double-blocked |
| SA-8 `churrasco` -> `Churros` 0.385 | weak | `label_absent` | double-blocked |
| SA-18 `leche de tigre` -> `Dulce de Leche` 0.450 | ask | `unrequested_qualifier` | escalates |
| SA-45 `collard greens` -> `Poke greens, cooked` 0.375 | weak | `unrequested_qualifier` -> "Poke greens" | double-blocked |
| SA-39 `masa harina` -> `Masa harina, cooked` 0.632 | auto | `state_conflicts` if state=dry | correct row anyway |

**Two claimed autos survive the guards, not three.** `white rice cooked` is
already caught: `Rice, white, cooked, glutinous` has "glutinous" as a later
segment sharing no word with the query, which is exactly what
`unrequested_qualifier` was written for. The audit files it with SA-43 and
SA-44 as the same class; it is not the same class, because the wrong word is in
a *later* segment where the guard can see it. Filing it with them overstates
the residual risk by 50%.

The two that do survive share one property the audit identified correctly and
should have stated as the general rule: **the disqualifying word sits in the
first segment**, which `unrequested_qualifier` deliberately skips. `Pie, sweet
potato` and `Flour, rice, brown` both name a *different food* in segment 0 and
the queried food afterwards. Worth adding: `state_conflicts` cannot help either,
because `_DRY_WORDS = ("dry","dried","dehydrated","powder","powdered")` does not
contain **"flour"** — a `brown rice` item declared `cooked` still does not
conflict with `Flour, rice, brown`. Adding "flour" and "meal" to `_DRY_WORDS`
would close SA-44 on its own, at no cost to `Flour, cassava` (where the query
says flour too).

Also measured, and the audit does not mention it: the guards **over-block** two
of the targets it recommends. `beef tenderloin` -> `Beef, steak, tenderloin` is
blocked by `unrequested_qualifier` on "steak", and `evaporated milk` ->
`Milk, evaporated, whole` on "whole". SA-46's claim that "the short FNDDS rows
behave correctly by contrast" is true of `search_foods` and false of the
resolver. Both escalate rather than resolve — harmless, but the audit's
recommendation to prefer short FNDDS rows is resting on a measurement that does
not survive the guards.

---

# 2. Overturned proposals

All figures below are per 100 g, read from `food_nutrient` with a read-only
`SELECT`, quoted verbatim.

## 2.1 `anchoveta -> 2706232 Fish, anchovy` — **REJECT. A 36x sodium error, filed as "high confidence, safe to encode automatically".**

```
 fdc_id  | description                                  | kcal | prot | fat | na_mg
 2706232 | Fish, anchovy                                |  210 | 28.9 | 9.7 |  3668
  174183 | Fish, anchovy, european, canned in oil, drai |  210 | 28.9 | 9.7 |  3668
  174182 | Fish, anchovy, european, raw                 |  131 | 20.4 | 4.8 |   104
```

`Fish, anchovy` is byte-identical to the **canned-in-oil, salt-cured** row. The
audit's rationale — "*Engraulis ringens*, same genus and oily-pelagic class" —
is a taxonomy argument, and taxonomy is not a cure. Anchoveta in Peru is eaten
**fresh**: grilled, escabechado, in ceviche, and it is the subject of a national
campaign to eat it fresh rather than render it into fishmeal. A 150 g plate of
grilled anchoveta logged against this row reports **5,502 mg of sodium** where
the food carries about 156 — more than twice a daily ceiling, from one item, on
a mapping the audit marks safe to apply with no model consulted.

This is the exact shape the audit itself names in its own Notes: *"USDA tends to
name its processed rows in the source language ... Any synonym written for a
Latin American fruit must pin the raw row explicitly."* It wrote the rule and
then broke it on a fish two tables later.

**Correct target: 174182 `Fish, anchovy, european, raw`**, and only at medium
confidence — the Peruvian anchoveta is a different species from *Engraulis
encrasicolus* and runs oilier. If the intended food is the salted conserva, that
is a second surface (`anchoas`, `anchoveta en conserva`), not the same one.

## 2.2 `palmito -> 167714 Hearts of palm, raw` — **DOWNGRADE. The audit fixed a 44x error with a 4x error.**

```
  167714 | Hearts of palm, raw    | 115 kcal | 2.7 prot | 25.6 carb | 17.2 sugar |  14 mg Na
  168569 | Hearts of palm, canned |  28 kcal | 2.5 prot |  4.6 carb |     (null) | 426 mg Na
```

Palmito is essentially never eaten raw outside a palm plantation. In Brazil,
Argentina, Paraguay and Colombia it arrives **in a jar or a tin**, brined, and
goes into salad, empanadas and torta de palmito. The audit relegates the canned
row to a parenthetical — "Canned form 168569" — and pins the *raw* row as the
high-confidence synonym.

The measured cost of that choice: **4.1x the energy, 5.6x the carbohydrate, and
1/30th the sodium** of the form actually eaten. It is a smaller error than
`Oil, palm` (which the finding correctly kills) but it is the same *kind* of
error, and it is the one being written into the table.

**Correct target: 168569 `Hearts of palm, canned`.** If the raw row is kept at
all it should be behind an explicit `palmito fresco`.

## 2.3 `boniato` in `camote, batata doce, boniato -> 2709697 Sweet potato, NFS` — **SPLIT THE SURFACE. 684 µg RAE of phantom vitamin A.**

```
 2709697 | Sweet potato, NFS | 115 kcal | 17.1 carb | 6.0 sugar | vit A 684 µg RAE
```

`camote` and `batata doce` are fine. **`boniato` is not the same food.** Boniato
(also *batata blanca*, Cuban/Caribbean sweet potato, and the dominant cultivar
in much of the Caribbean coast of Colombia and Venezuela) has **white or
cream flesh and essentially no beta-carotene**. `Sweet potato, NFS` is the
orange-fleshed American cultivar and carries 684 µg RAE per 100 g — roughly 76%
of an adult male RDA. A 250 g portion of boniato logged through this synonym
reports **1,710 µg RAE that the food does not contain**, silently, with no model
consulted.

This is the audit's own `yam is not sweet potato` trap one cultivar further in,
and it is precisely the class of error `/improve` would then act on — a
micronutrient shown as met when it is not.

`boniato` should be a separate surface at **medium** confidence, or an entity
gap. Merging it into the camote row is over-breadth dressed as a synonym.

## 2.4 `mamey, zapote, sapote -> 167760 Sapote, mamey, raw` — **DOWNGRADE. `zapote` and `sapote` are category nouns, not this fruit.**

```
  167760 | Sapote, mamey, raw |  124 kcal | 32.1 carb | 20.1 sugar
  167759 | Sapodilla, raw     |   83 kcal | 20.0 carb
```

"Sapote" names at least four unrelated fruits across this domain: mamey sapote
(*Pouteria sapota*), sapodilla / chicozapote (*Manilkara zapota*), black sapote
(*Diospyros nigra*) and white sapote (*Casimiroa*). In Colombia and Venezuela
`mamey` frequently means *Mammea americana* — the mamey amarillo, a different
genus from *Pouteria* altogether. USDA holds `Sapodilla, raw` separately at
**83 kcal against 124**, a 49% gap in the same table.

Encoding bare `zapote`/`sapote` as a high-confidence synonym for one of them is
the `halloumi -> cheese` failure the brief warns about, with a number attached.
Keep `mamey sapote` and `zapote colorado` at high; drop bare `zapote` and
`sapote` to the model tier, where a competent parse can read the country.

## 2.5 `bife de chorizo -> 2727572 Beef, short loin (NY strip steak), **raw**` — **WRONG STATE, and inconsistent with every other beef row in the same table.**

```
 2727572 | Beef, short loin (NY strip steak), raw | 196 kcal | 21.3 prot | 11.5 fat
  173061 | Beef, loin, top sirloin cap steak, ... cooked, grilled | 242 | 26.0 | 15.0
  173397 | Beef, plate steak, ... outside skirt, ... cooked, grilled | 292 | 27.1 | 20.5
```

Every other beef proposal — picanha, entraña, ojo de bife, asado de tira, bife
de lomo, colita de cuadril — pins a **cooked** row. This one pins raw, with no
note saying why. A bife de chorizo is a grilled steak and the mass a person
states is the cooked mass; `yield_factor` is 1.0 outside the model tier, so the
result is roughly a **25–30% energy understatement** on the single most commonly
eaten item in Argentine cuisine.

CLAUDE.md already records this as a golden case (`near_chicken_thigh_cooked`:
"a cooked mass must not land on a raw row at `yield_factor` 1.0"). The proposal
reintroduces it.

## 2.6 The linguiça rejection is justified by a figure that is false

The `Deliberately rejected` table says of `linguiça -> Chorizo`: *"Chorizo is
pimentón-heavy and often markedly fattier."* Measured:

```
 2706179 | Chorizo                            | 341 kcal | 19.3 prot | 28.1 fat | 983 mg Na
  174584 | Sausage, smoked link sausage, pork | 309 kcal | 12.0 prot | 28.2 fat | 827 mg Na
```

**Fat is 28.1 against 28.2 — identical to within a rounding error.** The chosen
target is *less* protein-dense by 38%. The rejection may still be right on cure
and paprika grounds, but in a document whose whole authority rests on quoting
measurements, this one rejection was decided on an assumption and stated as a
fact. Worth noting too that `linguiça calabresa` — a paprika-cured, smoked pork
sausage — is closer to `Chorizo` than to a plain smoked link, and the audit
folds it into the same row as fresh linguiça.

---

# 3. Confidence inflation and downgrades

## 3.1 `mollejas -> 2706158 Sweetbreads` — **HIGH is not defensible. The database holds two "sweetbreads" that differ by 2.6x in energy and 10x in fat, and the audit picked the one that resolves, not the one that is right.**

```
 2706158 | Sweetbreads (FNDDS)                            | 124 kcal | 22.5 prot |  3.1 fat
  173092 | Beef, NZ, imported, sweetbread, cooked, boiled | 318 kcal | 12.5 prot | 29.8 fat
  173093 | Beef, NZ, imported, sweetbread, raw            | 303 kcal | 11.5 prot | 28.6 fat
 2706165 | Gizzard (FNDDS)                                | 153 kcal | 30.1 prot |  2.7 fat
```

Argentine mollejas are thymus, grilled over coals until the fat renders and
crisps. Every SR Legacy sweetbread row in this database sits at **~300 kcal and
~29 g of fat**; the FNDDS row the audit pins sits at 124 and 3.1 — a figure much
closer to **gizzard** than to any other sweetbread row here. The stated
rationale is *"sweetbreads auto-matches this at 1.000"*, which selects on
resolvability rather than on the number. That is the wrong criterion, and it is
the one criterion the audit's own SA-46 argues against.

Second, `mollejas` is not unambiguous across this domain. In Peru, Colombia and
Ecuador `mollejas` / `mollejitas` routinely means **chicken gizzards** —
anticuchos de molleja, mollejitas fritas — a different organ from a different
animal. A word that means one thing in Buenos Aires and another in Lima is
**medium** by the brief's own standard: not "beyond dispute by a competent
cook".

## 3.2 `mandioca, aipim, macaxeira, manioc -> 169985 Cassava, raw` — **wrong row, and `Cassava, cooked` exists.**

```
  169985 | Cassava, raw    | 160 kcal | 0.3 fat |  14 mg Na
 2709564 | Cassava, cooked | 191 kcal | 3.0 fat | 145 mg Na
 2709565 | Yuca fries      | 269 kcal | 13.9 fat
```

Cassava is **cyanogenic and cannot be eaten raw**. Mandioca cozida, aipim
frito, yuca a la huancaína, casabe — every form is cooked. The audit did not
report `Cassava, cooked` (2709564) and did not say why it preferred raw.

This one also exposes a structural defect in the proposal set as a whole. Six of
the thirty-four high-confidence targets are **`, raw` rows for foods nobody eats
raw**: cassava, collards (couve), hearts of palm (palmito), plus the raw NY
strip of §2.5. I ran the real `state_conflicts` from `nutrai/llm/parse.py`:

```
cassava        state=cooked  vs  Cassava, raw          -> BLOCKED ("raw")
collards       state=cooked  vs  Collards, raw         -> BLOCKED ("raw")
plantain       state=cooked  vs  Plantain, raw         -> BLOCKED ("raw")
```

**A synonym table that resolves ahead of the guards would install precisely the
matches the resolver's own guard refuses.** That is not a detail: `state_conflicts`
exists because "egg white, fried" took `Egg, white, dried`. Whatever mechanism
carries these synonyms has to be *subject* to the guards, not upstream of them —
and if it is subject to them, half these entries never fire. The audit does not
address where in `resolve_items` the table plugs in, and the answer changes
which rows are correct.

For couve the cost is small (`Collards, raw` 32 kcal / 251 µg RAE vs cooked 33 /
380 — vitamin A 51% low). For cassava it is 19% energy and a tenth of the
sodium. For palmito it is §2.2's 4x.

## 3.3 `chicharrón -> 2705895 Pork, cracklings` — **variant-dependent; medium.**

`Pork, cracklings` is 569 kcal, 45.0 g protein, 41.7 g fat, **1,289 mg sodium**.
The audit's choice over `Pork skin rinds` is well argued and I agree with it for
the *Colombian* chicharrón. But `chicharrón` is not one food across this domain:

- Peru: `chicharrón de chancho` is boiled-then-fried pork belly chunks, served
  with camote and salsa criolla — and `chicharrón de pescado` / `de calamar`
  are **fried fish and fried squid**, sold under the same word on the same menu.
- Bolivia: boiled in its own fat, closer to confit.
- Venezuela / Colombia coast: the crackling-with-meat the target describes.

A high-confidence synonym that turns `chicharrón de pescado` into 41.7 g of pork
fat is the `bife de chorizo` trap the audit itself flags, in a word it marked
safe. Medium, with `chicharrón de pescado` and `de calamar` as separate surfaces.

## 3.4 `ají amarillo, ají limo, rocoto -> 169395 Peppers, serrano, raw` — the stated limit is false for rocoto

The rationale reads *"Used in gram quantities."* **Rocoto is not.** `Rocoto
relleno` is a whole stuffed pepper — 100–150 g of fruit per serving, the
centrepiece of the dish. The limit that makes the fallback tolerable for ají
amarillo paste does not hold for the one member of the group eaten as a
vegetable. Split rocoto out.

## 3.5 `ají panca -> 168570 Peppers, hot chile, sun-dried` — right class, wrong mass basis

```
  168570 | Peppers, hot chile, sun-dried | 324 kcal | 69.9 carb | 41.1 sugar | 1324 µg RAE
```

Ají panca is bought and used as **pasta de ají panca**, a rehydrated paste. A
person stating "2 tablespoons of ají panca" is stating a wet mass against a
dried row: roughly **3–4x the energy and 4x the vitamin A**. Since the recorded
quantity is small the absolute error is bounded, but the rationale should say
"dried, whole" and the paste should be a distinct surface.

## 3.6 `merkén -> 171329 Spices, paprika` — sodium is the missing half

```
  171329 | Spices, paprika | 282 kcal | 68 mg Na | 2463 µg RAE | 21.1 mg Fe
```

Merkén is **salted**: smoked ají cacho de cabra, toasted coriander seed and salt,
commonly 10–25% salt by weight. Paprika carries 68 mg of sodium per 100 g. At a
realistic 3 g dose the mapping silently omits **300–750 mg of sodium** — a
quarter to a third of a daily ceiling, on a "medium confidence" fallback whose
rationale mentions coriander seed and not salt.

## 3.7 `asado de tira -> 171222` — boneless row, bone-in cut, and braised for a grilled food

```
  171222 | Beef, chuck, short ribs, boneless, ... cooked, braised | 305 kcal | 22.6 fat
```

Two problems the rationale ("cross-cut short rib") does not mention. Asado de
tira is cut across the **plate/rib** bones and is bought, cooked and served
**bone-in** — bone is roughly 25–35% of the stated mass — so a boneless row
against a stated plate weight overstates energy by about a third. And it is
grilled, not braised; braising renders fat into the liquid and is discarded,
which is the opposite of what happens over coals. Medium, not high.

## 3.8 `matambre` and `carne de sol` are folded into rows that do not fit them

- `matambre -> 168733 Beef, flank steak` (192 kcal, **8.2 g fat**). Matambre is
  the fat-laced sheet between hide and ribs; flank is one of the leanest cuts on
  the animal. The fallback understates fat in the direction that matters.
- `carne seca, charque, **carne de sol** -> 2705858 Beef, dried, chipped,
  uncooked` (153 kcal, 31.1 prot, **1.9 g fat**, 2,790 mg Na). Carne de sol is a
  *light* 24–48 h cure, sold moist, fried in fat before eating; charque is a
  hard salt cure. Folding both into one row is over-breadth in the same cell,
  and 1.9 g of fat is wrong for Brazilian charque, which is made from fatty
  cuts and is visibly marbled.

## 3.9 A measured slip

The maduros row says *"sugar differs ~3x from green"*. Measured: `Plantains,
green, fried` **3.6 g** sugar, `Plantains, yellow, fried` **21.8 g**. That is
**6x**, not 3x. The mapping is right; the number quoted beside it is not.

## 3.10 Credit where due

The rejections are the strongest part of the document and I could not break any
of them. I re-measured five and they are exact: hominy 1.4 g protein vs sweet
corn 3.4; corn nuts 446 kcal / 15.6 g fat; molasses 290 kcal / 4.7 mg Fe vs
turbinado 399 / 0.4; `Corn flour, masa, enriched` **138 mg calcium** against
masarepa's zero; pork skin rinds 61.3/31.3 vs cracklings 45.0/41.7. The
`sopaipilla`, `tuna (fruit)` homograph and `queso`-as-category-noun rejections
are all correct and well reasoned.

---

# 4. What the audit missed

## 4.1 `avocado -> Oil, avocado` — **a third surviving auto-match of the SA-43 shape, and worse than SA-43 because it is decided by a tie-break**

```
avocado -> auto
    0.667 Oil, avocado          <- taken. precedence 2 (sr_legacy)
    0.667 Avocado, raw          <- the right row. precedence 3 (fndds). SAME SIMILARITY.
    0.471 Avocado dressing
palta   -> none
```

```
  173573 | Oil, avocado | 884 kcal |  0.0 prot | 100.0 fat
 2709223 | Avocado, raw | 160 kcal |  2.0 prot |  14.7 fat
```

Guard check, with the real functions: `label_absent` passes ("avocado" is in the
description), `unrequested_qualifier` passes (the wrong word "Oil" is in
segment 0, which the guard skips), `state_conflicts` passes. **It survives all
three and auto-matches.**

`palta` — the word used in Peru, Chile, Bolivia, Argentina and Uruguay — returns
**nothing**, so the English fallback is exactly what a South American user
types. Avocado is not incidental here: it is causa limeña, palta reina, palta a
la jardinera, and the standard garnish on ajiaco. A 150 g palta logged this way
reports **1,326 kcal instead of 240**, silently, with the alias cached forever.

The mechanism is worse than SA-43's. Sweet potato at least loses by 0.047.
Avocado is a **dead tie at 0.667** broken by `precedence` — and CLAUDE.md's own
note says precedence "never decides anything ... only to break an exact tie in
a float, which does not occur". It occurs here, and it decides for the oil.

## 4.2 `pumpkin -> Pie, pumpkin` — **a fourth, and the largest multiple in the domain**

```
pumpkin  -> auto
    0.727 Pie, pumpkin
    0.667 Pumpkin, raw
    0.615 Soup, pumpkin
zapallo  -> none
auyama   -> none
```

```
 2708011 | Pie, pumpkin    | 249 kcal | 9.8 fat | 24.6 sugar | 252 mg Na
 2709692 | Pumpkin, cooked |  52 kcal | 2.8 fat |  2.9 sugar | 131 mg Na
```

Survives all three guards, same first-segment shape. **4.8x energy, 8.5x sugar.**
`zapallo` (Argentina, Chile, Peru, Uruguay) and `auyama` (Colombia, Venezuela)
both return nothing, and zapallo is load-bearing in this domain — locro, sopa
paraguaya, charquicán, cazuela, mazamorra — so again the English fallback is the
realistic input.

The audit found `Pie, sweet potato` and stated the general rule ("the wrong word
sits in the first segment"), then did not apply it. Searching for `Pie, %` and
`Oil, %` rows whose second segment is a plain vegetable is a five-minute query
and it would have found both of these.

## 4.3 `culantro -> Cilantro, raw` — the perilla/shiso trap of this domain, untested

```
weak  culantro    0.375  Cilantro, raw
auto  cilantro    0.692  Cilantro, raw
```

Culantro (*Eryngium foetidum*) — recao, sacha culantro, chillangua, chicoria —
is a **different genus and family** from cilantro (*Coriandrum sativum*). It is
the standard herb of the Colombian and Venezuelan coast and of Amazonian
Ecuador and Peru. It is weak today, so it escalates and no harm is done, but it
is exactly the class of pair a synonym table would collapse, and the audit never
tested it.

## 4.4 Four obvious synonyms for targets the audit already chose, and never probed

```
none  arequipe          -   (nothing)      target already chosen: 173461 Dulce de Leche
none  manjar            -   (nothing)                 "
none  manjar blanco     -   (nothing)                 "
weak  bocadillo       0.333  Armadillo      target already chosen: 2710307 Guava paste
none  bocadillo veleno  -   (nothing)                 "
none  castanha do para  -   (nothing)      target: 2707492 Brazil nuts
```

The audit proposed `doce de leite -> Dulce de Leche` and `goiabada -> Guava
paste`, then stopped at the Portuguese. **`arequipe`** (Colombia, Venezuela) and
**`manjar` / `manjar blanco`** (Chile, Peru, Ecuador) are the Spanish-American
names for the identical food and cost nothing to add. **`bocadillo` /
`bocadillo veleño`** is the Colombian guava paste — the same product as
goiabada, eaten daily with queso — and it currently reaches `Armadillo`.

`castanha do pará` is the more serious omission. Brazil nuts carry **1,917 µg of
selenium per 100 g** — by a wide margin the most extreme micronutrient figure in
this database, and a 30 g handful is ~575 µg, above the 400 µg tolerable upper
limit. A Brazilian food vocabulary that cannot reach it is missing the one entry
where the gap can breach a ceiling rather than merely miss a target. `brazil
nut` resolves at 0.769; only the Portuguese name is unreachable.

## 4.5 Staples with zero recall that the audit's dish list implies but never probed

```
none  panceta            none  papa amarilla      none  mote
none  zapallo            none  papa criolla       none  arracacha
none  auyama             none  name (ñame)        none  chontaduro
none  guayaba            none  achiote / urucum   none  pitahaya
none  camu camu          none  tomate de arbol    none  curuba
weak  tamarillo  0.462 Tamarind
weak  granadilla 0.314 Passion-fruit, (granadilla), purple, raw
weak  tapioca    0.444 Tapioca, pearl, dry
```

Three of these carry a trap the audit's method was designed to catch:

- **`panceta` is not pancetta.** Argentine and Uruguayan panceta is a smoked,
  sliced bacon; Italian pancetta is unsmoked salt-cured belly. Zero recall today,
  so the danger is entirely in what a synonym writer does with it.
- **`ñame` is not sweet potato.** The brief's own named trap, live in this
  domain: ñame is a Caribbean-coast staple in Colombia and Venezuela (sancocho,
  mote de queso). `Yam, raw` (118 kcal, 0.5 g sugar, 7 µg RAE) against `Sweet
  potato, NFS` (115 kcal, 6.0 g sugar, **684 µg RAE**) — near-identical energy
  and a 98x vitamin A difference, which is why the two must never merge. `yam`
  itself resolves at 0.500 (`ask`), so the target is reachable and only the
  Spanish surface is missing.
- **`tapioca` in Brazil is a crepe** made from polvilho (cassava starch), not
  the pearls. `Tapioca, pearl, dry` at 0.444 is the wrong food in the wrong
  state. `polvilho` and `cassava starch` both fail too (`cassava starch` reaches
  `Cassava, raw` at 0.421 — 160 kcal against a ~350 kcal pure starch).

And one naming trap inside a proposal the audit made: it proposes `maracujá,
maracuya -> 2709248 Passion fruit, raw`, correctly. But USDA also holds
`Passion-fruit, (granadilla), purple, raw` — and **granadilla
(*Passiflora ligularis*) is a different species from maracuyá (*P. edulis*)**,
sweeter and far less acid. USDA's row uses "granadilla" as a synonym for purple
passion fruit, which is the Andean usage inverted. Anyone writing `granadilla`
into the table from that row description will encode the wrong fruit.

## 4.6 An inconsistency in the audit's own rejection of dish mappings

The rejection table refuses *"feijoada, moqueca, ajiaco, sancocho, bandeja paisa
and every other composite dish"* on principle — "these are dishes ... the model
tier exists for exactly this". But:

```
auto  empanada   0.692  Empanada, NFS      -> survives all three guards
```

`Empanada, NFS` (291 kcal, 16.0 g fat, 446 mg Na) already auto-matches and
already caches an alias, and it stands for the baked Argentine beef empanada,
the deep-fried Chilean empanada de pino and the fried-corn Colombian empanada
alike — a range of roughly 2x in fat. The audit's principle is right; it just
never checked whether the resolver was already violating it. If composite
dishes must go to the model tier, `Empanada, NFS` is a live counter-example
that needs a note, not silence.

## 4.7 A framing error worth correcting

SA-7 files `feijoada -> Feijoa, raw` as "BAD FUZZY MATCHING". The match is bad,
but the row is not a foreign object:

```
auto  feijoa   0.636  Feijoa, raw     (168176 | 61 kcal | 15.2 carb | 8.2 sugar)
```

**Feijoa (*Acca sellowiana*) is a South American fruit** — goiaba-serrana in
Brazil, guayabo del país in Uruguay, where it is a national emblem, and native
to the Uruguay/Rio Grande do Sul highlands. It belongs *in* this domain's
vocabulary, resolves correctly at 0.636, and should have been listed as a
working case rather than only as feijoada's unlucky neighbour.

---

# 5. Verdict

The audit's measurements are sound and reproduce exactly. Its structural
conclusions — 75% zero recall, reachability rather than entity gaps, length
dilution, diacritics as total loss, fdc_id targets rather than strings — all
stand and are the most useful thing in the document.

Its **proposals** are where it stops being careful, and the failure has one
shape: *having established that the processed row outranks the plain row, it
then picked processed and non-eaten rows for its own targets.* `Fish, anchovy`
is the canned salt-cure. `Hearts of palm, raw` is the form nobody eats.
`Cassava, raw` is inedible. `Beef, short loin, raw` is not what a bife de
chorizo is. Four of thirty-four high-confidence entries, plus `boniato`'s 684 µg
of phantom vitamin A, plus a `zapote` that names four fruits.

The guard analysis is incomplete in the audit's own favour: it reports three
surviving wrong-confident autos and there are two, because `unrequested_qualifier`
already blocks the glutinous-rice case. But the *count* of the class is worse
than reported, not better — `avocado` and `pumpkin` are two more of the exact
first-segment shape SA-43 describes, and both survive every guard.

Concrete next actions, in order of expected harm avoided:

1. Repoint or reject `anchoveta` (3,668 mg Na), `palmito` (4.1x), `boniato`
   (684 µg RAE), `bife de chorizo` (raw), `mandioca` (raw, cooked row exists).
2. Add `avocado` and `pumpkin` to SA-43/SA-44 as confirmed surviving autos.
   Sweep the whole `food` table for `Pie, %` / `Oil, %` / `Flour, %` rows whose
   later segment is a plain food name — that query defines the class.
3. Add "flour" and "meal" to `_DRY_WORDS` in `nutrai/llm/parse.py`; it closes
   SA-44 outright at no cost to `Flour, cassava`.
4. Decide where a synonym table sits relative to the three guards before writing
   one. Six of the proposed high-confidence targets are `, raw` rows that
   `state_conflicts` would itself refuse for the state the food is eaten in.
5. Free additions the audit's own targets already support: `arequipe`,
   `manjar`, `manjar blanco`, `bocadillo`, `castanha do pará`.
