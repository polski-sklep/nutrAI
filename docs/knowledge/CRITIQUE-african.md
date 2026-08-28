# Critique — AUDIT-african.md

Critic pass, 28 Aug 2026. Read-only. Every claim below is either pasted probe
output, pasted SQL from the live database, or a reading of the guard functions
in `nutrai/llm/parse.py`. In progress; appended in batches.

## Verdict in one line

The audit's **§1 is right and its §2 is wrong about what "weak" costs**. Every
dangerous auto-match it names does survive all three guards — I replayed them
through `_candidates` + the real guard functions, not by hand — and every USDA
figure it quotes is correct to the decimal. But the class it calls "the most
valuable" (§2) is largely not a failure at all, its §7 recommendation is
mis-prioritised as a result, and the one structural cause that actually explains
half of §1 is never named.

---

## A. Method: what I re-ran, and why it differs from the audit's

The audit's guard table (§0) shows guard verdicts against a **bare label with no
`search_terms`**. Production does not work that way. `resolve_items` builds

```python
asked_for = f"{label} {it.get('search_terms') or ''}"      # parse.py:688
```

and passes `asked_for` — not the label — to `inverts_meaning` and
`unrequested_qualifier`; only `label_absent` sees the bare label. And
`_candidates` searches the model's `search_terms`, the label, the dish hint and
every alternation of each, pooling by **max** similarity. So the probe is a
lower bound on similarity and the audit's guard runs are an approximation of a
guard that in production is fed a longer string.

I replayed the decision properly: `_candidates(it, label, user_id=None)` with a
plausible `search_terms` and `state`, then every guard in the same order
`resolve_items` applies them, taking the first survivor. Script:
`/private/tmp/.../scratchpad/guard.py` (read-only; it calls `search_foods` and
the pure guard functions and nothing else).

**This mattered in one direction only, and it is worth knowing:** giving the
model a good `search_terms` rescues `couscous` completely —

```
=== label='couscous' terms='couscous, cooked' state='cooked'
  AUTO  1.000   169700 Couscous, cooked
  BLOCK 0.636   169699 Couscous, dry            state='dry'
```

— and rescues nothing else. `peanut butter soup` with `search_terms="peanut
butter soup, groundnut soup"` and `state=cooked` still auto-matches
`Peanut butter`:

```
  AUTO  0.737  2707537 Peanut butter
  PASS  0.632  2707547 Soup, peanut
```

So §1.3 is **stronger** than the audit claims: it is not rescuable by the model
writing better search terms, because the better search terms score the jar
higher too.

## B. §1 — every claimed dangerous auto survives the guards. Upheld.

Replayed with realistic `search_terms`/`state`. `-->` is the row production
would take with no model consulted, and each writes a permanent alias.

| claim | replayed result | survives? |
|---|---|---|
| 1.1 `couscous` -> `Couscous, dry` | AUTO 169699 when state is `None`/`as_sold` **and** search_terms do not say "cooked" | yes, conditionally |
| 1.2 `sorghum grain cooked` -> `Sorghum grain` | AUTO 169716 even with state=cooked | yes |
| 1.3 `peanut butter soup` -> `Peanut butter` | AUTO 2707537 with good search_terms | yes |
| 1.4 `akara bean cake`, `bean cake fried` -> `Bean cake` | AUTO 2707409 | yes |
| 1.5 `red palm oil` -> `Oil, palm` | AUTO 171015 | yes |
| 1.6 `avocado` -> `Oil, avocado` | AUTO 173573 | yes |
| 1.6 `pumpkin` -> `Pie, pumpkin` | AUTO 2708011 | yes |
| 1.6 `sweet potato` -> `Pie, sweet potato` | AUTO 2708012 | yes |
| 1.6 `brown rice` -> `Flour, rice, brown` | AUTO 1104812 | yes |
| 1.7 `spinach cooked` -> `Spaghetti, spinach, cooked` | AUTO 168912 | yes |

Every USDA figure the audit quotes is correct. Pasted from the live database:

```
169699 Couscous, dry                  376.0 kcal  12.8 prot   0.6 fat  77.4 carb
169700 Couscous, cooked               112.0        3.8         0.2      23.2
169716 Sorghum grain                  329.0       10.6         3.5      72.1
2707537 Peanut butter                 598.0       22.2        51.4      22.3
2707547 Soup, peanut                   88.0        3.2         5.3       8.4
2707409 Bean cake                     414.0        5.8        21.4      49.9
171015 Oil, palm                      884.0        0.0       100.0       0.0   vitA_RAE 0
173573 Oil, avocado                   884.0                                   
2709223 Avocado, raw                  160.0        2.0        14.7       8.5
2708011 Pie, pumpkin                  249.0                                   vitA 327
168448 Pumpkin, raw                    26.0                                   vitA 426
2708012 Pie, sweet potato             269.0                                   vitA 189
2709697 Sweet potato, NFS             115.0                                   vitA 684
1104812 Flour, rice, brown            368.0
2708414 Rice, brown, cooked, no fat   123.0
168912 Spaghetti, spinach, cooked     130.0        4.6         0.6      26.1   fibre NULL
```

No overturns in §1. The one correction is 1.1's severity (search-term-dependent)
and 1.3's (worse than stated).

## C. Overturned — §2 "reachability gaps" mostly are not gaps

This is the audit's largest error and it runs through §2, §7 and the summary
counts.

**A `weak` verdict does not stop the model tier.** `resolve_items`:

```python
        if not cands:                     # parse.py:747
            ... unresolved.append(label); continue
        best = float(cands[0]["sim"] or 0)
        if best < WEAK_MATCH_SIMILARITY:  # parse.py:755
            weak.append((label, best))
        need_model.append((it, cands, _event(...)))   # parse.py:759 — unconditional
```

A weak best score adds a "check this" line to the confirm card and a "define it
yourself" button. The **full top-5 still goes to Haiku**. So wherever the right
row is in the candidate list, `weak` is the *escalated* outcome the brief calls
the system working — one call, a fraction of a penny, no cached alias written
by the resolver. The audit calls §2 "the most valuable class"; for the cases
where the right row leads the list it is not a failure class at all.

### C.1 §2.1 — `ghee` is a probe artefact, not a finding

The audit's headline case. In production `search_terms` are present, and:

```
=== label='ghee' terms='ghee, clarified butter' state='as_sold'
  AUTO  1.000   171314 Butter, Clarified butter (ghee)
  PASS  1.000  2710168 Ghee, clarified butter
```

`ghee` **auto-matches at 1.000**, correctly. The audit's 0.227 is
`search_foods('ghee')` alone, which is not what the resolver asks. §4's claim
that ghee "is the part currently unreachable" for doro wat is false.

`injera`, `teff` and `fonio` do stay weak — but the right row leads the list and
the model tier gets it:

```
=== label='injera' terms='injera, Ethiopian teff flatbread' state='cooked'
  BLOCK 0.618  2707796 Injera, Ethiopian bread    below-gate(0.618)
  --> escalates to model tier
```

Correct row, correct outcome. The residual harm is real but much smaller than
claimed: the card shows a spurious "weak match" warning and offers to define a
food USDA already has, which invites a duplicate `user_product` row.

### C.2 §2.2 and §2.3 — three of five cases dissolve with `search_terms`

| audit's claim | replayed with realistic `search_terms` |
|---|---|
| `garden eggs`: "No eggplant row anywhere in the list" | `Eggplant, raw` (2685577/169228/2709785) is the **head** of the list at 0.448 |
| `cowpeas`: "the leaf row wins... the seed sits at 0.145" | `Blackeyed peas, NFS` (2707412) heads it; **four of five** candidates are the seed |
| `maize meal`: `none` | five cornmeal rows, `Cornmeal, white (Navajo)` at 0.517 heading them |

All three escalate to the model with the right row present. Overturned.

`collard greens` / `sukuma wiki` and `groundnut` **survive** and are worse than
the audit shows — with good search terms the collards rows still do not appear:

```
=== label='collard greens' terms='collard greens, cooked' state='cooked'
  BLOCK 0.583 2709612 Poke greens, cooked        BLOCK 0.560 2709571 Beet greens, cooked
  BLOCK 0.560 2709598 Greens, canned, cooked     BLOCK 0.481 2709953 Onions, green, cooked
  BLOCK 0.467 2709589 Dandelion greens, cooked
  --> escalates to model tier
```
```
170407 Collards, cooked, boiled, drained, without salt  33.0 kcal  2.7 prot  4.0 fibre  380 vitA
2709579 Collards, NS as to form, cooked                 58.0       3.1       4.2        260
```

Neither is on the list. Upheld, and the strongest genuine finding in §2.

### C.3 §2.5 offal — largely dissolves too

```
=== label='lung' terms='beef lung, cooked' state='cooked'
  BLOCK 0.302  168629 Beef, variety meats and by-products, lungs, cooked, braised
  --> escalates to model tier
```

The right row is in the top five. `oxtail` likewise heads its own list
(`Beef, oxtails` 0.524). The "0.091" and "0.119" numbers are true of the bare
word and not of the resolve path. The `variety meats and by-products` length
penalty is real; the damage attributed to it is not.

## D. Three factual errors

### D.1 §1.6 — the avocado tie is decided by `precedence`, not by "the ordering tail"

The audit writes "`avocado` is a **tie at 0.667** decided by the ordering tail".
It is not. The sort key is `(-sim, precedence)` (`parse.py:355`), the tie is
exact, and precedence decides it deterministically:

```
fdc_id | description  | data_type       | precedence | similarity(description,'avocado')
173573 | Oil, avocado | sr_legacy_food  | 2          | 0.6666667
2709223| Avocado, raw | survey_fndds_food | 3        | 0.6666667
```

This matters twice over. It makes the bug reproducible and fixable rather than
incidental. And it is a **direct counterexample to a claim recorded in
CLAUDE.md and RECONCILED §1** — "precedence never decides anything… it is only
used to break an exact tie in a float, which does not occur". It does occur, it
decides, and here it ranks a refined oil (884 kcal) above the whole fruit
(160 kcal). That belongs in the audit's structural section and is not in it.

### D.2 §6 "What actually works" is probe output, not resolver behaviour

The audit's own §0 warns the next reader not to confuse the two, then §6 does
exactly that — and §6 is offered as a regression baseline ("worth recording so
the fixes do not break it"). At least two of its twenty-two rows are wrong
about production:

```
=== label='boiled plantain' state='cooked'
  BLOCK 0.625  168216 Plantains, green, boiled   unreq='green'
  --> escalates to model tier

=== label='hibiscus tea'
  BLOCK 0.812 2710503 Tea, hot, hibiscus         unreq='hot'
  --> escalates to model tier
```

Both are listed as `auto`. Both are blocked by `unrequested_qualifier` and
escalate. The outcomes are *fine* — but a baseline that misstates current
behaviour cannot detect a regression against it. (I re-checked the rest:
`amaranth leaves`, `sweet potato leaves`, `roselle`, `goat`, `millet` do
auto-match as claimed.)

### D.3 §5 — the biltong arithmetic does not support its own conclusion

```
170604 Beef, cured, dried                     153.0 kcal  31.1 prot   1.9 fat  2790 Na  2.7 sug
2705860 Beef jerky                            410.0       33.2       25.6     1785 Na  (2000 NULL)
167536 Snacks, beef jerky, chopped and formed 410.0       33.2       25.6     1785 Na   9.0 sug
```

The audit states biltong "runs 250–350" and that "`Beef jerky` is closer on
energy". At the bottom of its own stated range it is not: |250−153| = 97 against
|250−410| = 160. The cured/dried row is the closer of the two for lean biltong,
which is what most biltong is. Separately, the "9 g sugar" figure belongs to
`Snacks, beef jerky, chopped and formed` (167536); the row the audit names,
`Beef jerky` (2705860), reports **no** sugar value at all — so the caveat is
sourced from a row the recommendation is not about. The conclusion (don't map
it) survives; the reasoning offered for it does not.

## E. The structural cause §1 has and the audit never names

`unrequested_qualifier` assumes USDA writes `Food, qualifier, qualifier`. FNDDS
and SR very often write the **opposite** shape: `<DishClass>, <food>`. The guard
is blind to that shape by construction (`parse.py:551-555`) — a first segment
that shares *no* word with the query is skipped, because blocking it once
promoted `Spaghetti squash` and the fix was to treat a non-echoing head as "a
different food, judged by similarity like anything else".

Similarity does not judge it. It rewards it, because the dish word is short.
The asymmetry is visible in one run:

```
=== label='sweet potato' state='cooked'
  AUTO  0.812 2708012 Pie, sweet potato          <- head segment "Pie": invisible
  BLOCK 0.722 2710308 Sweet potato paste         unreq='Sweet potato paste'
  BLOCK 0.722 2709715 Sweet potato tots          unreq='Sweet potato tots'
  PASS  0.684 2707648 Bread, sweet potato        <- head segment "Bread": invisible
```

`paste` and `tots` are caught; `Pie` and `Bread` are not, and they are the
larger errors. **Five of the audit's ten surviving auto-matches are this one
shape**: `Oil, palm`, `Oil, avocado`, `Pie, pumpkin`, `Pie, sweet potato`,
`Flour, rice, brown` — and `Peanut butter` beating `Soup, peanut` is the same
fact from the other side. The exposure is not small:

```
head        rows        head      rows
Beverages    278        Cake        56
Soup         231        Sauce       52
Bread        192        Pie         50
Cheese       162        Muffin      34
Snacks       144        Flour       28
Cookie        95        Stew        17
Cereals       85        ...
Oil           84
```

A fourth guard is the honest answer, and it is narrower than the rule that was
withdrawn: **a first segment drawn from a closed list of dish-class nouns, when
the query names none of them, disqualifies an auto-match** (escalate, do not
reject). It cannot resurrect the `Spaghetti squash` failure, because "squash" is
not a dish class. This belongs in §7 and is absent from it.

By contrast, §7's own first recommendation — "a query that prefixes a
candidate's first segment cannot be scored weak" — buys much less than claimed,
because per §C those cases already reach the model tier with the right row.

## F. What the audit missed — probed, and they fail

912 terms is a lot and these are not obscure.

### F.1 `dried crayfish` -> `Crayfish, fried` — AUTO, and it is a vocabulary trap

The domain's own bresaola. Nigerian/Ghanaian "crayfish" is **dried ground
shrimp or prawn**, sold as a seasoning powder — not *Procambarus*. It is in egusi
soup, okra soup, moi moi, pepper soup and jollof.

```
=== label='dried crayfish' terms=None state='as_sold'
  AUTO  0.667  2706347 Crayfish, fried
  BLOCK 0.500  2706348 Crayfish, cooked   below-gate(0.500)
  --> AUTO 2706347 Crayfish, fried
```
```
2706347 Crayfish, fried  223.0 kcal  14.1 prot  12.9 fat   387 Na
2706366 Shrimp, dried    250.0       51.0        3.4      2175 Na    <- the right row
```

Protein 14 against 51, fat 12.9 against 3.4, and **sodium 387 against 2,175**
on the one ingredient in the pot that is there for salt and umami. Energy is
within 12%, so the Atwater cross-check passes and nothing raises. And it caches
an alias.

Guard check: `state_conflicts` blocks it **only** if the model emits
`state="dry"` (`Crayfish, fried` matches `_COOKED_WORDS`). With `as_sold`,
`unknown` or `None` — the honest reading of a powder in a jar — it goes
straight through. `Shrimp, dried` (2706366) auto-matches `dried shrimp` at
1.000, which the audit lists in §6: the right row is one word away and
unreachable. Same gap as its own `groundnut` finding, and it is an `auto`
rather than a `weak`.

### F.2 `millet` (state `dry`) -> `Millet` = the cooked grain — and §6 calls this working

```
2708377 Millet         118.0 kcal   3.5 prot   1.0 fat  23.6 carb   168 Na   <- FNDDS, cooked
169702  Millet, raw    378.0        11.0       4.2      72.8          5 Na
168871  Millet, cooked 119.0
```

```
=== label='millet' terms='millet, dry grain' state='dry'
  AUTO  1.000  2708377 Millet
  PASS  0.636   169702 Millet, raw
  --> AUTO 2708377 Millet
```

`Millet` says neither "cooked" nor "dry", so `state_conflicts` has nothing to
contradict — **precisely the audit's own §1.2 sorghum mechanism**, in a term it
files under "What actually works". 100 g of dry millet weighed out for uji or
ogi logs 118 kcal instead of 378. It is §1.1's couscous inverted: same shape,
opposite direction, and the mirror image is what makes it invisible to a reader
who has just read §1.1.

### F.3 `white yam`, `fried yam`, `pounded yam` — the yam disappears

```
weak  white yam    0.429  Wine, white
none  pounded yam  -      (nothing)
weak  fried yam    0.400  Tofu, fried
```
```
=== label='white yam' terms='white yam, boiled' state='cooked'
  0.429 Wine, white | 0.375 Bread, white | 0.375 Icing, white
  0.375 Chili, white | 0.333 White Russian
  --> escalates to model tier
=== label='fried yam' terms='fried yam, dundun' state='cooked'
  0.400 Tofu, fried | 0.400 Dove, fried | 0.400 Fried okra
  0.400 Clams, fried | 0.368 Ice cream, fried
  --> escalates to model tier
```

`Yam, cooked, boiled, drained, or baked, without salt` (170072, 116 kcal) and
`Yam, raw` (170071) exist. **Neither appears in either candidate list.** The
qualifier — the ordinary Nigerian way of naming it — captures the whole query
and the food is lost. Bare `yam` resolves fine (`ask`, `Yam, raw` 0.500), which
is why a term-list audit misses this: you have to probe the phrase people type.
The audit's §2.2 documents this exact mechanism for `garden eggs` and never
tests yam, the single most-eaten West African staple after cassava.

### F.4 `palm wine` — a whole beverage class, absent, and not filed

```
=== label='palm wine' terms='palm wine, fermented palm sap' state='as_sold'
  0.357 Oil, palm | 0.357 Wine, red | 0.333 Wine, white | 0.333 Wine, rose | 0.333 Wine, rice
  --> escalates to model tier
```

Escalates, so not dangerous — but the model is offered grape wine (83 kcal,
10.6 g alcohol) and palm oil for a drink that is roughly 35–45 kcal and 2–5%
ABV, drunk by the litre. §3's list of "no row and no near neighbour" should
carry it, along with `tej`, `tella`, `zobo`/`sobolo`/`bissap`, `kunu` and
`mageu` — all `none`, none of them mentioned.

### F.5 Others confirmed `none`, absent from §3

`gari`/`garri`, `eba`, `amala`, `banku`, `kenkey`, `moi moi`, `pounded yam`,
`yam porridge`, `matoke`, `githeri`, `amasi`, `nyama choma`, `kachumbari`,
`mandazi`, `chin chin`, `boerewors`, `attieke`, `alloco`, `mafe`, `yassa`,
`merguez`, `shiro`, `misir wat`, `tibs`, `kitfo`, `gomen`, `doro wat`, `ponmo`,
`shaki`, `kilishi`, `bitter leaf`. §3 covers North African dish names
exhaustively and West/East African ones barely; `gari` and `eba` are to Ghana
and Nigeria what `ugali` is to Kenya and get no mention.

## G. Confidence and over-breadth

- **§2.4 `cocoyam` -> `Taro, cooked`: honestly medium, not a synonym.**
  `Yautia (tannier), raw` (169401, 98 kcal, 1.5 fibre) is in this database and
  the audit never mentions it. In Nigeria and Ghana "cocoyam" covers both
  *Colocasia* (taro, 169308 raw 112 kcal, 4.1 fibre) and *Xanthosoma* (yautia).
  The energy gap is small; the fibre gap is 2.7x. Escalate-with-both-candidates
  is right; a cached synonym is not.
- **§4 doro wat "the butter is the calorie term"** overstates it, and rests on
  the ghee claim that C.1 overturns.
- **§3 vs §4 disagree on ugali.** §3 says 110–130 kcal/100 g; §4 says 25–33 g
  dry per 100 g, which at ~370 kcal/100 g dry is 92–122. The "understates by
  about half" line holds at the thick end (58 vs 122 = 2.1x) and is 1.6x at the
  thin end. Small, but the two numbers are in the same document.
- **§1.4 akara at "7–8 g protein"** is low; cowpea-paste akara is usually
  9–13 g. The finding is unaffected — `Bean cake` at 5.8 g protein and 49.9 g
  carbohydrate is the wrong shape either way.
- Nothing in the audit is over-broad in the `halloumi -> cheese` sense. §5 is
  the strongest section in the document and I would not change a line of it
  except the biltong arithmetic (D.3).

## H. Scoreboard

- Claimed dangerous autos: **10**. Surviving all three guards in a faithful
  replay: **10**. Caught by the guards already: **0** — the audit's §0 method
  note did its job and I could not overturn a single one.
- Findings overturned or materially downgraded: **7** (§2.1 ghee entirely;
  §2.1 injera/teff/fonio downgraded to correct-via-model-tier; §2.2 garden eggs,
  §2.2 maize meal, §2.3 cowpeas dissolve with `search_terms`; §2.5 offal
  downgraded).
- Factual errors: **3** (avocado tie mechanism; §6 baseline wrong for
  `boiled plantain` and `hibiscus tea`; biltong arithmetic and sourcing).
- Missed and demonstrated failing: **`dried crayfish` (auto, wrong)**,
  **`millet` dry (auto, 3.2x, listed as working)**, `white yam` / `fried yam` /
  `pounded yam`, `palm wine`, and ~30 further `none` terms.
- Missed structural cause: the `<DishClass>, <food>` head, which explains five
  of the ten upheld autos and is absent from §7.
