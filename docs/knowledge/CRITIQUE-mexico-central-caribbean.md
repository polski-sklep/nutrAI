# CRITIQUE-mexico-central-caribbean

28 Aug 2026. Critic pass over `AUDIT-mexico-central-caribbean.md`. Every claim
below was re-probed or re-read against `nutrai/llm/parse.py` and the live
`food` table (SELECT only). Findings are appended as they are established.

_Work in progress — appended in batches._

## C1 — The method the audit calls "conservative" is not, and four of its eleven escalations are wrong

This is the biggest correction in the file, and it is about the audit's own
correction to the brief.

The audit's Notes say it re-ran terms through a scratchpad mirroring the
selector with **`asked_for` set to the label alone**, and defends that as
conservative: *"the model's `search_terms` can only add words to the query, and
every guard here turns on words the query lacks, so including them could only
make more candidates survive, never fewer."*

Production sets `asked_for = f"{label} {it.get('search_terms') or ''}"`
(`nutrai/llm/parse.py:686`). "More candidates survive" is precisely the
problem: the audit's list of eleven **escalations** is a list of cases where a
guard blocked *every* candidate. Add the words back and several stop being
blocked — so the audit's headline claim ("six were false alarms", "eleven
escalations") is measured under an assumption that makes escalation *more*
likely, not less. Re-run through `_candidates` with the same `asked_for`
production uses, and realistic `search_terms` for each dish:

```
== 'cotija cheese'  search_terms='cheese, cotija, aged, hard, solid'
  0.684  Cheese, cotija, solid                          [foun] OK
  => AUTO -> Cheese, cotija, solid

== 'bacalaitos'  search_terms='bacalaitos fritos, salt cod fritters, fried'
  0.733  Bacalaitos fritos                              [surv] OK
  => AUTO -> Bacalaitos fritos

== 'sour cream'  search_terms='sour cream, cultured, full fat'
  0.704  Cream, sour, full fat                          [foun] OK
  0.647  Sour cream, light                              [sr_l] qual:light
  => AUTO -> Cream, sour, full fat

== 'pumpkin seed'  search_terms='pumpkin seeds, hulled, raw, pepitas'
  0.781  Seeds, pumpkin seeds (pepitas), raw            [foun] OK
  0.650  Pumpkin seeds, salted                          [surv] qual:salted
  => AUTO -> Seeds, pumpkin seeds (pepitas), raw

== 'chimichanga'  search_terms='chimichanga, meat, fried, beef'
  0.706  Chimichanga, meat                              [surv] OK
  => AUTO -> Chimichanga, meat
```

Four of the audit's eleven escalations are not escalations in production, and
in every one of the four the auto-match lands on the **right** row. That
overturns three separate claims:

- **The "cost of the guards" is overstated.** §B2-8 and §B3-2 present
  `cotija cheese` and `bacalaitos` as correct rows lost to a model call — "a
  fee paid on every Foundation cheese". They are not lost. The model supplies
  the word the guard wanted and the match goes through free.
- **§B2-9 is wrong on its own terms.** It says of `sour cream` that
  "`Sour cream, regular` — the right row — is not even on the first page". With
  `search_terms`, `Cream, sour, full fat` (Foundation) leads at 0.704 and is
  taken. The candidate list is not a fixed object; it is a function of the
  query, and the audit measured it under one query only.
- **§B2-11's pepita complaint is answered by the same mechanism.** The audit
  files `pepita` 0.231 / `pepitas` 0.320 as a length-penalty failure "against
  the row that literally contains the word". Under the production query that
  row scores **0.781** and auto-matches. `pepita` is a term the model rewrites,
  which is `B4-3`'s own thesis — the audit stops applying it one section early.

The claim of monotonicity is also false as stated. `unrequested_qualifier`'s
`i == 0` branch fires on `(words & q) and extra`: adding words to `q` can make
`words & q` non-empty where it was empty, and *newly block* a head segment.
Measured on a domain term the audit chose not to guard-check:

```
== 'elote'  search_terms=''                       => ESCALATES (no candidates)
== 'elote'  search_terms='corn on the cob, boiled, with butter'
  0.358  Corn, canned, cooked with butter or margarine   qual:canned,label_absent
  0.352  Corn, fresh, cooked with butter or margarine    qual:fresh,label_absent
  => ESCALATES to model tier
```

Every `Corn, <pack>, cooked with butter` row is blocked on a head-adjacent
qualifier that only exists because "corn" entered `q` from `search_terms`. The
direction is not one-way; it is query-dependent, which is the honest statement.

**What survives unharmed:** the audit's five claimed *reorders* (`quesadilla`,
`burrito`, `butter`, `tamale`, `jalapeno pepper`) all replicate exactly under
the faithful selector, and `taquito`, `oaxaca cheese`, `panela cheese`,
`jerk pork` and `tomato` still escalate with `search_terms` supplied. The
audit's central methodological point — that a probe `auto` is not a production
auto — is correct and well made. Its arithmetic is what does not hold.

## C2 — F1 is worse than the audit says, and the audit under-argues it

Confirmed and strengthened. `Form, food` auto-matches survive `search_terms`
too, which the audit never tested:

```
== 'chicken'  search_terms='chicken, breast, roasted, skinless'
  0.667  Fat, chicken                                   [sr_l] OK
  0.641  Chicken, breast, boneless, skinless, raw       [foun] qual:boneless
  => AUTO -> Fat, chicken
```

A model that does its job perfectly — rewrites "pollo" into
`chicken, breast, roasted, skinless` — puts the correct Foundation row on the
list at 0.641, and `unrequested_qualifier` blocks it on the word *boneless*
while waving `Fat, chicken` through. The guard is not merely blind to the form
word; here it actively removes the only competitor. §B5-1 reports this row as
"no generic row at all", which is true of `Chicken, NFS` and not of the
candidate list a real parse produces.

## C3 — F3 is contradicted by a line in the audit's own probe output

**F3: "USDA never writes the word *chile*"** and **"only ancho, pasilla,
serrano and jalapeño have rows at all"**. Both are false, and the first is
refuted by a line the audit itself printed in §B2-3:

```
weak  dried chile                        0.429  Peppers, hot chile, sun-dried
```

`Peppers, hot chile, sun-dried` (168570) contains the literal word *chile*. So
does `Sauce, hot chile, sriracha`. The audit repeats the claim twice (§B2-3 and
F3) with its own counterexample three lines above it.

The second half matters more, because it drives the audit's blanket rejection
("Any neighbour for … no fallback whose numbers I can defend"). The varieties
are absent; adequate **category** rows are not:

```
   168570 | sr_l | Peppers, hot chile, sun-dried   kcal 324  fat 5.81  carb 69.86  fibre 28.7  K 1870
   169396 | sr_l | Peppers, ancho, dried           kcal 281  fat 8.2   carb 51.42  fibre 21.6  K 2411
   168579 | sr_l | Peppers, pasilla, dried         kcal 345  fat 15.85 carb 51.13  fibre 26.8  K 2222
   170106 | sr_l | Peppers, hot chili, red, raw    kcal 40   fat 0.44  carb 8.81   fibre 1.5
   170497 | sr_l | Peppers, hot chili, green, raw  kcal 40   fat 0.2   carb 9.46   fibre 1.5
  2709798 | surv | Peppers, hot, raw               kcal 34   fat 0.4   carb 7.66   fibre 2.2
```

`Peppers, hot chile, sun-dried` at 324 kcal sits **between** the two named
dried chiles the audit accepts (281 and 345) — a ±15% band on a food used at
5–20 g in a mole or an adobo, i.e. under 5 kcal of error. For guajillo, árbol,
cascabel, morita and mulato — all dried — it is a defensible target by exactly
the standard the audit applied to `poblano` (which it rejected, correctly, at
14x). For habanero and scotch bonnet, `Peppers, hot, raw` at 34 kcal is
likewise within noise. The audit rejects the chile fallbacks and the
`poblano → ancho` fallback in the same breath, when the measurements it took
separate them cleanly by two orders of magnitude of error.

Reachability, not coverage, is the finding here, and it is already stated
better one section up (F2). F3 as written overstates the gap.

```
ask   dried chili pepper                 0.516  Peppers, hot chile, sun-dried
weak  guajillo dried chile               0.324  Peppers, hot chile, sun-dried
weak  chile de arbol dried               0.333  Peppers, hot chile, sun-dried
```

The category row is retrieved by every one of those queries. It is below the
gate, so the model tier decides — which is the system working, and the audit
should have counted it as such rather than as "the model tier is being handed a
list on which the right food does not appear" (§B2-3). It appears.

## C4 — The audit never probed `chorizo`, the domain's canonical trap, and it is a 1.000 auto-match

The brief names it: *Spanish and Mexican chorizo are different foods*. The word
appears nowhere in 416 probes.

```
== 'chorizo'  state=None
  1.000  Chorizo                                          [surv] OK
  0.200  Sausage, pork, chorizo, link or ground, raw      [sr_l] below_gate,qual:pork
  => AUTO -> Chorizo
```

```
  2706179 | surv | Chorizo                                       kcal 341  fat 28.1  prot 19.3  Na 983  chol 107
   746781 | foun | Sausage, pork, chorizo, ... cooked, pan-fried  kcal 346  fat 28.1  prot 19.3  Na 983  chol 107
   173859 | sr_l | Sausage, pork, chorizo, link or ground, raw    kcal 296  fat 25.1  prot 13.63 Na 788  chol 63
```

FNDDS `Chorizo` is nutritionally identical to the *pan-fried* Foundation row,
so USDA's bare `Chorizo` is **Mexican fresh chorizo, cooked**. For this domain
that is the right default and the auto-match is defensible — but the audit
should have said so, because two things follow that it did not measure:

- **Spanish cured chorizo has no row and cannot escalate to one.**
  `spanish chorizo` escalates with `Chorizo` (0.500) as the only real
  candidate; the cured sausage is ~455 kcal per 100 g against 341, a 33%
  understatement, and it is eaten cold in slices where the Mexican one is
  cooked out of a casing. A model handed that list has nothing correct to pick.
- **The auto-match writes an alias for the bare word `chorizo` forever**, and
  no command repoints one (CLAUDE.md). The first Spanish chorizo logged as
  "chorizo" fixes the wrong row for every later one.

```
== 'mexican chorizo'  search_terms='chorizo, pork sausage, fresh, cooked'
  0.619  Sausage, pork and beef, fresh, cooked   below_gate,label_absent
  => ESCALATES
```

Naming the country correctly makes it *unreachable* — F2's shape, on the one
term in the domain where the two readings differ by a third of the energy.

## C5 — Three "entity gaps" that are not gaps: the row exists under another name

§B3-4 and F5 list foods with "no row, no neighbour". Three of them have rows.

**`malanga`** — declared absent. `Yautia (tannier), raw` (169401) is malanga,
under its Puerto Rican name:

```
   169401 | sr_l | Yautia (tannier), raw   kcal 98  prot 1.46  fat 0.4  carb 23.63  fibre 1.5  K 598
weak  yautia                             0.368  Yautia (tannier), raw
```

The audit put `malanga` in the "no row anywhere in `food`" list on the strength
of a regex scan that searched for `malanga` — the word USDA does not use. That
is the same reachability error the audit spends the rest of the file
documenting, committed by its own method. Note `Taro, raw` is **not** the
substitute: taro is *Colocasia*, malanga/yautía is *Xanthosoma*, and the taro
row is 112 kcal against 98 with a different mineral profile.

**`casabe`** — never probed; `bammy` was, and returned nothing, from which
§B3-4 concludes cassava bread is absent. It is not:

```
weak  casabe                             0.389  Casabe, cassava bread
== 'casabe'  search_terms='casabe, cassava bread, flatbread'
  0.750  Casabe, cassava bread   [surv] OK    => AUTO -> Casabe, cassava bread
auto  cassava bread                      0.778  Casabe, cassava bread
```

`Casabe, cassava bread` (2709566) is 299 kcal, 71 g carbohydrate and **1,185 mg
sodium** per 100 g — the second-most sodium-dense staple in this domain after
salt cod, and the audit does not know it exists.

**`gandules`** — listed as an entity gap in the F6 table. `Pigeon peas (red
gram), mature seeds, cooked, boiled` exists; the word `gandules` does not reach
it (0.333, `label_absent`), which is a synonym failure, not an absence.

## C6 — `panela` is not only a cheese

§B2-8 treats `panela` as a Mexican cheese without qualification, and F-level
readers will take the mapping from it. Across Colombia, Venezuela, Central
America and much of the Caribbean, **panela is unrefined whole-cane sugar** —
the same product the audit lists separately as `piloncillo` (`none`). Both
readings are in this domain's countries. In practice nothing breaks today:

```
none  panela                             -      (nothing)
none  piloncillo                         -      (nothing)
weak  panela sugar                       0.353  Sugar, NFS
```

so the correction is to the write-up, not to a live defect. But it is exactly
the `bresaola-is-beef` shape the brief warns about, and if anyone encodes
`panela → Cheese, …` from §B2-8 it becomes a ~380 kcal/100 g error in the wrong
direction (sugar ~380 vs fresh cheese ~300, with fat and protein inverted) for
every Central American who types it.

## C7 — Culinary/etymological errors in the reasoning

- **§B3-1: "*jerk* is from Taíno *charqui*… *jerk* and *jerky* are unrelated
  words."** Wrong twice. *Charqui* is **Quechua** (*ch'arki*), not Taíno — the
  Taíno loan in this sentence's vicinity is *barbacoa*. And English *jerky* and
  Jamaican *jerk* are standardly traced to that same Spanish *charqui* /
  *charquear*, so they are cognates, not unrelated. The **conclusion is right**
  — `Pork jerky` (412 kcal, 1,810 mg Na) is not jerk pork — but it is right
  because they are different *preparations*, not because the words are
  unrelated. A knowledge doc that will be read as a reference should not carry
  the false etymology as its justification.

- **§B2-11: `annatto` and `Natto` are "one letter apart".** Two ("an").
  Cosmetic, but it is presented as a measurement.

- **§B3-5: `ackee and saltfish -> Fish, mackerel, salted` — "Both halves are
  wrong".** The saltfish half is not wrong in kind: salted mackerel is a salted
  cured fish, and `Fish, mackerel, salted` is 305 kcal / 4,450 mg Na against
  salt cod's 290 / 7,027. Wrong species, right food class, and about 60% of the
  sodium — which is a much milder failure than "both halves are wrong" implies,
  and the audit gives the salt-cod numbers itself two sections later.

- **§B2-4 omits that `mulato` is also a dried poblano** (a different cultivar
  of the same fruit), while listing it as an unrelated missing chile. Minor,
  but it is the one place the audit's own `poblano ≡ ancho` reasoning would
  have extended.

## C8 — A new F1 instance the audit missed, and it is the worst one

The audit's §B5-1 is right that `chicken` has no generic row. It stops there.
Give the model tier its own correct rewrite and the guard actively removes the
right answer:

```
== 'roast chicken'  search_terms='chicken, roasted, meat and skin'
  0.769  Chicken, roasting, meat and skin, cooked, roasted  [sr_l] qual:roasting
  0.732  Chicken, capons, meat and skin, cooked, roasted    [sr_l] qual:capons
  0.650  Chicken, chicken roll, roasted                     [surv] OK
  => AUTO -> Chicken, chicken roll, roasted
```

```
  2706087 | surv | Chicken, chicken roll, roasted   kcal 164  fat 6.33  prot 26.68  Na 499
```

`Chicken, roasting, …` is the *right row*, leads the list at 0.769, and is
disqualified because `roasting` is a noun (a class of bird) that
`unrequested_qualifier` reads as a narrowing word. What survives is a
**pressed deli roll**: 499 mg sodium against roughly 80 for roast chicken, on a
word that `pollo asado`, `pernil de pollo` and `jerk chicken` all rewrite to.
Same defect as C2's `qual:boneless` — the guard is not merely blind to the
wrong row, it clears the field for it.

## C9 — F7 (salt cod) is overstated once the model tier is in the picture

The audit says only "the fullest English phrasing, which nobody says, gets into
the `ask` band". It never probed **`bacalao`**, the word actually used in
Puerto Rico, Cuba and the Dominican Republic:

```
== 'bacalao'  search_terms='salt cod, dried salted codfish'
  0.528  Fish, cod, Atlantic, dried and salted  [sr_l] below_gate,qual:Atlantic,label_absent
  => ESCALATES to model tier
```

The correct 7,027 mg-sodium row leads the candidate list. It escalates — which
is the system working — so F7's "the row in the domain where being unreachable
costs the most" is true of the *auto* path and false of the path this food
actually takes. Downgrade, not overturn: `saltfish -> Fish sauce` stands.

## C10 — F1's proposed remedy would break the audit's own correct matches

F1 says the fix is "a fifth guard or an extension of `unrequested_qualifier`
over a closed set of form words", and §B5 names fourteen: `Oil`, `Fat`,
`Flour`, `Tea`, `Syrup`, `Juice`, `Seeds`, `Spices`, `Nuts`, `Fish oil`,
`Vegetable oil`, `Candies`, `Puddings`, `Snacks`.

That set cannot be used. The audit's own scan says 65 of 108 tails auto-match
their form row and "most of the 65 are correct". Concretely, blocking a head
segment drawn from that list destroys two matches the audit itself certifies as
right:

```
== 'pumpkin seed'  search_terms='pumpkin seeds, hulled, raw, pepitas'
  0.781  Seeds, pumpkin seeds (pepitas), raw   [foun] OK   => AUTO
auto  coriander seed                     0.714  Spices, coriander seed
```

`Seeds` and `Spices` are on the list, and both of those are the correct row.
The usable set is much smaller — `Oil`, `Fat`, `Flour`, `Tea`, `Pie` — and even
then it is a judgement per word, which is what §B5-2 concedes for
`soybean`/`safflower` and then forgets when writing F1. The finding is sound;
the remedy as stated is not a closed set and should not be written as one.

## C11 — Foods the audit did not test that fail

All probed here, verbatim.

```
weak  casabe                             0.389  Casabe, cassava bread     <- own row, unreachable
weak  yautia                             0.368  Yautia (tannier), raw     <- = malanga, declared absent
weak  bacalao                            0.353  Bacalaitos fritos         <- salt cod word, lands on a fritter
weak  oxtail                             0.429  Beef, oxtails             <- Jamaica's headline dish
weak  arepa                              0.353  Arepa Dominicana          <- and that row is NOT an arepa
weak  morcilla                           0.333  Mortadella
weak  longaniza                          0.375  Longans, raw              <- a fruit, for a sausage
weak  malta                              0.308  Milk, malted
weak  aguas frescas                      0.333  Frescavena
weak  sorrel drink                       0.400  Soft drink, NFS
weak  conch salad                        0.438  Crab salad
weak  stew peas                          0.429  Stew, pork
none  crema                              -      (nothing)
none  media crema                        -      (nothing)
none  chicharrones                       -      (nothing)   <- while `chicharron` is also none
none  maduros                            -      (nothing)
none  boniato                            -      (nothing)
none  batata                             -      (nothing)
none  ñame                               -      (nothing)
none  pastelillo                         -      (nothing)
none  cou cou                            -      (nothing)
none  mauby                              -      (nothing)
```

Two of these are worse than anything in F5, because the row exists:

- **`Arepa Dominicana` (2707828) is not an arepa.** It is a Dominican
  cornmeal-and-coconut pudding — 267 kcal, 14 g fat, 30 g carbohydrate, 53 mg
  cholesterol per 100 g — and a Venezuelan or Colombian arepa is a plain corn
  griddle bread with no egg, no coconut and roughly a third of the fat. It is
  the only row containing the word, it heads the list for `arepa` (0.353) and
  for `la bandera dominicana` (0.393, §B3), and the audit reports the second
  without noticing the first. Below the gate, so it escalates — but the model
  tier is handed one candidate whose name is an exact match and whose food is
  not.
- **`Casabe, cassava bread`** — see C5. 1,185 mg sodium per 100 g.

And two auto-matches worth recording that the audit did not reach:

```
auto  chorizo                            1.000  Chorizo            (see C4)
auto  johnny cake                        0.643  Johnnycake
```

`Johnnycake` (2707820) is the US cornmeal griddle bread: 277 kcal, 7.46 g fat,
871 mg sodium. Caribbean *johnny cake* / *bake* is fried dough — materially
fattier — and this auto-matches with no model consulted and caches an alias.
Smaller than the F1 class (roughly 20–40% on energy, not 6x), but it is a clean
unguarded auto on a word the audit's own Trinidad/Jamaica section should have
covered: §B3 probed `bammy` and `festival` and stopped.

Correct auto-matches the audit also missed, for balance — this domain is better
served than 44% `none` suggests: `guava paste` 1.000 (292 kcal, 71.6 g sugar),
`dulce de leche` 1.000, `fufu` 1.000, `curry chicken` 1.000 `Chicken curry`,
`cuban coffee` 1.000, `cafe con leche` 0.737, `empanada` 0.692 `Empanada, NFS`,
`tamarindo` 0.727, `cassava bread` 0.778, `queso blanco` 0.500
`Cheese, white, queso blanco` (a sixth Mexican cheese §B2-8 does not list).

## Verdict

The audit is careful, unusually well measured, and right about the thing that
matters most: **F1, the `Form, food` head-segment class, is real, survives
every guard, survives `search_terms`, and is worse than reported** (C2, C8).
F2, F5 in outline, F6, F8, F9, F10, F11 and F12 stand. The five claimed
reorders replicate exactly.

What does not hold: the guard reconciliation's arithmetic, because it was run
with `asked_for = label` when production uses `label + search_terms` — four of
eleven escalations are autos, all onto correct rows (C1). F3 is contradicted by
the audit's own output and its blanket rejection of chile fallbacks is
inconsistent with the standard it applied to `poblano` (C3). Three "entity
gaps" have rows under other names (C5). The domain's canonical trap — chorizo —
was never probed (C4). F1's remedy is stated as a closed set that cannot be
closed (C10).

