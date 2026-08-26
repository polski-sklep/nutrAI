# Knowledge audit — Italian and French cuisine

26 Aug 2026. 881 distinct terms through `scripts/probe_knowledge.py` against the
live `food` table (13,636 rows + 15 `user_product`). Read-only throughout.
Every line quoted below is verbatim probe output.

```
none=403 (46%)   weak=254 (29%)   ask=116 (13%)   auto=108 (12%)
```

Term lists live in the session scratchpad; the ten batches were cured meats (60),
cheeses (67), Italian dishes (86), French dishes (114), pasta shapes (48),
defining ingredients (105), desserts/drinks/aromatics (103), regional +
alternative spellings (115), descriptive-English phrasings (103), and
larder staples (78).

---

## 0. Headline

**Nearly half this cuisine is invisible to the resolver.** 403 of 881 terms
return *nothing at all* — not a bad candidate, an empty list. The model tier is
never even offered a choice.

**The auto-match guards work.** I ran every `auto` verdict back through
`state_conflicts`, `label_absent` and `unrequested_qualifier`
(scratchpad `effective.py`, which reproduces `resolve_items`' "best candidate
that survives all of them"). Of 108 `auto` verdicts, the guards disqualified
every semantically wrong one I found except two. `spaghetti` → `Spaghetti sauce`
(0.667), `olive` → `Olive oil` (0.667), `marsala` → `Veal Marsala` (0.615) and
`sour cream` → `Sour cream, light` (0.647) are all blocked by
`unrequested_qualifier` and escalate instead. That is the guard wave doing
exactly what CLAUDE.md claims for it, measured rather than assumed.

The two that get through are in §3 and both are ordinary larder words, not
Italian ones.

**The dominant failure in this domain is reachability, and §1 of RECONCILED.md
explains all of it.** A person types the short name. USDA writes the long one.

---

## 1. Reachability: the right row exists and the query cannot reach it

### 1.1 The motivating case reproduces exactly

```
none  guanciale                          -      (nothing)
weak  pork jowl                          0.400  Pork jerky
weak  cured pork jowl                    0.440  Pork, cured, salt pork, raw
```

and the row is there:

```
 168269 | sr_legacy_food | Pork, fresh, variety meats and by-products, jowl, raw
```

655 kcal, 69.6 g fat per 100 g — a very good stand-in for guanciale on energy
and fat, and a bad one on sodium (25 mg against ~1,500 mg for the cured
product). `Pork jerky` outranks it on the query that names the cut.

### 1.2 Osso buco — the same shape, in one dish

```
none  ossobuco                           -      (nothing)
weak  osso buco                          0.175  Veal, foreshank, osso buco, separable lean only, cooked, braised
```

USDA carries the dish's name *in the description* (172646, 172649) and the
query scores 0.175 against it. The single-word spelling — the one Italians and
most menus use — returns nothing, because trigram + tsvector both key on the
space. `veal shank` (0.324) and `braised veal shank` (0.333) do no better.

### 1.3 Cheeses cannot reach their own rows without the word "cheese"

The clearest demonstration of the length/coverage mechanism I found. Same row,
same database, one extra token:

```
weak  brie                               0.417  Cheese, brie
auto  brie cheese                        1.000  Cheese, brie
weak  parmesan                           0.429  Cheese, parmesan, hard
auto  parmesan cheese                    0.762  Cheese, parmesan, hard
weak  pecorino romano                    0.318  Cheese, romano
auto  pecorino romano cheese             0.636  Cheese, romano
ask   gruyere                            0.533  Cheese, gruyere
auto  gruyere cheese                     1.000  Cheese, gruyere
ask   roquefort                          0.588  Cheese, roquefort
auto  roquefort cheese                   1.000  Cheese, roquefort
auto  romano cheese                      1.000  Cheese, romano
```

Nobody types "brie cheese". They type "brie", and it lands in `weak` — the
bucket whose name means *the right answer is probably absent*, when the right
answer is the top candidate.

### 1.4 Exact rows sitting below the weak floor

Every one of these is the correct USDA row, ranked first, scoring below 0.45:

```
weak  farro                              0.273  Farro, pearled, dry, raw
weak  oxtail                             0.429  Beef, oxtails
weak  squid                              0.194  Mollusks, squid, mixed species, raw
weak  cuttlefish                         0.297  Mollusks, cuttlefish, mixed species, raw
weak  turbot                             0.280  Fish, turbot, european, raw
weak  morels                             0.238  Mushrooms, morel, raw
weak  chanterelles                       0.393  Mushrooms, Chanterelle, raw
weak  tomato paste                       0.342  Tomato, paste, canned, without salt added
weak  sage                               0.278  Spices, sage, ground
weak  oregano                            0.381  Spices, oregano, dried
weak  anchovies                          0.353  Fish, anchovy
weak  sardines                           0.429  Fish, sardines, canned
weak  foie gras                          0.238  Pate de foie gras, canned (goose liver pate), smoked
weak  antipasto                          0.238  Antipasto with ham, fish, cheese, vegetables
weak  calzone                            0.286  Calzone, with cheese, meatless
weak  cannelloni                         0.250  Cannelloni, cheese- and spinach-filled, no sauce
weak  manicotti                          0.303  Manicotti, cheese-filled, no sauce
weak  ravioli                            0.296  Ravioli, cheese-filled, canned
weak  tortellini                         0.344  Tortellini, meat-filled, no sauce
weak  focaccia                           0.391  Focaccia, Italian, plain
weak  chocolate mousse                   0.370  Desserts, mousse, chocolate, prepared-from-recipe
weak  mirepoix                           0.300  Mirepoix, cooked, as ingredient
weak  eclair                             0.179  Cream puff, eclair, custard or cream filled, iced
weak  veal shank braised                 0.333  Veal, shank (fore and hind), separable lean only, cooked, braised
weak  smoked bacon                       0.448  Pork bacon, smoked or cured, cooked
weak  salt cod                           0.235  Fish, cod, Atlantic, dried and salted
weak  snails                             0.238  Mollusks, snail, raw
weak  guinea hen                         0.440  Guinea hen, meat only, raw
weak  pork shoulder                      0.292  Pork, fresh, shoulder, whole, separable lean only, raw
weak  lamb shoulder                      0.222  Lamb, shoulder, arm, separable lean and fat, trimmed to 1/4" fat, choice, raw
weak  bread crumbs                       0.433  Bread, crumbs, dry, grated, plain
```

None of these needs a synonym table entry pointing anywhere new. They need the
ranking function fixed, per RECONCILED.md §3. I list them because they are the
evidence that the fix is worth its cost, and because a synonym table built
without knowing this would fill up with `farro → farro`.

### 1.5 Pasta shapes: a category-wide blind spot

USDA has **no shape names at all**. Not one. There is `Pasta, cooked` (157 kcal)
and `Pasta, dry, enriched`, and there is no `Spaghetti, cooked`.

```
none  bucatini / rigatoni / penne / fusilli / farfalle / orecchiette /
      tagliatelle / fettuccine / pappardelle / linguine / trofie / casarecce /
      paccheri / cavatelli / strozzapreti / garganelli / tonnarelli /
      capellini / ziti / conchiglie / gemelli / bigoli / malloreddus /
      busiate / pizzoccheri / tortelloni / agnolotti / maltagliati /
      stelline / ditalini / orzo                     (all: nothing)
```

37 of 48 pasta terms return nothing. And the one shape USDA *does* spell:

```
auto  spaghetti                          0.667  Spaghetti sauce
```

with a candidate list containing no pasta at all —

```
0.667 Spaghetti sauce          0.500 Spaghetti, spinach, dry
0.435 Spaghetti, spinach, cooked   0.435 Spaghetti squash, cooked
0.435 Spaghetti sauce, fat free
```

`unrequested_qualifier('spaghetti','Spaghetti sauce')` returns `Spaghetti sauce`,
so the auto-match is blocked and the item escalates — but tier 3 is then handed
five candidates, four of them a sauce and one a squash. That is the
"candidate list itself is nonsense" case the brief carves out.

Shape does not change composition. `penne → Pasta, cooked` is as safe a mapping
as this domain contains.

### 1.6 Synonyms USDA already satisfies under another name

```
none  emmental                           -      (nothing)      # USDA: Cheese, swiss
none  chevre                             -      (nothing)      # USDA: Cheese, goat
none  polenta                            -      (nothing)      # USDA: Cornmeal mush
none  boeuf bourguignon                  -      (nothing)      # USDA: Beef burgundy
weak  beef bourguignon                   0.318  Beef burgundy
none  quiche lorraine                    -      (nothing)      # USDA: Quiche with meat, poultry or fish
none  baguette                           -      (nothing)      # USDA: Bread, French or Vienna
none  courgette / aubergine              -      (nothing)      # USDA: zucchini / eggplant
none  prawns                             -      (nothing)      # USDA: Shrimp
none  boudin noir                        -      (nothing)      # USDA: Blood sausage (and "blood sausage" is auto 1.000)
weak  eggplant parmigiana                0.440  Veal parmigiana   # USDA: Eggplant parmesan casserole, regular
```

`eggplant parmigiana → Veal parmigiana` deserves its own line. The row
`Eggplant parmesan casserole, regular` (2710050, 155 kcal, 10.5 g fat) exists;
the query lands on a **meat** dish instead. All three phrasings do:

```
weak  parmigiana di melanzane            0.379  Veal parmigiana
weak  eggplant parmigiana                0.440  Veal parmigiana
weak  melanzane alla parmigiana          0.355  Veal parmigiana
ask   parmigiano                         0.500  Veal parmigiana
weak  parmigiano reggiano                0.391  Veal parmigiana
weak  parmigiano-reggiano                0.391  Veal parmigiana
```

`Veal parmigiana` is a four-way attractor for the word "parmigian-": the cheese,
the cheese's DOP name, and the aubergine dish all fall into it.

---

## 2. Entity gaps: USDA genuinely has nothing

Checked by ingredient and by category, not only by name. Searches pasted.

### 2.1 The cured-meat shelf

`select ... where description ilike '%jowl%' or '%andouille%' or
'%blood sausage%' or '%foie gras%' or '%rillette%' or '%merguez%'` returns
**four rows**: Blood sausage ×2, Pate de foie gras, and the jowl row. That is
the whole of it.

```
none  guanciale, pancetta, lardo, culatello, bresaola, nduja, soppressata,
      coppa, capocollo, speck, finocchiona, salsiccia, luganega, cotechino,
      zampone, ciccioli, saucisson, saucisson sec, andouille, andouillette,
      boudin noir, boudin blanc, rillettes, jambon de bayonne, jambon cru,
      ventreche, magret de canard, confit de canard, terrine, galantine,
      merguez                                                  (all: nothing)
weak  porchetta                          0.312  Bruschetta
weak  lardons                            0.444  Lard
weak  duck confit                        0.333  Duck egg, cooked
weak  pate de campagne                   0.320  Champagne punch
```

Near neighbours *do* exist for most of them and are named in §5:
`Pork, cured, bacon, unprepared` (393 kcal / 37.1 g fat / 751 mg Na),
`Salami, Italian, pork` (425 / 37.0 / 21.7), `Beef, cured, dried` (153 / 1.9 /
31.1), `Ham, prosciutto` (195 / 8.3 / 27.8), `Duck, domesticated, meat and
skin, cooked, roasted` (337 / 28.4 / 19.0). So these are *fallback*
opportunities, not dead ends — but the fallback has to be written down, because
nothing in the ranking will find `Beef, cured, dried` from the word "bresaola".

**`andouille` and `andouillette` I refuse to map.** US USDA data would carry the
Cajun smoked pork sausage; the French article is a cold chitterling sausage and
the two are not interchangeable. USDA has neither, so nothing is lost by saying
so, and a great deal is lost by pretending.

### 2.2 Risotto and its rice

```
none  risotto, risotto alla milanese, risotto ai funghi, arborio rice
weak  carnaroli rice                     0.389  Rice cake
weak  risotto rice                       0.312  Rice milk
weak  saffron risotto                    0.364  Spices, saffron
weak  mushroom risotto                   0.409  Mushrooms, raw
```

`... where description ~* 'risotto|arborio'` returns **zero rows**. There is no
risotto in this database in any form. `Rice, white, short-grain, enriched,
cooked` (168882, 130 kcal) is arborio's honest identity; the dish itself has to
be decomposed.

### 2.3 Polenta

`... ~* 'polenta'` → zero rows. `Cornmeal mush, NS as to fat` (2708373, 71 kcal,
12.3 g carb) *is* polenta under an American name, and is unreachable from the
Italian one.

### 2.4 Porcini, truffle, and the aromatics

```
none  porcini, tartufo, zafferano, colatura di alici, bottarga, pinoli,
      soffritto, battuto, puntarelle, finocchio, fiori di zucca, cepes,
      girolles, morilles, echalote                             (all: nothing)
weak  dried porcini                      0.389  Pear, dried
weak  truffle                            0.400  Pate, truffle flavor
weak  black truffle                      0.316  Bread, black
weak  truffle oil                        0.333  Pate, truffle flavor
```

`... ~* 'porcini'` → zero rows. `Mushrooms, Chanterelle, raw` and
`Mushrooms, morel, raw` exist; porcini does not. Fresh porcini → generic
mushroom is defensible; **dried** porcini is not (roughly ten times the dry
matter), and I do not propose it.

Truffle's only rows are `Pate, truffle flavor` and truffle-flavoured products.
A fresh truffle is an entity gap, but a 5 g shaving is nutritionally
irrelevant, which is why it is in §6 rather than §5.

### 2.5 Regional dishes with no analogue

`cassoulet, coq au vin, blanquette de veau, pot au feu, pissaladiere, socca,
tartiflette, choucroute, quenelles, gratin dauphinois, aligot, truffade,
baeckeoffe, flammekueche, hachis parmentier, vichyssoise, cacciucco, ribollita,
panzanella, caponata, bagna cauda, vitello tonnato, saltimbocca, coda alla
vaccinara, trippa alla romana, arancini, suppli, pastiera, cassata, cannoli,
sfogliatella, panna cotta, zabaglione, kouign amann, far breton, canele,
clafoutis, tarte tatin, paris-brest, ile flottante` — all `none`.

These are dishes, and the right treatment for a dish is a decomposition, not a
row. See §5's `dish_ingredient` proposals.

### 2.6 Drinks

`prosecco, chianti, barolo, amarone, vin santo, limoncello, grappa, campari,
negroni, vermouth, cognac, armagnac, calvados, pastis, pernod, kir, sambuca,
nocino` — all `none`. But:

```
auto  white wine                         1.000  Wine, white
auto  red wine                           1.000  Wine, red
auto  sparkling wine                     1.000  Wine, sparkling
auto  dessert wine                       0.684  Wine, dessert, sweet
ask   amaretto liqueur                   0.471  Liqueur
```

`Liqueur` (2710623, 279 kcal) and `Alcoholic beverage, distilled, all (gin, rum,
vodka, whiskey) 80 proof` (174815, 231 kcal) cover the whole spirits shelf at
better-than-nothing accuracy. Varietal names are pure reachability.

---

## 3. Wrong-confident matches

Two survive all three guards. Both are larder words, not Italian ones — which is
what makes them worse, because they will fire in every cuisine.

### 3.1 `egg white` → dried egg white, 7× the energy

```
auto  egg white                          0.625  Egg, white, dried
```

`Egg, white, dried` (323793) is **376 kcal / 100 g**. `Egg, white only, raw`
(2707168) is 52. Measured guard behaviour:

```
state_conflicts(None,  'Egg, white, dried') -> None
state_conflicts('raw', 'Egg, white, dried') -> dried
state_conflicts('fresh','Egg, white, dried') -> None
unrequested_qualifier('egg white','Egg, white, dried') -> None
```

`dried` is in `_DRY_WORDS`, so `unrequested_qualifier` exempts it as
preparation and hands the judgement to `state_conflicts` — which has nothing to
judge when the parse leaves `state` null or says `unknown`, and *still* nothing
when it says `fresh`. This is the failure CLAUDE.md records for
"egg white, fried", one guard-generation later, arriving through the case where
the user simply did not say. It auto-matches, and it writes an alias that is
never re-checked.

Carbonara is eggs. This is the single most consequential finding in the domain.

### 3.2 `walnut` → walnut oil

```
auto  walnut                             0.636  Oil, walnut
ask   walnuts                            0.471  Nuts, walnuts, glazed
```

`Oil, walnut` (171030) is 884 kcal / 100 g of pure fat. `Nuts, walnuts, english`
(170187) is 654 and `Walnuts, excluding honey roasted` (2707531) exists too.
Guards: `label_absent=False`, `unrequested_qualifier=None` — the first segment
"Oil" shares no word with the query so it is judged a *name*, not a narrowing
qualifier, and names are left to similarity. Only the plural escapes
(`unrequested_qualifier('walnuts','Oil, walnut')` → `walnut`, because the
prefix-match is directional).

Ligurian salsa di noci, Roquefort salads, and every "handful of walnuts"
resolve to oil.

### 3.3 Near-misses worth recording (blocked, but only just)

```
ask   marsala                            0.615  Veal Marsala          # wine -> a veal dish
ask   bolognese                          0.500  Bologna               # sauce -> luncheon meat
ask   zucchini                           0.600  Bread, zucchini       # vegetable -> a cake
ask   carrot                             0.500  Muffin, carrot
ask   brandade                           0.455  Brandy
ask   burrata cheese                     0.478  Burrito, beef, cheese
ask   comte cheese                       0.500  Cheese, colby
weak  cantal                             0.375  Cantaloupe, raw
weak  mimolette                          0.308  Mimosa
weak  bearnaise                          0.364  Bear
weak  sorrel                             0.333  Squirrel
weak  branzino                           0.333  Brandy
weak  italian parsley                    0.421  Italian Ice
weak  cassata                            0.333  Cassava, raw
weak  mille-feuille                      0.385  Millet
weak  pain de campagne                   0.320  Champagne punch
weak  peperoncino                        0.300  Pepperoni, NFS
weak  pizza margherita                   0.350  Margarita
weak  maritozzo                          0.333  Margarita
weak  unsalted butter                    0.348  Pretzels, soft, ready-to-eat, unsalted, no butter
weak  gorgonzola cheese                  0.429  Cheese, goat
weak  taleggio cheese                    0.375  Taco, cheese only
weak  mascarpone cheese                  0.346  Cheese, provolone
weak  reblochon cheese                   0.381  Roll, cheese
weak  raclette cheese                    0.400  Roll, cheese
```

`unsalted butter` is worth a second look. CLAUDE.md records it scoring 0.73
against `Butter, stick, unsalted`; that row is now filtered by `UNUSABLE_ROW`
(no energy value), and with it gone the query's best remaining candidate is a
*pretzel*. The filter is right and the consequence was not anticipated.

---

## 4. Preparation-state and ambiguity notes

- `couscous` → `Couscous, dry` (auto 0.636) and `short grain white rice` →
  `Rice, white, short-grain, raw, unenriched` (auto 0.639). Correct food, dry
  form. Fine when the parse supplies `cooked`; a 3× mass error when it does not.
- `stracciatella` is three foods: burrata's cream-and-curd filling, a Roman
  egg-drop soup, and a gelato flavour. It returns `none`, and I propose nothing
  for it — a single mapping would be wrong two-thirds of the time.
- `raclette` and `fondue` are each a cheese and a dish. `alpine cheese fondue`
  auto-matches `Cheese fondue` (0.667) correctly; `raclette` alone returns
  nothing.
- `marsala`, `chianti` and `barolo` are wines that name dishes. `marsala` at
  0.615 onto `Veal Marsala` is 5 thousandths from auto-matching a wine to a
  veal dish.
- `confit` alone returns nothing and means both duck confit and fruit preserve.

---

## 5. What I propose to encode

Full list in the structured return. Grouping and reasoning:

**High — cured meats.** guanciale/pork jowl → 168269 (energy and fat right,
sodium badly low, and that should be recorded with the mapping);
pancetta → `Pork, cured, bacon, unprepared`; bresaola → `Beef, cured, dried`;
speck and culatello → `Ham, prosciutto`; soppressata, saucisson sec,
finocchiona, salame → `Salami, Italian, pork`; boudin noir → `Blood sausage`;
foie gras → the pate row it already ranks first at 0.238.

**High — cheeses.** pecorino romano → `Cheese, romano` (romano *is* pecorino
romano in USDA); parmigiano reggiano and grana padano → `Cheese, parmesan,
hard`; emmental → `Cheese, swiss`; comté and beaufort → `Cheese, gruyere`
(413/32.3/29.8 against comté's 417/34/29); gorgonzola, bleu d'auvergne and
fourme d'ambert → `Cheese, blue`; cantal → `Cheese, cheddar` (403/33.3/22.9 vs
cantal 390/33/24); chèvre → `Cheese, goat`; fior di latte → `Cheese, mozzarella,
whole milk`; caciocavallo → `Cheese, provolone`.

**Medium — cheeses where the number moves.** mascarpone → `Cheese, cream`
understates fat by about 20% (350/34.4 against ~429/44) and must be flagged as
such; burrata → whole-milk mozzarella understates fat and overstates protein;
reblochon, taleggio, époisses, munster, livarot, pont-l'évêque → `Cheese, brie`
or `Cheese, limburger`, which match on numbers (334/27.7 and 327/27.3) and not
on culture; crème fraîche → `Cream, heavy` overstates by ~15%; raclette →
`Cheese, gouda` (356/27.4/24.9, near-exact).

**High — pasta shapes.** Every dried shape → `Pasta, cooked` (2708357). Shape is
not a nutritional variable. Egg-ribbon shapes (tagliatelle, pappardelle,
tajarin, tonnarelli) → `Pasta, homemade, made with egg, cooked` (168901,
130 kcal) at medium, because usage splits between fresh egg and dried semolina.

**High — plain synonyms.** polenta → `Cornmeal mush`; arborio and carnaroli →
`Rice, white, short-grain, enriched, cooked`; boeuf bourguignon → `Beef
burgundy`; quiche lorraine → `Quiche with meat, poultry or fish`; eggplant
parmigiana → `Eggplant parmesan casserole, regular`; ossobuco → 172646;
baguette → `Bread, French or Vienna`; courgette → zucchini; aubergine →
eggplant; prawns → shrimp.

**High — dish decompositions.** carbonara, cacio e pepe, amatriciana, gricia,
ragù alla bolognese, pesto alla genovese, risotto alla milanese, cassoulet,
coq au vin, tartiflette, choucroute garnie, gratin dauphinois, brandade,
pissaladière, socca/farinata, salade niçoise, bagna càuda, vitello tonnato.
Each names ingredients that are themselves reachable (or reachable once the
synonyms above exist), which is the test I applied: a decomposition into
unresolvable parts is not a decomposition.

---

## 6. What I refuse to encode

- **andouille / andouillette → any sausage row.** The French article is a cold
  chitterling sausage; a US database's "andouille" is Cajun smoked pork. USDA
  has neither. A wrong sausage is worse than an escalation.
- **halloumi-style parent mappings generally.** `taleggio → cheese`,
  `nduja → sausage` and the like are nutritionally near-useless: the category
  spans 250–420 kcal and 7–35 g fat. Where I map to a category at all I map to
  a *specific row whose numbers I checked*, and say by how much it is off.
- **dried porcini → mushrooms.** ~10× the dry matter. `dried porcini` currently
  returns `Pear, dried` (0.389), which is absurd, and the fix is not a mapping
  to fresh mushrooms.
- **truffle → anything.** `Pate, truffle flavor` is a pâté. A fresh truffle has
  no row and, at 5 g, no material effect. Leave it to escalate.
- **stracciatella → anything.** Three unrelated foods share the word.
- **ossau-iraty, tomme de savoie, saint-nectaire, morbier, banon, robiola,
  montasio, castelmagno → any row.** I could not find a neighbour I would
  defend on numbers. Escalating is correct here.
- **fromage blanc / petit suisse → cottage cheese or cream cheese.** Fromage
  blanc is 100–160 kcal; both candidates are wrong by more than 2×.
- **nduja → salami.** Tempting (it is a salami), but 'nduja is spreadable and
  eaten by the spoon while salami is eaten by the slice, so the portion prior
  would be wrong even where the composition is close. Medium at best; I list it
  at medium and would accept it being dropped.
- **peperoncino → pepperoni.** A chilli is not a sausage. Named here so nobody
  encodes the 0.300 match that already exists.
- **Anything for `raclette` bare.** Cheese or dish, unresolvable without context.

---

## 7. Note for whoever implements

The single highest-value change in this domain is not in a knowledge table. It
is §1.3: a query of one word cannot reach a `Cheese, X` row, and adding the word
"cheese" moves the same row from 0.417 to 1.000. Fix that and roughly forty of
the findings above evaporate. The synonym table should then be built for the
things that remain — the cured meats, the dish decompositions, and the pasta
shapes, which no ranking change can reach because USDA does not contain the
words at all.

And fix `egg white`. It is one alias away from being permanent.
