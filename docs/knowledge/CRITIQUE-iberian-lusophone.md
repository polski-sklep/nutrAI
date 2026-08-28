# Critique — Iberian / Lusophone knowledge audit

28 Aug 2026. Review of `docs/knowledge/AUDIT-iberian-lusophone.md`.

46 claims and proposals examined. **30 upheld, 8 downgraded, 8 overturned.**
Every probe line and every nutrient figure below was re-run today against the
live database; nothing is quoted from the audit on trust.

The audit is careful, well-measured and mostly right. Its three headline
auto-matches are real and survive the resolver's guards. But it has one
methodological hole that inflates roughly a third of §2, one wrong substitute
proposed while the exact USDA row sat in the database, one arithmetically
impossible nutrient figure, and it applies its own best principle — salted vs
fresh — to bacalhau and then breaks it for boquerones.

---

## A. The guard check

The brief's most important question: of the auto-matches the audit calls
dangerous, which survive `state_conflicts`, `unrequested_qualifier` and
`label_absent` in `resolve_items`?

Method: `/tmp/gcheck.py` calls `db.search_foods(label)` for the candidates
(same as the probe) and then applies `inverts_meaning`, `state_conflicts`,
`unrequested_qualifier` and `label_absent` exactly as `resolve_items` does,
taking the best surviving candidate at or above `AUTO_MATCH_SIMILARITY`.

| claimed auto | production outcome |
|---|---|
| `chorizo` → `Chorizo` 1.000 | **AUTO survives** (all three guards pass, any state) |
| `octopus` → `Octopus` 1.000 | **AUTO survives** |
| `chicken` → `Fat, chicken` 0.667 | **AUTO survives** |
| `turkey` → `Fat, turkey` 0.636 | **AUTO survives** |
| `pimiento rojo` → `Pimiento` 0.643 | **AUTO survives** |
| `sweet potato` → `Pie, sweet potato` 0.812 | **AUTO survives** |
| `sweet bread` → `Bread, sweet potato` 0.632 | **AUTO survives** |
| `custard tart` → `Custard` 0.667 | **AUTO survives** |
| `cold vegetable soup` → `Soup, vegetable` 0.750 | **AUTO survives** |
| `cold tomato soup` → `Soup, tomato` 0.706 | **AUTO survives** |
| `broccoli rabe` → `Broccoli, raw` 0.688 | **caught — conditionally** |

**10 of 11 survive.** The audit does not overstate its headline.

The one catch is worth stating precisely because it is *not* a clean win:

    === 'broccoli rabe' state='cooked'
      0.688 Broccoli, raw    blocked:state_conflicts:raw
      0.579 Broccoli raab, raw  blocked:below-gate,unrequested_qualifier:Broccoli raab
      -> ESCALATES to model tier

    === 'broccoli rabe' state=None
      0.688 Broccoli, raw    AUTO
      -> AUTO (321900, 'Broccoli, raw', 0.688)

`state_conflicts` only fires because grelos are always eaten cooked and the
parse would say so. With the state unstated the auto-match stands. So the
guard mitigates this case rather than closing it, and the audit's framing was
not wrong — but its confidence should be "escalates when the state is stated",
not "auto".

Two things the guards do **not** do, which the audit did not test and which
matter more than the catch above:

- **`unrequested_qualifier` blocks the correct row.** On `broccoli rabe`, the
  right USDA row is `Broccoli raab, raw` (170381) — and the guard flags its
  first segment `Broccoli raab` as an unrequested qualifier because the query
  says *rabe* and the row says *raab*. It is below the gate anyway today, but
  if similarity ever improved the guard would keep blocking the correct answer.
- **The three guards are silent on every one of the audit's `weak`/`none`
  findings**, because they only run on candidates at or above the gate. Guards
  are not a defence against §2 at all, and the audit does not claim they are.

---

## B. Overturned

### B1. "The FNDDS `Chorizo` row is raw in the Mexican sense" — false, and the audit's own numbers say so

§1.1 argues the identity error is compounded by a state error: *"It is also a
raw food in the Mexican sense — it must be cooked."* Re-measured:

    2706179 | survey_fndds_food | Chorizo                                        | 341 | 19.3 | 28.1 | 2.6 |  983
    332864  | foundation_food   | Sausage, pork, chorizo, ... cooked, pan-fried  | 346 | 19.3 | 28.1 | 2.6 |  983
    173859  | sr_legacy_food    | Sausage, pork, chorizo, ... raw                | 296 | 13.6 | 25.1 | 3.8 |  788

FNDDS `Chorizo` is protein-for-protein, fat-for-fat, sodium-for-sodium the
**cooked pan-fried** Foundation row. It is not raw. The identity finding
(Mexican fresh chorizo ≠ Spanish cured chorizo) stands and is the important
one; the state claim layered on top of it is wrong and should be struck, since
it is the kind of secondary claim that gets copied forward into a mapping note.

### B2. `grelos` → Collards, when USDA holds the exact plant

§1.5 and the §4 refusals table both propose `Collards, raw` for *grelos* /
*couve-nabiça*, reasoning that "*Brassica rapa* leaf ≠ broccoli floret". The
premise is right and the conclusion swaps one species error for another:
collards are *Brassica oleracea*. USDA has the actual plant:

    170381 | sr_legacy_food    | Broccoli raab, raw     | 22 | 3.2 | 0.5 | 2.9 |  33
    170382 | sr_legacy_food    | Broccoli raab, cooked  | 25 | 3.8 | 0.5 | 3.1 |  56
    2709573| survey_fndds_food | Broccoli raab, cooked  | 46 | 3.2 | 3.1 | 2.9 | 159
    170406 | sr_legacy_food    | Collards, raw          | 32 | 3.0 | 0.6 | 5.4 |  17

*Broccoli raab* / *cime di rapa* / *grelos* / *rapini* are the same
*Brassica rapa* ssp., and the audit's own §1.5 heading is "broccoli rabe". The
row appeared on its own candidate list at 0.579 and the audit did not report
it. `grelos → Broccoli raab, cooked` is a **high**-confidence identity mapping;
`grelos → Collards` should be withdrawn.

(The nutritional stake is small — all three rows are 22–46 kcal — which is
exactly why this needs saying now rather than after it is encoded: it is a free
correction from wrong species to right species.)

### B3. "The alias tier never gets to cache a right answer either" — false

§2.13 concludes that because `label_absent` blocks a Spanish label from
auto-matching an English row, "every single one of these costs a model call,
every time, forever". `resolve_items` contradicts this: the model tier ends
with

    await db.upsert_alias(user_id, label, int(pick["fdc_id"]), ...)

so `morcilla` costs one Haiku call **once per user**, and every later
`morcilla` resolves free at the alias tier. The correct statement is that these
cost one escalation each, not that they never cache. This matters because the
audit's recommendation 2 (a synonym tier) is partly justified by a recurring
cost that does not recur. The synonym tier is still worth building — it removes
the first call *and* the risk that the one cached answer is wrong — but the
argument has to be the risk, not the bill.

### B4. §2's central framing — "the correct row is not on the candidate list at all"

The audit measures with `probe_knowledge.py`, which searches the **label
alone**. `_candidates` pools the label *and* the model's `search_terms` and
ranks by whichever scored higher. `schemas.py` instructs the model to write
`search_terms` as plain American English. The audit knows this — it says so in
§2.13 — but does not carry the correction back into §2.1, §2.2, §2.3 or §2.7,
which are written as reachability failures. Measured through `_candidates`
with a plausible `search_terms`:

    morcilla      + "blood sausage, pork"          -> Blood sausage    0.737  (head)
    jamon serrano + "ham, dry-cured, prosciutto"   -> Ham, prosciutto  0.600  (head)
    salt cod      + "fish, cod, dried and salted"  -> Fish, cod, Atlantic, dried and salted  0.758 (head)
    anchoas       + "anchovy, canned in oil"       -> Fish, anchovy, european, canned in oil 0.449 (head)

So "the correct row is not on the candidate list at all; the head is a
completely unrelated emulsified pork sausage" (§2.1) is a statement about the
probe, not about production. In production the right row leads, `label_absent`
blocks the auto, and the item escalates with the correct candidate at the top
of the list — **the system working**, by the CLAUDE.md standard the audit
itself cites for `near_chicken_thigh_cooked`.

What survives, and should be the finding instead: the resolver's knowledge of
Iberian vocabulary is entirely borrowed from the parse model's prompt
compliance. Every §2 case is one model paraphrase away from silence, and there
is no test anywhere that fails if that instruction is dropped from
`schemas.py`. That is a real and sharper finding than the one filed.

One further methodological note the audit should carry: `_candidates` re-sorts
the pooled union by raw `sim` (`key=lambda c: (-sim, precedence)`), which
**discards** the FTS-coverage-first ordering `db.search_foods` applied. The
audit's measurement caveat says a low-scoring correct row is "right row, at the
head". That is true of the probe's output and not of the list the model tier
receives, where it is re-ranked by the score that put it last. `salt cod` alone
returns `Salt, table` 0.333, `Cape Cod` 0.308, then the correct row at 0.235.

### B5. `jamón ibérico ≈ 375 kcal, 43 g fat` is arithmetically impossible

§2.2. 43 g of fat is 387 kcal on its own, before any protein. The 43 is the
**protein** figure; ibérico de bellota is roughly 375 kcal / 43 g protein /
22 g fat. The conclusion — prosciutto (195 | 27.8 | 8.3) understates ibérico
badly — survives, and the multiple is ~2.6× on fat rather than "roughly twice",
but a mapping note carrying an impossible macro is a note that will be trusted
and propagated. Fix the number.

### B6. `boquerones` → `Fish, anchovy` breaks the audit's own salted/fresh rule

§2.9 maps `boquerones` to 2706232. That row is the canned-in-oil one:

    2706232 | survey_fndds_food | Fish, anchovy                                  | 210 | 28.9 | 9.7 | 3668
    174183  | sr_legacy_food    | Fish, anchovy, european, canned in oil, drained | 210 | 28.9 | 9.7 | 3668
    174182  | sr_legacy_food    | Fish, anchovy, european, raw                    | 131 | 20.4 | 4.8 |  104

*Boquerones* (white, vinegar-marinated or fried, fresh fish) and *anchoas*
(brown, salt-cured, packed in oil) are two different foods that the audit maps
to one row. Sodium is **35× apart**; fat is 2× apart. A 60 g plate of
boquerones en vinagre logged on 2706232 books 2,200 mg of sodium that was never
eaten — comparable in scale to the "751 mg from one invented word" turkey
failure in CLAUDE.md. §2.3 states the correct principle for bacalhau
("salted vs fresh matters more here than anywhere else") and then does not
apply it one section later. Split them: `anchoas → 174183` (high),
`boquerones → 174182` (high, with the fried/marinated preparation noted).

### B7. `jurel` / `carapau` → `Fish, mackerel` — not a mackerel, and ~4× the fat

§2.9 lists this as "approximate". It is worse than approximate.

    2706263 | survey_fndds_food | Fish, mackerel, NFS                    | 237 | 24.9 | 14.3 | 322
    173674  | sr_legacy_food    | Fish, mackerel, spanish, cooked, dry heat | 158 | 23.6 |  6.3 |  66
    175122  | sr_legacy_food    | Fish, mackerel, king, raw              | 105 | 20.3 |  2.0 | 158

*Jurel* / *carapau* is horse mackerel, *Trachurus trachurus* — family
Carangidae, not Scombridae. It is a lean fish at roughly 110–140 kcal and
2–5 g fat. Against `Fish, mackerel, NFS` that is a 2× energy and 3–7× fat
overstatement, in the domain where *carapau grelhado* is an everyday meal. This
is the domain's bresaola-is-beef case. Either map it to `Fish, mackerel,
king, raw` / `Fish, mackerel, spanish` at **medium** with the family error
stated, or refuse it. Do not encode it against the NFS row.

### B8. Spanish `chorizo` and Portuguese `chouriço` get two targets 116 kcal apart

§1.1 proposes `Salami, Italian, pork` (425 | 21.7 | 37.0 | 1890) for cured
Spanish chorizo. §3.2's table then routes `linguiça, chouriço` to
`Sausage, smoked link sausage, pork` (309 | 12.0 | 28.2 | 827).

Portuguese *chouriço* and Spanish *chorizo* are the same class of food: dry- or
semi-dry-cured, smoked, paprika-heavy pork sausage. Splitting them by the
language the user happened to type gives **116 kcal and 9.7 g of protein per
100 g** of difference for one sausage. *Linguiça* is genuinely wetter and
belongs on the smoked-link row; *chouriço* belongs with chorizo on the salami
row. Move `chouriço` and keep `linguiça` where it is.

---

## C. Downgraded

1. **`cold vegetable soup` and `cold tomato soup` (§1.5) are synthetic
   queries.** Both auto-match and both survive the guards, so they are
   technically correct findings — but nobody types "cold vegetable soup", and
   in production the model's `search_terms` for gazpacho would contain the word
   *gazpacho*, which resolves correctly on its own (`auto 0.643 Soup,
   gazpacho`). Low priority, not "a plain fallback defect".

2. **`salmorejo → Soup, gazpacho` is nutritionally 5× wrong and the audit does
   not say so.** §2.11 calls gazpacho salmorejo's "nearest relative … one row
   away, unreached", which reads as a mapping recommendation.

       2710106 | Soup, gazpacho | 26 | 0.8 | 0.6 | 4.5 | 208
       2709757 | Soup, tomato   | 19 | 0.7 | 0.4 | 3.6 | 244

   Salmorejo is tomato, bread and a substantial fraction of olive oil:
   ~130–160 kcal and ~10 g fat per 100 g. A 250 g bowl on 2710106 logs 65 kcal
   against ~350. Reachability is not the problem here; the row is. This belongs
   in §4 as a refusal, alongside membrillo, not in §2 as a near miss.
   (The same figure makes `gazpacho → Soup, gazpacho` a mild understatement for
   an Andalusian recipe with 10% olive oil — worth a note, not a finding.)

3. **`membrillo` was rejected too hard.** §3.4 rejects it because
   `Quinces, raw` (57 kcal) understates a set paste ~4×. Correct — but the
   database has a row that is nearly exact for a fruit-and-sugar set paste:

       169642 | sr_legacy_food | Jellies | 266 | 0.1 | 0.0 | 70.0 | 30

   Membrillo is ~250 kcal and ~65–70 g sugar. `membrillo → Jellies` at
   **medium** is defensible and materially better than "define it yourself".
   The audit searched by name and by category for cheeses and fish and did not
   do the same here.

4. **`manchego → Cheese, cheddar` is presented as a forced choice it is not.**
   The comparison table in §3.1 omits the closest row in the database:

       171242 | Cheese, gruyere     | 413 | 29.8 | 32.3 | 714
       328637 | Cheese, cheddar     | 409 | 23.3 | 34.0 | 654
       171249 | Cheese, romano      | 387 | 31.8 | 26.9 | 1433
       170848 | Cheese, parmesan, hard | 392 | 35.8 | 25.0 | 1175

   Against the audit's own target (manchego curado ≈ 390 | 26 | 33), gruyere is
   within 0.7 g on fat where cheddar is within 1.0 g, and it is a hard, aged,
   pressed cheese rather than an American block. The audit's dramatised
   trade-off ("cheddar is the best nutritional fit and a culturally absurd one")
   is a false dilemma. The rejection of `manchego → Cheese` (parent) is right
   and should stand.

5. **`morcilla de Burgos` is a material error, not a footnote.** §2.1 files the
   rice content as "a note, not a blocker". `Blood sausage` is 379 | 14.6 |
   34.5 | 1.3 g carb. Morcilla de Burgos is roughly 300 | 12 | 20 | 15 —
   **70% more fat** on the USDA row, which is the exact size of error the audit
   treats as disqualifying elsewhere. Encode `morcilla` → `Blood sausage` at
   medium, not high, with Burgos named.

6. **`bacalhau` "overstates protein by about 2.5×"** (§2.3). 62.8 g against the
   audit's own 27–32 g range is 2.0–2.3×. Sodium at 4× is right (7027 vs
   ~1500). Small, but the mapping note will carry the number.

7. **`dorada` → `Fish, snapper` is medium for the right reason, unstated.**
   Snapper is 100 | 20.5 | **1.3**; farmed gilt-head bream is 4–8 g fat. The
   confidence is right; the reason should be the fat, and it is not given.

8. **`turkey` (§1.3) is less bad than `chicken`.** `Fat, turkey` leads at
   0.636, but `Turkey, NFS` (2706104, 139 | 28.8 | 2.1) ties it at 0.636 and
   also survives every guard — the outcome turns on a sort tie-break, not on a
   knowledge gap. `chicken` has no whole-muscle row anywhere on its list and is
   the genuinely serious one. Do not present them as the same finding.

---

## D. What the audit missed

Probed today. Each fails, and each is in the domain the audit claims to cover.

### D1. `queso fresco` — a 1.000 auto-match, guard-immune, the audit's own headline shape

    auto  queso fresco                       1.000  Queso Fresco
    ask   queijo fresco                      0.588  Queso Fresco

    === 'queso fresco'  state=None
      1.000 Queso Fresco                AUTO
      0.591 Cheese, fresh, queso fresco  blocked:below-gate
      -> AUTO (2705745, 'Queso Fresco', 1.0)

    2705745 | survey_fndds_food | Queso Fresco               | 298 | 18.9 | 23.4 | 626
    172223  | sr_legacy_food    | Cheese, fresh, queso fresco| 299 | 18.1 | 23.8 | 751

Every `queso fresco` row in the database is the **Mexican/Central American**
cheese. Spanish *queso fresco de Burgos* is ~174 kcal / 12 g protein / 12 g fat
and famously low-salt (~50–100 mg sodium); Portuguese *queijo fresco* is
~190–240 kcal / 15 g protein / 17 g fat. Logging 100 g of Burgos on 2705745
books **+124 kcal, +11 g fat and roughly 6–10× the sodium**, silently, with an
alias cached forever.

This is the identical shape to the audit's own §0 item 1 — a bare FNDDS
description scoring 1.000 against a one-word query, a Latin American food
wearing an Iberian name — and the audit reached the words "queso fresco" in its
§4 refusals table ("paneer-style reasoning on queso fresco … not proposed")
without ever probing it. It belongs in §0 beside chorizo.

### D2. Tuna is entirely absent from the audit, and unreachable

    none  atun / atún / atum / bonito        -      (nothing)
    ask   tuna in olive oil                  0.529  Olive oil
    auto  canned tuna                        0.706  Fish, tuna, canned

*Atún en aceite de oliva*, *bonito del norte*, *marmitako*, *empanada de atún*
— tinned tuna is a staple of both cuisines and does not appear once in §2.9's
fish list or §2.13's common-noun list. `tuna in olive oil` heading to
`Olive oil` (884 kcal, 100 g fat) is the same failure as `chicken → Fat,
chicken`: the preparation medium beating the food. It escalates rather than
autos, so it is a candidate-list defect rather than a silent one, but it is a
larger omission than several §2 entries.

### D3. `horchata` — a Spain/Mexico homograph, uncaught

    weak  horchata  0.391  Horchata, made with milk
      Horchata, made with milk    0.391   (2710603 |  91 | 1.4 | 0.6 | 19.6 | 9)
      Horchata, made with water   0.375   (2710602 |  88 | 1.1 | 0.1 | 20.4 | 4)
      Beverages, Horchata, as served in restaurant  0.209

All three rows are the Latin American rice-and-cinnamon drink. Valencian
*horchata de chufa* is a tiger-nut emulsion at ~66–100 kcal with **2–3 g of
fat**; the USDA rows carry 0.1–0.6 g. Verdict `weak`, so it escalates and the
harm is bounded — but the model tier is handed three rows for the wrong drink
and nothing else. Same class as chorizo, one tier less dangerous.

### D4. `paella` auto-matches, which quietly cancels the audit's own §0 item 3

    auto  paella                             0.636  Paella, NFS
    weak  paella valenciana                  0.318  Paella, NFS

§0 argues `chicken → Fat, chicken` matters "because *paella valenciana* is
chicken and rabbit". If the parse returns the dish as a single item labelled
`paella`, it auto-matches `Paella, NFS` and no chicken component is ever
resolved. The chicken finding is real, but its stated justification in this
domain is the weaker of the two available ones — *frango piri-piri* carries it,
paella does not. Note also `piri piri` → **nothing**.

### D5. A cluster of everyday items returning nothing, none of them in §2.13's list

    none  fabada / cocido / cocido madrileno / pisto / migas / fideua
    none  marmitako / arroz caldoso / cochinillo / leitao / suckling pig
    none  callos / mollejas / lengua / chistorra / botifarra / torrezno
    none  piquillo / escalivada / romesco / alioli / caldo verde
    none  bifana / francesinha / broa / vinho verde / gambas / lupini
    none  partridge / chicharrones
    weak  croquetas                          0.412  Ham croquette   (right row, at head)
    weak  manzanilla olives                  0.391  Olives, green, Manzanilla, stuffed with pimiento
    weak  port wine                          0.357  Wine, red
    weak  goose barnacle                     0.316  Fat, goose

Most belong with the 86 dishes the audit rightly leaves alone. Four do not:

- **`piquillo`** — piquillo peppers are a distinct roasted product, not the raw
  bell pepper the audit proposes for `pimiento rojo`. Unreachable by name.
- **`mollejas`** — and note the audit's §1.5 `sweet bread → Bread, sweet
  potato` finding sits on top of an unremarked homograph: `Sweetbreads` (thymus
  offal, *mollejas*) is on that very candidate list at 0.500.
- **`gambas`** — §2.9 probes `langostinos` and `gambas rojas` and not the bare
  word, which is the one people type.
- **`port wine` → `Wine, red`** — port is ~157 kcal against red wine's ~85,
  and it is Portugal's single most exported food product.

`goose barnacle → Fat, goose` independently confirms the audit's percebes
rejection, which is worth recording as a corroboration rather than a finding.

---

## E. Upheld without qualification

Listed so the record shows what survived scrutiny, not only what did not.

- **§0/§1.1 `chorizo`.** Identity error real, guard-immune, alias-caching. The
  proposed `Salami, Italian, pork` (425 | 21.7 | 37.0 | 1890) against cured
  Spanish chorizo (~450 | 24 | 38 | ~1900) is the best row in the database and
  is close on all four figures. **High.**
- **§0/§1.2 `octopus`.** `Octopus` 2706331 (226 | 13.3 | 13.0) carries less
  protein than *raw* octopus (174218, 82 | 14.9 | 1.0) and 6× the fat of the
  boiled row (174249, 164 | 29.8 | 2.1). Guard-immune, exactly as the audit
  says: `state_conflicts` cannot fire on a description that says nothing.
  Arithmetic on the 200 g portion checks out.
- **§0/§1.3 `chicken` → `Fat, chicken`** (173564, 900 | 0.0 | 99.8). Real,
  guard-immune, and the candidate list contains feet, skin, tail and back with
  no whole-muscle row — so the model tier cannot rescue it either. Verified.
- **§1.4 `pimiento rojo` → `Pimiento`** (2709979, 28 | 1.4 | 0.4). Real and
  guard-immune; the sole candidate, so `pimiento verde` lands on the red row
  too. Correct.
- **§1.5 `sweet potato` → `Pie, sweet potato`** (269 | 5.0 | 9.8) beating
  `Sweet potato, NFS` (115 | 1.6 | 4.5) at 0.812 to 0.765, guard-immune. This
  is the most generalisable defect in the audit and is under-sold at "smaller
  ones, same shape" — it is a 2.3× energy error on a staple, in every domain.
- **§2.2 serrano homograph.** `Peppers, serrano, raw` is USDA's only *serrano*
  row; `Ham, prosciutto` (195 | 27.8 | 8.3 | 2695) is the right family for
  *jamón serrano* / *presunto*. Confirmed. (See B5 for the ibérico figure.)
- **§2.3 bacalhau state hazard.** `Fish, cod, Atlantic, dried and salted`
  (290 | 62.8 | 2.4 | 7027) is the unsoaked brick; nobody eats it in that
  state; there is no row for *demolhado*. The audit's refusal to pick one of
  two wrong rows and its insistence on recording the hazard is the right call
  and the best judgement in the document.
- **§2.4 `pimentón` vs `pimiento`.** `Pimento, canned` (23 | 1.1 | 0.3) against
  `Spices, paprika` (282 | 14.1 | 12.9). Textbook false friend, correctly
  identified, correctly de-escalated on absolute impact.
- **§2.5 `azafrán`, §2.6 `merluza`/hake→whiting, §2.7 `rape`→monkfish.** All
  three re-verified. `%hake%` returns only milkshakes; silver hake is sold as
  whiting (173713, 90 | 18.3 | 1.3) and the mapping is sound.
- **§2.8 `cecina` → `Beef, cured, dried`** (170604, 153 | 31.1 | 1.9 | 2790) at
  **medium** with the ~⅓ energy understatement stated. Honest and correctly
  graded.
- **§3.1 no sheep's-milk cheese in USDA.** Re-verified: `%sheep%` returns two
  fish rows and `Milk, sheep, fluid`. `cabrales → Cheese, blue` (172175, 353 |
  21.4 | 28.7 | 1146) is a genuinely good match. The `requeijão`
  Portugal/Brazil ambiguity is the sharpest single observation in the audit and
  the medium grading is right.
- **§3.2, §3.3, §3.4 refusals.** sobrasada (liver rows would fabricate vitamin
  A and B12 coverage), alheira and farinheira (bread- and flour-based, no
  neighbour), percebes, angulas, mojama, gofio, torta del Casar. Every one
  correctly refused with a stated reason. Refusing is the harder half and this
  section does it well.
- **§3.5 leaving 86 regional dishes alone**, and **§2.14 declining to file
  accent folding as a finding**. Both correct, and both are restraint the
  document did not have to show.
- **The alias-permanence framing throughout.** An auto-match writes an alias no
  command can repoint; that is what makes 10 surviving autos serious rather
  than annoying. The audit is right to lead with it.

---

## F. Summary of what should change in the audit

1. Strike the "raw in the Mexican sense" clause from §1.1 (B1).
2. Replace `grelos → Collards` with `grelos → Broccoli raab, cooked`, high (B2).
3. Correct the ibérico figure to 43 g **protein** / ~22 g fat (B5).
4. Split `boquerones` (174182) from `anchoas` (174183) (B6).
5. Drop or downgrade-with-numbers `jurel/carapau → Fish, mackerel` (B7).
6. Move `chouriço` onto the salami row with `chorizo`; leave `linguiça` (B8).
7. Add `queso fresco` to §0 as a fourth headline auto-match (D1).
8. Add tuna, `piquillo`, `gambas`, `port wine` and `horchata` to §2 (D2–D5).
9. Rewrite §2's framing to measure through `_candidates`, and re-file the
   finding as "the domain's entire vocabulary is carried by one prompt
   instruction with no test behind it" (B4).
10. Fix the §2.13 claim about alias caching (B3).
