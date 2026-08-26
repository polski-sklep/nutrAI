# Knowledge audit — Iberian / Lusophone

26 Aug 2026. Spanish, Portuguese, Catalan, Basque, Galician, Canarian.

**843 distinct terms probed** with `scripts/probe_knowledge.py` against the
live database. Every line quoted below is verbatim probe output or verbatim
`psql` output. Nothing here is inferred from what the resolver "would" do.

    none = 443 (53%)   weak = 234 (28%)   ask = 97 (12%)   auto = 69 (8%)

Term lists and raw output are in the scratchpad
(`terms.txt`…`terms4.txt`, `all.json`).

> **Measurement caveat.** These probes ran against the working tree at
> `9bf452d` **plus an uncommitted change to `nutrai/db.py`** made by another
> agent during the audit: the FTS-coverage flag promoted from a 1.35 multiplier
> to the leading `ORDER BY` key. That change is why the correct row now leads
> several lists at a very low `sim` (e.g. `salt cod` → `Fish, cod, Atlantic,
> dried and salted` at 0.235). The `verdict` in the probe still reads the
> *head's* `sim`, so "weak" here often means "right row, at the head, scoring
> badly" — which escalates to the model tier with the right candidate on the
> list, and is the system working. I have kept those apart from the cases where
> the right row is **not on the list at all**.

---

## 0. The three things that actually hurt

1. **`chorizo` auto-matches Mexican fresh chorizo at similarity 1.000 and
   caches an alias.** The Iberian food of that name is a different food.
2. **`octopus` auto-matches a fried-preparation FNDDS row at 1.000**, losing
   more than half the protein of boiled *pulpo*.
3. **`chicken` auto-matches `Fat, chicken` (900 kcal, 0 g protein).** Chicken
   is the defining ingredient of *paella valenciana* and *frango piri-piri*.

All three are verdict `auto`: silent, and cached forever by `upsert_alias`.

---

## 1. Wrong-confident matches (verdict `auto` onto a semantically wrong row)

### 1.1 `chorizo` — Spanish and Mexican chorizo are conflated

    auto  chorizo                            1.000  Chorizo
    ask   spanish chorizo                    0.500  Chorizo
    ask   chorizo iberico                    0.500  Chorizo
    ask   chorizo picante                    0.500  Chorizo
    ask   mexican chorizo                    0.500  Chorizo
    ask   chorizo, cured                     0.615  Chorizo
    weak  chorizo sausage                    0.400  Sausage, pork, chorizo, link or ground, raw

Every chorizo row in the database is fresh Mexican-style pork chorizo:

    2706179 | survey_fndds_food | Chorizo                                                   | 341 | 19.3 | 28.1 |  983
    332864  | foundation_food   | Sausage, pork, chorizo, link or ground, cooked, pan-fried | 346 | 19.3 | 28.1 |  983
    173859  | sr_legacy_food    | Sausage, pork, chorizo, link or ground, raw               | 296 | 13.6 | 25.1 |  788
    (kcal | protein | fat | sodium, per 100 g)

Spanish *chorizo* (sarta, ibérico, vela) is a **dry-cured, ready-to-eat**
sausage at roughly 450 kcal / 24 g protein / 38 g fat / ~1900 mg sodium per
100 g. The FNDDS row understates energy by ~25%, fat by ~26% and **sodium by
about half**. It is also a *raw* food in the Mexican sense — it must be cooked
— which is a state error on top of the identity error.

The closest row in the database by construction and by numbers is
`Salami, Italian, pork` (174603): **425 | 21.7 | 37.0 | 1890**. That is a much
better nutritional stand-in for cured Spanish chorizo than the row that
currently wins at 1.000.

`Chorizo` is a bare one-word FNDDS description, which is exactly the shape that
scores 1.000 against a one-word query — RECONCILED §1's length effect, arriving
as a false *confidence* rather than a false ranking.

### 1.2 `octopus` / `pulpo` — a fried row wins over the boiled one

    auto  octopus                            1.000  Octopus
    ask   octopus boiled                     0.533  Octopus
    ask   boiled octopus                     0.533  Octopus
    ask   grilled octopus                    0.500  Octopus
    weak  octopus cooked                     0.395  Mollusks, octopus, common, cooked, moist heat
    none  pulpo                              -      (nothing)
    none  polvo                              -      (nothing)
    none  pulpo a feira                      -      (nothing)
    none  pulpo a la gallega                 -      (nothing)

    2706331 | survey_fndds_food | Octopus                                      | 226 | 13.3 | 13.0
    174249  | sr_legacy_food    | Mollusks, octopus, common, cooked, moist heat | 164 | 29.8 |  2.1
    174218  | sr_legacy_food    | Mollusks, octopus, common, raw                |  82 | 14.9 |  1.0

FNDDS `Octopus` carries **less protein than raw octopus and thirteen times the
fat** — it is a fried/prepared assumption. *Pulpo a feira* is boiled octopus
dressed with paprika and olive oil. A 200 g portion scored on 2706331 logs
452 kcal / 27 g protein when the octopus alone is 328 kcal / 60 g protein.

`state_conflicts` cannot catch this: the description `Octopus` says nothing
about preparation, and by design "a description silent about its state is not
evidence against anything". Correct design, wrong outcome here.

### 1.3 `chicken` and `turkey` auto-match rendered fat

    auto  chicken                            0.667  Fat, chicken
        0.667 [sr_] Fat, chicken
        0.615 [sur] Chicken kiev
        0.615 [sur] Chicken feet
        0.615 [sur] Chicken, back
        0.615 [sur] Chicken, tail
        0.615 [sur] Chicken skin
    auto  turkey                             0.636  Fat, turkey

    173564 | sr_legacy_food | Fat, chicken | 900 kcal | 0.0 g protein | 99.8 g fat

`Fat, chicken` is nine hundred calories of pure fat with zero protein. This is
in scope for this domain because *paella valenciana* is chicken and rabbit, and
*frango piri-piri* is the single most-ordered Portuguese restaurant dish.
`rabbit` resolves correctly (`auto 1.000 Rabbit`); its partner ingredient does
not. Note also that the first eight candidates contain chicken feet, chicken
skin, chicken tail and chicken back and **no whole-muscle cooked chicken row**,
so the model tier would not rescue it either.

    ask   piri piri chicken                  0.556  Pot pie, chicken
        0.556 [sur] Pot pie, chicken
        0.471 [sr_] Fat, chicken
        0.444 [sur] Chicken skin
        0.444 [sur] Chicken, tail
        0.444 [sur] Chicken, back
        0.444 [sur] Chicken feet

The right row exists — `Chicken fillet, grilled` (2706090) — and is reachable
only by a query nobody types:

    ask   grilled chicken portuguese         0.500  Chicken fillet, grilled

### 1.4 `pimiento rojo` → canned pimiento; `pimiento verde` → the same red row

    auto  pimiento rojo                      0.643  Pimiento
    ask   pimiento verde                     0.600  Pimiento
    ask   red pepper                         0.526  Peppers, red, cooked
    ask   green pepper                       0.545  Peppers, green, cooked

`Pimiento` (2709979, 28 kcal) is the canned red pimiento used as an olive
stuffing, not a fresh bell pepper — and it wins for the *green* query as well,
where the colour word is the whole distinction. `Peppers, sweet, red, raw`
(170108) exists and is what a *sofrito* actually contains.

### 1.5 Smaller ones, same shape

    auto  broccoli rabe                      0.688  Broccoli, raw
    auto  cold vegetable soup                0.750  Soup, vegetable
    auto  cold tomato soup                   0.706  Soup, tomato
    auto  sweet bread                        0.632  Bread, sweet potato
    auto  sweet potato                       0.812  Pie, sweet potato

*Grelos* / *couve-nabiça* are `Brassica rapa` leaf, not broccoli; `Collards,
raw` (32 kcal, 3.0 g protein) is the honest stand-in and the mapping to
`Broccoli, raw` is a conflation rather than a nutritional catastrophe — I mark
it medium, not high. `cold vegetable soup` auto-matching `Soup, vegetable`
while `Soup, gazpacho` (2710106) sits unreached is a plain fallback defect.
`sweet potato` → **`Pie, sweet potato`** and `sweet bread` → `Bread, sweet
potato` are the length effect in its purest form: `Pie, sweet potato` is
shorter than `Sweet potato, NFS` and beats it 0.812 to 0.765.

---

## 2. Reachability gaps — USDA has the row and the query cannot reach it

These are the valuable ones. In each case I searched by ingredient and by
category, not only by name, and the search is pasted.

### 2.1 `morcilla` → `Mortadella`; USDA has `Blood sausage`

    weak  morcilla                           0.333  Mortadella
    none  morcilla de burgos                 -      (nothing)
    none  morcela                            -      (nothing)
    none  morcela de arroz                   -      (nothing)
    auto  blood sausage                      1.000  Blood sausage

    $ ... where description ilike '%morcilla%'   -> (0 rows)
    $ ... where description ilike '%blood sausage%'
    171618  | sr_legacy_food    | Blood sausage   | 379 | 14.6 | 34.5 | 680
    2706173 | survey_fndds_food | Blood sausage

Morcilla *is* blood sausage. The correct row is not on the candidate list at
all; the head is a completely unrelated emulsified pork sausage.
(Caveat worth encoding as a note, not a blocker: *morcilla de Burgos* contains
rice, so its carbohydrate is materially higher than the USDA row's.)

### 2.2 `jamón serrano` → a chilli pepper; USDA has `Ham, prosciutto`

    weak  jamon serrano                      0.308  Peppers, serrano, raw
    weak  jamón serrano                      0.308  Peppers, serrano, raw
    weak  serrano                            0.400  Peppers, serrano, raw
    weak  serrano ham                        0.333  Peppers, serrano, raw
        0.333 [sr_] Peppers, serrano, raw
        0.333 [sur] Ham
    weak  iberico ham                        0.333  Ham
    none  jamon iberico                      -      (nothing)
    none  jamón ibérico                      -      (nothing)
    none  presunto                           -      (nothing)
    weak  jamon                              0.429  Jam
    weak  cured ham                          0.400  HORMEL, Cure 81 Ham
    weak  air dried ham                      0.368  Apple, dried

    2705879 | survey_fndds_food | Ham, prosciutto | 195 | 27.8 |  8.3 | 2695
    2705878 | survey_fndds_food | Ham             | 117 | 19.0 |  3.9 | 1149

This is the domain's cleanest reachability failure. `serrano` is a homograph:
USDA's only `serrano` row is a chilli. Worse, the *second* candidate for
"serrano ham" is `Ham` — wet-cured cooked ham at 117 kcal, which a model could
reasonably pick and which understates a 60 g plate of jamón by ~70 kcal and
half its sodium. The correct family — `Ham, prosciutto`, a dry-cured raw ham —
never appears.

Honest limits: prosciutto (195/27.8/8.3) is a good stand-in for *jamón serrano*
(≈240/31/12) and a poor one for *jamón ibérico de bellota* (≈375 kcal, 43 g
fat), which is roughly twice as fatty. Encode serrano/presunto high, ibérico
medium with the understatement stated.

### 2.3 `bacalhau` / `bacalao` → nothing, or Puerto Rican fritters

    none  bacalhau                           -      (nothing)
    none  bacalhau à brás                    -      (nothing)
    none  bacallà                            -      (nothing)
    weak  bacalao                            0.353  Bacalaitos fritos
    weak  salt cod                           0.235  Fish, cod, Atlantic, dried and salted
    weak  salted cod                         0.333  Fish, cod, Atlantic, dried and salted
    weak  dried salt cod                     0.412  Fish, cod, Atlantic, dried and salted
    weak  salted cod desalted                0.333  Fish, cod, Atlantic, dried and salted
    ask   fresh cod                          0.500  Coconut, fresh

    174190 | Fish, cod, Atlantic, dried and salted | 290 | 62.8 | 2.4 | 7027
    171955 | Fish, cod, Atlantic, raw             |  82 | 17.8 | 0.7 |   54
    171956 | Fish, cod, Atlantic, cooked, dry heat| 105 | 22.8 | 0.9 |   78

The English phrases reach the right row (post-coverage-key); the Portuguese,
Spanish and Catalan names do not. `bacalao` lands on *bacalaítos fritos*, a
Puerto Rican fritter.

**Salted vs fresh matters more here than anywhere else in the domain**, and
neither existing row is right for the eaten food. `Fish, cod, Atlantic, dried
and salted` is the dry brick at 7027 mg sodium; nobody eats it in that state.
Portuguese *bacalhau demolhado* — soaked 24–48 h, then cooked — is roughly
130–160 kcal, 27–32 g protein, ~1500 mg sodium. Mapping `bacalhau` to 174190
and logging a 150 g cooked portion overstates protein by about 2.5× and sodium
by about 4×. There is no row for the soaked state:

    weak  soaked salt cod                    0.321  Taro, cooked, with salt
    ask   reconstituted salt cod             0.457  Coffee, instant, reconstituted

So: make the *name* reachable (that is unambiguously right), and record the
state hazard explicitly rather than silently picking one of two wrong rows.

### 2.4 `pimentón` → `Pimento, canned`; USDA has `Spices, paprika`

    weak  pimenton                           0.412  Pimento, canned
    weak  pimentón                           0.333  Pimento, canned
    weak  pimenton picante                   0.364  Pimento, canned
    weak  pimenton dulce                     0.318  Pan dulce, NFS
    none  pimenton de la vera                -      (nothing)
    weak  smoked paprika                     0.429  Spices, paprika

    168559 | Pimento, canned |  23 |  1.1 |  0.3 | 14
    171329 | Spices, paprika | 282 | 14.1 | 12.9 | 68

A textbook false friend: *pimiento* is the vegetable, *pimentón* is the ground
dried spice. The absolute calorie error is small (a teaspoon), but the mapping
is flatly wrong and it is one point of similarity away from caching.

### 2.5 `azafrán` → nothing; USDA has `Spices, saffron`

    none  azafran                            -      (nothing)
    none  azafrán                            -      (nothing)
    ask   saffron                            0.571  Spices, saffron
    170934 | Spices, saffron | 310 | 11.4 | 5.8

Saffron is the defining ingredient of paella and it is unreachable by its
Spanish name.

### 2.6 `merluza` / `hake` — no `hake` row anywhere, but `whiting` is the same fish

    none  merluza                            -      (nothing)
    none  hake                               -      (nothing)   [top hits were milk *shakes*]
    none  pescada                            -      (nothing)

    $ ... where description ilike '%hake%'  -> only "Vanilla Shake", "SLIMFAST Shake", etc.
    173713 | Fish, whiting, mixed species, raw | 90 | 18.3 | 1.3

USDA holds no row containing the word *hake*. It holds eight `whiting` rows —
and silver hake (*Merluccius bilinearis*) is **sold in the US as whiting**.
This is an entity gap by name and a reachability gap by ingredient: the fish is
in the database under a different national name.

### 2.7 `rape` → `Grapes, raw`; USDA has `Fish, monkfish`

    weak  rape                               0.333  Grapes, raw
    ask   monkfish                           0.600  Fish, monkfish, raw
    173676 | Fish, monkfish, raw | 76 | 14.5 | 1.5

*Rape* is Spanish for monkfish and an English word besides. The right row is
one trigram hop away and never appears.

### 2.8 `cecina` → nothing; USDA has `Beef, cured, dried`

    none  cecina                             -      (nothing)
    none  cecina de leon                     -      (nothing)
    weak  dry cured ham                      0.364  Beef, cured, dried
    170604 | Beef, cured, dried | 153 | 31.1 | 1.9 | 2790

Cecina de León is air-dried beef. `Beef, cured, dried` is the only cured-beef
row and is leaner than cecina (≈250 kcal, 39 g protein, 10 g fat), so it
understates energy by around a third — medium confidence, not high.

### 2.9 The whole Iberian fish and shellfish vocabulary is unreachable

Every one of these has a perfectly good USDA row that the Spanish or Portuguese
name cannot reach:

    none  pulpo / polvo                      -> Mollusks, octopus, common (174249 / 174218)
    none  sepia                              -> Mollusks, cuttlefish (174215)
    none  chipirones / lulas                 -> Mollusks, squid (174223) / Calamari (2706333)
    none  mejillones                         -> Mussels (2706350)
    none  almejas / ameijoas                 -> Clams, raw (2706338)
    none  berberechos                        -> Cockles, raw (169803)
    none  vieiras / zamburinas               -> Scallops
    none  navajas                            -> Clams (razor clams -> "Clams, raw" 0.571)
    none  langostinos / gambas rojas         -> Crustaceans, shrimp
    none  boquerones                         -> Fish, anchovy (2706232)
    none  lubina                             -> Fish, sea bass, mixed species (175142)
    none  rodaballo                          -> Fish, turbot, european (173710)
    none  caballa                            -> Fish, mackerel (2706263)
    none  jurel / carapau                    -> Fish, mackerel  (approximate)
    weak  robalo                             0.300  Rob Roy        <- a whisky cocktail
    weak  sardinas / sardinhas               0.333  Sardine sandwich
    weak  anchoas                            0.312  Fish, anchovy   (right row, at head)
    weak  cuttlefish                         0.297  Mollusks, cuttlefish, mixed species, raw
    weak  calamares                          0.389  Calamari, cooked (right row, at head)

`robalo` → `Rob Roy` is the funniest and the most instructive: three shared
trigrams and no shared meaning.

### 2.10 `tortilla española` — the candidate list is entirely Mexican flatbread

    weak  tortilla espanola                  0.429  Tortilla, NFS
        0.429 [sur] Tortilla, NFS
        0.409 [sur] Tortilla, corn
        0.409 [sur] Soup, tortilla
        0.391 [sur] Tortilla, flour
        0.333 [sur] Tortilla, whole wheat
        0.310 [sur] Tortilla chips, plain
    weak  tortilla de patatas                0.391  Tortilla, NFS
    weak  tortilla de patata                 0.409  Tortilla, NFS
    weak  tortilla de bacalao                0.375  Tortilla, NFS
    weak  tetilla                            0.312  Tortilla, NFS
    ask   spanish tortilla                   0.476  Soup, tortilla
    none  spanish potato omelette            -      (nothing)
    weak  potato omelet                      0.241  Egg omelet or scrambled egg, with potatoes and/or onions, NS as to fat

    2707822 | Tortilla, NFS                                          | 262 |  7.0 |  5.4
    2707279 | Egg omelet or scrambled egg, with potatoes and/or onions| (the right family)

This is the brief's "candidate list itself is nonsense" case. Six candidates,
all of them Mexican flatbreads, none of them containing an egg. The right
family — `Egg omelet or scrambled egg, with potatoes and/or onions` (2707277 /
2707278 / 2707279) — exists and is reachable only from the phrase "potato
omelet", at 0.241. A tortilla española is ~170 kcal with 11 g fat and 6 g
protein per 100 g; a corn tortilla is 262 kcal, almost all carbohydrate.

### 2.11 `salmorejo` → `Salmon salad`; `feijoada` → `Feijoa, raw`

    weak  salmorejo                          0.333  Salmon salad
    weak  feijoada                           0.429  Feijoa, raw
    none  feijoada portuguesa                -      (nothing)
    auto  gazpacho                           0.643  Soup, gazpacho

Salmorejo is a thicker, bread-and-oil gazpacho; `Soup, gazpacho` (2710106) is
its nearest relative and is one row away, unreached. `Feijoa` is a tropical
fruit. Both lists contain exactly one candidate and it is the wrong food.

### 2.12 Nonsense heads, catalogued

Each is verdict `weak`, so each escalates — but the model tier is handed these:

    weak  jamon                              0.429  Jam
    weak  morcilla                           0.333  Mortadella
    weak  longaniza                          0.375  Longans, raw
    weak  bocadillo                          0.333  Armadillo
    weak  montadito                          0.308  Mojito
    weak  bolo rei                           0.308  Bologna
    weak  tarta de santiago                  0.304  Tartar sauce
    weak  pan gallego                        0.300  Moo Goo Gai Pan
    weak  pao                                0.308  Kung Pao pork
    weak  pan                                0.286  Moo Goo Gai Pan
    weak  mantequilla                        0.333  Tequila
    weak  nata / natas                       0.375  Natto
    weak  frango                             0.333  Mango, frozen
    weak  pato                               0.417  Potato patty
    weak  laranja                            0.300  Lard
    weak  cava                               0.333  Caviar
    weak  sea bream                          0.333  Bread, soy
    weak  costilla                           0.353  Tortilla, corn
    weak  tetilla                            0.312  Tortilla, NFS
    weak  picos                              0.182  Salsa, pico de gallo
    weak  rojoes                             0.111  Frijoles rojos volteados
    weak  ginjinha                           0.300  Gin
    weak  coca                               0.104  Beverages, The COCA-COLA company, Minute Maid, Lemonade
    weak  huevo                              0.294  Huevos rancheros
    weak  leche                              0.429  Dulce de Leche
    weak  azucar                             0.092  Pan Dulce, La Ricura, Salpora de Arroz con Azucar, ...
    weak  arroz                              0.133  Restaurant, Latino, arroz con leche (rice pudding)
    weak  garbanzos                          0.200  Chickpeas, (garbanzo beans, bengal gram), dry   <- right family, at head
    weak  queso de cabra                     0.333  Queso cotija
    weak  queso azul                         0.389  Queso Asadero
    weak  burgos cheese                      0.444  Cheese, brie
    weak  idiazabal cheese                   0.381  Cheese ball

### 2.13 The plain-language layer: Spanish and Portuguese common nouns

    none  cebolla / cebola / ajo / alho / patata / batata / ovo / leite
    none  canela / limon / limao / naranja / acucar / farinha / manteca
    none  banha / manteiga / aceitunas / azeitonas / azeite / vinagre
    none  almendras / amendoas / avellana / castana / castanha / habas
    none  alubias / fabes / lentejas / judias verdes / grelos / couve / nabo
    none  berenjena / beringela / calabacin / cordero / ternera / vitela
    none  solomillo / chuleta / entrecot / pavo / peru / codorniz / perdiz
    none  cerveza / cerveja / sidra / sherry / jerez / iogurte / cortado

Fifty-plus everyday ingredients, every one of which is in USDA in English.

**This is mitigated but not solved by the parse tier.** `schemas.py` already
instructs the model: *"USDA is an American database and holds almost no foreign
food WORDS… search_terms must be the plain American-English description"*, with
`pancetta -> bacon, cured pork` as the worked example. So in production a
Spanish label usually arrives alongside an English `search_terms`. Two things
still follow:

- **`label_absent` then blocks the auto-match by design.** If the user typed
  `morcilla` and the winning row is `Blood sausage`, none of the user's words
  appear in the description, so the guard fires and the item escalates. Correct
  behaviour, and it means every single one of these costs a model call, every
  time, forever — the alias tier never gets to cache a *right* answer either.
- **The whole domain is one prompt away from silence.** The resolver has no
  independent knowledge that `ajo` is garlic. A synonym table gives it one.

### 2.14 Accents are *not* a significant separate failure here

Worth stating because it is the obvious hypothesis and it is mostly wrong:

    weak  pimenton                           0.412  Pimento, canned
    weak  pimentón                           0.333  Pimento, canned
    ask   choriço                            0.455  Chorizo
    none  chourico                           -      (nothing)
    none  chouriço                           -      (nothing)
    none  pasteis de nata / pastéis de nata  -      (nothing)
    none  acorda / açorda                    -      (nothing)

Accented forms score a little lower, but in this domain the base word is
usually absent anyway, so folding accents would change almost no outcome. I am
not filing it as a finding.

---

## 3. Genuine entity gaps (searched by ingredient and by category first)

### 3.1 Cheeses — the largest true gap

    none  manchego / queso manchego / idiazabal / mahon / cabrales
    none  torta del casar / roncal / zamorano / majorero / queixo tetilla
    none  queijo da serra / queijo serra da estrela / queijo sao jorge
    none  queijo de azeitao / requeijao / requeijão
    weak  manchego cheese                    0.381  Cheese, romano
    ask   hard sheep cheese                  0.462  Cheese, parmesan, hard
    ask   sheep milk cheese                  0.478  Milk, sheep, fluid

    $ ... where description ilike '%manchego%'  -> (0 rows)
    $ ... where description ilike '%pecorino%'  -> (0 rows)
    $ ... where description ilike '%sheep%'
    175145 | Fish, sheepshead, cooked, dry heat
    175144 | Fish, sheepshead, raw
    170882 | Milk, sheep, fluid

USDA has **no sheep's-milk cheese at all** — only fluid sheep milk. So the
category search fails as well as the name search. Candidate stand-ins, with
what each gets wrong (manchego curado ≈ 380–400 kcal, 26 g protein, 33 g fat):

    171249 | Cheese, romano        | 387 | 31.8 | 26.9 | 1433   protein +22%, fat -18%
    170848 | Cheese, parmesan,hard | 392 | 35.8 | 25.0 | 1175   protein +38%, fat -24%
    328637 | Cheese, cheddar       | 409 | 23.3 | 34.0 |  654   closest on macros, wrong salt

Cheddar is the best *nutritional* fit and a culturally absurd one; romano is
the culturally nearest and misstates the macro split. I propose cheddar as a
`nutritional_fallback` at **medium**, say plainly what it gets wrong, and
**reject `manchego -> cheese`** outright: a parent category spanning ricotta
(150 kcal) to hard goat (452 kcal) carries no nutritional information.

Where a real analogue does exist I say so:

    172175 | Cheese, blue                | 353 | 21.4 | 28.7 | 1146   <- cabrales (high)
    170851 | Cheese, ricotta, whole milk | 150 |  7.5 | 10.2 |  110   <- requeijão (medium, see below)
    171241 | Cheese, gouda               | 356 | 24.9 | 27.4 |  819   <- São Jorge (medium)

`requeijão` is the case for refusing confidence: in Portugal it is a whey
cheese, essentially ricotta; in Brazil the same word means a spreadable
processed cream cheese. One word, two foods, and the tracker cannot tell which
country the user learned it in. Medium, with the ambiguity recorded.

### 3.2 Charcuterie with no analogue

    none  sobrasada / sobrasada mallorquina / alheira / alheira de mirandela
    none  farinheira / salpicao / paio / lomo embuchado / caña de lomo
    none  secreto iberico / pluma iberica / presa iberica / lacon / morcillo

*Sobrasada* is a spreadable raw-cured pork-and-paprika paste at ~450–500 kcal
and ~40 g fat. The only spreadable sausage rows are liver-based
(`Liver sausage, liverwurst, pork` 173870, 326 | 14.1 | 28.5), and liver brings
vitamin A and B12 figures that sobrasada does not have. **Rejected.**
*Alheira* (bread, poultry, garlic) and *farinheira* (flour and pork fat) have
no analogue in any USDA family. **Rejected.**

Where an analogue does exist:

    174603 | Salami, Italian, pork              | 425 | 21.7 | 37.0 | 1890  <- fuet, salchichón, chorizo curado
    174584 | Sausage, smoked link sausage, pork | 309 | 12.0 | 28.2 |  827  <- linguiça, chouriço
    168287 | Pork, cured, salt pork, raw       | 748 |  5.0 | 80.5 | 2684  <- tocino
    168277 | Pork, cured, bacon, unprepared                                 <- panceta
    168269 | Pork, fresh, ... jowl, raw        | 655 |  6.4 | 69.6 |   25  <- papada / tocino de papada

### 3.3 Seafood with genuinely nothing

    none  percebes / percebe / goose barnacles / barnacles
    $ ... where description ilike '%barnacle%'  -> (0 rows)

    none  angulas / elvers          (only "Fish, eel" — adult, 184 kcal, 11.7 g fat)
    none  mojama / cured tuna loin
    none  erizo de mar / sea urchin / ourico
    none  sea snail / periwinkle / caracol de mar
    weak  whelk                              0.194  Mollusks, whelk, unspecified, raw

Percebes, sea urchin and mojama are real entity gaps with no defensible
neighbour. **Rejected rather than approximated.** `dorada` / sea bream is a
gap by name (`%bream%` and `%porgy%` both return 0 rows) with a usable
neighbour in `Fish, snapper, mixed species` (173698, 100 | 20.5 | 1.3) —
medium.

### 3.4 Sweets and preserves

    none  membrillo / dulce de membrillo -> weak "Dulce de Leche"
    weak  quince paste                       0.316  Quinces, raw

`Quinces, raw` is 57 kcal of fresh fruit; *membrillo* is a set paste that is
roughly 70% sugar at ~250 kcal. Mapping the paste to the fruit would understate
a 30 g slab by three-quarters of its energy. **Rejected** — this is the
`ingredient_vs_dish_ambiguity` trap.

    none  turron / turron de jijona / marzipan / mazapan
    weak  almond nougat                      0.448  Candies, nougat, with almonds
    169060 | Candies, nougat, with almonds

That one is a fair analogue for turrón duro (medium). Turrón de Jijona is
ground almond and much fattier; say so rather than encode it.

    none  pasteis de nata / pastel de nata / pastel de belem
    auto  custard tart                       0.667  Custard
    weak  portuguese custard tart            0.348  Custard

`Custard` (2705682) alone is not a pastel de nata — the puff-pastry shell is
most of the fat. `Pastry, puff` (2708053) exists. This is a dish that should
decompose, not map.

### 3.5 Dishes: 86 of 95 regional dishes return nothing

Batch 4 (Catalan, Basque, Galician, Canarian, Balearic, Andalusian):
`none = 86 (91%)`. Representative:

    none  esqueixada / suquet / escudella / trinxat / samfaina / fricando
    none  ajoarriero / purrusalda / zurrukutuna / gilda / cocochas
    none  empanada gallega (though `empanada` -> auto 0.692 Empanada, NFS)
    none  filloas / lacon con grelos / caldeirada galega
    none  papas arrugadas / mojo picon / mojo verde / gofio / bienmesabe
    none  tumbet / frito mallorquin / arros brut / caldereta
    none  atascaburras / pipirrana / espetos de sardinas / flamenquin
    none  cazon en adobo / tortillitas de camarones / porra antequerana

I am **not** proposing rows or mappings for these. A tracker cannot hold a
national dish list, and the architecture already has the right answer: the
parse tier decomposes a dish into items and the resolver matches ingredients.
The correct investment is in the ingredients, which is where §1 and §2 are.
The `dish_ingredient` proposals I do make are limited to the dozen dishes whose
*signature* ingredient currently fails — the carbonara/guanciale pattern that
started this audit.

---

## 4. What I refused to encode

Recorded because refusals are half the job.

| Surface | Considered | Why refused |
|---|---|---|
| manchego | `Cheese` (parent) | Spans 150–452 kcal. A parent category this wide carries no nutritional information — the phantom-precision failure. |
| paneer-style reasoning on queso fresco | queso fresco → mozzarella | Different make, different moisture. Not proposed. |
| sobrasada | Liver sausage, liverwurst | Liver brings vitamin A and B12 that sobrasada has none of; would fabricate micronutrient coverage. |
| alheira, farinheira | any sausage row | Bread- and flour-based; every USDA sausage row is meat-and-fat. No neighbour. |
| membrillo | Quinces, raw | Paste is ~70% added sugar; the fruit row understates energy ~4×. |
| percebes | any crustacean | No barnacle row and no defensible substitute. `%barnacle%` = 0 rows. |
| angulas | Fish, eel | Elvers are whole glass eels; the row is adult eel at 11.7 g fat. Different food, and most restaurant "angulas" are surimi anyway. |
| mojama | Beef, cured, dried | Cured *tuna*; matching it to cured beef is a category error dressed as a fallback. |
| gofio | any flour | Toasted mixed grain; the toasting and the grain blend both matter and neither is in any row. |
| torta del casar | Cheese, brie | Sheep, raw-milk, thistle-rennet, runny. Brie is a cow bloomy-rind. Culturally and compositionally wrong. |
| grelos | Broccoli, raw | Currently `auto` at 0.688. `Brassica rapa` leaf ≠ broccoli floret; propose Collards instead, medium. |
| erizo de mar, cocochas, papada de cerdo (as a dish) | — | No neighbour; leave as an honest "define it yourself". |
| any of the 86 regional dishes | new food rows | Decompose to ingredients. Encoding dishes is how a tracker acquires a maintenance burden it cannot carry. |

---

## 5. Recommendations, in the order I would do them

1. **Stop `chorizo`, `octopus` and `chicken` auto-matching.** These three are
   `auto`, so they are silent and they cache. Whatever mechanism is chosen —
   an ambiguity list, a rule that a bare one-word FNDDS description cannot
   score 1.000 into an auto-match, or a `homograph` guard alongside
   `label_absent` — these three should escalate.
2. **A synonym tier that maps a surface form to an `fdc_id` without going
   through similarity.** Every §2 finding is fixed by one, and none of them is
   fixable by tuning a threshold: `morcilla`→`Blood sausage` scores 0.333, and
   no floor that admits it excludes `Mortadella`.
3. **Record the salted/fresh and boiled/fried state hazards** on the
   bacalhau and pulpo mappings specifically. They are the two places in this
   domain where the state is worth more than the identity.
4. Leave the 86 regional dishes alone.
