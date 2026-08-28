# CRITIQUE-japanese-korean

Critic pass over `docs/knowledge/AUDIT-japanese-korean.md`. 28 Aug 2026.
Read-only throughout: `SELECT` only, `scripts/probe_knowledge.py` as arbiter,
guards evaluated by importing `state_conflicts` / `unrequested_qualifier` /
`label_absent` / `inverts_meaning` from `nutrai/llm/parse.py` and calling them
directly on (label, search_terms, state, description) tuples.

**Headline.** The audit is careful, well-measured and mostly right. Three things
are wrong with it and they are not small:

1. **Its single most-emphasised finding — F1, `tare sauce` -> `Tartar sauce` —
   does not happen in production.** `unrequested_qualifier` blocks it. The
   audit calls it "the single most damaging `auto` in the batch" and "the one
   to fix first"; it escalates to the model tier today, which is the system
   working.
2. **It measured `db.search_foods` and reported the result as resolver
   behaviour.** Ten of the 44 `auto` verdicts I re-checked are blocked by a
   guard before they can cache an alias. The audit's closing section "On the
   `auto` verdicts" names three dangerous autos; two of the three are wrong
   about which ones.
3. **The two genuinely dangerous surviving autos in this domain are not in the
   audit at all**, and one of them (`barley tea` -> `Barley`) is printed
   verbatim in the audit's own Batch 3 probe dump and passed over in silence.

Plus four mappings in the **High** table that a competent cook would dispute,
one of which is a straight bok-choy-is-not-napa-cabbage error.

---

## 1. The guard check

Method: for each claimed `auto`, evaluate the four disqualifiers
`resolve_items` applies at `nutrai/llm/parse.py:733-739`. `label_absent` reads
the bare label; `unrequested_qualifier` and `inverts_meaning` read
`asked_for = f"{label} {search_terms}"`; `state_conflicts` reads `it["state"]`.
Where the state matters I show both branches.

44 auto / near-auto pairs checked. **10 blocked, 34 survive.**

### Blocked — the audit reports these as autos and they are not

| claimed auto | row | guard that fires | note |
|---|---|---|---|
| `tare sauce` | `Tartar sauce` | `unrequested_qualifier` -> `"Tartar sauce"` | **F1 overturned.** Segment 0 echoes the query's word "sauce" and adds "tartar", which is exactly the narrowing case the guard was written for. Next candidate is `Taco sauce` at 0.571, below `AUTO_MATCH_SIMILARITY`, so the item escalates. Adding a model `search_terms` of "soy mirin glaze sauce" does not change it — re-tested. |
| `california roll` | `Sushi roll, California` | `unrequested_qualifier` -> `"Sushi roll"` | Correct row, blocked. Escalation cost, not damage. |
| `rice cracker` | `Rice crackers` | `unrequested_qualifier` -> `"Rice crackers"` | Blocked on a **plural**: `crackers` is not `cracker` and both are ≥4 chars, so it counts as an added word. Worth recording as a guard over-fire the audit never looked for. |
| `pickled ginger` | `Ginger root, pickled` | `unrequested_qualifier` -> `"Ginger root"` | Correct row for gari, blocked. |
| `noodles japanese` | `Noodles, japanese, soba, dry` | `state_conflicts` (state=dry) **and** `unrequested_qualifier` -> `"soba"` | F3's "the *less* Japanese the phrasing, the better it scores" is true of the probe and false of the resolver: this one is doubly disqualified. |
| `tteokbokki korean` | `Dukboki or Tteokbokki, Korean` | `unrequested_qualifier` -> `"Dukboki or Tteokbokki"` | **F18 partially overturned.** "Appending the word `korean` doubles the score to 0.692 and turns it into an `auto`" is false. Segment 0 is `Dukboki or Tteokbokki`: it echoes the query's `tteokbokki` and adds `dukboki`, which is the narrowing case, so the guard fires and the item escalates. |
| `napa cabbage` | `Cabbage, napa, cooked` | `state_conflicts` -> `"cooked"` when state=raw | Survives when state is `cooked` or unset. |
| `bamboo shoots` | `Bamboo shoots, raw` | `state_conflicts` -> `"raw"` when state=cooked | Survives raw/unset. Correct behaviour: takenoko is nearly always eaten boiled. |
| `fish cake steamed` (mine) | `Fish, catfish, steamed` | `unrequested_qualifier` -> `"catfish"` | See §4. |
| `imitation crab` (mine) | `Imitation crab meat` | `unrequested_qualifier` | Correct row blocked. |

### Survivors — real, uncaught autos

All of `octopus`, `chicken skin`, `natto`, `miso`, `rice wine`, `wasabi`,
`wasabi paste`, `horseradish`, `fried tofu`, `shiitake mushroom`, `lotus root`,
`burdock root`, `sesame seeds`, `sesame oil`, `worcestershire sauce`, `kimchi`,
`cabbage kimchi`, `napa cabbage kimchi`, `seaweed soup`, `blood sausage`,
`asian pear`, `teriyaki sauce`, `chinese cabbage`, `wasabi peas`, `brisket`,
`bibimbap korean`, `enoki mushroom`, `fish anchovy`, `radish oriental`,
`rice cake`, `sweet rice wine`, `barley tea`, `glutinous rice`, `tahini`
survive every guard. Most are correct. Three are not — see §4.

**Correction to the audit's closing paragraph.** It says: "Three are wrong in a
way that would cache forever: `tare sauce -> Tartar sauce` (F1), `rice cake ->
Rice cake` when the user meant tteok (F21), and `seaweed soup -> Soup, seaweed`
is right but sits one letter from `miyeok guk`." F1 is blocked. `seaweed soup`
is not wrong at all — it is the right row and the audit says so in the same
sentence. Only F21 survives as stated, and the two worst cases are absent.

---

## 2. Culinary and nutritional errors in the proposals

### 2.1 OVERTURN — `hakusai`, `baechu` -> `Cabbage, Chinese, raw` is bok choy, not napa

High table, rated "high". Hakusai and baechu are napa cabbage,
*Brassica rapa* subsp. *pekinensis* — USDA's **pe-tsai**. The proposed row is
FNDDS `Cabbage, Chinese, raw` (2709774), and it is a byte-for-byte nutrient
copy of SR's `Cabbage, chinese (pak-choi), raw` (170390) — i.e. it is **bok
choy**, subsp. *chinensis*, a different vegetable:

```
2709774 Cabbage, Chinese, raw               13 kcal   65 mg Na   2.2 g carb   1.2 g sugar
170390  Cabbage, chinese (pak-choi), raw    13 kcal   65 mg Na   2.2 g carb   1.2 g sugar   <- identical
169979  Cabbage, chinese (pe-tsai), raw     16 kcal    9 mg Na   3.2 g carb   1.4 g sugar   <- this is hakusai/baechu
```

**7x on sodium**, 1.45x on carbohydrate, and it is the wrong plant. This is the
domain's own version of "perilla is not shiso". The audit's own proposal even
hedges by naming two targets ("`Cabbage, Chinese, raw` / `Cabbage, napa`")
without noticing they are different foods and that only the second is right.

Correct target: **169979 `Cabbage, chinese (pe-tsai), raw`** (raw), with
169980 `…pe-tsai, cooked, boiled, drained, without salt` as the cooked pair.
`Cabbage, napa, cooked` (168572) is fine for the cooked case; there is no raw
FNDDS napa row with energy (2727583 Foundation has no kcal). Confidence stays
high — the identification is not in dispute, only the row the audit picked.

Note also that baechu kimchi is made from pe-tsai, so the same error would
propagate into any kimchi component breakdown.

### 2.2 OVERTURN — `atsuage` and `aburaage` are not the same food, and `Tofu, fried` is neither

High table, rated "high", both mapped to 172451 `Tofu, fried` (270 kcal,
20.2 g fat). They are different products:

- **aburaage** — thin tofu sliced and deep-fried through, ~377 kcal / 34 g fat
  per 100 g. `Tofu, fried` **understates by ~1.4x**.
- **atsuage** (namaage) — a thick block fried only on the surface; the interior
  is unchanged tofu, ~143 kcal / 11 g fat. `Tofu, fried` **overstates by
  ~1.9x**.

One row cannot be "high confidence" for both when the two sit a factor of 2.6
apart on fat. `aburaage` -> `Tofu, fried` is defensible at high; `atsuage` /
`namaage` should be **medium at best**, and honestly belongs with `Tofu, firm`
(78 kcal) plus a fried-surface allowance, or in the rejected list.

### 2.3 OVERTURN — `bonito` -> raw skipjack contradicts the audit's own F13

High table: "`katsuo`, `bonito` -> 175156 `Fish, tuna, fresh, skipjack, raw`",
rated high, on the grounds that "katsuo is skipjack".

Taxonomically true. Nutritionally it is the wrong end of the food. F13 in the
same document says katsuobushi is "eaten dry by the handful on okonomiyaki and
takoyaki at roughly 350 kcal and 77 g protein per 100 g". The proposed row is:

```
175156 Fish, tuna, fresh, skipjack, raw    103 kcal   1.0 g fat   37 mg Na
```

**~3.4x understatement on energy** for the form the word almost always names in
this cuisine. In a Japanese food log `bonito` is a shaving, not a fillet;
nobody eats 100 g of raw katsuo and calls it bonito.

Two separate surfaces are needed: `katsuo` / `katsuo sashimi` -> 175156 (high),
and `bonito`, `bonito flakes`, `katsuobushi`, `dried bonito` -> **no target**
(entity gap), because USDA has no dried-fish-shaving row. Confirmed:
`katsuobushi flakes` -> nothing; `dried bonito flakes` -> 0.304 `Fig, dried`;
`bonito` -> nothing.

Also, in English "bonito" is *Sarda* spp., a different genus from *Katsuwonus
pelamis*. The equivalence only holds inside Japanese usage, which is another
reason it is not a "high, beyond dispute" edge.

### 2.4 OVERTURN — `kimchi jjigae` in the High table maps a stew to a pickle

The High table's kimchi row reads: "`kimchee`, `gimchi`, `baechu kimchi`,
`kimchi jjigae`→ingredient | synonym | 2710077 `Kimchi` | high".

`Kimchi` is **15 kcal / 498 mg Na per 100 g**. Kimchi jjigae is a pork-and-tofu
stew in the 60-90 kcal range with several grams of fat. Whatever "→ingredient"
was meant to convey, a synonym table maps a surface to an `fdc_id`, and the
`resolve_alias` tier does not read arrows. Encoding this writes an alias that
logs a bowl of stew as a side of pickled cabbage — **4-6x under**, silently,
forever. Drop `kimchi jjigae` from the row; the dish belongs to the parse tier,
exactly as the audit itself argues for `korean fried chicken` and
`japanese curry` in its rejected list. The inconsistency is internal.

### 2.5 OVERTURN — `kabocha` -> `Squash, winter, all varieties, raw` is ~2.3x low

Medium table, "34 kcal. Kabocha is drier and denser than the average winter
squash, so the figure is conservative rather than exact."

"Conservative" is the wrong word when the error understates energy. Seiyou
kabocha (the ordinary Japanese/Korean kabocha, *Cucurbita maxima*) is ~78 kcal
and ~20 g carbohydrate per 100 g raw. The proposed row:

```
170489 Squash, winter, all varieties, raw    34 kcal   8.6 g carb
```

**2.3x under on energy, 2.4x under on carbohydrate**, on a vegetable eaten in
100-200 g servings in nimono and in Korean hobakjuk. The nearest honest USDA
rows are `Squash, winter, hubbard, baked` (50 kcal) or `…butternut, raw`
(45 kcal) — still low. My recommendation: **reject**, and record kabocha with
the other entity gaps, or accept 45 kcal butternut explicitly labelled as a
floor. A fallback that is wrong in the direction of "you ate less than you did"
is the same class of failure as the phantom-deficiency bug.

### 2.6 CONTRADICTION — `joseon ganjang` is `guk ganjang`

The High table maps `shoyu`, `shōyu`, `ganjang`, **`joseon ganjang`** -> `Soy
sauce` at high. The Medium table then maps **`guk ganjang`**, `soup soy sauce`
-> `Soy sauce` at medium, noting it is "materially saltier than ordinary
ganjang; same class, understated sodium".

조선간장 (joseon ganjang) and 국간장 (guk ganjang) are the same product — the
traditional, light-coloured, high-salt soup soy sauce. The audit rates the same
food high in one table and medium in the other. Move `joseon ganjang` into the
medium row with `guk ganjang`.

For scale: `Soy sauce` (2707442) is 53 kcal / **5493 mg Na**; guk ganjang runs
roughly 1.3-1.5x that sodium. Not catastrophic, but it is used by the teaspoon
in exactly the soups being counted.

---

## 3. Confidence inflation — downgrade, do not reject

### 3.1 `hamachi`, `buri` -> `Fish, yellowtail, mixed species` — high to **medium**

```
175163 Fish, yellowtail, mixed species, raw    146 kcal   5.2 g fat
```

Farmed hamachi — which is what reaches a sushi counter — is ~250 kcal and
~17 g fat per 100 g. **1.7x on energy, 3.3x on fat.** USDA's "mixed species"
row is *Seriola lalandi/dorsalis*, wild Pacific yellowtail; the Japanese
farmed *S. quinqueradiata* is a fattier animal by design. Taxonomically inside
the row, nutritionally not. This is the "cured vs fresh, full-fat vs skimmed"
case the brief warns about, in fish form. Keep the mapping — it beats `Ham` —
but it is medium, and the rationale should say so rather than resting on the
genus.

### 3.2 `firm tofu`, `momen` -> 172448 — high to **medium**

USDA holds two rows both fairly called firm tofu, and they are **1.85x apart**:

```
172448 Tofu, firm, prepared with calcium sulfate and magnesium chloride (nigari)    78 kcal   4.2 g fat
172475 Tofu, raw, firm, prepared with calcium sulfate                              144 kcal   8.7 g fat
174291 Tofu, hard, prepared with nigari                                            145 kcal  10.0 g fat
```

The audit lists 172475 in its own F10 SELECT dump and then proposes 172448 at
"high" without mentioning that a differently-coagulated firm tofu row sits at
nearly double. Japanese momen (~73 kcal) and the US brand rows (74-98 kcal)
both favour 172448, so the *choice* is right; the *confidence* is not. Say
which two rows were compared and why, or a later author will re-point it.

Same treatment for the bare `tofu` -> 172476 `Tofu, raw, regular` (76 kcal):
defensible, but it is a coin-flip against 172475 at 144, and 144 is what a
supermarket block usually is in the US.

### 3.3 The seaweed block — right species, wrong moisture, and the audit never says so

The audit calls this "the highest-value block in the domain" and "not
disputable". The species identifications are all correct (laver = nori = gim,
*Pyropia*; kelp = kombu = dashima, *Laminaria*; wakame = miyeok, *Undaria*).
What is missing is that **every proposed row is the raw, ~85%-water form, and
every one of these foods is bought and logged dry**:

```
168458 Seaweed, laver, raw     35 kcal    48 mg Na
168457 Seaweed, kelp, raw      43 kcal   233 mg Na
170496 Seaweed, wakame, raw    45 kcal   872 mg Na
2709988 Seaweed, dried        298 kcal   575 mg Na    <- the only dried row, generic
```

A nori sheet is ~2.5 g at ~5% water; 10 g of dried miyeok rehydrates to ~80 g.
Log "10 g dried wakame" against 170496 and you get 4.5 kcal and 87 mg sodium
against a true ~28 kcal and several hundred mg. `state_conflicts` cannot rescue
this: it fires on a *declared* state, and nori and dried miyeok are sold in one
state only, so the parse has no reason to declare it.

The mappings should stand — they are still enormously better than `Tea,
kombucha` — but each needs an explicit "USDA carries only the hydrated form;
2709988 `Seaweed, dried` is the row for a dry mass" line, and the block's claim
to be beyond dispute should be softened to the *identification* being beyond
dispute.

### 3.4 `oshinko` does not mean pickled daikon — split it out

Medium table: "`takuan`, `danmuji`, `oshinko` -> 2710099 `Radishes, pickled`".

Takuan and danmuji are pickled daikon; **oshinko (お新香) is a generic term for
any lightly-pickled vegetable** — cucumber, hakusai, eggplant, turnip. Mapping
it to a radish row is the "halloumi -> cheese" failure run backwards: too
*narrow* rather than too broad, and wrong in the specific case. Keep takuan and
danmuji; move `oshinko` and `tsukemono` to `Seaweed`-style generic handling —
in practice `2710100`-adjacent FNDDS pickled-vegetable rows, or leave them to
the model tier, which is where an ambiguous word belongs.

### 3.5 `pa` as a synonem surface, and `negi`

`scallion`, `spring onion`, `negi`, **`pa`**, `daepa` -> 170005. Two problems:

- **`pa` is two characters.** As an alias surface it will collide with anything
  the loose `_label_match` reaches. Any synonym table needs a minimum-length
  rule or `pa` alone will be the next `sundae`.
- **negi is not a scallion.** Japanese naganegi (*Allium fistulosum*) is a
  leek-sized allium with a long white shaft; a Tokyo negi is 20-30 g of white
  per portion against a scallion's 5 g. Nutritionally close enough per 100 g
  that the mapping is fine, but it is a *portion* trap, not a synonym one, and
  "high, beyond dispute" oversells it. Medium.

### 3.6 `myeolchi` -> `Fish, anchovy` is the canned-in-oil row

```
2706232 Fish, anchovy                                          210 kcal   9.7 g fat   3668 mg Na
174183  Fish, anchovy, european, canned in oil, drained solids  210 kcal   9.7 g fat   3668 mg Na   <- same numbers
174182  Fish, anchovy, european, raw                            131 kcal   4.8 g fat    104 mg Na
```

The FNDDS row the audit proposes *is* the oil-packed one. Dried myeolchi is
~330 kcal, ~5 g fat, ~65 g protein — so the mapping understates energy (the
audit says this) **and overstates fat by ~2x from packing oil that is not
there** (the audit does not). Worse, the dominant use is stock: 15 g of
myeolchi simmered and discarded contributes almost nothing, and the mapping
would log all of it. Keep at medium, but the rationale needs the fat line and a
note that boiled-and-discarded stock fish is a portion problem the resolver
cannot see.

---

## 4. What the audit missed

Two dangerous autos, both confirmed to survive all four guards, and both worse
than anything in the audit's own list.

### M1. `glutinous rice` -> `Flour, rice, glutinous` — auto 0.714, **3.8x**

```
auto  glutinous rice                     0.714  Flour, rice, glutinous
```
```
1104867 Flour, rice, glutinous                       368 kcal
169711  Rice, white, glutinous, unenriched, cooked    97 kcal
168883  Rice, white, glutinous, unenriched, uncooked 370 kcal
```

Guards: `unrequested_qualifier` does not fire (segment 0 `Flour` shares no word
with the query, so the echo test declines to judge it; `rice` and `glutinous`
both appear in the query). `label_absent` false. `state_conflicts` false even
with `state="cooked"` — "flour" is not in `_DRY_WORDS`. **Survives.**

This is the most-used ingredient word in the domain's sweets and rice dishes —
mochi, daifuku, chapssaltteok, tteok, ohagi, sekihan all decompose to it — and
it caches an alias that scores cooked glutinous rice at flour density.
**3.8x over on energy**, in the direction that inflates a day. The audit never
probed the phrase.

Correct target for the cooked form: 169711 (97 kcal). And note this is a case
`unrequested_qualifier` was written for and cannot reach: `Flour` is a
*different food class* in segment 0 that shares nothing with the query, which
the guard deliberately treats as "a weak match judged by similarity" — except
that similarity is 0.714 here because the other two segments match perfectly.

### M2. `barley tea` -> `Barley` — auto 0.636, **~140x**, and it is in the audit's own probe dump

```
auto  barley tea                         0.636  Barley
```
```
2708361 Barley                     139 kcal   199 mg Na    <- cooked barley grain
2710490 Tea, hot, leaf, green        1 kcal     1 mg Na
```

Guards: nothing fires. `Barley` is one segment, it echoes the query's "barley",
and adds nothing. **Survives.**

Boricha / mugicha is a brewed infusion at ~0-1 kcal drunk by the half-litre. A
500 ml glass logged against `Barley` scores **~695 kcal of energy that does not
exist**. This is precisely the unit mismatch the audit correctly rejected for
matcha ("a three-hundred-fold unit mismatch dressed as the same plant") — and
it appears as a printed `auto` line in Batch 3, is folded into "most are
correct" in the closing section, and gets no finding. It should have been F1.

### M3. Korean instant noodles have no route at all

```
none  ramyeon    |  none  ramyun    |  none  shin ramyun
```
The audit tested `instant ramen` (nothing) and stopped. Ramyeon is plausibly
the single most-eaten packaged food in the Korean half of this domain, carries
~1700-1900 mg sodium per packet, and has three common romanisations none of
which reaches anything. `Ramen bowl, NFS` (2709153, 127 kcal, 333 mg Na) exists
and is the obvious escalation target. No finding, no proposal, no rejection.

### M4. Half the sushi counter was never probed

```
none  ika   |  none  tako   |  none  ebi   |  none  hotate   |  none  anago
none  tarako  |  none  mentaiko
```

The audit probed `maguro`, `ikura`, `tobiko`, `uni` and `sea urchin` and
concluded Japan is "half-present". It skipped the five commonest neta whose
USDA rows **do** exist:

```
174223 Mollusks, squid, mixed species, raw      92 kcal    <- ika
2706331 Octopus                                226 kcal    <- tako (already auto 1.000 from English)
174220 Mollusks, scallop, mixed species, raw    69 kcal    <- hotate
```

By the audit's own framing these are its highest-value class — the exact row
exists and the native word cannot reach it — and five of them are missing from
a 477-term sweep.

### M5. `Fish, surimi` never appears anywhere in the audit

```
none  kamaboko  |  none  chikuwa  |  ask  surimi  0.583  Fish, surimi
auto  fish cake steamed  0.714  Fish, catfish, steamed     <- blocked by unrequested_qualifier
```
```
173702 Fish, surimi         99 kcal   0.9 g fat   143 mg Na
2706550 Fish, cake or patty 212 kcal              429 mg Na
```

The audit's F1 batch has `narutomaki` -> nothing and `fish cake` -> 0.526
`Fish, cake or patty` and draws no conclusion. `Fish, surimi` is the right row
for kamaboko, chikuwa and narutomaki, is 2.1x lighter than the fried patty row
the query currently reaches, and is a clean high-confidence synonym the audit
left on the table. Also worth recording that `fish cake steamed` reaches
`Fish, catfish, steamed` at 0.714 — a *whole different fish* — and is saved
only by `unrequested_qualifier` catching the word "catfish".

### M6. A sixth row named after the query it cannot reach

The audit's Notes claim five, and builds its main structural argument on the
set. There are more:

```
weak  adzuki                             0.233  Beans, adzuki, mature seeds, raw
none  azuki                              -      (nothing)
```

`Beans, adzuki, mature seeds, raw` (329 kcal) is named after the query and
scores 0.233. Add it to the list; the argument gets stronger, not weaker.
`anko` and `azuki` also have no proposal and no rejection despite
`Beans, adzuki, mature seeds, canned, sweetened` (173729, 237 kcal) and
`Yokan, prepared from adzuki beans and sugar` (173730, 260 kcal) both sitting
in the database — the latter being a literal Japanese confection row the audit
never found.

### M7. `Cake made with glutinous rice` exists, and the tteok rejection did not find it

The audit rejects `tteok` -> `Rice cake` (392 kcal) on the correct grounds that
garaetteok is ~230 kcal boiled dough, and proposes nothing. But:

```
2708345 Cake made with glutinous rice                   279 kcal   6.5 g fat    36 mg Na
2708348 Cake made with glutinous rice and dried beans   185 kcal   0.6 g fat   942 mg Na
```

2708345 at 279 kcal is far closer to garaetteok (~230) and to mochi (~235) than
either row the audit compared, and it is the obvious target for `mochi`,
`daifuku`, `kirimochi` and `chapssaltteok`, all of which the audit either
reported as `none` or did not probe. It searched the category "rice cake" and
not the ingredient "glutinous rice", which is the same neighbour-search
discipline it applies correctly everywhere else.

### M8. `dubu`

```
none  dubu
```
The Korean word for tofu, absent from a proposal block that includes `sundubu`,
`momen`, `koyadofu`, `aburaage` and `atsuage`. One line.

Also unprobed and returning nothing: `kinako`, `mochiko`, `nurungji`,
`kongbap`, `dakgangjeong`, `gim gui`, `yuzu kosho`, `neri goma`. Of these
`neri goma` is worth a synonym — `sesame paste` already reaches
`Seeds, sesame butter, paste` at 0.542 and `tahini` auto-matches at 1.000.

---

## 5. What is right and should not be touched

Recorded because a critique that lists only faults invites the wrong revision.

- **The macron rule (F28) is the best item in the document.** `rāmen`, `shōyu`,
  `tōfu`, `gyōza` return *zero* candidates while their ASCII forms reach the
  list. NFKD-fold-and-strip is mechanical, strictly more permissive, and cannot
  lose a match. Ship it first.
- **The RR / McCune-Reischauer consonant rule (F23)** is correct and correctly
  scoped to search-term generation rather than to matching.
- **The perilla handling is exactly right.** kkaennip (*P. frutescens* var.
  *frutescens*) and shiso (var. *crispa*) are different leaves, USDA has no
  *Perilla* row, and the audit declines to create an edge with no target and
  names the `-626` precedent. This is the one place the domain's headline trap
  lives and the auditor did not fall into it.
- **The gochujang, mirin, konnyaku, matcha, MSG and dashi rejections are all
  measured, all correct, and all argued in the right direction** (a wrong row
  that returns a plausible number is worse than nothing).
- **F10's tofu diagnosis, F18's "five Korean rows in 8,204 foods", F29 tamari,
  F30 scallion, F33 kanpyo** all reproduce exactly at HEAD. I re-probed
  `tare sauce`, `tteokbokki`, `sake`, `scallion`, `kombu`, `nori`, `rice cake`
  and `wasabi`; every score matches the audit to three decimals.
- **The `wasabi` bare-word decision** — leave it on the paste row, add routes
  for `real wasabi` / `wasabi root` — is the right call and the reasoning
  ("changing the bare word to the root would make the common case wrong to fix
  the rare one") is worth reusing elsewhere.

---

## 6. Summary of verdicts

| | count |
|---|---|
| proposals examined (30 high + 2 rules + 13 medium + 13 rejections) | 58 |
| upheld as written | 43 |
| downgraded (keep, lower confidence or add caveat) | 8 |
| overturned (wrong food, wrong row, or claim false in production) | 7 |
| claimed autos re-checked against the three guards | 44 |
| of those, already blocked in production | 10 |
| of those, surviving to cache an alias | 34 |

**Overturned:** F1 `tare sauce` (guard-blocked); F18's `tteokbokki korean`
auto claim (guard-blocked); `hakusai`/`baechu` -> pak-choi row; `atsuage` ->
`Tofu, fried`; `bonito` -> raw skipjack; `kimchi jjigae` -> `Kimchi`;
`kabocha` -> winter squash.

**Downgraded:** `hamachi`/`buri`; `firm tofu`; the three seaweeds (moisture
caveat); `oshinko`; `pa` and `negi`; `myeolchi`; bare `tofu`; `joseon ganjang`
(moved to the medium row it duplicates).
