# Critique — AUDIT-italian-french.md

28 Aug 2026. Read-only. Every probe line below is verbatim `scripts/probe_knowledge.py`
output; every nutrient figure is a read-only SELECT against `food_nutrient`,
per 100 g.

Status: complete.

---

## A. The method error that moves the headline

**The audit measured the guards with the wrong argument, and measured
reachability with the wrong query.** Both errors run in the same direction:
they make the resolver look worse than it is on §1 and better than it is on §0.

### A.1 `unrequested_qualifier` is called with `asked_for`, not the label

`nutrai/llm/parse.py:688` and `:738`:

```python
asked_for = f"{label} {it.get('search_terms') or ''}"
...
and not unrequested_qualifier(asked_for, c["description"])
```

The audit's §0 reports `unrequested_qualifier('spaghetti','Spaghetti sauce')`
— the bare label. Production passes the label **plus the model's
`search_terms`**, which widens `q` and therefore *weakens* the guard: any
qualifier word the model happens to write into `search_terms` stops being
"unrequested". `label_absent` is the only one of the three that sees the bare
label (`:739` passes `label`), and `state_conflicts` sees neither.

For the four cases §0 names the conclusion survives — I re-derived them by hand
against the real signature and they still block:

| query | candidate | segment returned | blocked |
|---|---|---|---|
| `spaghetti` (+ any plausible search_terms) | `Spaghetti sauce` | `Spaghetti sauce` (i=0, echoes query, adds `sauce`) | yes |
| `olive` | `Olive oil` | `Olive oil` (i=0, echoes, adds `oil`) | yes |
| `sour cream` | `Sour cream, light` | `light` (i=1) | yes |
| `walnut` | `Oil, walnut` | none — `Oil` shares nothing with the query so i=0 is judged a *name* | **no** |

So §0's guard conclusion is right by luck of the examples, not by method. The
correction matters because a `search_terms` string that contains the qualifier
disarms the guard entirely, and no audit that tests with the bare label can see
that.

**`marsala` should not be in §0's list at all.** `AUTO_MATCH_SIMILARITY` is
0.62 and `marsala` scores 0.615, so it is an `ask` verdict — the audit's own
§3.3 files it as one. It never reaches a guard. §0 counts it among the "108
`auto` verdicts" it ran back through the guards; that is an internal
contradiction, and it inflates the count of dangerous autos the guards
"caught".

### A.2 §1.3 and §1.4 are measured on a query production does not use alone

`_candidates` (`parse.py:311`) searches **the model's `search_terms` as well as
the label** and pools by best score. `PARSE_SYSTEM` asks the model for "a
precise USDA-style phrase". So the production query set for "brie" is not
`{brie}`, it is `{brie, <USDA-style phrase>}`. Probed:

```
weak  brie                               0.417  Cheese, brie
auto  cheese, brie                       1.000  Cheese, brie
weak  parmesan                           0.429  Cheese, parmesan, hard
auto  cheese, parmesan, hard             1.000  Cheese, parmesan, hard
weak  pecorino romano                    0.318  Cheese, romano
auto  cheese, pecorino romano            0.636  Cheese, romano
weak  farro                              0.273  Farro, pearled, dry, raw
auto  farro, pearled                     0.636  Farro, pearled, dry, raw
weak  oxtail                             0.429  Beef, oxtails
auto  beef, oxtails                      1.000  Beef, oxtails
weak  morels                             0.238  Mushrooms, morel, raw
auto  mushrooms, morel                   0.789  Mushrooms, morel, raw
weak  anchovies                          0.353  Fish, anchovy
auto  fish, anchovy                      1.000  Fish, anchovy
```

`label_absent` does not block any of these (`brie` is in `Cheese, brie`;
`romano` is in `Cheese, romano`), so in production they auto-match the correct
row. §7's claim that fixing the one-word case would make "roughly forty of the
findings above evaporate" is therefore an overstatement of the *production*
loss: a large share of §1.3 and §1.4 is already recovered by the second pooled
query. It remains a real finding for the resolver's ranking, and for the
`label_absent` risk it creates, but it is not the headline the audit makes it.

Not all of them recover — `squid, raw` still returns 0.323 — so the §1.4 list
needs re-scoring one row at a time rather than being cited wholesale.

---

## B. Overturned

### B.1 §3.3 `unsalted butter` — the audit reported its own probe's *second* row

The audit files this under "near-misses worth recording (blocked, but only
just)" as:

```
weak  unsalted butter   0.348  Pretzels, soft, ready-to-eat, unsalted, no butter
```

and narrates: "with [`Butter, stick, unsalted`] gone the query's best remaining
candidate is a *pretzel*. The filter is right and the consequence was not
anticipated."

Re-probed today, full candidate list:

```
unsalted butter auto
    0.667 Butter, salted
    0.348 Pretzels, soft, ready-to-eat, unsalted, no butter
    0.333 Pretzels, soft, ready-to-eat, unsalted, buttered
    0.391 Pecans, unsalted
    0.375 Almonds, unsalted
```

The verdict is **`auto`, not `weak`**, and the head is **`Butter, salted`**, not
a pretzel. The audit quoted candidate #2 and built a paragraph on it. The real
consequence of the `UNUSABLE_ROW` filter is both worse and different: with
`Butter, stick, unsalted` (789828, no energy value) gone, the query for
*unsalted* butter clears the auto gate onto the *salted* row —
`Butter, salted` (173410) at **643 mg Na / 100 g** against
`Butter, without salt` (173430) at **11 mg**, on otherwise identical macros
(717 / 81.1 both).

It is saved, and only just, by one guard:

```
unrequested_qualifier('unsalted butter', 'Butter, salted') -> 'salted'
```

— because `salted` and `unsalted` are different tokens and this function does
no prefix matching. That is a lucky escape from a tokenisation detail, not a
designed one, and it belongs in §3 as a live near-auto, not in a list of
already-solved near-misses.

### B.2 §1.5 "USDA has **no shape names at all**. Not one." — false

Present in the loaded `food` table:

```
  168903  367.0    1.0   13.1   74.9    43.0  Macaroni, vegetable, enriched, dry
  168904  128.0    0.1    4.5   26.6     6.0  Macaroni, vegetable, enriched, cooked
```

plus `Noodles, egg, dry, enriched`, `Noodles, cooked`, `Vermicelli, made from
soy`, and — quoted by the audit itself four lines below the claim —
`Spaghetti, spinach, dry` and `Spaghetti, spinach, cooked`. The audit's own
`spaghetti` candidate list contradicts its own section heading.

The *useful* claim underneath is intact: no plain-semolina shape row exists, so
`penne`/`rigatoni`/`fusilli` are unreachable. Say that instead. The absolute
form is the kind of sentence an implementer stops checking.

### B.3 §5 `chèvre → Cheese, goat` — wrong sub-type, +38% energy

USDA carries three goat rows and they are not interchangeable:

```
  173435  264.0   21.1   18.5    0.0   459.0  Cheese, goat, soft type
  173433  364.0   29.8   21.6    0.1   415.0  Cheese, goat, semisoft type
  172197  452.0   35.6   30.5    2.2   423.0  Cheese, goat, hard type
 2705716  364.0   29.8   21.6    0.1   415.0  Cheese, goat            <- what "Cheese, goat" resolves to
```

`Cheese, goat` is the **semisoft** figure. In French and Italian usage *chèvre*
unqualified means the fresh soft log — `chèvre frais`, the disc on a *salade de
chèvre chaud*, `chèvre` on a tart. That is 264 / 21.1, and the audit's mapping
delivers 364 / 29.8: **+38% energy, +41% fat**. Map `chèvre` and `chèvre frais`
to **173435** and reserve `Cheese, goat` for `bûche`-style aged/semisoft.

### B.4 §5 `ossobuco → 172646` — the leaner of an adjacent pair, unremarked

```
  172646  157.0    4.5   29.1    0.0    90.0  Veal, foreshank, osso buco, separable lean only, cooked, braised
  172649  182.0    7.8   27.9    0.1    90.0  Veal, foreshank, osso buco, separable lean and fat, cooked, braised
```

Osso buco is braised on the bone with the fat on and the marrow eaten. The
"separable lean only" row is a butchery abstraction; picking it understates fat
by **42%** (4.5 vs 7.8 g) and the audit does not say it made the choice.
**172649** is the honest row of the pair.

Second, smaller point: §2.5 states the audit's own rule — "the right treatment
for a dish is a decomposition, not a row" — and then §5 files `ossobuco` under
"plain synonyms" and gives it a row. Either the rule has an exception for
dishes that are ~85% one cut, or `ossobuco` should be a decomposition. It should
be stated which.

### B.5 §0 counts `marsala` among the `auto` verdicts

`AUTO_MATCH_SIMILARITY` is 0.62. `marsala` probes at **0.615** — an `ask`, as
the audit's own §3.3 records it. It is not one of "108 `auto` verdicts", it
never reaches a guard, and crediting `unrequested_qualifier` with blocking it
inflates the guards' measured hit rate. (It *would* be blocked —
`unrequested_qualifier('marsala','Veal Marsala') -> 'Veal Marsala'` — which is
why the error is bookkeeping rather than substance.)

---

## C. The guard check, run properly

`state_conflicts` takes only the states the parse schema can emit —
`nutrai/llm/schemas.py:64`: `["raw","cooked","dry","as_sold","unknown"]`.
**There is no `fresh`**, so §3.1's line `state_conflicts('fresh','Egg, white,
dried') -> None` tests a value that cannot occur and should not be cited as
exposure.

Every claimed or found `auto` in this domain, run against the real functions:

| query | head candidate | `state_conflicts` | `unrequested_qualifier` | `label_absent` | production |
|---|---|---|---|---|---|
| `spaghetti` | `Spaghetti sauce` | – | `Spaghetti sauce` | F | **blocked** |
| `olive` | `Olive oil` | – | `Olive oil` | F | **blocked** |
| `sour cream` | `Sour cream, light` | – | `light` | F | **blocked** |
| `unsalted butter` | `Butter, salted` | – | `salted` | F | **blocked** |
| `butter` | `Butter, tub` | – | `tub` | F | **blocked** (and harmless: 731 vs 743 kcal) |
| `gnocchi` | `Gnocchi, cheese` | – | `cheese` | F | **blocked** |
| `couscous` | `Couscous, dry` | `dry` if state raw/cooked | – | F | blocked **only if state stated** |
| `short grain white rice` | `Rice, white, short-grain, raw, unenriched` | `raw` if state cooked | – | F | blocked **only if state cooked** |
| `egg white` | `Egg, white, dried` | `dried` if state raw/cooked | – | F | **survives** when state is null / `unknown` / `as_sold` |
| `walnut` | `Oil, walnut` | – | – | F | **survives** |
| `olives` | `Olives, NFS` | – | – | F | survives, and is correct |

**Six caught, two dangerous survivors — the audit's count is right.** What it
gets wrong is the framing of both survivors, and it misses the mechanism they
share with half of its own §3.3 list.

### C.1 §3.1 `egg white` — upheld, but not by the route claimed

The defect is real: `Egg, white, dried` (376 kcal) vs `Egg, white only, raw`
(52), auto at 0.625, and an alias written forever. But "Carbonara is eggs. This
is the single most consequential finding in the domain" does not follow. A
carbonara parse states `raw` or `cooked` for its eggs, and **both block**. The
live exposure is the *stateless* log — "2 egg whites" typed on its own, state
`unknown` or `as_sold` — which is a breakfast-and-baking failure, not an
Italian one. Uphold the finding, drop the carbonara.

### C.2 §3.2 `walnut` — upheld, and it is a *class*, not a case

The audit diagnoses this correctly at the level of the one food:
`unrequested_qualifier` treats a first segment sharing nothing with the query as
a *name* and leaves it to similarity (`parse.py:552-556`, deliberate — it is
what stopped `Spaghetti squash` being promoted). What the audit does not say is
that this makes the whole `<OtherFood>, <query>` shape unguardable, and that
USDA is dense with it. Its own §3.3 "near-misses" list is four instances of the
same mechanism and it files them as unrelated coincidences:

```
ask   zucchini    0.600  Bread, zucchini          unrequested_qualifier -> None
ask   carrot      0.500  Muffin, carrot           unrequested_qualifier -> None
weak  truffle     0.400  Pate, truffle flavor     unrequested_qualifier -> None
ask   cream       0.600  Cake, cream              unrequested_qualifier -> None   (not in the audit)
```

None of these is blocked by anything. The **only** thing between them and
`walnut`'s outcome is the 0.62 constant. `cream → Cake, cream` at 0.600 is five
thousandths away, on a word that appears in every French recipe in the domain.
That is the finding: not "fix `walnut`", but "the i==0 rule has no defence for a
query that is a bare ingredient noun and a candidate whose first segment is a
different food."

---

## D. Nutritional defensibility of §5, checked row by row

Figures are per 100 g from `food_nutrient`: kcal / fat g / protein g / Na mg.

### D.1 Upheld — numbers check out

| mapping | USDA row | figures | real food | verdict |
|---|---|---|---|---|
| bresaola → `Beef, cured, dried` (170604) | | 153 / 1.9 / 31.1 / 2790 | bresaola ≈151 / 2.6 / 32 | **excellent** — and correctly **beef**, the trap the brief names |
| pancetta → `Pork, cured, bacon, unprepared` (168277) | | 393 / 37.1 / 13.7 / 751 | pancetta ≈400–460 / 40–45 | good (unsmoked vs smoked; composition close) |
| culatello → `Ham, prosciutto` (2705879) | | 195 / 8.3 / 27.8 / 2695 | culatello ≈198 / 9 / 31 | good |
| soppressata / saucisson sec / finocchiona / salame → `Salami, Italian, pork` (174603) | | 425 / 37.0 / 21.7 / 1890 | ≈440 / 38 / 24 | good |
| boudin noir → `Blood sausage` (171618) | | 379 / 34.5 / 14.6 / 680 | ≈370 / 33 / 14 | good, and culinarily exact |
| comté / beaufort → `Cheese, gruyere` (171242) | | 413 / 32.3 / 29.8 / 714 | comté ≈417 / 34 / 29 | excellent — all three are alpine cooked-pressed |
| cantal → `Cheese, cheddar` (173414) | | 403 / 33.3 / 22.9 / 653 | cantal ≈390 / 33 / 24 | good |
| raclette → `Cheese, gouda` (171241) | | 356 / 27.4 / 24.9 / 819 | raclette ≈357 / 28 / 23 | near-exact |
| gorgonzola → `Cheese, blue` (172175) | | 353 / 28.7 / 21.4 / 1146 | ≈350 / 32 / 19 | fine |
| fior di latte → `Cheese, mozzarella, whole milk` (170845) | | 299 / 22.1 / 22.2 / 486 | ≈300 / 22 / 20 | good |
| caciocavallo → `Cheese, provolone` (170850) | | 351 / 26.6 / 25.6 / 727 | ≈380 / 28 / 28 | acceptable, both pasta filata |
| crème fraîche → `Cream, heavy` (2705597) | | 343 / 35.6 / 2.0 | crème fraîche ≈300 / 30 | audit's "+15%" is right, and it says so |
| mascarpone → `Cheese, cream` (173418) | | 350 / 34.4 / 6.2 | mascarpone ≈429 / 44 | audit's "−20% fat" is right, and it says so |
| polenta → `Cornmeal mush, NS as to fat` (2708373) | | 71 / 1.8 / 1.1 / 12.2 c | soft polenta ≈75–85 | good |
| foie gras → `Pate de foie gras` (171100) | | 462 / 43.8 / 11.4 / 697 | ≈462 / 45 | good |
| eggplant parmigiana → `Eggplant parmesan casserole, regular` | 155 / 10.5 | ≈180–210 | acceptable |
| courgette→zucchini, aubergine→eggplant, prawns→shrimp, baguette→`Bread, French or Vienna`, boeuf bourguignon→`Beef burgundy`, emmental→`Cheese, swiss` | | | **all correct** |

### D.2 Downgraded — the audit's confidence is higher than the numbers support

**D.2.1 `guanciale → 168269` at "High" — this is the cured-vs-fresh trap.**

```
  168269  655.0   69.6    6.4    0.0    25.0  Pork, fresh, variety meats and by-products, jowl, raw
```

`fresh` here means *uncured*, and `raw` means raw. Guanciale is a dry-cured,
salt-rubbed product. Energy and fat land well; **sodium is 25 mg against
~1300–1800 mg**, a 50–70× understatement on a nutrient that carries a ceiling
target — the exact shape of the "751 mg from one invented word" turkey failure
already recorded in CLAUDE.md. The audit does note the sodium caveat, and then
files the mapping as **High** anyway.

Worse, and unmentioned: a knowledge-table entry resolves through the alias
tier, which **bypasses `state_conflicts` entirely** (`parse.py:663-681` returns
before the guard block). So this permanently pins a cooked, cured food to a raw
uncured row with no guard able to intervene, on any future log. Medium at most,
and the sodium figure has to travel with it in whatever the table's note field
is.

**D.2.2 `speck → Ham, prosciutto` at "High" — 36% low on energy, 2.6× low on fat.**

`Ham, prosciutto` is 195 / 8.3. Speck Alto Adige IGP is ≈300 / 22 — it is a
smoked, marbled, boned shoulder-and-leg product, not the trimmed lean crudo the
USDA row describes. The audit maps **speck and culatello to the same row**;
culatello is the leanest cure in Italy and speck one of the fattier ones, and
they cannot both be 195 / 8.3. Culatello stands. Speck should be medium with the
fat caveat, or refused — there is no good row (the nearest alternative,
`Pork, cured, bacon, unprepared` at 393 / 37.1, errs as far the other way).

**D.2.3 `pecorino romano → Cheese, romano`: "romano *is* pecorino romano in USDA" is not true.**

```
  171249  387.0   26.9   31.8    3.6  1433.0  Cheese, romano
```

Nothing in the row says sheep. US "Romano" is routinely *Vacchino* Romano —
cow's milk — and the SR figures reflect that: 26.9 g fat and 31.8 g protein
against Pecorino Romano DOP's ≈32 g fat and ≈26 g protein. The *mapping* is
still the best available and I would keep it; the **assertion of identity** is
wrong and the confidence should be medium. (In production this mapping is
largely moot — `cheese, pecorino romano` already auto-matches `Cheese, romano`
at 0.636 via `search_terms`.)

**D.2.4 Pasta shapes → `Pasta, cooked` — the dry/cooked caveat the audit applied to couscous and then dropped.**

```
  169736  371.0    1.5   13.0   74.7     6.0  Pasta, dry, enriched
 2708357  157.0    0.9    5.8   30.7   232.0  Pasta, cooked
```

**2.36×.** §4 correctly flags `couscous → Couscous, dry` as "a 3× mass error
when [the state] is not [supplied]" and then §5 maps every dried shape to the
*cooked* row without the same warning. Someone typing "penne 100 g" almost
always means the dry weight in the packet. The mapping has to be a pair keyed on
state, not one row.

**D.2.5 Egg-ribbon shapes → `Pasta, homemade, made with egg, cooked` (168901) is *lower* than plain pasta.**

```
  168901  130.0    1.7    5.3   23.5    83.0  Pasta, homemade, made with egg, cooked
 2708357  157.0    0.9    5.8   30.7   232.0  Pasta, cooked
```

The audit presents this as the more careful choice for tagliatelle and
pappardelle. It delivers **17% less energy and 23% less carbohydrate** than the
plain row — a USDA moisture artefact, not a fact about egg pasta, which in
reality is the *richer* of the two. Mapping the egg shapes there installs a
systematic understatement on every ragù. Prefer `Pasta, cooked` for these too,
or say plainly that the egg row is wetter and not richer.

**D.2.6 `quiche lorraine → Quiche with meat, poultry or fish` (2708731): 387 / 30.6 / 15.5.**
Culinarily right family (lardons). Numerically ~25% above a typical quiche
lorraine (≈310). Medium, not high.

### D.3 Refusals in §6 — all upheld

`andouille`/`andouillette` (Cajun vs chitterling — correct and well argued),
dried porcini, truffle, stracciatella, fromage blanc/petit suisse, peperoncino →
pepperoni (a chilli is not a sausage), the Basque/Savoyard cheese list, and the
blanket rejection of `X → cheese`-style parent mappings. Nothing to add: this is
the strongest section of the audit and it is right on every one.

---

## E. What 881 terms missed

All probe output below is verbatim and reproducible today. These are not
obscure: every one is an ordinary word in the two cuisines the audit covers.

### E.1 `prosciutto cotto` — this domain's own bresaola trap, and it is not in the file

```
ask   prosciutto cotto                   0.579  Ham, prosciutto
ask   prosciutto crudo                   0.524  Ham, prosciutto
```

Both spellings land on the same row. They are different foods:

```
 2705879  195.0    8.3   27.8    0.3  2695.0  Ham, prosciutto          <- crudo, dry-cured
  173864  164.0    8.8   16.6    3.6   814.0  Ham, sliced, regular     <- cotto, cooked
```

*Cotto* is cooked ham off the bone; *crudo* is the dry-cure. Mapping cotto to
the crudo row gives **3.3× the sodium** (2695 vs 814) and **+67% protein**. The
audit tested 60 cured-meat terms, proposed `speck` and `culatello` onto this very
row, and never tested the one Italian word pair that decides which side of it
you are on. Both need explicit entries: `prosciutto crudo`/`prosciutto` → 2705879,
`prosciutto cotto` → 173864.

### E.2 `ricotta` and `ricotta salata` — 67 cheese terms and ricotta is in none of them

```
ask   ricotta                            0.533  Cheese, Ricotta
weak  ricotta salata                     0.381  Cheese, Ricotta
```

```
 2705750  148.0    9.5    9.6    6.0   102.0  Cheese, Ricotta
```

Ricotta is the second-most-used cheese in Italian home cooking after parmesan and
does not appear anywhere in the audit. `ricotta salata` — pressed, salted, aged,
the cheese on a pasta alla Norma — is ≈300 / 24 / 21 with high sodium, roughly
**2× the fresh row on energy and 2.5× on fat**, and its only candidate is the
fresh row. It escalates today (0.381), so this is a knowledge-table entry, not a
resolver bug: `ricotta salata` must not be allowed to become an alias for
`Cheese, Ricotta`.

### E.3 `gnocchi` — top ten Italian dish, untested, and the head is the wrong gnocchi

```
ask   gnocchi                            0.533  Gnocchi, cheese
auto  gnocchi potato                     1.000  Gnocchi, potato
```

```
 2708721  178.0   12.0    8.5    9.4   263.0  Gnocchi, cheese
 2708722  135.0    6.3    2.4   17.2   279.0  Gnocchi, potato
```

Unqualified *gnocchi* means potato gnocchi. The head is the cheese row: **+32%
energy, 1.9× fat, 3.5× protein, −45% carbohydrate**. It is an `ask` and
`unrequested_qualifier` returns `cheese` anyway, so production is safe — but a
knowledge entry `gnocchi → 2708722` is free and obviously right, and the audit
did not look.

### E.4 `duck fat` → `Duck sauce`, with the correct row one word away

```
weak  duck fat                           0.333  Duck sauce
weak  duck leg                           0.333  Duck sauce
auto  goose fat                          1.000  Fat, goose
```

```
  173572  900.0   99.8    0.0    0.0     0.0  Fat, goose
```

`Duck sauce` is a Chinese-American plum condiment. Duck fat is the defining
ingredient of `confit de canard` — which the audit lists in §2.5 and proposes to
*decompose* — and its own decomposition therefore contains a term that resolves
to a sweet plum sauce. `Fat, goose` and duck fat are both ~900 / 99.8 and the
substitution is exact. `duck fat` → 173572.

### E.5 `rocket` → nothing, while `arugula` auto-matches

```
none  rocket                             -      (nothing)
auto  arugula                            0.667  Arugula, raw
```

§1.6 gets `courgette`, `aubergine` and `prawns` — the British-to-American
vocabulary bridge — and misses the fourth member of the same set, on a leaf that
is in every Italian salad. Same class, same fix, zero cost.

### E.6 `asiago` — none, and `Cheese, fontina` is sitting right there

```
none  asiago                             -      (nothing)
weak  asiago cheese                      0.389  Cheese, NFS
ask   fontina                            0.533  Cheese, fontina
```

```
  170843  389.0   31.1   25.6    1.6   800.0  Cheese, fontina
```

Asiago d'allevo is ≈390 / 30 / 24 — within 1% of the fontina row on energy. The
audit's cheese batch found `taleggio`, `reblochon` and `mimolette` and skipped
asiago, which is more common on a UK or US shelf than any of them.

### E.7 `lasagne` vs `lasagna`, and a guard doing real work

```
weak  lasagne                            0.242  CARRABBA'S ITALIAN GRILL, lasagne
ask   lasagna                            0.471  Lasagna, meatless
```

The audit ran a 115-term "regional + alternative spellings" batch and did not
test the -e/-a pair, which is the single commonest Italian/English spelling split
in the language. Worth recording that `Lasagna, meatless` is caught twice over —
`inverts_meaning` returns True and `unrequested_qualifier` returns `meatless` —
which is the guard wave working, and a data point the audit could have used in
§0 and did not have.

### E.8 Also `none`, untested, and each one a plain word

```
none  passata / bechamel / creme fraiche / aioli / cornichon / haricot vert /
      croque monsieur / amaretti / grissini / langoustine / john dory / brill
weak  pain au chocolat                   0.385  Pancakes, chocolate
weak  sole                               0.308  Soup, pozole
weak  duck breast                        0.387  Duck, wild, breast, meat only, raw
```

`creme fraiche` returning nothing is notable given §5 proposes a mapping for it:
the audit priced the mapping without probing the term. `pain au chocolat` →
`Pancakes, chocolate` and `sole` → `Soup, pozole` (a Mexican pork soup) are both
weak and therefore harmless, but they belong in §1.6 —
`pain au chocolat → Croissant` is the same synonym move as
`baguette → Bread, French or Vienna`. `duck breast` landing on
`Duck, wild, breast` is a genuine mismatch: farmed magret is a different fat
class from wild duck.

### E.9 What the audit got right that deserves saying

`bresaola → Beef, cured, dried` is correct and is exactly the trap the brief
warns about; the audit did not fall into it. The §6 refusals are disciplined and
well-argued, particularly andouille/andouillette and the blanket rejection of
parent-category mappings. The `unrequested_qualifier` blocks in §0 are real. The
`egg white` and `walnut` survivors are both genuine and both correctly
identified as the only two.

---

## F. Verdict

The audit is competent, disciplined about refusals, and the only serious
knowledge-audit in this set that ran the guards at all. Its two guard survivors
are real and correctly counted.

Three things need fixing before it is acted on:

1. **§3.3's `unsalted butter` entry is a misread of its own probe** (B.1). The
   verdict is `auto`, the head is `Butter, salted`, and the paragraph built on
   the pretzel is fiction. This is the one factual error in the file that would
   mislead an implementer.
2. **§1.3/§1.4/§7's reachability headline is measured on a query production does
   not use alone** (A.2). `_candidates` pools the model's `search_terms`, and
   most of the "exact row below the weak floor" list auto-matches correctly in
   production. The ranking defect is real; the "forty findings evaporate" prize
   is not that large.
3. **Four §5 mappings are over-confident on numbers I checked**: guanciale
   (Na 25 vs ~1500, and an alias bypasses `state_conflicts` forever), speck
   (fat 8.3 vs ~22), chèvre (wrong goat sub-type, +38%), pasta shapes and the
   egg-ribbon row (dry/cooked, and a row that is wetter rather than richer).

And the best thing in the file is under-stated: §3.2 is not a fact about
walnuts. It is `unrequested_qualifier`'s i==0 rule having no defence for the
`<OtherFood>, <ingredient>` shape, and USDA is full of it — `Cake, cream` sits
0.005 below the auto gate on a word this cuisine uses constantly.

*Status: COMPLETE.*
