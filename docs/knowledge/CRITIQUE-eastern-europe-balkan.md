# Critique — AUDIT-eastern-europe-balkan.md

Reviewer pass, 28 Aug 2026. Read-only. Every claim re-probed; every nutrient
figure re-pulled from `food_nutrient` per 100 g; every claimed `auto` re-run
against the three `resolve_items` guards.

STATUS: complete.

## Summary of the verdict

The audit is strong on **mechanism** and weak on **the food**. Its §1 guard
re-runs reproduce almost exactly (one exception, below), its §4 mechanism
analysis is correct and is the most valuable thing in the file, and its §5
refusals are well argued. What fails is §3's absence claims (two are simply
false — it searched the wrong word), one §1 nutrient claim that is wrong in
sign as well as magnitude, and §6, which repeatedly contradicts §4 and §5 by
promoting to **synonym, high confidence** exactly the ingredient-for-dish and
fold-two-foods-into-one mappings the earlier sections spend pages refusing.

---

## A. Guard check — which claimed autos actually survive in production

Re-run with `state_conflicts`/`unrequested_qualifier`/`label_absent` over the
live `db.search_foods` list, taking `next()` over survivors exactly as
`resolve_items` does.

| §   | term | audit says | verdict here |
|---|---|---|---|
| 1.1 | `oatmeal` | auto → `Pie, oatmeal` | **UPHELD.** Reproduced. Survives all three guards at state `cooked` too. |
| 1.2 | `buckwheat kasha` | auto → `Buckwheat` (raw) | **UPHELD.** Survives even with `state="cooked"`, exactly as the audit predicted. |
| 1.3 | `dried mushrooms` | auto → `Fried mushrooms` | **OVERTURNED for the realistic parse.** With `state="dry"` — which a label containing the word *dried* will almost always produce — `state_conflicts` returns `fried` and the item **escalates to the model tier**. The audit ran this one at `state=None` and reported the result as a live defect, while §1.2 shows it knew state was the deciding input. Survives only when the model leaves state unset/`as_sold`. |
| 1.4 | `russian salad` | auto → `Salad dressing, russian dressing` | **UPHELD**, and worse than stated: 1133 mg sodium/100 g on top of the macro error. |
| 1.5 | `sauerkraut stew` | auto → `Sauerkraut` | **UPHELD.** Single candidate, unblocked at every state. |
| 1.6 | `carrot salad` | auto → `Carrots, raw, salad`, "plain raw carrot, understates by roughly half" | **OVERTURNED on the food.** See §B.1. The auto fires, but the row is not plain carrot and the error runs the other way. |
| 1.7 | `pumpernickel` | auto → `Roll, pumpernickel` | **DOWNGRADED to a non-finding.** `Roll, pumpernickel` (2707767) and `Bread, pumpernickel` (174918) are *byte-identical* on every macro: 250 kcal / 8.7 P / 3.1 F / 47.5 C / 596 Na. There is no nutritional error to report. Keep it as an illustration of tie-breaking (§4a), not in a section headed "wrong-confident matches". |

So of seven claimed dangerous autos: **five survive the guards**, one survives
only under an unlikely parse, one is nutritionally inert.

---

## B. Culinary and nutritional errors

### B.1 §1.6 `carrot salad` is wrong about the food, and wrong in sign

The audit: *"the row is plain raw carrot… Understates by roughly half."*

Actual figures, `food_nutrient`, per 100 g:

```
 2709661 Carrots, raw, salad                 212 kcal  1.25 P  15.74 F  17.62 C  12.04 sugar
 2709662 Carrots, raw, salad with apples     181       0.85    16.02     8.59     4.47
  169145 Beets, raw (for scale)               43
```

`Carrots, raw, salad` is **not** plain raw carrot (41 kcal). It is a dressed
carrot salad at 15.7 g fat — the `raw` refers to the carrot, not to the dish.
Surówka z marchewki is ~100–130 kcal, so the auto-match **overstates by ~1.7×**,
not understates by half. Worse for the audit's case: `Carrots, raw, salad with
apples` (181 kcal) is *literally* surówka z marchewki i jabłka, it is on the
candidate list, and `unrequested_qualifier` blocks it (`qual:salad with
apples`). The audit reproduced that trace and did not notice the row was the
right answer. The finding survives as a guard defect; the nutritional claim
attached to it does not.

### B.2 §3.2 "There is no sheep-milk cheese of any kind" — false

The audit searched `ILIKE '%sheep%'` and concluded from three rows that the
class is absent. It is not; USDA does not put the animal in the name.

```
  171250 Cheese, roquefort            369 kcal  21.5 P  30.6 F
 2705705 Cheese, Blue or Roquefort    353       21.4    28.7
  171249 Cheese, romano               387       31.8    26.9
probe:  ask  roquefort  0.588  Cheese, roquefort
```

Roquefort is sheep's milk by AOC definition. This does not rescue oscypek
(smoked, hard, scalded) and the audit's refusal there still stands on its own
merits — but the *reason given* is wrong, and `Cheese, roquefort` at 21.5 g
protein is a better anchor for **bryndza** (soft, salty, sheep, ~21 P) than
`Cheese, feta` at 14.2 (173420). The categorical sentence should go.

### B.3 §3.8 "halva (0 rows)" — false

```
  167996 Candies, halavah, plain      469 kcal  12.5 P  21.5 F  60.5 C
probe:  none  halva     -   (nothing)
probe:  none  halvah    -   (nothing)
```

USDA spells it **halavah**. The row exists and is a perfectly good target. This
is a *reachability* gap of exactly the kind §2 is about, and the audit filed it
under §3 "genuinely absent" — the one section whose whole claim is that it
searched by ingredient and category, not only by name. One spelling variant
away from the answer.

### B.4 Maślanka has an exact row and the audit routes it to kefir

```
probe:  none  maslanka    -      (nothing)
probe:  auto  buttermilk  1.000  Buttermilk
 2705393 Buttermilk  43 kcal  3.5 P  1.1 F  4.8 C
 2705394 Kefir       52       3.6   1.0   7.5 C  6.9 sugar
```

§6 medium lists `maslanka (drinking)` in the `→ Kefir` fallback row. Buttermilk
is a distinct product with its own row and its own carbohydrate figure (4.8 vs
7.5 g, and kefir's 6.9 g sugar against buttermilk's ~4.8). Route maślanka to
`Buttermilk` 2705393 as a synonym; leave kefir to kefir.

---

## C. §6 contradicts §4 and §5 — twelve mappings to overturn

The audit spends §4(c) establishing that *ingredient-for-dish* substitution is
"the class that produced the largest errors in this domain", and §5 refusing
folds that hide a 2–3× error behind a spelling variant. Then §6 encodes both,
at **high confidence, as synonyms**.

### C.1 `barszcz, borsch, borshch, boršč, borș → Soup, borscht` — its own §5 forbids this

§5, verbatim in substance: folding `barszcz` with `borshch` "is a 2–3× error
dressed up as a spelling fix", because `Soup, borscht` (2710105, **20 kcal**)
is right only for the clear beetroot broth. §6 row 30 then puts all six
spellings on 2710105 as a **synonym**. Pick one. (`Soup, vegetable, with meat`
2710116 at 44 kcal is already in the medium table for the hearty version — so
the fix the audit wants is in the file, one section away from the mapping that
breaks it.)

### C.2 `sernik → Cheesecake, plain` — its own §3.1 forbids this

§3.1 rejects every twaróg mapping and adds "same for … every dish built on
them (syrniki, leniwe, **sernik z twarogu**, knedle)". §6 row 25 encodes
`sernik → Cheesecake, plain` (2707861: **399 kcal / 5.3 P / 26.5 F**) at high
confidence. Polish sernik is a pressed-curd cake at roughly 270–300 kcal and
8–10 g protein. Same error, same direction, same magnitude as the one §3.1
built its whole argument on.

### C.3 `flaki, flaczki, dršťky, pacal, ciorbă de burtă → Tripe` — its own §1.5 forbids this

`Tripe` 2706162 is 89 kcal / 12.6 P / 3.9 F / **0 C**. Flaki is a *soup*:
tripe in a root-vegetable broth, ~50–60 kcal/100 g and carrying carbohydrate
the target row does not have. This is §1.5 (`sauerkraut stew → Sauerkraut`)
with the labels changed, promoted to a synonym. Ciorbă de burtă additionally
carries cream and egg yolk. Fallback at best, and only for the drained tripe.

### C.4 `sarma → Grape leaves stuffed with rice` — the ambiguity is resolved backwards

§2.7 spots the ambiguity and then picks the minority sense. In Serbian,
Bosnian and Croatian, bare **sarma is the sour-cabbage roll with minced meat** —
the same food as gołąbki. The vine-leaf version is `japrak`, `dolma`, or
explicitly "sarma od vinove loze". The two rows are not close:

```
 2706620 Stuffed cabbage rolls with beef and rice  114 kcal  8.3 P   5.1 F
 2709064 Grape leaves stuffed with rice            168       2.3    11.9
```

Protein 3.6× wrong, fat 2.3× wrong, on the default reading of the word. Move
bare `sarma` to 2706620 with the rest of the cabbage-roll group and leave
`japrak`/`dolma` on 2709064.

### C.5 `płatki owsiane` folded into `Oatmeal, NFS` — the §1.1 error, re-committed

§6 row 32: `oatmeal, owsianka, płatki owsiane, ovesná kaše → Oatmeal, NFS`.

```
 2708380 Oatmeal, NFS                              76 kcal
 2346396 Oats, whole grain, rolled, old fashioned  382 kcal  13.5 P  5.9 F  68.7 C
probe:  weak  rolled oats  0.333  Oats, whole grain, rolled, old fashioned
probe:  none  porridge     -      (nothing)
```

**Płatki owsiane are dry rolled oats**; owsianka is the cooked porridge made
from them. The audit's own headline finding is a 5.2× energy error on this
exact food, and its proposed fix folds a **5.0×** one in beside it. Split the
surfaces: `owsianka`/`ovesná kaše` → 2708380; `płatki owsiane`/`rolled oats` →
2346396, which is itself unreachable today at 0.333.

### C.6 `dried mushrooms → Mushrooms, shiitake, dried` as a *synonym*

Shiitake is a species, not a generic. `Mushrooms, shiitake, dried` is 296 kcal
/ **9.6 P** / 75.4 C; dried porcini — what "grzyby suszone" means in a bigos or
a wigilia sauce — runs roughly 350 kcal and ~30 g protein. A 3× protein error.
The audit knows this row is a narrowing qualifier: its own trace shows
`unrequested_qualifier` blocking it with `qual:shiitake`. Encoding it as a
synonym is a deliberate override of a guard that was right. Fallback only.

### C.7 Five folds that put two different foods on one row

| §6 group | the error |
|---|---|
| `kotlet schabowy, … bécsi szelet, schnitzel, šnicla → Pork, chop, coated` | **Wiener Schnitzel is veal** — that is the whole meaning of *bécsi szelet*. Pork is *Schnitzel Wiener Art*. Domain twin of "bresaola is beef". |
| `salo, słonina, slanina, szalonna → Pork, cured, salt pork, raw` (748 kcal / 5.0 P / 80.5 F) | **`slanina` is bacon** in Czech, Slovak and BCS — streaky cured pork belly at ~400–500 kcal and 12–17 g protein. Energy ~1.7× out, protein ~3× out. Salo/słonina/szalonna are fine. |
| `kabanosy, kabanos, sudžuk, lukanka, kulen → Salami, dry or hard, pork` | **Sudžuk/sucuk is beef**, and in the Balkan and Turkish contexts where the word is used, deliberately not pork. Culturally as well as compositionally wrong. |
| `mamaliga, mămăligă, kačamak, žganci, polenta → Cornmeal mush, no added fat` | **Ajdovi žganci are buckwheat**, not maize. Slovenian žganci without a qualifier are commonly the buckwheat kind. |
| `sgushchenka, mleko skondensowane → Milk, condensed, sweetened` (321 kcal) | Polish *mleko skondensowane* covers the **unsweetened evaporated** product too (~134 kcal). A 2.4× split hiding under one surface, cached as an alias forever. |

---

## D. Confidence inflation — right direction, wrong tier

These belong in the medium/fallback table, not under "a competent cook would
not dispute it".

| §6 high-confidence row | figures | why it is medium |
|---|---|---|
| `kaszanka, krvavica, verivorst, kishka → Blood sausage` 171618 | 379 kcal / 14.6 P / 34.5 F / **1.3 C** | Every food in that group is roughly one third **grain** — buckwheat groats (kaszanka), rice (krvavica), barley (verivorst). The target row has 1.3 g carbohydrate. Kaszanka is ~230–280 kcal with 10–15 g carb: energy ~1.4× over and the carbohydrate simply vanishes. |
| `skwarki, čvarci, jumări, tepertő → Pork, cracklings` 2705895 | 569 kcal / **45.0 P** / 41.7 F | That row is puffed pork *rind*. Skwarki are rendered from słonina — ~700 kcal and ~10 g protein. Protein is ~4× out in the direction that matters most for this user. |
| `śmietana, smetana, smântână, kisela pavlaka, tejföl → Sour cream, regular` 2705614 | 196 kcal / 18.0 F | Śmietana is sold at 12%, 18%, 30% and 36%; tejföl is 20%, smântână 20–25%. Variant-dependent by definition, which is the textbook medium. |
| `rosół, bulion, wywar, vývar, húsleves → Soup, chicken` 2707134 | 40 kcal | **`bulion` and `wywar` are stock**, and `Soup, chicken broth, ready-to-serve` (174536, **6 kcal**) exists for them. Folding a 6 kcal broth and a 40 kcal soup onto one row is a ~6× spread inside one proposal. |
| `szarlotka, jabłecznik, štrúdl, rétes, almás pite → Strudel, apple` 2708039 | 281 / 2.0 P / 14.1 F / 37.2 C | Štrúdl and rétes are strudel. **Szarlotka and almás pite are not** — shortcrust or sponge, more egg and more protein, less laminated fat. Split the group. |
| `mamaliga → Cornmeal mush, no added fat` 2708374 | 58 kcal | Cornmeal mush is a thin American porridge; mămăligă is set firm enough to slice, ~90–110 kcal. ~1.7× under. |
| `buraczki, burak, beetroot, cvekla → Beets, raw` 169145 | 43 kcal | **Buraczki is a cooked dish** — braised grated beet, usually with butter or a roux, ~80–100 kcal. `burak`/`beetroot`/`cvekla` (the vegetable) are fine on 169145; `buraczki` is the §4(c) shape again. |
| `fasolka po bretońsku, pasulj, bob chorba, fazolová polévka → Soup, bean, with meat` 2707457 | 84 kcal | Pasulj and fazolová polévka are soups. **Fasolka po bretońsku is not** — beans in a thick tomato-and-sausage sauce, ~120–140 kcal. |

---

## E. What the audit upheld

Stated plainly, because most of it holds. Re-verified independently:

- §3.1 twaróg. Every figure re-pulled and correct to the decimal; no USDA row
  exceeds 12.4 g protein; `Cottage cheese, farmer's` really is the worst
  numbers under the best name (148 kcal / 11.0 P / 9.7 F). The refusal is right.
- §2.11 rapeseed. `Oil, canola` appears nowhere on the list; `Oil, grapeseed`
  heads it at 0.688 and is blocked; the item escalates with no usable
  candidate. Reproduced exactly.
- §2.3 `beet salad`. `Beef salad` at 0.692, blocked only by `label_absent`.
  Reproduced exactly.
- §3.3 sorrel: `ILIKE '%sorrel%'` → **0 rows**. Confirmed. Genuine entity gap.
- §3.6, §3.7, §3.4, `kompot` (0 rows): confirmed absent.
- §5's refusal list is the best-argued part of the document. Keep all of it —
  and then apply it to §6.
- §4(a)–(d) is correct and is the finding with the widest reach. The four
  structural proposals that follow from it are the right work.

---

## F. What the audit missed

Foods in the domain it did not probe, with output.

```
probe:  weak  rolled oats        0.333  Oats, whole grain, rolled, old fashioned   (382 kcal; see C.5)
probe:  none  porridge           -      (nothing)
probe:  none  halva / halvah     -      (nothing)          row 167996 exists — B.3
probe:  ask   roquefort          0.588  Cheese, roquefort  row 171250 exists — B.2
probe:  none  maslanka           -      (nothing)          `buttermilk` → auto 1.000 — B.4
probe:  ask   moussaka           0.455  Mousse
probe:  none  musaka             -      (nothing)
probe:  ask   beetroot soup      0.500  Soup, beef
probe:  ask   cold beet soup     0.471  Soup, beef
probe:  ask   cabbage soup       0.471  Cabbage, raw
probe:  ask   goose              0.600  Fat, goose
probe:  none  sprats             -      (nothing)
probe:  none  kajmak / kaymak / urda / kashkaval / leczo / lecso / tarator  -  (nothing)
probe:  none  boczek / schab / parowki / mizeria / surowka / zapiekanka     -  (nothing)
```

1. **`moussaka` heads on `Mousse`** — a chocolate dessert, for a baked
   minced-meat-and-potato dish eaten across the whole southern half of this
   domain. `ILIKE '%moussaka%'` → 0 rows; a genuine entity gap the audit's §3
   never looked for. Nearest honest fallback is a decomposition, not a row.
2. **The beet/beef collision is not confined to salads.** The audit found
   `beet salad → Beef salad`. `beetroot soup` and `cold beet soup` — barszcz
   and chłodnik, the two most-logged Polish soups after rosół — both head on
   `Soup, beef` (blocked by `qual:beef`, so they escalate; the list is still
   nonsense). Same root cause, three surfaces, one tested.
3. **`cabbage soup → Cabbage, raw`** at 0.471. Kapuśniak, and the §4(c)
   ingredient-for-dish shape at `ask` rather than `auto`. No cabbage-soup row
   surfaces at all. It widens §4(c) from four instances to at least six.
4. **`goose` heads on `Fat, goose`** (900 kcal of pure fat) at 0.600. Gęś is a
   Polish festive staple and is untested in the audit. `unrequested_qualifier`
   blocks it (`extra={fat}`) so it escalates — the guard works — but the
   candidate list handed to the model contains no goose *meat* row in the
   top 5.
5. **`sprats`, `boczek`, `schab`, `parówki`, `mizeria`, `surówka`,
   `zapiekanka`, `leczo`, `tarator`** all return nothing and none appear
   anywhere in the audit's five batches. `Cucumber salad made with cucumber and
   vinegar` (2709821, 34 kcal) is a decent mizeria fallback and is reachable
   only at 0.405.

---

## G. Guard-check tally

| | |
|---|---|
| claimed dangerous autos | 7 (§1.1–1.7) |
| survive all three guards in production | **6** |
| already blocked | **1** (`dried mushrooms`, once `state="dry"` is emitted — the realistic parse for a label containing the word *dried*) |
| survive but are nutritionally inert | 1 (`pumpernickel`: `Roll, pumpernickel` and `Bread, pumpernickel` are identical on every macro) |

Method note the audit should carry: it ran its guard re-runs at `state=None`.
`resolve_items` passes `it.get("state")`, and the parse schema calls state "the
largest error source in the system" precisely because the model does fill it
in. Any guard re-run that omits state over-reports survivors. `buckwheat kasha`
was checked against `state="cooked"` and survives regardless — that one is
solid — but `dried mushrooms` was not, and it does not.

A second method note: the audit's re-runs also omit `search_terms`.
`asked_for` in production is `label + search_terms`, so the query word-set is
*larger*, `unrequested_qualifier`'s `extra` set is *smaller*, and the guard
blocks **less** than these traces show. Where a trace here says "blocked
qual:X" and X is a word the model would plausibly write into `search_terms`,
the real system may auto-match after all. That cuts against the audit's
conclusions in the safe direction only for `escalates` verdicts, and against it
everywhere else.
