# Critique — AUDIT-south-asian.md

Adversarial review. In progress; appended as verified.

## Method

I re-ran every claim through `scripts/probe_knowledge.py` and, separately,
replayed the three production guards (`state_conflicts`,
`unrequested_qualifier`, `label_absent` from `nutrai/llm/parse.py`) over the
same candidate lists. USDA figures below are `SELECT`s against the live
database, per 100 g. No writes.

One caveat on the replay, stated so it can be discounted: production calls
`unrequested_qualifier(asked_for, …)` where `asked_for = label + search_terms`,
and `label_absent(label, …)` on the label alone. My replay uses the bare label
for both, so it is the *strict* reading of the qualifier guard. Where a model's
`search_terms` would plausibly re-supply the blocked word I say so.

---

## 1. The flagship finding is wrong. `paneer` does not auto-match.

The audit's §1 — the item it ranks first in §9 and calls "the single most
logged South Asian ingredient" — rests on this sentence:

> `unrequested_qualifier` inspects only comma segments and "Palak Paneer" has
> none

That is a misreading of the function. `unrequested_qualifier` splits on commas
and then judges segment 0 **as well**, by a different rule:

```python
if i == 0:
    # Only a name that echoes the query can narrow it.
    if (words & q) and extra:
        return seg.strip()
    continue
```

"Palak Paneer" is exactly that shape: it echoes the query word (`paneer`) and
adds one (`palak`). The guard fires. Replayed against the live candidate list:

```
=== 'paneer'  state=None
   0.636 AUTO BLOCKED Palak Paneer     qual:Palak Paneer
   0.500 ask    ok    Cheese, paneer
   -> ESCALATES to model tier
```

The probe verdict `auto` is real — `search_foods` alone would take it — but
production does not. The item goes to the model tier with `Cheese, paneer` on
the list, which is the system working. And the guard is robust to the
`search_terms` pooling: any plausible model phrase for paneer ("paneer indian
cheese", "paneer cheese cubes") still leaves `palak` as an unrequested extra.

This matters beyond the one term. The docstring the auditor was reading records
that exempting the first segment outright was *tried and reverted*, because it
promoted `Spaghetti squash, cooked` into an auto-match. The behaviour the audit
says is absent is the behaviour that fix installed.

**Verdict: overturned.** §1 and §9 item 1 should be struck. `paneer` is a
reachability annoyance (the right row is rank 2 and costs a model call), not a
silent 3× error.

The nutritional gap the audit quotes is real, and I confirm its figures
exactly — which establishes only that the escalation is worth having, not that
a silent error occurs:

```
Cheese, paneer (2705740)   299 kcal   15.9 g protein   15.5 g fat
Palak Paneer   (2709631)   101 kcal    5.4 g protein    7.0 g fat
```

---

## 2. The guard check on §2's table: 3 of 11 claimed autos never happen

Replaying `resolve_items`' auto gate over the same candidate lists:

| §2 claim | Guard verdict | What production actually does |
|---|---|---|
| `paneer` → `Palak Paneer` | **blocked** `qual:Palak Paneer` | escalates |
| `white rice cooked` → `Rice, white, cooked, glutinous` | **blocked** `qual:glutinous` | escalates (all six candidates blocked) |
| `yogurt plain` → `Yogurt, plain, nonfat` | **blocked** `qual:nonfat` | escalates (all six blocked) |
| `almond` → `Oil, almond` | survives | **auto `Oil, almond`** |
| `walnut` → `Oil, walnut` | survives | **auto `Oil, walnut`** |
| `coconut cream` → `Pie, coconut cream` | survives | **auto `Pie, coconut cream`** |
| `cucumber raita` → `Cucumber, raw` | survives | **auto `Cucumber, raw`** |
| `tamarind rice` → `Tamarind` | survives | **auto `Tamarind`** |
| `milk rice` → `Rice milk` | survives | **auto `Rice milk`** |
| `ginger` → `Tea, ginger` | survives | **auto `Tea, ginger`** |
| `spinach cooked` → `Malabar spinach, cooked` | head blocked, **worse row survives** | **auto `Spaghetti, spinach, cooked`** |

Eight of eleven stand. The pattern in the three that fall is worth naming: the
guard fires whenever the wrong row's distinguishing word is a *word*
(`glutinous`, `nonfat`, `palak`) and cannot fire when the wrong row's identity
is in its **first segment and shares nothing with the query** — `Pie`, `Tea`,
`Oil`, `Rice milk`. `unrequested_qualifier` deliberately exempts a first
segment that shares no word with the query, because a name that shares nothing
is "a different food and a weak match, judged by similarity like anything
else". These eight are the cases where similarity judged it wrong. That is a
sharper statement of the residual risk than the audit's, and it survives the
correction.

### 2.1 `spinach cooked` is worse than reported, not better

The audit stops at the head. The guard blocks `Malabar spinach, cooked`
(`qual:Malabar spinach`) and the next row through the gate is:

```
   0.652 AUTO BLOCKED Malabar spinach, cooked        qual:Malabar spinach
   0.652 AUTO   ok    Spaghetti, spinach, cooked
   -> PRODUCTION AUTO = 'Spaghetti, spinach, cooked'
```

```
Malabar spinach, cooked         23 kcal   3.0 prot   0.8 fat   2.7 carb
Spinach, NS as to form, cooked  59 kcal   3.3 prot   3.7 fat   3.0 carb
Spaghetti, spinach, cooked     130 kcal   4.6 prot   0.6 fat  26.1 carb
```

Palak or saag logged at 200 g lands on **spinach pasta**: 26 g of carbohydrate
per 100 g against 3. The audit's own §2 entry understates its own finding by a
factor of four on carbohydrate, because it read the probe head rather than the
gate. This is the one place where "check the guards" makes a claim *worse*.

### 2.2 `coconut cream`: the auto is real, the proposed replacement is wrong

`Pie, coconut cream` does survive. But the audit's proposed target,
`Coconut cream, canned, sweetened`, is the Coco López–style **sweetened dessert
concentrate**, not a curry base:

```
Coconut cream, canned, sweetened            357 kcal  1.2 prot  16.3 fat  53.2 carb
Nuts, coconut cream, raw (liquid expressed) 330 kcal  3.6 prot  34.7 fat   6.7 carb
Coconut milk, used in cooking               230 kcal  2.3 prot  23.8 fat   5.5 carb
Pie, coconut cream                          297 kcal  2.5 prot  17.8 fat  32.0 carb
```

Against real coconut cream the audit's target has **half the fat and eight
times the carbohydrate**. It is barely better than the pie it is replacing —
both are sugar-dominated desserts. This is the exact "culturally right,
nutritionally 3× off" failure the brief warns about, and it is in the audit's
own remedy rather than in the system.

The defensible targets are `Coconut milk, used in cooking` (2707568) or
`Nuts, coconut cream, raw` (170580). **Downgrade the proposed mapping and
repoint it.**

### 2.3 `ginger`: real, but the severity is inflated

`Tea, ginger` at 1 kcal/100 g does survive the gate. But ginger enters a curry
at 5–15 g, so the error is on the order of 10 kcal and 2 g of carbohydrate a
meal against `Ginger root, raw` (80 kcal, 17.8 g carb). It caches an alias
forever, which is the real cost, but ranking it alongside `almond → Oil,
almond` (884 kcal, **zero protein**, at 30 g portions) flattens a two-order-of-
magnitude difference in consequence. Honest severity: low, fix cheap.

### 2.4 A correction the audit could not have made from probe output alone

`mutton` reaches `Mutton, cooked, roasted (Navajo)` and
`Stew, hominy with mutton (Navajo)`. The audit identifies the `indian` →
`(Navajo)` / `(Northern Plains Indians)` trap in §6 and then does not notice
that **`mutton` is in the same family of rows** — Diné mutton is adult sheep,
which is precisely the meaning §8 rejects for South Asia. All the candidates
are weak (≤0.368) so nothing auto-matches, but the §8 rejection should name it:
the risk is not only that a mapping points at lamb, it is that the model tier
is handed a list of Navajo sheep stews.

---

## 3. A guard interaction the audit never looked for

`unrequested_qualifier` treats USDA's **parenthetical vernacular synonym** as a
narrowing qualifier, because it is a word the query did not contain:

```
'chickpea flour' 0.714 AUTO BLOCKED Chickpea flour (besan)   qual:Chickpea flour (besan)
                 -> ESCALATES to model tier
'barfi indian dessert' 0.778 AUTO BLOCKED Barfi or Burfi, Indian dessert  qual:Barfi or Burfi
                 -> ESCALATES to model tier
```

In this domain the parenthetical is very often *the Indian name* —
`Chickpea flour (besan)`, `Pigeon peas (red gram)`,
`Balsam-pear (bitter gourd)`, `Gourd, dishcloth (towelgourd)`,
`Coriander (cilantro) leaves`, `Butter, Clarified butter (ghee)`. The guard
suppresses exactly the row that carries the vernacular word.

Two honest limits on this finding, both of which the audit would have needed
the guard replay to state:

- It only *matters* above 0.62, because the guards are consulted only at the
  auto gate. `pigeon peas`, `bitter gourd` and `coriander leaves` are blocked
  in my replay but were never going to auto-match anyway, so the block is a
  no-op there. Only `chickpea flour` and `barfi indian dessert` are affected in
  practice.
- Both of those escalate to the model with the correct row at the head of the
  list, which is a fraction of a penny, not a wrong number. **Not a bug —
  a cost.**

But it does falsify the audit's framing in §3.1 and §9 item 6. The audit's
argument is "adding a redundant English word moves the same row from `weak` to
`auto`" and therefore the fix is reachability. For `chickpea flour` and
`barfi indian dessert` the redundant word does *not* produce an auto-match; the
guard takes it back. The mechanism the audit is describing is real for `ghee`,
`sambar`, `firni`, `ladoo` and `clarified butter` (all verified to auto in
production) and does not hold for the two that carry a parenthetical.

---

## 4. What the audit missed. The biggest South Asian defect in the database is
not in it.

### 4.1 `coconut milk` auto-matches a carton beverage. This is the worst one.

```
=== 'coconut milk'  state=None
   1.000 AUTO   ok    Coconut milk
   0.650 AUTO   ok    Yogurt, coconut milk
   0.481 ask  BLOCKED Coconut milk, used in cooking     qual:used in cooking
   -> PRODUCTION AUTO = 'Coconut milk'
```

```
Coconut milk               (2705413)   31 kcal  0.2 prot   2.1 fat   2.9 carb
Coconut milk, used in cooking (2707568) 230 kcal 2.3 prot  23.8 fat   5.5 carb
Beverages, coconut milk, sweetened, fortified (174116)
                                        31 kcal  0.2 prot   2.1 fat   2.9 carb
```

FNDDS `Coconut milk` is the **drinking carton** — its figures are identical to
the sweetened fortified beverage row. `Coconut milk, used in cooking` is the
tin. A Kerala fish curry, a Sri Lankan kiri hodi, a chicken korma or a
Bangladeshi chingri malai curry with 200 ml of tinned coconut milk is logged at
**62 kcal and 4 g of fat instead of 460 kcal and 48 g** — a 7.4× energy and
11× fat understatement, on the ingredient that carries most of the fat in an
entire regional cuisine.

It survives every guard (single-segment description, exact string match, no
state word to contradict), it caches an alias forever, and the correct row is
*actively blocked* by `unrequested_qualifier` on "used in cooking". It is
strictly worse than every entry in the audit's §2 table and the audit tested
only `coconut cream`.

### 4.2 The audit tested transliterations and skipped Indian English entirely

It probes `lauki`, `turai`, `karela`, `dahi`, `besan`, `bhindi`-adjacent
transliterations — and never the English-language layer that Indian, Pakistani
and Sri Lankan speakers actually type in English. Probe output:

```
weak  curd               0.385  Soybean curd
weak  curd rice          0.429  Rice cake
none  brinjal            -      (nothing)
none  capsicum           -      (nothing)
weak  ladies finger      0.333  Cookie, ladyfinger
weak  gram flour         0.429  Flour, 00
auto  raw banana         1.000  Banana, raw
```

- **`curd`** is the standard Indian English word for dahi and is far commoner
  than `dahi` in written English. It returns **tofu** (`Soybean curd`,
  `Soybean curd cheese`, `Soybean curd, deep fried`). This is the audit's own
  §5 complaint — an escalation whose candidate list is nonsense — on a word it
  never tested, and the confusion is a genuine culinary trap: bean curd and
  milk curd are different foods that share an English word.
- **`gram flour`** is the commonest British/Indian English name for besan. The
  audit tested `besan` and `chickpea flour` and missed it. It returns
  `Flour, 00` and `Flour, rye`.
- **`ladies finger`** (okra) returns `Cookie, ladyfinger`. `okra` itself
  reaches `Okra, raw` at 0.556, so this is pure vocabulary.
- **`brinjal`** and **`capsicum`** return nothing at all, while `eggplant` and
  `bell pepper` are ordinary USDA rows.

### 4.3 `raw banana` — a state/identity homonym the audit's method cannot see

```
=== 'raw banana'  state=raw
   1.000 AUTO   ok    Banana, raw
   -> PRODUCTION AUTO = 'Banana, raw'
```

In South Asian English "raw banana" is the **green cooking plantain**
(kachcha kela, vazhakkai) — a starchy vegetable fried into poriyal or kofta —
not an uncooked dessert banana. `state_conflicts` cannot fire: the declared
state is `raw` and the description says `raw`, so the two *agree* while meaning
opposite things. `Plantain, raw` exists and reaches 0.692 from `plantain`.
Sugar 12.2 g against roughly 2 in green plantain, and the whole point of the
ingredient — that it behaves like a potato — is erased.

### 4.4 Absences the audit's entity-gap section did not reach

All verified `none`: `khoya`, `mawa` (the milk solid that is the base of
barfi, gulab jamun and most Indian sweets, ~400 kcal/100 g — a far larger
omission than the sweets themselves, which the audit does list), `rajma`,
`keema`/`kheema`, `korma`, `vindaloo`, `rogan josh`, `tikka masala`,
`pulao`, `basmati`, `rasam`, `avial`, `appam`, `puttu`, `uttapam`, `pongal`,
`ash gourd`, `snake gourd`, `kathal`, `suran`, `colocasia`, `sev`, `bhujia`,
`namkeen`, `murmura`, `soya chunks`, `tandoori roti`, `dhania`, `elaichi`,
`kesar`.

And the §6 "nonsense candidate head" list omits the three most-ordered South
Asian dishes on earth:

```
ask   butter chicken     0.474  Chicken, back
ask   tandoori chicken   0.500  Chicken, tail
ask   chicken tikka      0.500  Chicken, tail
```

`Chicken, tail` and `Chicken, back` are offal-adjacent butchery rows. These are
`ask` verdicts on a nonsense list, which is the defect class the audit itself
defines in §5 — and it is more consequential than `arbi` → `ARBY'S`.

### 4.5 A row the audit declared missing, which exists

§2 and §7 both say there is "no kiribath row" and that the Sri Lankan corpus is
empty. `Rice, cooked with coconut milk` (2709032, **267 kcal, 3.6 prot,
17.2 fat, 26.6 carb**) exists and is a defensible neighbour for kiribath and
for Kerala/Malay-style coconut rice. It is even *on the `milk rice` candidate
list* the audit pasted — at 0.357, two rows below the `Rice milk` head it
quoted. The audit truncated the list at two rows and concluded from the
truncation.

---

## 5. Upheld

I tried to break these and could not.

- **§4, the dal collapse.** Verified. Every named dal returns only the generic
  FNDDS `Dal` (145 kcal, 8.6 prot, **7.5 g fibre** — figure confirmed), and the
  species rows exist and are never returned. The observation that a fix must
  carry a *state* decision with it — `Dal` is a cooked dish, the species rows
  are dry seed at 2.4× the energy — is the strongest single piece of reasoning
  in the audit, and it is right.
- **§2, `almond` and `walnut`.** Both survive all three guards and auto-match
  the oils. `Oil, almond` 884/0/100 against `Almonds, NFS` 598/21.0/52.5,
  confirmed. Zero protein on a nut is the invariant-1 failure shape and this
  one is real.
- **§5, `curry leaf`.** Confirmed: zero curry-leaf rows, and every candidate is
  a composite curry dish. The recommendation to omit rather than approximate is
  correct — a ~1 g garnish has no defensible proxy.
- **§8 rejections.** `paneer → Cheese, NFS`, `jaggery → Molasses` (Molasses
  confirmed at 290 kcal), `biryani → Rice, cooked, NFS` (`Biryani with meat`
  145/6.8 against `Rice, cooked, NFS` 129/0.3, confirmed), `mutton → Lamb`,
  `dahi → nonfat`, and the refusal to invent a bread neighbour for hoppers —
  all correctly reasoned. §8 is the best part of the document.
- **`prawn` → nothing.** Verified `none`. `shrimp` → `Shrimp, NFS` (146 kcal)
  auto-matches and survives the guards, so the proposed synonym pointing at the
  same NFS row is exactly right.

## 6. Smaller errors of fact

- **`ragi` calcium is off by an order of magnitude.** §8 says ragi carries
  "roughly 3× the calcium" of millet. `Millet, raw` (169702) carries **8 mg**
  calcium per 100 g; finger millet is ~340 mg. That is ~40×, not 3×. The
  direction is right and it strengthens the audit's own conclusion, but a "3×"
  figure reads as "close enough" and invites the mapping it is arguing against.
- **`finger millet → Millet` repeats the state error §4 identifies.** §8 calls
  it "defensible for energy and macros at medium". `Millet` (2708377) is
  **cooked**, 118 kcal; `Millet, raw` is 378. Ragi flour is a dry flour. The
  proposal as written is a 3× energy error of exactly the kind §4 warns about
  two pages earlier. Downgrade to reject, or restate it against `Millet, raw`.
- **The header claims 1,026 terms; the verdict counts sum to 1,026 but the
  document evidences a few hundred.** Not falsifiable from here, and every
  probe line I re-ran reproduced exactly, so I treat the pasted output as
  trustworthy. Noted only because §4.2 above shows the *selection* of terms was
  skewed toward transliteration and away from Indian English.

## 7. Revised priority order

1. **`coconut milk` → `Coconut milk, used in cooking`.** 7.4× energy, 11× fat,
   auto-matched, cached, on the defining fat of three regional cuisines. Not in
   the audit at all.
2. `spinach cooked` → `Spaghetti, spinach, cooked`. Auto, and worse than the
   audit's own account of it.
3. `almond` / `walnut` → the oils. Auto, zero protein.
4. `curd` → tofu; `gram flour`, `ladies finger`, `brinjal`, `capsicum`,
   `raw banana`. The Indian English layer, untested by the audit.
5. `cucumber raita`, `tamarind rice`, `milk rice`, `coconut cream` — auto onto
   a wrong row, but repoint `coconut cream` at the cooking row, not the
   sweetened one.
6. `prawn`, then transliteration. Both as the audit has them.
7. **Struck from the audit's list:** `paneer`, `white rice cooked`,
   `yogurt plain`. The guards already handle all three. They cost a model call,
   not a wrong number.
