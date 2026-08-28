# CRITIQUE-middle-east-central-asia-america

28 Aug 2026. Critic pass over `docs/knowledge/AUDIT-middle-east-central-asia-america.md`.
Read-only. No integration suite. Probe output and read-only SELECTs only.

Status: complete. Guard replay, nutrient SELECTs and re-probes all run against the live database on 28 Aug 2026.

## Method

Two instruments beyond the probe:

1. **A guard replay.** `scripts/probe_knowledge.py` measures `db.search_foods`
   alone. Production adds `inverts_meaning`, `state_conflicts`,
   `unrequested_qualifier` and `label_absent`, and — this is the part the audit
   never accounts for — `resolve_items` takes the first candidate that clears
   `AUTO_MATCH_SIMILARITY` **and** survives all four, not the head. I replayed
   that selection verbatim against live `search_foods` output for every claimed
   auto-match.
2. **Read-only `SELECT`s** against `food_nutrient` for every substitution the
   audit proposes, quoted per 100 g.

## Part 1 — the guard check. Three of the six "wrong_confident_match" findings do not happen

The audit's headline claim is that six findings (F11, F12, F17, F18, F19, F22)
are wrong-confident matches. F11 and F12 are `weak` by the audit's own output,
so they escalate and were never autos. Of the four genuine `auto` claims, **two
are blocked in production and one names the wrong row.**

### C1 — F17 is OVERTURNED. `white rice cooked` does not auto-match glutinous rice

The audit calls this "the worst finding in this audit". Guard replay, live:

```
=== 'white rice cooked'
   0.643  Rice, white, cooked, glutinous          qual:glutinous
   0.600  Rice, white, cooked, no added fat       below_gate
   0.581  Rice, white, cooked, made with oil      below_gate
   0.562  Rice, white, cooked, as ingredient      below_gate
   -> production: escalates to model tier
```

`unrequested_qualifier` fires on segment 3, `glutinous`: the description's first
segment (`Rice`) echoes the query and adds nothing, segment 1 (`white`) is in
the query, segment 2 (`cooked`) is exempt preparation, and segment 3 contributes
a word the user never typed. That is the *exact* case the guard was written for
— it is `Spaghetti, spinach, cooked` with a different noun. No candidate below
it clears 0.62, so the item goes to the model tier with the correct row second
on the list.

Consequence for the audit: the claimed 26% energy undercount never occurs, **no
alias is cached**, and the row the proposals table calls "the highest-value
single entry" is buying an escalation that already happens. The mapping is not
harmful, but its stated justification is false and its priority is wrong.

Identical result for `cooked white rice`, and with `state="cooked"` supplied.

### C2 — F18 is OVERTURNED. `hot sauce` does not auto-match `Hot Thai sauce`

```
=== 'hot sauce'
   0.667  Hot Thai sauce            qual:Hot Thai sauce   <- BLOCKED on "Thai"
   0.588  Hot pepper sauce          below_gate
   0.533  Hoisin sauce              below_gate
   -> production: escalates to model tier
```

Single-segment description, `i == 0`: it shares `hot` and `sauce` with the query
and adds `thai`, which is the narrowing case the first-segment rule exists to
catch. The 3.2x sodium error the audit describes (2055 vs 633 mg/100 g,
confirmed) is real *as a ranking fact* and does not reach a log. Escalation with
`Hot pepper sauce` on the candidate list is the system working.

### C3 — F19 is OVERTURNED twice: the head is not the soup, and the two rows barely differ

Re-probed three times, deterministic:

```
auto  seaweed   0.667  Seaweed, raw
```

`Seaweed, raw` (2709805) is the head; `Soup, seaweed` ties at 0.667 and sits
second. Guard replay confirms production auto-matches **`Seaweed, raw` — the row
the audit says is correct**. The audit's quoted candidate list has the two
reversed, and its "Provenance note" claims all headline results were re-probed
at the end and "every one reproduced identically". That claim does not hold for
F19.

The stated consequence is wrong too. Per 100 g, from `food_nutrient`:

```
Seaweed, raw    kcal 41   fat 0.49   pro 3.51   carb 7.94   Ca 129
Soup, seaweed   kcal 37   fat 1.87   pro 3.73   carb 1.52   Ca  20
```

"A soup is mostly water, so 10 g of nori logged as seaweed soup is
nutritionally nothing" is not what the numbers say — the energy figures are
within 10%. The real divergence is calcium (6.5x) and carbohydrate. Note also
that FNDDS `Seaweed, raw` is fresh/rehydrated weed, not dried nori, so the
audit's own worked example (10 g of nori) is against the wrong row in either
case.

### C4 — F22 is UPHELD, and it is the only surviving dangerous auto the audit found

```
=== 'sweet potato'
   0.812  Pie, sweet potato     SURVIVES     <- taken
   0.765  Sweet potato, NFS     SURVIVES
=== 'sweet potatoes'
   0.632  Pie, sweet potato     SURVIVES     <- taken
   0.600  Sweet potato, NFS     below_gate
```

No guard fires. `unrequested_qualifier` cannot see it: `Pie` is segment 0 and
shares no word with the query, so the first-segment rule skips it by design
(the rule that stopped `Spaghetti squash` being promoted is what lets `Pie`
through here), and segment 1 is `sweet potato` verbatim. `label_absent` passes
because both query words are present.

```
Pie, sweet potato   kcal 269  fat 9.75  carb 41.08  sugar 25.16
Sweet potato, NFS   kcal 115  fat 4.53  carb 17.14
```

2.3x energy, 2.4x carbohydrate, and 25 g of sugar invented per 100 g on a plain
vegetable — with an alias written and never re-checked. Confirmed on both
singular and plural. **This is the finding the audit should have led with**, and
the proposals table is right to demand it displace the pie.

Guard tally on claimed autos: **reviewed 4, blocked by guards 2, wrong row 1,
survives 1.**

## Part 2 — proposals that are culinarily or nutritionally wrong

### C5 — `hog jowl`, `jowl bacon` -> **fresh** jowl is the cured/fresh trap, at 107x sodium

Proposed at **high**: `hog jowl`, `pork jowl`, `jowl bacon` -> `Pork, fresh,
variety meats and by-products, jowl`. Per 100 g:

```
168269  Pork, fresh, variety meats and by-products, jowl, raw   kcal 655  fat 69.6  Na    25
168287  Pork, cured, salt pork, raw                             kcal 748  fat 80.5  Na  2684
```

`jowl bacon` is by its name a **cured, smoked** product, and hog jowl in the
use the audit itself cites — seasoning hoppin' john and a pot of greens — is
smoked jowl, not fresh. Mapping it onto the fresh row understates sodium by a
factor of **107** on a food used specifically as a salt-and-fat seasoning. The
audit's own F25 probe found `cured pork jowl` -> `Pork, cured, salt pork, raw`
at 0.440, i.e. the right target was on screen and was not used.

Verdict: **overturn as written.** Split the surfaces —
`hog jowl` / `jowl bacon` / `smoked jowl` -> `168287 Pork, cured, salt pork`
(medium: salt pork is belly, not cheek, but it is the right *cure and salt
level*, which is what the mapping exists to supply); `fresh pork jowl` ->
`168269` (high). A single high-confidence mapping across both senses is the
guanciale-vs-pancetta error in American clothes.

### C6 — `country ham` -> `Ham` is confidence inflation on a ceilinged nutrient

```
2705878  Ham   kcal 117  fat -  pro -  Na 1149
```

USDA has **no** country ham row (the only match on the string is the QUAKER
grits flavouring the audit correctly rejects). Country ham is dry-cured and
runs roughly 2,300-2,600 mg sodium per 100 g, so the fallback halves it. The
audit says so in its own rationale — "the sodium figure is understated by the
fallback" — and then marks the row **high**. That is exactly the size of error
for which it rejected `labneh` ("a systematic ~2x undercount"). Sodium is a
targeted ceiling nutrient here.

Verdict: **downgrade to medium.** The target is better than a dry cereal mix;
the confidence is not defensible.

### C7 — the flatbread bucket is over-broad, and USDA has the row it needs

Proposed at medium: `lavash`, `khubz`, `khobz`, `taftoon`, `regag`,
`lepyoshka`, `non` -> `Bread, pita, white, enriched`.

```
174915  Bread, pita, white, enriched   kcal 275  fat 1.20  pro  9.10  carb 55.7
2707613 Bread, naan                    kcal 311  fat 7.28  pro 11.09  carb 50.2
```

`Bread, naan` exists and the audit never probed it (`naan` -> `ask 0.455
Bread, naan`). Uzbek `non` and Afghan naan are thick tandoor breads enriched
with fat and often milk; lavash, taftoon and ragag are lean sheet breads. Pita
is right for the lean half and understates fat **6x** for the enriched half.
Lumping them is the "halloumi -> cheese" failure at smaller scale.

Verdict: **split.** `lavash`, `taftoon`, `khubz`, `ragag` -> pita (medium);
`non`, `nan`, `naan` -> `2707613 Bread, naan` (medium).

### C8 — `mutton` at **high** ignores that mutton means goat in half the domain

The audit's own rationale says mutton is "the default meat across Gulf, Yemeni,
Afghan and **South Asian** cooking" — and in South Asian and much Gulf English,
`mutton` on a menu is **goat**, not adult sheep. USDA carries both:

```
167634  Mutton, cooked, roasted (Navajo)  kcal 234  fat 11.09  pro 33.43
        Game meat, goat, raw              (the audit itself probed: ask 0.529)
```

Sheep and goat differ materially in fat. A `high` synonym asserts this is
beyond dispute by a competent cook; it is variant-dependent by region.

Verdict: **downgrade to medium**, or make it a disambiguation rather than a
synonym.

### C9 — three dish_ingredient decompositions verified *reachability* and called it correctness

This is a method error, not a typo, and it repeats:

- **`mujadara`** — "Components all auto or ask. `lentils` auto 0.667". That auto
  lands on **`Lentils, dry`, 360 kcal / 100 g**, against `Lentils, NFS` at 166.
  See C11.
- **`harees` / `halim` / `haleem`** — "`cracked wheat` and `pearl barley` both
  reachable". `cracked wheat` auto-matches **`Roll, wheat or cracked wheat`** —
  a bread roll, 273 kcal, 524 mg sodium — not a grain. See C12.
- **`fesenjan`** — component given as "pomegranate juice/**molasses**", with
  only `pomegranate juice` verified (auto 0.818). Pomegranate molasses is juice
  reduced roughly sevenfold; `pomegranate molasses` probes to `ask 0.480
  Pomegranate, raw` and USDA has no molasses row. Writing the two as one
  component logs a syrup as a juice.
- **`ghormeh sabzi`** — components "verified" but `dried lime` was not among
  them: it probes to `ask 0.471 **Litchis, dried**`. Also, the defining herb of
  ghormeh sabzi is dried **fenugreek** leaf (shanbalileh), which the
  decomposition omits entirely; `dried fenugreek leaves` -> `weak 0.375 Spices,
  fenugreek seed` (seed, not leaf).

Verdict: **downgrade all four to medium-with-caveats** and re-verify each
component against the row it actually lands on, not merely against its verdict.

### C10 — the `polenta` rejection is wrong on both of its premises

Rejected with: "polenta returns nothing today and should keep doing so **until a
cornmeal-mush row is identified**", and "grits are hominy — nixtamalised,
lime-treated corn ... the two rows differ on the nutrients the mapping would
exist to supply" (niacin, calcium).

Both premises are false against this database.

USDA has three cornmeal-mush rows:

```
2708373  Cornmeal mush, NS as to fat
2708374  Cornmeal mush, no added fat
2708375  Cornmeal mush, fat added
```

And grits do not differ from them on the named nutrients:

```
                              kcal  fat   pro   carb   niacin  calcium
Grits, NFS                     71   1.84  1.19  12.20   0.62      4
Cornmeal mush, fat added       71   1.84  1.11  12.25   —         4
Cornmeal mush, no added fat    58   0.28  1.12  12.47   0.70      4
```

Identical to two decimal places on energy and fat, and calcium is 4 mg in both
— i.e. commercial "grits" here are degerminated ground corn, not lime-treated
hominy. (The row that *is* different is `Grits, instant, made with water`:
niacin 1.62, calcium 74, iron 7.33 — and that is **enrichment**, not
nixtamalisation.)

Verdict: **overturn the rejection.** `polenta` -> `2708374 Cornmeal mush, no
added fat` (high), `polenta with butter/cheese` -> `2708375` (medium).

## Part 3 — what the audit missed. Five surviving dangerous auto-matches

Every one below was probed, then guard-replayed, and **auto-matches in
production with an alias cached**. None appears anywhere in the audit.

### C11 — the dry/cooked staple class. `bulgur`, `couscous`, `lentils`

```
auto  bulgur     0.636  Bulgur, dry      SURVIVES all guards
auto  couscous   0.636  Couscous, dry    SURVIVES all guards
auto  lentils    0.667  Lentils, dry     SURVIVES all guards
```

Per 100 g:

```
Bulgur, dry      342   Bulgur, cooked    83     4.1x
Couscous, dry    376   Couscous, cooked 112     3.4x
Lentils, dry     360   Lentils, NFS     166     2.2x
```

`unrequested_qualifier` cannot fire — `dry` is in the preparation-exempt set, by
design, because that is `state_conflicts`' job — and `state_conflicts` only
fires if the parse actually declares `state="cooked"`. With `state="cooked"`
supplied, `bulgur` correctly escalates and `lentils` correctly moves to
`Lentils, NFS`; with the state unstated, all three take the dry row silently.

This is the audit's own F16 grits argument ("the guard is documented to treat
silence as no evidence") — but the audit only ever found it at `weak`, where it
escalates and is harmless. Here it is `auto`, so it caches. Bulgur is the grain
of tabbouleh, kibbeh and Gulf jareesh; lentils are the whole of mujadara and
adas polo. These are the highest-volume in-domain staples in the audit.

Proposed: `bulgur`, `bulghur`, `burghul` -> `170287 Bulgur, cooked`;
`lentils`, `adas` -> `2707423 Lentils, NFS`; `couscous` -> `169700 Couscous,
cooked` — all **high**, all as displacements of a dry row.

### C12 — `cracked wheat` auto-matches a **bread roll**

```
auto  cracked wheat  0.636  Roll, wheat or cracked wheat   SURVIVES all guards
```

```
2707746  Roll, wheat or cracked wheat   kcal 273  fat 6.30  carb 46   Na 524
170287   Bulgur, cooked                 kcal  83  fat 0.24  carb 18.6 Na   5
```

3.3x energy and **100x sodium**, and it is a different food category — bread,
not grain. `label_absent` passes (both query words are in the description) and
`unrequested_qualifier` skips segment 0 (`Roll` shares nothing with the query,
so the first-segment rule declines to judge it — the same mechanism that lets
`Pie, sweet potato` through in C4).

Cracked wheat is the base of harees, jareesh and keshkek. The audit proposed
harees as a `cracked wheat + meat + ghee` decomposition on the strength of the
word being "reachable".

Proposed: `cracked wheat`, `jareesh`, `harees wheat` -> `170287 Bulgur, cooked`
(high; cracked wheat and bulgur differ by parboiling, not by composition).

### C13 — `grape leaves` auto-matches the **raw** leaf; dolma uses the brined one

```
auto  grape leaves  0.765  Grape leaves, raw   SURVIVES all guards
```

```
168575  Grape leaves, raw      kcal 93  pro 5.60  Na     9
169393  Grape leaves, canned   kcal 69  pro 4.27  Na  2853
```

**317x sodium.** Vine leaves are sold brined and are essentially never used
fresh outside the few weeks they are on the vine; dolmeh, warak enab and yalanji
are all made from the canned/brined leaf. Same fresh-vs-cured shape as C5.

Proposed: `grape leaves`, `vine leaves`, `warak enab` -> `169393 Grape leaves,
canned` (high).

### C14 — `steak sandwich` auto-matches the raw filling and drops the bread

The audit noticed this in its closing Notes as an illustration of "short beats
long" and never filed it as a finding or guard-checked it. It survives:

```
auto  steak sandwich  0.737  Beef, sandwich steak   SURVIVES all guards
```

```
2705852  Beef, sandwich steak                   kcal 326  fat 27.59  carb  0     Na 359
2706960  Cheese steak sandwich or sub on white  kcal 270  fat 12.03  carb 21.48  Na 527
```

The whole roll disappears (21.5 g carbohydrate to zero) and fat density more
than doubles. Note this is the *opposite* direction from the audit's F12
`cheesesteak` finding and lands in the same meal, so a proposal that fixes only
the closed compound leaves the open one confidently wrong.

Proposed: `steak sandwich` (no cheese stated) -> `2706958 Steak sandwich or sub
on white` (high), alongside the audit's existing `cheesesteak` entry.

### C15 — smaller misses, recorded without proposals

```
ask   dried lime          0.471  Litchis, dried        <- limoo omani; lychee sugar ~66 g/100 g
ask   mint                0.455  Candy, mint           <- Persian/Levantine staple herb -> confectionery
ask   date syrup          0.455  Date                  <- silan; a syrup, not a fruit
weak  rose water          0.400  Wine, rose            <- an alcoholic drink for a flavouring
weak  turkish delight     0.348  Coffee, Turkish
weak  sweet tea           0.438  Tamale, sweet         <- the Southern US drink
none  halloumi, harissa, fattoush, baba ganoush, ful medames, kofta, shawarma,
      dolma, sujuk, basturma/pastirma, freekeh, halva/halvah, laban, goetta,
      quahog, whoopie pie, poke bowl, hot links
```

All escalate, so none is dangerous; they are recorded because the audit's
"Persian is an entity void" framing under-counts the Levantine-Gulf overlap
(`harissa`, `fattoush`, `baba ganoush`, `ful medames` are all zero-row and none
was tested).

`basturma` / `pastirma` deserves its own line as the domain's bresaola: an
air-dried, fenugreek-crusted **beef** cure. It returns nothing today, which is
correct; if anyone later proposes it, the trap is that `pastrami` (a different,
brined-and-smoked product) auto-matches `Pastrami, NFS` at 0.692 and looks like
a spelling variant of it. It is not.

## Summary of the guard check

| audit finding | claimed | production |
|---|---|---|
| F17 white rice -> glutinous | dangerous auto, "worst in this audit" | **blocked** by `unrequested_qualifier`; escalates |
| F18 hot sauce -> Hot Thai sauce | dangerous auto | **blocked** by `unrequested_qualifier`; escalates |
| F19 seaweed -> Soup, seaweed | dangerous auto | **wrong row**: head is `Seaweed, raw`, which is the audit's own expected answer |
| F22 sweet potato -> Pie, sweet potato | dangerous auto | **upheld**, singular and plural |
| F11 clam chowder, F12 cheesesteak | listed as wrong_confident_match | both `weak` by the audit's own output; they escalate |

Two of four claimed autos are already handled by the guards the audit did not
apply, and one names the wrong row. The audit found **one** real dangerous
auto-match; this critique adds **five** it did not test.
