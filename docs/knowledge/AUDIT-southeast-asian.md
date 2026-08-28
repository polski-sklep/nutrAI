# AUDIT-southeast-asian

28 Aug 2026. Domain: Thai, Vietnamese, Filipino, Indonesian, Malaysian,
Singaporean, Cambodian, Burmese, Lao. Probe: `scripts/probe_knowledge.py`
(no alias tier — measures knowledge, not cache). Database read-only, SELECT only.

Verdicts: `none` nothing returned | `weak` below the weak floor | `ask` goes to
the model tier (the system working) | `auto` taken with no model consulted.

Written incrementally, batch by batch. Sections are appended to as batches land.

## Verdict counts

**411 terms probed**, in 7 batches, all against the same HEAD in one sitting.

    none = 197 (48%)   weak = 110 (27%)   ask = 50 (12%)   auto = 54 (13%)

Per batch:

| batch | terms | none | weak | ask | auto |
|---|---|---|---|---|---|
| 1 Thai dishes | 50 | 28 | 16 | 4 | 2 |
| 2 core ingredients / condiments | 51 | 18 | 18 | 3 | 12 |
| 3 Vietnamese | 52 | 31 | 15 | 6 | 0 |
| 4 Filipino | 56 | 43 | 8 | 5 | 0 |
| 5 Indonesian / Malaysian / Singaporean | 67 | 46 | 11 | 5 | 5 |
| 6 Cambodian / Burmese / Lao, staples, produce | 66 | 22 | 22 | 9 | 13 |
| 7 defining ingredients, proteins, aromatics | 69 | 9 | 20 | 18 | 22 |

**48% of this domain's vocabulary returns nothing at all** — the worst figure of
any audit written so far (Chinese was 26%). Filipino alone is 77% `none`.

The gradient across batches is the whole story in one table: dish names are
almost entirely absent (batches 1, 3, 4, 5 are 56-77% `none`), while ingredients
that happen to have English names are largely reachable (batch 7 is 13% `none`
and 32% `auto`). The system knows *ingredients* and does not know *this
cuisine's words for them*.


### Batch 1 — Thai dishes (50 terms)

    ask=4 (8%)  auto=2 (4%)  none=28 (56%)  weak=16 (32%)

```
auto  pad thai                           0.692  Pad Thai, NFS
weak  pad see ew                         0.308  Papad
weak  pad krapow                         0.308  Papad
none  pad kee mao                        -      (nothing)
none  som tam                            -      (nothing)
weak  green papaya salad                 0.355  Mixed salad greens, raw
none  tom yum                            -      (nothing)
none  tom yum goong                      -      (nothing)
none  tom kha                            -      (nothing)
none  tom kha gai                        -      (nothing)
weak  massaman curry                     0.300  Beef curry
none  massaman                           -      (nothing)
weak  panang curry                       0.333  Beef curry
none  panang                             -      (nothing)
none  khao soi                           -      (nothing)
weak  green curry                        0.389  Chicken curry
none  gaeng keow wan                     -      (nothing)
weak  red curry                          0.400  Beef curry
weak  thai red curry                     0.344  SMART SOUP, Thai Coconut Curry
weak  larb                               0.429  Lard
none  laab gai                           -      (nothing)
none  larb moo                           -      (nothing)
weak  khao pad                           0.364  Papad
ask   thai fried rice                    0.550  Rice, fried, NFS
weak  mango sticky rice                  0.333  Mango, raw
none  khao niao mamuang                  -      (nothing)
weak  sticky rice                        0.375  Soup, rice
auto  glutinous rice                     0.714  Flour, rice, glutinous
none  satay                              -      (nothing)
none  moo ping                           -      (nothing)
none  gai yang                           -      (nothing)
none  pla rad prik                       -      (nothing)
ask   thai basil chicken                 0.464  Pad Thai with chicken
none  crying tiger                       -      (nothing)
ask   thai green curry chicken           0.565  Chicken curry
weak  thai iced tea                      0.375  Long Island iced tea
none  cha yen                            -      (nothing)
none  kanom krok                         -      (nothing)
none  tod mun pla                        -      (nothing)
weak  thai fish cake                     0.417  Fish, cake or patty
weak  pomelo salad                       0.438  Pea salad
none  yum woon sen                       -      (nothing)
weak  boat noodles                       0.400  Noodles, cooked
none  kuay teow                          -      (nothing)
none  guay tiew                          -      (nothing)
none  thai omelette                      -      (nothing)
none  kai jeow                           -      (nothing)
none  khao man gai                       -      (nothing)
ask   thai chicken rice                  0.481  Pad Thai with chicken
none  roti sai mai                       -      (nothing)
```

Neighbour searches run for this batch (read-only `ILIKE` over `food.description`):

```
ILIKE %thai%      -> 7 rows, ALL of them Pad Thai variants plus "Hot Thai sauce"
                     and "SMART SOUP, Thai Coconut Curry". Pad Thai is the only
                     Thai dish USDA names.
ILIKE %satay%     -> 0 rows
ILIKE %galangal%  -> 0 rows
ILIKE %lemongrass%-> 1 row, "SMART SOUP, Vietnamese Carrot Lemongrass" (a
                     branded soup, not the aromatic)
ILIKE %papaya%    -> 11 rows, all ripe papaya (raw/canned/nectar/dried).
                     No green/unripe papaya row.
```


### Batch 2 — core ingredients and condiments (51 terms)

    ask=3 (6%)  auto=12 (24%)  none=18 (35%)  weak=18 (35%)

```
auto  fish sauce                         1.000  Fish sauce
none  nam pla                            -      (nothing)
none  nuoc mam                           -      (nothing)
ask   shrimp paste                       0.450  Kung Pao shrimp
none  kapi                               -      (nothing)
none  belacan                            -      (nothing)
none  terasi                             -      (nothing)
none  bagoong                            -      (nothing)
none  galangal                           -      (nothing)
auto  ginger                             0.636  Tea, ginger
none  kha                                -      (nothing)
none  kaffir lime leaves                 -      (nothing)
weak  makrut lime                        0.312  Lime, raw
weak  lime leaves                        0.350  Taro leaves, raw
weak  thai basil                         0.400  Basil, raw
weak  holy basil                         0.400  Basil, raw
none  horapha                            -      (nothing)
none  krapow                             -      (nothing)
weak  sweet basil                        0.375  Basil, raw
weak  palm sugar                         0.400  Sugar, NFS
weak  coconut sugar                      0.333  Sauce, peanut, made from coconut, water, sugar, peanuts
auto  tamarind                           1.000  Tamarind
ask   tamarind paste                     0.600  Tamarind
auto  tamarind pulp                      0.643  Tamarind
weak  lemongrass                         0.282  SMART SOUP, Vietnamese Carrot Lemongrass
weak  coriander root                     0.385  Spices, coriander seed
none  bird's eye chilli                  -      (nothing)
weak  thai chilli                        0.308  Pad Thai with chicken
none  prik kee noo                       -      (nothing)
auto  coconut milk                       1.000  Coconut milk
auto  coconut cream                      0.765  Pie, coconut cream
none  santan                             -      (nothing)
weak  green curry paste                  0.304  Guava paste
weak  red curry paste                    0.333  Beef, cured, pastrami
weak  curry paste                        0.353  Fish curry
none  massaman curry paste               -      (nothing)
auto  oyster sauce                       1.000  Oyster sauce
auto  soy sauce                          1.000  Soy sauce
none  kecap manis                        -      (nothing)
auto  sweet soy sauce                    0.643  Soy sauce
auto  dark soy sauce                     0.643  Soy sauce
auto  rice noodles                       0.765  Rice noodles, dry
weak  rice vermicelli                    0.319  Rice and vermicelli mix, rice pilaf flavor, unprepared
weak  glass noodles                      0.381  Noodles, cooked
weak  mung bean noodles                  0.378  Long rice noodles, made from mung beans, cooked
weak  cellophane noodles                 0.317  Noodles, chinese, cellophane or long rice (mung beans), dehydrated
ask   wide rice noodles                  0.591  Rice noodles, dry
none  sen lek                            -      (nothing)
auto  rice paper                         1.000  Rice paper
none  banh trang                         -      (nothing)
weak  tapioca starch                     0.203  Rolls, gluten-free, ... tapioca starch ...
```

Neighbour searches for this batch:

```
ILIKE %shrimp paste%   -> 0 rows
ILIKE %anchovy paste%  -> 0 rows
ILIKE %cellophane%     -> 1: 174258 Noodles, chinese, cellophane or long rice
                              (mung beans), dehydrated
ILIKE %long rice%      -> 2708355 Long rice noodles, made from mung beans, cooked
                          174258 (above)
ILIKE %coconut cream%  -> 11 rows incl. 170580 Nuts, coconut cream, raw
                          (liquid expressed from grated meat)  <- the real one
ILIKE %coconut milk%   -> 9 rows incl. 2705413 "Coconut milk" (FNDDS),
                          2707568 "Coconut milk, used in cooking",
                          170172/170173 Nuts, coconut milk raw/canned
```

Nutrients pulled for the rows in dispute (read-only `food_nutrient`, per 100 g):

```
  2705413 Coconut milk                       kcal=31   prot=0.21 fat=2.08  carb=2.92
  2707568 Coconut milk, used in cooking      kcal=230  prot=2.29 fat=23.84 carb=5.54
   170173 Nuts, coconut milk, canned         kcal=197  prot=2.02 fat=21.33 carb=2.81
   170172 Nuts, coconut milk, raw            kcal=230  prot=2.29 fat=23.84 carb=5.54
  2708006 Pie, coconut cream                 kcal=297  prot=2.55 fat=17.83 carb=31.96 sug=18.66
   170580 Nuts, coconut cream, raw           kcal=330  prot=3.63 fat=34.68 carb=6.65
  2707571 Coconut cream, canned, sweetened   kcal=357  prot=1.17 fat=16.31 carb=53.21 sug=51.5
   174258 Cellophane/long rice, dehydrated   kcal=351  prot=0.16 fat=0.06  carb=86.09
  2708355 Long rice noodles, cooked          kcal=84   prot=0.04 fat=0.01  carb=20.66
```


### Batch 3 — Vietnamese (52 terms)

    ask=6 (12%)  none=31 (60%)  weak=15 (29%)

```
weak  pho                                0.235  Soup, pho, no meat
none  pho bo                             -      (nothing)
none  pho ga                             -      (nothing)
ask   beef noodle soup                   0.531  Soup, beef noodle, canned, condensed
ask   vietnamese noodle soup             0.462  Soup, noodle, NFS
weak  bun cha                            0.364  Bao bun
weak  bun bo hue                         0.308  Bao bun
none  banh mi                            -      (nothing)
weak  vietnamese sandwich                0.379  Cheese sandwich, NFS
none  banh xeo                           -      (nothing)
none  goi cuon                           -      (nothing)
weak  summer roll                        0.350  Sushi roll, eel
weak  fresh spring roll                  0.323  Roll, sweet, no frosting
none  cha gio                            -      (nothing)
weak  fried spring roll                  0.333  Fried onion rings
weak  spring roll                        0.333  Roll, rye
none  com tam                            -      (nothing)
weak  broken rice                        0.438  Bread, rice
ask   cao lau                            0.500  Lau lau
none  mi quang                           -      (nothing)
none  banh cuon                          -      (nothing)
none  banh beo                           -      (nothing)
none  banh khot                          -      (nothing)
none  cha ca                             -      (nothing)
none  nem nuong                          -      (nothing)
none  bo luc lac                         -      (nothing)
weak  shaking beef                       0.353  Stew, beef
none  thit kho                           -      (nothing)
weak  caramelised pork                   0.348  Pork, carnitas
none  canh chua                          -      (nothing)
weak  vietnamese iced coffee             0.414  Coffee, Iced Latte
none  ca phe sua da                      -      (nothing)
none  nuoc cham                          -      (nothing)
none  vietnamese dipping sauce           -      (nothing)
none  pickled carrot and daikon          -      (nothing)
none  do chua                            -      (nothing)
weak  vietnamese coriander               0.312  Spices, coriander seed
none  rau ram                            -      (nothing)
none  perilla                            -      (nothing)
weak  sawtooth coriander                 0.379  Spices, coriander seed
none  banh trang nuong                   -      (nothing)
none  bun thit nuong                     -      (nothing)
none  hu tieu                            -      (nothing)
weak  banh bao                           0.400  Bao bun
none  xoi                                -      (nothing)
ask   sticky rice cake                   0.588  Rice cake
ask   vietnamese pork roll               0.476  Pork, roll
none  cha lua                            -      (nothing)
none  gio lua                            -      (nothing)
none  pate chaud                         -      (nothing)
none  vietnamese ham                     -      (nothing)
ask   mung bean                          0.474  Mung beans, cooked
```

Neighbour searches for this batch:

```
ILIKE %pho%         -> 2707125 Soup, pho, no meat ; 2707124 Soup, pho, with meat
                       (+4 false hits on "phosphate"/"SYMPHONY")
ILIKE %spring roll% -> 0 rows
ILIKE %banh%        -> 0 rows
ILIKE %vietnamese%  -> 1 row, the SMART SOUP brand item
ILIKE %egg roll%    -> 9 rows (Egg roll meatless / shrimp / beef-pork /
                       chicken, + wrappers)

  2707125 Soup, pho, no meat        kcal=37   prot=1.42 fat=0.93  Na=357
  2707124 Soup, pho, with meat      kcal=77   prot=5.81 fat=3.33  Na=365
  2708700 Egg roll, meatless        kcal=270  prot=5.62 fat=14.14 carb=30.0
  2708702 Egg roll, w/ beef or pork kcal=272  prot=7.58 fat=14.7  carb=27.0
```


### Batch 4 — Filipino (56 terms)

    ask=5 (9%)  none=43 (77%)  weak=8 (14%)

The worst-covered cuisine in the domain by a wide margin: 77% return nothing at
all.

```
weak  adobo                              0.375  Adobo, with rice
ask   chicken adobo                      0.450  Almond chicken
weak  pork adobo                         0.333  Pork, NFS
none  sinigang                           -      (nothing)
none  sinigang na baboy                  -      (nothing)
none  kare-kare                          -      (nothing)
none  kare kare                          -      (nothing)
none  lechon                             -      (nothing)
none  lechon kawali                      -      (nothing)
weak  crispy pata                        0.333  Crisp, peach
none  sisig                              -      (nothing)
none  pancit                             -      (nothing)
none  pancit bihon                       -      (nothing)
none  pancit canton                      -      (nothing)
none  lumpia                             -      (nothing)
none  lumpiang shanghai                  -      (nothing)
none  tapsilog                           -      (nothing)
none  tapa                               -      (nothing)
ask   beef tapa                          0.467  Tamale, beef
none  tocino                             -      (nothing)
none  longganisa                         -      (nothing)
weak  longanisa                          0.375  Longans, raw
weak  filipino sausage                   0.381  Sausage, NFS
none  halo-halo                          -      (nothing)
none  halo halo                          -      (nothing)
none  bibingka                           -      (nothing)
none  puto                               -      (nothing)
none  kutsinta                           -      (nothing)
ask   leche flan                         0.455  Flan
none  ube                                -      (nothing)
none  ube halaya                         -      (nothing)
none  purple yam                         -      (nothing)
ask   taro                               0.556  Taro, raw
none  gabi                               -      (nothing)
weak  calamansi                          0.316  Calamari, cooked
none  philippine lime                    -      (nothing)
none  bagoong alamang                    -      (nothing)
none  patis                              -      (nothing)
none  suka                               -      (nothing)
none  kinilaw                            -      (nothing)
weak  laing                              0.059  Crackers, cream, La Moderna Rikis Cream Crackers
none  pinakbet                           -      (nothing)
none  dinuguan                           -      (nothing)
none  menudo                             -      (nothing)
none  afritada                           -      (nothing)
none  caldereta                          -      (nothing)
none  bulalo                             -      (nothing)
none  arroz caldo                        -      (nothing)
none  lugaw                              -      (nothing)
none  champorado                         -      (nothing)
weak  turon                              0.300  Turtle
ask   banana ketchup                     0.571  Ketchup
none  pandesal                           -      (nothing)
none  ensaymada                          -      (nothing)
none  sotanghon                          -      (nothing)
none  palabok                            -      (nothing)
```

Neighbour searches for this batch:

```
ILIKE %adobo%     -> 2708958 Adobo, with rice ; 2708809 Adobo, with noodles
ILIKE %filipino%  -> 0 rows
ILIKE %lumpia%    -> 0 rows
ILIKE %pancit%    -> 0 rows
ILIKE %ube%       -> 24 rows, ALL false hits (jujube, cube roll, Reuben,
                     bouillon cubes, yogurt tube). No ube.
ILIKE %yam%       -> 9 rows: Yam raw/cooked, Mountain yam hawaii, Yambean (jicama)
ILIKE %taro%      -> 16 rows: Taro raw/cooked/chips/leaves/shoots/tahitian

  170071 Yam, raw                    kcal=118 prot=1.53 carb=27.88 fib=4.1
  170072 Yam, cooked, boiled         kcal=116 prot=1.49 carb=27.48 fib=3.9
  169308 Taro, raw                   kcal=112 prot=1.5  carb=26.46 fib=4.1
  168486 Taro, cooked, without salt  kcal=142 prot=0.52 carb=34.60 fib=5.1
  2708958 Adobo, with rice           kcal=181 prot=17.69 fat=7.94 Na=522
  2708809 Adobo, with noodles        kcal=172 prot=16.89 fat=7.66 Na=510
```


### Batch 5 — Indonesian / Malaysian / Singaporean (67 terms)

    ask=5 (7%)  auto=5 (7%)  none=46 (69%)  weak=11 (16%)

```
none  nasi goreng                        -      (nothing)
weak  indonesian fried rice              0.423  Rice, fried, NFS
none  rendang                            -      (nothing)
weak  beef rendang                       0.333  Beef, roast
none  satay                              -      (nothing)
none  sate ayam                          -      (nothing)
ask   chicken satay                      0.500  Soup, chicken
auto  peanut sauce                       1.000  Peanut sauce
ask   satay sauce                        0.462  Soy sauce
none  gado-gado                          -      (nothing)
none  gado gado                          -      (nothing)
none  soto                               -      (nothing)
none  soto ayam                          -      (nothing)
weak  rawon                              0.333  Lemon, raw
none  nasi lemak                         -      (nothing)
none  nasi uduk                          -      (nothing)
none  laksa                              -      (nothing)
weak  curry laksa                        0.389  Lentil curry
none  asam laksa                         -      (nothing)
none  penang laksa                       -      (nothing)
none  char kway teow                     -      (nothing)
none  char kuey teow                     -      (nothing)
weak  hainanese chicken rice             0.394  Chicken curry with rice
ask   chicken rice                       0.565  Chicken curry with rice
none  roti canai                         -      (nothing)
none  roti prata                         -      (nothing)
none  mee goreng                         -      (nothing)
none  bak kut teh                        -      (nothing)
none  sambal                             -      (nothing)
none  sambal oelek                       -      (nothing)
none  sambal badjak                      -      (nothing)
none  sambal terasi                      -      (nothing)
none  belacan                            -      (nothing)
none  candlenut                          -      (nothing)
none  kemiri                             -      (nothing)
none  pandan                             -      (nothing)
none  pandan leaf                        -      (nothing)
none  screwpine                          -      (nothing)
auto  tempeh                             1.000  Tempeh
auto  tempe                              0.625  Tempeh
ask   tofu                               0.455  Tofu, fried
weak  tahu                               0.333  Tahini
none  krupuk                             -      (nothing)
none  kerupuk                            -      (nothing)
weak  prawn cracker                      0.421  Cracker, meal
auto  shrimp chips                       1.000  Shrimp chips
none  bakso                              -      (nothing)
weak  martabak                           0.308  Martini
none  otak-otak                          -      (nothing)
none  rojak                              -      (nothing)
none  nasi campur                        -      (nothing)
none  ayam penyet                        -      (nothing)
none  gulai                              -      (nothing)
none  opor ayam                          -      (nothing)
none  serundeng                          -      (nothing)
none  lontong                            -      (nothing)
none  ketupat                            -      (nothing)
none  lemper                             -      (nothing)
none  kangkung                           -      (nothing)
weak  water spinach                      0.444  Spinach, raw
weak  pete                               0.132  Sauce, hot chile, sriracha, CHA! BY TEXAS PETE
none  petai                              -      (nothing)
auto  jackfruit                          0.714  Jackfruit, raw
none  nangka                             -      (nothing)
ask   young jackfruit                    0.500  Jackfruit, raw
weak  salted egg                         0.289  Egg, yolk, raw, frozen, salted, pasteurized
none  century egg                        -      (nothing)
```

Neighbour searches for this batch:

```
ILIKE %sambal%        -> 0 rows
ILIKE %chili sauce%   -> 2 rows, both "tomato chili sauce" (US ketchup-style)
ILIKE %shrimp chip%   -> 1: 2708246 Shrimp chips
ILIKE %jackfruit%     -> 2: 174687 Jackfruit, raw ; 168190 Jackfruit, canned, syrup
ILIKE %water spinach% -> 0 ; %swamp% -> 0 ; %Ipomoea% -> 0
ILIKE %tempeh%        -> 2: 174272 Tempeh ; 172467 Tempeh, cooked
ILIKE %tofu, %        -> 22 rows (fried, silken, firm, koyadofu, fuyu, nigari...)

  2708246 Shrimp chips                 kcal=426 prot=7.14  fat=17.86 carb=59.1 Na=571
   174687 Jackfruit, raw               kcal=95  prot=1.72  fat=0.64  carb=23.3 sug=19.1
   174272 Tempeh                       kcal=192 prot=20.29 fat=10.80 carb=7.64
   172467 Tempeh, cooked               kcal=195 prot=19.91 fat=11.38 carb=7.62
   172476 Tofu, raw, regular (CaSO4)   kcal=76  prot=8.08  fat=4.78  carb=1.87
   172451 Tofu, fried                  kcal=270 prot=18.82 fat=20.18 carb=8.86
```


### Batch 6 — Cambodian / Burmese / Lao, staples and produce (67 terms)

    ask=9 (14%)  auto=13 (20%)  none=22 (33%)  weak=22 (33%)

```
none  amok                               -      (nothing)
weak  fish amok                          0.375  Fish, smoked
none  lok lak                            -      (nothing)
none  nom banh chok                      -      (nothing)
none  prahok                             -      (nothing)
none  kroeung                            -      (nothing)
none  num pang                           -      (nothing)
none  kuy teav                           -      (nothing)
none  bai sach chrouk                    -      (nothing)
none  khao poon                          -      (nothing)
none  tam mak hoong                      -      (nothing)
none  sai oua                            -      (nothing)
ask   lao sausage                        0.500  Sausage, NFS
weak  padaek                             0.300  Papad
none  jeow bong                          -      (nothing)
none  mohinga                            -      (nothing)
weak  burmese fish soup                  0.370  Soup, fish or shrimp
none  lahpet                             -      (nothing)
weak  tea leaf salad                     0.360  Tea, hot, leaf, green
none  laphet thoke                       -      (nothing)
none  ohn no khao swe                    -      (nothing)
weak  shan noodles                       0.400  Noodles, cooked
none  danbauk                            -      (nothing)
none  balachaung                         -      (nothing)
weak  chickpea tofu                      0.400  Chickpeas, NFS
weak  burmese curry                      0.389  Beef curry
ask   rice                               0.500  Soup, rice
weak  jasmine rice                       0.438  Wine, rice
ask   white rice                         0.524  Beans and white rice
auto  brown rice                         0.647  Flour, rice, brown
weak  red rice                           0.333  Rice, red, unenriched, dry, raw
ask   black rice                         0.458  Rice, black, unenriched, raw
weak  rice porridge                      0.316  Rice paper
auto  congee                             1.000  Congee
weak  banana leaf                        0.400  Banana, baked
weak  banana blossom                     0.400  Orange Blossom
auto  bamboo shoots                      0.778  Bamboo shoots, raw
auto  bamboo shoot                       0.632  Bamboo shoots, raw
none  morning glory                      -      (nothing)
auto  bean sprouts                       0.765  Bean sprouts, raw
weak  mung bean sprouts                  0.395  Mung beans, mature seeds, sprouted, raw
weak  long beans                         0.250  Long rice noodles, made from mung beans, cooked
auto  yardlong beans                     0.650  Yardlong bean, raw
weak  snake beans                        0.438  Baked beans
auto  chinese broccoli                   0.810  Broccoli, chinese, raw
none  gai lan                            -      (nothing)
none  choy sum                           -      (nothing)
ask   thai eggplant                      0.500  Eggplant, raw
ask   pea eggplant                       0.529  Eggplant, raw
ask   winged bean                        0.545  Winged bean tuber, raw
auto  bitter melon                       0.650  Bitter melon, cooked
weak  bitter gourd                       0.406  Balsam-pear (bitter gourd), pods, raw
weak  green mango                        0.389  Mango, frozen
weak  unripe mango                       0.353  Mango, raw
none  pomelo                             -      (nothing)
weak  rambutan                           0.333  Rambutan, canned, syrup pack
weak  mangosteen                         0.379  Mangosteen, canned, syrup pack
ask   longan                             0.462  Longans, raw
auto  lychee                             1.000  Lychee
weak  durian                             0.333  Durian, raw or frozen
auto  dragon fruit                       1.000  Dragon fruit
auto  soursop                            0.667  Soursop, raw
weak  custard apple                      0.412  Custard-apple, (bullock's-heart), raw
auto  sapodilla                          0.714  Sapodilla, raw
auto  starfruit                          0.714  Starfruit, raw
ask   guava                              0.600  Guava, raw
```

Neighbour searches for this batch:

```
ILIKE %durian%     -> 1: 168192 Durian, raw or frozen
ILIKE %pomelo%     -> 0 ; %shaddock% -> 0
ILIKE %rambutan%   -> 1: 168167 Rambutan, canned, syrup pack   (no raw row)
ILIKE %mangosteen% -> 1: 169090 Mangosteen, canned, syrup pack (no raw row)
ILIKE %rice, brown%-> 40 rows incl. 2708414 Rice, brown, cooked, no added fat
                      and 2512380 Rice, brown, long grain, unenriched, raw

  1104812 Flour, rice, brown              kcal=365 prot=7.19 fat=3.85 carb=75.5
  2708414 Rice, brown, cooked, no added fat kcal=123 prot=2.43 fat=1.11 carb=25.8
   168192 Durian, raw or frozen           kcal=147 prot=1.47 fat=5.33 carb=27.1
```


### Batch 7 — defining ingredients, proteins, fats, aromatics (69 terms)

Chosen specifically to hunt `auto` verdicts, since a wrong `auto` is the only
class that logs a wrong number with no model consulted and caches an alias.

    ask=18 (26%)  auto=22 (32%)  none=9 (13%)  weak=20 (29%)

```
auto  rice flour                         0.647  Flour, rice, brown
auto  white rice flour                   0.630  Flour, rice, white, unenriched
auto  tapioca pearls                     0.650  Tapioca, pearl, dry
none  sago                               -      (nothing)
none  sago pearls                        -      (nothing)
auto  palm oil                           1.000  Oil, palm
auto  coconut oil                        1.000  Oil, coconut
auto  peanut oil                         1.000  Peanut oil
weak  groundnut oil                      0.333  Groundhog
weak  chilli oil                         0.333  Corn oil
ask   fried shallots                     0.609  Shallots, freeze-dried
ask   crispy shallots                    0.450  Shallots, raw
ask   shallot                            0.500  Shallots, raw
auto  garlic                             0.636  Garlic, raw
auto  lime juice                         0.733  Lime juice, raw
none  kalamansi juice                    -      (nothing)
ask   thai fried chicken                 0.483  Rice, fried, with chicken
auto  pork belly                         1.000  Pork, belly
ask   crispy pork belly                  0.611  Pork, belly
weak  pork jowl                          0.400  Pork jerky
ask   chicken thigh                      0.467  Chicken thigh, stewed, skin eaten
auto  chicken thigh skinless             0.697  Chicken, thigh, boneless, skinless, raw
none  prawns                             -      (nothing)
auto  shrimp                             0.636  Shrimp, NFS
none  tiger prawn                        -      (nothing)
weak  squid                              0.364  Squirrel
weak  fish ball                          0.412  Fish, bass, NFS
weak  fish balls                         0.389  Fish, bass, NFS
ask   fish cake                          0.526  Fish, cake or patty
ask   surimi                             0.583  Fish, surimi
weak  anchovies                          0.353  Fish, anchovy
auto  dried shrimp                       1.000  Shrimp, dried
weak  dried anchovies                    0.440  Peppers, ancho, dried
none  ikan bilis                         -      (nothing)
ask   salted fish                        0.571  Fish, mackerel, salted
weak  pork floss                         0.333  Pork, NFS
weak  beef balls                         0.357  Beef, NFS
ask   quail egg                          0.588  Quail egg, canned
ask   duck egg                           0.562  Duck egg, cooked
auto  condensed milk                     0.625  Milk, condensed, sweetened
auto  sweetened condensed milk           1.000  Milk, condensed, sweetened
auto  evaporated milk                    0.727  Milk, evaporated, whole
ask   palm heart                         0.500  Palm hearts, cooked
weak  young coconut                      0.444  Oil, coconut
ask   coconut water                      0.583  Coconut water, sweetened
auto  coconut flesh                      0.647  Coconut, fresh
weak  grated coconut                     0.278  Nuts, coconut cream, raw (liquid expressed from grated meat)
ask   desiccated coconut                 0.500  Nuts, coconut meat, dried (desiccated), creamed
weak  toasted coconut                    0.421  Nuts, coconut meat, dried (desiccated), toasted
auto  roasted peanuts                    0.762  Peanuts, roasted, salted
weak  crushed peanuts                    0.409  Peanuts, boiled
auto  peanut brittle                     0.714  Candy, peanut brittle
auto  sesame seeds                       1.000  Sesame seeds
auto  white pepper                       0.650  Spices, pepper, white
weak  star anise                         0.333  Spices, anise seed
ask   cinnamon stick                     0.500  Sugar, cinnamon
weak  turmeric                           0.391  Spices, turmeric, ground
weak  fresh turmeric                     0.350  Thyme, fresh
weak  turmeric powder                    0.364  Tomato powder
weak  cumin                              0.353  Spices, cumin seed
auto  coriander seed                     0.714  Spices, coriander seed
auto  curry powder                       0.650  Spices, curry powder
none  five spice                         -      (nothing)
weak  shaoxing wine                      0.381  Wine, sparkling
none  mirin                              -      (nothing)
ask   rice vinegar                       0.615  Vinegar
ask   white vinegar                      0.571  Vinegar
ask   lime                               0.556  Lime, raw
none  kalamansi                          -      (nothing)
```

Neighbour searches for this batch:

```
ILIKE %squid%     -> 174223 Mollusks, squid, mixed species, raw
                     171982 Mollusks, squid, mixed species, cooked, fried
                     2708977 Rice with squid, Puerto Rican style
ILIKE %calamari%  -> 2706333 Calamari, cooked ; 2706334 Calamari, fried
ILIKE %prawn%     -> 0 rows
ILIKE %anchovy%   -> 2706232 Fish, anchovy ; 174182 raw ; 174183 canned in oil
ILIKE %sago%      -> 0 rows
```


### Guard check — which `auto` verdicts survive `resolve_items`

`probe_knowledge.py` computes its verdict from `search_foods` similarity alone.
`resolve_items` then applies `inverts_meaning`, `state_conflicts`,
`unrequested_qualifier` and `label_absent` before taking an auto-match. So a
probe `auto` is a claim about ranking, not about what would be logged.

Re-ran the domain's `auto` verdicts through the real guards (read-only; bare
user label, no model `search_terms`, `state` unset — the honest worst case for a
typed message):

```
== coconut milk      1.000 Coconut milk               -> SURVIVES  AUTO
== coconut cream     0.765 Pie, coconut cream         -> SURVIVES  AUTO
== brown rice        0.647 Flour, rice, brown         -> SURVIVES  AUTO
== sweet soy sauce   0.643 Soy sauce                  -> SURVIVES  AUTO
== dark soy sauce    0.643 Soy sauce                  -> SURVIVES  AUTO
== ginger            0.636 Tea, ginger                -> SURVIVES  AUTO
== bitter melon      0.650 Bitter melon, cooked       -> SURVIVES  AUTO
== peanut brittle    0.714 Candy, peanut brittle      -> SURVIVES  AUTO
== jackfruit         0.714 Jackfruit, raw             -> SURVIVES  AUTO
== shrimp            0.636 Shrimp, NFS                -> SURVIVES  AUTO
== garlic            0.636 Garlic, raw                -> SURVIVES  AUTO
== bean sprouts      0.765 Bean sprouts, raw          -> SURVIVES  AUTO
== bamboo shoots     0.778 Bamboo shoots, raw         -> SURVIVES  AUTO
== chinese broccoli  0.810 Broccoli, chinese, raw     -> SURVIVES  AUTO
== white pepper      0.650 Spices, pepper, white      -> SURVIVES  AUTO
== curry powder      0.650 Spices, curry powder       -> SURVIVES  AUTO
== tempe             0.625 Tempeh                     -> SURVIVES  AUTO

== rice flour        0.647 Flour, rice, brown         -> BLOCK:qual  escalates
== tapioca pearls    0.650 Tapioca, pearl, dry        -> BLOCK:qual  escalates
== yardlong beans    0.650 Yardlong bean, raw         -> BLOCK:qual  escalates
== evaporated milk   0.727 Milk, evaporated, whole    -> BLOCK:qual  escalates
== condensed milk    0.625 Milk, condensed, sweetened -> BLOCK:qual  escalates
== coconut flesh     0.647 Coconut, fresh             -> BLOCK:qual  escalates
== roasted peanuts   0.762 Peanuts, roasted, salted   -> BLOCK:qual
                     0.727 Peanuts, honey roasted     -> SURVIVES  AUTO  (see F36)
```

Two things this settles. **F1, F2, F4, F6 and F25 are confirmed at the resolver
level, not merely at the ranker** — the four highest-harm findings in this audit
are things the shipped system would actually log with no model consulted.

And `unrequested_qualifier` is doing real work: seven of twenty-four escalate
because of it. One (F33) was a finding until this check retracted it.

The blind spot the check exposes is that `unrequested_qualifier` only inspects
segments *after* the first, by design — so `Pie, coconut cream` passes, because
`Pie` is the first segment and a different food name in the first segment is
read as "a weak match" rather than "a narrowed one". That design note is quoted
verbatim in CLAUDE.md; F2 is the case where it costs something.

## Findings


### F1 — `coconut milk` auto-matches the drink, not the cooking ingredient

- **kind:** wrong_confident_match (also preparation_state_mismatch)
- **category:** `bad_fallback` / `ingredient_vs_dish_ambiguity`
- **confidence:** high

```
auto  coconut milk                       1.000  Coconut milk
```

Similarity is **1.000** — an exact string match against FNDDS 2705413. Nothing
in any ranking function can ever displace it, and no model is consulted.

    2705413  Coconut milk                     31 kcal/100 g,  2.08 g fat
    2707568  Coconut milk, used in cooking   230 kcal/100 g, 23.84 g fat
     170173  Nuts, coconut milk, canned      197 kcal/100 g, 21.33 g fat

FNDDS 2705413 is the *carton beverage* (a diluted, often fortified drink).
Every Southeast Asian use of the words "coconut milk" — santan, gata, kati — is
the canned/pressed cooking liquid at 197-230 kcal. A 400 ml can in one pot of
curry or rendang is **~790 kcal actually eaten against ~124 kcal logged**, and
because the verdict is `auto` an alias is written and never re-checked, so
every subsequent curry inherits the error silently. USDA holds the right row
under a name a person will never type.

This is the highest-harm finding in the domain: it is the single most common
ingredient across Thai, Malaysian, Indonesian, Filipino and Burmese cooking,
and the failure is silent, confident and permanent.

### F2 — `coconut cream` auto-matches a dessert pie

- **kind:** wrong_confident_match
- **category:** `bad_fuzzy_matching` / `ingredient_vs_dish_ambiguity`
- **confidence:** high

```
auto  coconut cream                      0.765  Pie, coconut cream
```

    2708006  Pie, coconut cream        297 kcal, 17.8 g fat, 32.0 g carb, 18.7 g sugar
     170580  Nuts, coconut cream, raw  330 kcal, 34.7 g fat,  6.7 g carb

The taken row is a *pie*. The ingredient exists at 170580 and is unreachable
because USDA files it under the "Nuts," prefix. Carbohydrate is out by a factor
of five and the sugar figure is fabricated from a pie crust and filling.
`auto`, so it caches.

Note the interaction with F1: 2707571 `Coconut cream, canned, sweetened`
(53 g carb, 51.5 g sugar) is *cream of coconut* — the sweetened pina-colada
product — and is a third distinct food again. Three different things share the
words; the resolver picks the one no cook means.

### F3 — glass / cellophane / mung bean noodles: the row exists and is unreachable

- **kind:** reachability_gap
- **category:** `missing_synonym` / `bad_fuzzy_matching`
- **confidence:** high

```
weak  glass noodles                      0.381  Noodles, cooked
weak  cellophane noodles                 0.317  Noodles, chinese, cellophane or long rice (mung beans), dehydrated
weak  mung bean noodles                  0.378  Long rice noodles, made from mung beans, cooked
none  sen lek                            -      (nothing)
```

`cellophane noodles` scores 0.317 against a row whose description *contains the
literal word "cellophane"* — the length effect from RESUME.md in its purest
form (the description is 61 characters). `mung bean noodles` scores 0.378
against a row containing "made from mung beans". Both are below the weak floor,
so the model tier is not even asked with a good list.

Meanwhile `glass noodles` — the commonest English name — takes `Noodles,
cooked`, which is **wheat-and-egg** noodles: 0.04 g protein per 100 g in the
mung bean row against several grams in the wheat row, and a different
carbohydrate entirely. Used in yum woon sen, japchae-adjacent Thai salads,
Vietnamese mien and Filipino sotanghon.

### F4 — `sweet soy sauce` / `kecap manis` collapses onto soy sauce

- **kind:** wrong_confident_match + entity gap
- **category:** `overly_broad_mapping` / `missing_food_entity`
- **confidence:** high

```
auto  sweet soy sauce                    0.643  Soy sauce
none  kecap manis                        -      (nothing)
```

Kecap manis is roughly half palm sugar by mass — a thick syrup around
250 kcal/100 g with ~50 g sugar — and soy sauce is ~60 kcal/100 g with
essentially no sugar. Mapping one to the other is not a rounding error; it
zeroes the sugar in every nasi goreng, mee goreng and satay marinade. And it is
`auto`, so it caches. The brief flagged this as a test case and it fails.

### F5 — galangal is absent, and `ginger` is not a safe substitute anyway

- **kind:** entity_gap
- **category:** `missing_food_entity`
- **confidence:** high (that it is absent); the *mapping* is rejected below

```
none  galangal                           -      (nothing)
none  kha                                -      (nothing)
```

Neighbour search: `ILIKE %galangal%` -> **0 rows**. Searched by name and by
category (rhizome/spice); the only rhizome USDA carries in this family is
ginger, and `ginger` itself auto-matches `Tea, ginger` (see F6). So galangal is
a genuine entity gap, not a reachability one.

### F6 — `ginger` auto-matches `Tea, ginger`

- **kind:** wrong_confident_match
- **category:** `bad_fuzzy_matching`
- **confidence:** high

```
auto  ginger                             0.636  Tea, ginger
```

Already recorded in AUDIT-chinese.md §0. Re-measured here at the same value and
it matters at least as much in this domain — ginger is in tom kha, pho broth,
adobo, rendang and every Chinese-Malay stir-fry. Recording the second sighting
rather than re-filing it: one fix serves both audits.

### F7 — fish sauce resolves; every native name for it does not

- **kind:** reachability_gap
- **category:** `missing_synonym` / `spelling_transliteration_failure`
- **confidence:** high

```
auto  fish sauce                         1.000  Fish sauce
none  nam pla                            -      (nothing)
none  nuoc mam                           -      (nothing)
```

The row is right and reachable — but only from the English words. This is the
good case for a synonym layer: the target is unambiguous and already correct,
so `nam pla`/`nuoc mam` -> `Fish sauce` is a pure win with no nutritional
judgement involved. Sodium is the reason it matters: fish sauce is ~7,850 mg
sodium per 100 g, so a dish that loses it loses most of its sodium figure, and
the audit brief's own example of harm (751 mg from one invented word) is
smaller than what one tablespoon of unlogged nam pla costs.

### F8 — shrimp paste / belacan / terasi / bagoong: entity gap, all four names

- **kind:** entity_gap
- **category:** `missing_food_entity`
- **confidence:** high (absence); mapping deliberately rejected below

```
ask   shrimp paste                       0.450  Kung Pao shrimp
none  belacan                            -      (nothing)
none  terasi                             -      (nothing)
none  bagoong                            -      (nothing)
none  kapi                               -      (nothing)
```

`ILIKE %shrimp paste%` -> 0 rows. `ILIKE %anchovy paste%` -> 0 rows. Searched
by ingredient (shrimp, anchovy) and by category (paste, condiment): USDA has
`Fish sauce` and `Anchovy` but no fermented shrimp paste in any form. Genuine
entity gap. `shrimp paste` reaching `Kung Pao shrimp` at 0.450 is the system
correctly declining to be confident, so it lands in `ask` — working as designed.


### F9 — `pho` cannot reach the row literally named "pho"

- **kind:** reachability_gap
- **category:** `bad_fuzzy_matching` / `missing_synonym`
- **confidence:** high

```
weak  pho                                0.235  Soup, pho, no meat
none  pho bo                             -      (nothing)
none  pho ga                             -      (nothing)
```

USDA has exactly the two rows a person needs:

    2707125  Soup, pho, no meat     37 kcal, 1.42 g protein, 357 mg sodium
    2707124  Soup, pho, with meat   77 kcal, 5.81 g protein, 365 mg sodium

The query `pho` scores **0.235** against a description containing the word
`pho`, because a 3-character query against an 18-character description is
almost all non-matching trigrams. It is below the weak floor, so the model tier
is not even handed the list — a term that should be the easiest possible hit is
treated as an unknown word.

`pho bo` (beef) and `pho ga` (chicken) return nothing at all, and yet the
with-meat / no-meat split USDA already carries maps onto them exactly:
`pho bo`/`pho tai`/`pho ga` -> with meat, `pho chay` -> no meat.

This is RESUME.md's length effect at its most embarrassing: the audit's premise
is that ranking is not where the win is, and here even a *perfect substring*
match loses. Only a synonym layer fixes it.

### F10 — every `banh` and `bun` dish is unreachable, and the fuzzy fallbacks are Chinese

- **kind:** entity_gap with a bad-neighbour tail
- **category:** `spelling_transliteration_failure` / `missing_food_entity`
- **confidence:** high

```
none  banh mi                            -      (nothing)
none  banh xeo                           -      (nothing)
none  banh cuon                          -      (nothing)
none  banh beo                           -      (nothing)
none  banh khot                          -      (nothing)
weak  banh bao                           0.400  Bao bun
weak  bun cha                            0.364  Bao bun
weak  bun bo hue                         0.308  Bao bun
```

`ILIKE %banh%` -> **0 rows**. The interesting part is the tail: `bun cha`
(grilled pork with cold rice vermicelli) and `bun bo hue` (a spicy beef noodle
soup) both land on **`Bao bun`** — a Chinese steamed wheat bun. The word `bun`
in Vietnamese means rice vermicelli; in `Bao bun` it is an English loanword for
a bread roll. Two unrelated foods collide on three letters, and the collision is
*systematic* — every `bun ...` dish hits it. Only `banh bao` is a fair hit, and
by accident.

Below the weak floor, so nothing wrong is being logged today. It becomes
dangerous the moment anyone widens the floor.

### F11 — `spring roll` vs `summer roll`: the fried/fresh distinction has no anchor

- **kind:** entity_gap
- **category:** `missing_food_entity` / `preparation_state_mismatch`
- **confidence:** high for the gap; the tempting mapping is rejected below

```
weak  spring roll                        0.333  Roll, rye
weak  fried spring roll                  0.333  Fried onion rings
weak  summer roll                        0.350  Sushi roll, eel
weak  fresh spring roll                  0.323  Roll, sweet, no frosting
none  goi cuon                           -      (nothing)
none  cha gio                            -      (nothing)
```

`ILIKE %spring roll%` -> **0 rows**. What exists is the `Egg roll, *` family
(270 kcal, 14 g fat — deep-fried). So the *fried* case has a defensible
neighbour and the *fresh* case has none, and the two differ by roughly threefold
in energy. `Roll, rye` and `Roll, sweet, no frosting` are bread rolls reached
purely on the word "roll" — the `label_absent` guard cannot fire here, because
the label word "roll" genuinely is present. That is precisely the case that
guard is blind to.

### F12 — `nuoc cham` and the Vietnamese table condiments: entity gap

- **kind:** entity_gap
- **category:** `missing_food_entity`
- **confidence:** high

```
none  nuoc cham                          -      (nothing)
none  vietnamese dipping sauce           -      (nothing)
none  do chua                            -      (nothing)
none  pickled carrot and daikon          -      (nothing)
```

Searched by ingredient (fish sauce, lime, sugar, vinegar, daikon, carrot) and by
category (sauce, pickle, condiment). USDA has `Fish sauce`; there is no pickled
carrot row and no diluted-fish-sauce dipping preparation of any kind. Genuine
gap. Low harm alone — the quantities are small — but it carries the sodium in a
bun cha or banh mi, so it compounds F7.

### F13 — Vietnamese herbs are absent and coriander seed is not a substitute

- **kind:** entity_gap
- **category:** `missing_food_entity`
- **confidence:** high (absence)

```
weak  vietnamese coriander               0.312  Spices, coriander seed
weak  sawtooth coriander                 0.379  Spices, coriander seed
none  rau ram                            -      (nothing)
none  perilla                            -      (nothing)
```

Both fall to `Spices, coriander seed` — a dried seed spice used by the gram,
where the query is a fresh leaf herb used by the bunch. Below the weak floor so
nothing is logged, which is the right outcome. Recorded because the *shape* of
the failure (fresh leaf -> dried seed of a different plant) is a
`preparation_state_mismatch` waiting to become an `auto` if anything nudges
these scores.


### F14 — `chicken adobo` reaches `Almond chicken`; the Adobo rows are unreachable

- **kind:** reachability_gap
- **category:** `bad_fuzzy_matching` / `missing_synonym`
- **confidence:** high

```
weak  adobo                              0.375  Adobo, with rice
ask   chicken adobo                      0.450  Almond chicken
weak  pork adobo                         0.333  Pork, NFS
```

USDA carries the dish:

    2708958  Adobo, with rice      181 kcal, 17.7 g protein, 522 mg sodium
    2708809  Adobo, with noodles   172 kcal, 16.9 g protein, 510 mg sodium

The bare word `adobo` scores 0.375 against a row that *starts with the word
adobo* — below the weak floor. Adding the qualifier a Filipino cook always adds
(`chicken adobo`) makes it worse, not better: it now reaches `Almond chicken`,
a Chinese-American dish, because "chicken" is the longer and more common token.
`pork adobo` degrades to `Pork, NFS`, silently throwing away the soy-vinegar
braise and its 500+ mg of sodium.

Note that `Adobo, with rice` at 17.7 g protein per 100 g is clearly the Filipino
dish and not the Mexican adobo marinade — USDA has the right food, filed under
the one word nobody uses on its own.

### F15 — the entire everyday Filipino repertoire returns nothing

- **kind:** entity_gap
- **category:** `missing_food_entity`
- **confidence:** high

```
none  sinigang / kare-kare / lechon / sisig / pancit / lumpia / tapsilog
none  tocino / longganisa / halo-halo / bibingka / puto / kutsinta
none  pinakbet / dinuguan / afritada / caldereta / bulalo / arroz caldo
none  lugaw / champorado / pandesal / ensaymada / sotanghon / palabok
```

`ILIKE %filipino%` -> 0 rows. `ILIKE %lumpia%` -> 0. `ILIKE %pancit%` -> 0.
Searched by ingredient too: there is no peanut-and-oxtail stew for kare-kare,
no tamarind-soured broth for sinigang, no cured sweet pork for tocino. The two
`Adobo` rows in F14 are the *only* Filipino entries in the whole database.

This is the domain's structural finding rather than a per-food one: for a
Filipino user, nutrAI has essentially no vocabulary at all, and every meal
routes to the model tier or to a wrong neighbour. Filing it as one entity gap
rather than twenty-four is deliberate — the fix is not twenty-four mappings, it
is an acknowledgement that a knowledge layer for this cuisine has to be built
from dish-ingredient decomposition, not from synonyms onto rows that do not
exist.

### F16 — `ube` returns nothing while `taro` resolves; do not join them

- **kind:** entity_gap
- **category:** `missing_food_entity` (and a `culturally_incorrect_mapping` trap)
- **confidence:** high

```
none  ube                                -      (nothing)
none  ube halaya                         -      (nothing)
none  purple yam                         -      (nothing)
ask   taro                               0.556  Taro, raw
none  gabi                               -      (nothing)
```

`ILIKE %ube%` -> 24 rows, **every one a false hit** (jujube, cube roll, Reuben
sandwich, bouillon cubes, yogurt tube). There is no ube row.

The brief flagged ube/taro as a commonly confused pair and the probe shows the
asymmetry exactly: taro is reachable, ube is invisible, so anything that guesses
will guess taro. They are different genera — ube is *Dioscorea alata* (a yam),
taro is *Colocasia esculenta* (an aroid) — and the numbers are not
interchangeable in the cooked state that matters:

    170072  Yam, cooked, boiled         116 kcal, 1.49 g protein, 27.5 g carb
    168486  Taro, cooked, without salt  142 kcal, 0.52 g protein, 34.6 g carb

Cooked taro carries **three times the protein deficit** and 26% more
carbohydrate. Raw they look similar (118 vs 112 kcal), which is exactly the trap:
a mapping validated on the raw rows would look fine and be wrong for every dish.

The right target is `Yam, raw` / `Yam, cooked` — same genus, same species group.
`gabi` is the Tagalog for taro and is a clean synonym; `ube`/`purple yam` is a
clean synonym onto yam. Encoding both is what stops the conflation happening by
accident later.

### F17 — `calamansi` reaches `Calamari, cooked`

- **kind:** reachability_gap / near-collision
- **category:** `bad_fuzzy_matching` / `spelling_transliteration_failure`
- **confidence:** high

```
weak  calamansi                          0.316  Calamari, cooked
none  philippine lime                    -      (nothing)
```

A citrus fruit resolving toward squid. It sits at 0.316, below the weak floor,
so nothing is logged today — but `calamansi` and `calamari` differ by two
characters and share a nine-character prefix, so this is the highest-similarity
wrong neighbour in the domain and it is a *protein source* standing in for a
*juice*. `Lime, raw` and `Lime juice, raw` both exist and are the obvious
targets; neither is reachable from either name the fruit is known by.

### F18 — `longanisa`, `laing`, `turon`: three more spelling near-collisions

- **kind:** reachability_gap / near-collision
- **category:** `spelling_transliteration_failure` / `bad_fuzzy_matching`
- **confidence:** high (as observations); no mapping proposed for laing/turon

```
weak  longanisa                          0.375  Longans, raw
none  longganisa                         -      (nothing)
weak  laing                              0.059  Crackers, cream, La Moderna Rikis Cream Crackers
weak  turon                              0.300  Turtle
weak  crispy pata                        0.333  Crisp, peach
```

A cured pork sausage (~350 kcal, fatty) reaching **`Longans, raw`**, a lychee-like
fruit — and note the spelling sensitivity: the double-g spelling `longganisa`,
which is the commoner one, returns nothing while the single-g spelling returns a
fruit. `laing` at 0.059 against a branded cracker is the lowest score recorded
anywhere in this audit and shows the ranker will return *anything* rather than
nothing. `turon` (a fried banana roll) -> `Turtle`. `crispy pata` (deep-fried
pork knuckle, one of the fattiest things in the cuisine) -> `Crisp, peach`.

None are above the weak floor, so none are logging wrong numbers. They are filed
together because they share one cause — a short, unfamiliar token matching an
unrelated short English word on prefix trigrams — and because the *shape* is the
same as the `larb` -> `Lard` hit in Batch 1 and `bun` -> `Bao bun` in Batch 3.


### F19 — `krupuk` / `prawn cracker` cannot reach `Shrimp chips`, which is exactly it

- **kind:** reachability_gap
- **category:** `missing_synonym`
- **confidence:** high

```
auto  shrimp chips                       1.000  Shrimp chips
weak  prawn cracker                      0.421  Cracker, meal
none  krupuk                             -      (nothing)
none  kerupuk                            -      (nothing)
```

    2708246  Shrimp chips   426 kcal, 17.9 g fat, 59.1 g carb, 571 mg sodium

The right row exists and is perfectly reachable — from the one name (`shrimp
chips`) that a British, Australian or Indonesian speaker will not use. `prawn
cracker` is the standard name across the whole Commonwealth and it reaches
`Cracker, meal` — cracker *meal*, a breadcrumb product. `krupuk`/`kerupuk`
return nothing.

At 426 kcal/100 g and 571 mg sodium this is a materially dense side dish that
routinely goes unlogged or lands on a breadcrumb row. Cheapest fix in the whole
audit: three synonyms onto a row that is already correct.

### F20 — `sambal` in every form returns nothing, and the near neighbours are ketchup

- **kind:** entity_gap
- **category:** `missing_food_entity`
- **confidence:** high

```
none  sambal                             -      (nothing)
none  sambal oelek                       -      (nothing)
none  sambal badjak                      -      (nothing)
none  sambal terasi                      -      (nothing)
none  belacan                            -      (nothing)
```

`ILIKE %sambal%` -> 0 rows. Searched by ingredient (chilli, shrimp paste,
tamarind) and by category (sauce, condiment, relish): the nearest things USDA
has are `Tomato chili sauce` and `Sauce, tomato chili sauce, bottled, with salt`
— both American ketchup-style sauces, sweet and tomato-based, which is not what
any sambal is. Genuine entity gap, and the three named variants differ from each
other enough (oelek is chilli and salt; badjak carries sugar and oil; terasi
carries fermented shrimp) that a single sambal row would not serve them anyway.

Related: `belacan` and `terasi` are the same absence as F8.

### F21 — `tempeh` and `tofu` both resolve, and do NOT conflate — recorded as a pass

- **kind:** (not a defect) — the brief asked for this to be tested
- **confidence:** high

```
auto  tempeh                             1.000  Tempeh
auto  tempe                              0.625  Tempeh
ask   tofu                               0.455  Tofu, fried
weak  tahu                               0.333  Tahini
```

    174272  Tempeh                       192 kcal, 20.3 g protein, 10.8 g fat
    172476  Tofu, raw, regular           76 kcal,  8.1 g protein,  4.8 g fat

The brief flagged tempeh/tofu as a "very different, test" pair. They differ by
2.5x in protein and energy, and the resolver keeps them apart cleanly: both
spellings of tempeh land on `Tempeh` and nothing pulls tofu toward it. No
finding.

Two caveats worth recording rather than filing:

- `tofu` heads its candidate list with **`Tofu, fried`** (270 kcal, 20.2 g fat)
  rather than a plain raw row — 3.5x the energy. It is `ask`, so the model tier
  decides and the system is working, but the head of the list is the outlier.
- `tahu` (Indonesian/Malay for tofu) reaches **`Tahini`** — sesame paste,
  595 kcal. Below the weak floor, so harmless today; the same near-collision
  shape as F17/F18.

### F22 — `water spinach` / `kangkung`: entity gap, and `Spinach, raw` is not it

- **kind:** entity_gap
- **category:** `missing_food_entity` (with a `culturally_incorrect_mapping` trap)
- **confidence:** high

```
none  kangkung                           -      (nothing)
weak  water spinach                      0.444  Spinach, raw
```

`ILIKE %water spinach%` -> 0. `ILIKE %swamp%` -> 0 (USDA's old name for it,
"cabbage, swamp", is not in this load either). `ILIKE %Ipomoea%` -> 0. Genuine
gap.

`Spinach, raw` is the tempting target and should not be taken: water spinach is
*Ipomoea aquatica*, a morning-glory, not an *Amaranthaceae*, and the thing that
makes spinach nutritionally distinctive — its iron and oxalate and folate load —
is exactly what does not transfer. The name is a translation artefact, not a
botanical claim. It is the "halloumi -> cheese" error in vegetable form.

### F23 — ripe and young jackfruit are one row, and they are two foods

- **kind:** reachability_gap / preparation_state
- **category:** `preparation_state_mismatch`
- **confidence:** medium (see the caveat)

```
auto  jackfruit                          0.714  Jackfruit, raw
ask   young jackfruit                    0.500  Jackfruit, raw
none  nangka                             -      (nothing)
```

    174687  Jackfruit, raw   95 kcal, 1.72 g protein, 23.3 g carb, **19.1 g sugar**

USDA has only the ripe fruit (`ILIKE %jackfruit%` -> 2 rows, raw and canned in
syrup). Young/green jackfruit — `nangka muda`, the gudeg and curry ingredient,
and the ubiquitous meat substitute — is a starchy vegetable with a fraction of
that sugar, and there is no row for it. `young jackfruit` lands on the ripe row
at `ask`, so the model tier sees it, which is the system working; but the
candidate list contains no correct answer for it to pick.

Marked **medium** rather than high deliberately, and see the deliberately-rejected
section: CLAUDE.md already records fruit ripeness as asked-and-declined for
bananas, on the grounds that supplying a ripeness figure means a model estimating
a nutrient value. The jackfruit case is stronger than the banana one (young
jackfruit is used as a savoury vegetable, not as a riper or less ripe version of
a dessert fruit) but it is the same argument, so it is recorded and not proposed.

### F24 — `satay` and `peanut sauce`: the sauce resolves, the dish does not

- **kind:** reachability_gap (sauce) + entity_gap (dish)
- **category:** `missing_synonym` / `missing_dish_ingredient`
- **confidence:** high

```
none  satay                              -      (nothing)
none  sate ayam                          -      (nothing)
ask   chicken satay                      0.500  Soup, chicken
auto  peanut sauce                       1.000  Peanut sauce
ask   satay sauce                        0.462  Soy sauce
```

`ILIKE %satay%` -> **0 rows** (Batch 1). So satay the skewer is an entity gap —
but its defining component, the peanut sauce, has a perfect row that is
reachable only from the English words. `satay sauce`, the name it is sold under
in every British and Australian supermarket, reaches **`Soy sauce`** instead:
peanut sauce is ~230 kcal with 15 g of fat, soy sauce is ~60 kcal with none.
That is the whole calorie content of the sauce discarded.

This is the domain's cleanest instance of the pattern the audit was commissioned
for: the dish is absent, and its signature ingredient exists but is unreachable
under its common name.


### F25 — `brown rice` auto-matches `Flour, rice, brown` — a 3x energy error on a staple

- **kind:** wrong_confident_match
- **category:** `bad_fallback` / `preparation_state_mismatch`
- **confidence:** high

```
auto  brown rice                         0.647  Flour, rice, brown
```

    1104812  Flour, rice, brown                 365 kcal, 7.19 g protein, 75.5 g carb
    2708414  Rice, brown, cooked, no added fat  123 kcal, 2.43 g protein, 25.8 g carb

`ILIKE %rice, brown%` returns **40 rows**, including cooked, raw, long-grain and
every fat variant. The resolver takes the *flour*. A 200 g serving of cooked
brown rice logs as 730 kcal instead of 246 — and it is `auto`, so no model is
consulted and the alias caches.

This is the same defect the Chinese audit filed for `glutinous rice ->
Flour, rice, glutinous` (0.714). Two independent domains hitting the identical
`<grain> -> Flour, <grain>` shape makes it a class rather than a coincidence:
USDA's `Flour, rice, X` descriptions are *short*, and the length effect in
RESUME.md rewards short descriptions, so the flour row systematically outranks
every prepared form of every grain. Worth checking `white rice`, `rice flour`,
`corn`, `oat` for the same shape as a cross-cutting item rather than a
per-cuisine one.

Note `jasmine rice` — the default rice of Thailand, Laos and Cambodia — falls to
**`Wine, rice`** at 0.438, and `rice` alone falls to `Soup, rice`. The grain
staple of the entire domain has no reachable plain row under any of its
everyday names.

### F26 — a family of exact-substring rows below the weak floor

- **kind:** reachability_gap
- **category:** `bad_fuzzy_matching`
- **confidence:** high

Six terms in this batch score below the weak floor against a row that contains
their words verbatim:

```
weak  durian              0.333  Durian, raw or frozen
weak  bitter gourd        0.406  Balsam-pear (bitter gourd), pods, raw
weak  custard apple       0.412  Custard-apple, (bullock's-heart), raw
weak  red rice            0.333  Rice, red, unenriched, dry, raw
weak  mung bean sprouts   0.395  Mung beans, mature seeds, sprouted, raw
weak  rambutan            0.333  Rambutan, canned, syrup pack
weak  mangosteen          0.379  Mangosteen, canned, syrup pack
```

`durian` is the clearest: `ILIKE %durian%` -> exactly one row, `Durian, raw or
frozen`, 147 kcal and 5.33 g fat — the highest-fat fruit in the dataset and a
food eaten in half-kilo quantities. The query is the *entire first word of the
only matching description* and it scores 0.333, below the floor, so the model
tier is never handed it.

`custard apple` is a normalisation failure specifically: the description is
`Custard-apple, (bullock's-heart), raw` and the hyphen plus the parenthetical
gloss cost it the match. This one belongs to the orthography audit as much as
to this one.

`rambutan` and `mangosteen` have *only* canned-in-syrup rows, so even a
successful match would give a sugar figure from syrup for a fresh fruit — a
distinct problem, filed here as an observation rather than a proposal.

### F27 — `long beans` / `snake beans` miss the row `yardlong beans` hits

- **kind:** reachability_gap
- **category:** `missing_synonym`
- **confidence:** high

```
auto  yardlong beans      0.650  Yardlong bean, raw
weak  long beans          0.250  Long rice noodles, made from mung beans, cooked
weak  snake beans         0.438  Baked beans
```

The row is right and the resolver reaches it from the one name — `yardlong` —
that is the least used of the three. `long beans` (the standard Chinese-Malay
menu name) reaches a *noodle*; `snake beans` (the standard Australian and much
British greengrocer name) reaches **`Baked beans`**, a tinned sugary product at
several times the energy of a green vegetable. Both below the floor, so nothing
is logged today, but the correct target is sitting there.

Same shape: `gai lan` -> nothing while `chinese broccoli` -> auto 0.810
`Broccoli, chinese, raw`; and `morning glory` / `kangkung` -> nothing (F22).

### F28 — Cambodian, Lao and Burmese are near-total blanks

- **kind:** entity_gap
- **category:** `missing_food_entity`
- **confidence:** high

```
none  amok / lok lak / nom banh chok / prahok / kroeung / kuy teav / khao poon
none  tam mak hoong / sai oua / padaek / jeow bong
none  mohinga / lahpet / laphet thoke / ohn no khao swe / danbauk / balachaung
```

Of 23 dish and condiment terms across these three cuisines, one (`lao sausage`)
reaches `ask` and the rest are `none` or `weak`. `ILIKE` searches by ingredient
found no fermented fish (prahok, padaek — the Lao/Khmer equivalent of the fish
sauce in F7, but a chunky paste, not the liquid), no pickled tea leaf (lahpet),
no chickpea-flour tofu (the Shan staple; `chickpea tofu` reaches `Chickpeas,
NFS`, a whole pulse, which has roughly the right macros by accident and the
wrong texture-driven portion size entirely).

Filed as one gap for the same reason as F15: the answer is not twenty synonyms
onto rows that do not exist.

### F29 — `banana leaf` resolves to a banana

- **kind:** wrong neighbour (below floor)
- **category:** `other_semantic_failure`
- **confidence:** high

```
weak  banana leaf                        0.400  Banana, baked
weak  banana blossom                     0.400  Orange Blossom
```

A banana leaf is a *wrapper* and is not eaten; it appears in an ingredient list
for otak-otak, amok, bibingka and nasi lemak as packaging. Resolving it to
`Banana, baked` would add fruit sugar to a meal that contains none of it. It is
below the weak floor so this is latent rather than active, and the correct
behaviour is to recognise it as inedible rather than to find it a better row —
which is a knowledge-layer capability the system does not currently have any
place to express.

`banana blossom` (which *is* eaten, in Burmese and Thai salads) reaching
`Orange Blossom` is the ordinary near-collision shape again.


### F30 — `prawns` returns nothing while `shrimp` auto-matches

- **kind:** reachability_gap
- **category:** `missing_synonym`
- **confidence:** high

```
auto  shrimp                             0.636  Shrimp, NFS
auto  dried shrimp                       1.000  Shrimp, dried
none  prawns                             -      (nothing)
none  tiger prawn                        -      (nothing)
```

`ILIKE %prawn%` -> **0 rows**. USDA is an American dataset and uses "shrimp"
exclusively; every British, Irish, Australian, Singaporean, Malaysian and Indian
English speaker writes "prawn". Nothing in the ranking can bridge a word that
does not occur in the corpus.

Purest possible synonym case: the target row is already correct and already
auto-matched from the other word. `prawn`/`prawns`/`king prawn`/`tiger prawn` ->
the `Shrimp` family costs nothing and is not a nutritional judgement.

### F31 — `squid` reaches `Squirrel`; `Calamari, cooked` and the squid rows are unreachable

- **kind:** reachability_gap
- **category:** `bad_fuzzy_matching` / `missing_synonym`
- **confidence:** high

```
weak  squid                              0.364  Squirrel
```

    174223  Mollusks, squid, mixed species, raw
    171982  Mollusks, squid, mixed species, cooked, fried
    2706333 Calamari, cooked
    2706334 Calamari, fried

Four correct rows exist. The query `squid` — five letters, a *complete word* in
two of those descriptions — scores 0.364 and loses to **`Squirrel`**, on a
shared `squ` prefix. Below the weak floor, so the model tier is not consulted.

Squid is a core protein in Thai (pla muek), Filipino (adobong pusit), Malaysian
(sambal sotong) and Vietnamese cooking. Note the symmetry with F17: `calamansi`
-> `Calamari`, and `squid` -> `Squirrel` — the ranker will reach for any
short English word before an exact-but-buried match.

### F32 — `groundnut oil`, `anchovies`, `turmeric`, `cumin`: exact words, below the floor

- **kind:** reachability_gap
- **category:** `bad_fuzzy_matching` / `missing_synonym`
- **confidence:** high

```
auto  peanut oil                         1.000  Peanut oil
weak  groundnut oil                      0.333  Groundhog
weak  anchovies                          0.353  Fish, anchovy
weak  dried anchovies                    0.440  Peppers, ancho, dried
none  ikan bilis                         -      (nothing)
weak  turmeric                           0.391  Spices, turmeric, ground
weak  cumin                              0.353  Spices, cumin seed
```

`groundnut oil` is the British and Indian name for peanut oil, which auto-matches
at 1.000 from the American name. It reaches **`Groundhog`**.

`anchovies` (plural) scores 0.353 against `Fish, anchovy` — the singular form of
the same word. `dried anchovies` — *ikan bilis*, the defining garnish of nasi
lemak and a serious sodium and calcium source — reaches **`Peppers, ancho,
dried`**, a chilli, on the shared prefix `anch`. That is a fish becoming a
capsicum.

`turmeric` and `cumin`, both bare single words, fall below the floor against
`Spices, turmeric, ground` and `Spices, cumin seed`. USDA's `Spices, ` prefix
costs every spice roughly eight characters of description length, and the length
effect does the rest. This is systematic across the whole spice cabinet and is a
cross-cutting item, not a Southeast Asian one.

### F33 — WITHDRAWN: `rice flour` is blocked by `unrequested_qualifier`

- **kind:** filed as wrong_confident_match, then **retracted on measurement**
- **confidence:** n/a — the finding does not survive

The probe reported:

```
auto  rice flour                         0.647  Flour, rice, brown
```

which reads as a wrong `auto` onto brown flour when white was meant. Re-run
through the actual guards in `resolve_items`:

```
== rice flour
    0.647 Flour, rice, brown -> BLOCK:qual
    0.647 Rice flour, brown  -> BLOCK:qual
    RESULT: escalates to model
```

`unrequested_qualifier` fires on `brown` in both candidates and the item goes to
the model tier. **The system is working and there is no finding here.** Recorded
rather than deleted, because it is the case that forced the caveat in §"Notes"
below: a `auto` verdict from `probe_knowledge.py` is a statement about
*similarity*, not about what `resolve_items` would do.

### F34 — `fish ball` reaches `Fish, bass, NFS`

- **kind:** wrong neighbour (below floor) / entity gap
- **category:** `ingredient_vs_dish_ambiguity`
- **confidence:** high

```
weak  fish ball                          0.412  Fish, bass, NFS
weak  fish balls                         0.389  Fish, bass, NFS
ask   surimi                             0.583  Fish, surimi
weak  beef balls                         0.357  Beef, NFS
weak  pork floss                         0.333  Pork, NFS
```

Fish balls are a starch-extended surimi product — much of the mass is wheat or
tapioca flour, so the protein per 100 g is roughly half that of a fillet and the
carbohydrate is not zero. `Fish, bass, NFS` is a plain white fish fillet. The
correct neighbour, `Fish, surimi`, is reachable only from the Japanese technical
term `surimi`, which nobody types at a hawker stall.

Same shape for `beef balls` -> `Beef, NFS` and `pork floss` -> `Pork, NFS`: a
processed, extended, sweetened or dried product collapsing onto the plain raw
muscle it was made from. All below the weak floor, so latent.

### F35 — `sago` returns nothing; `tapioca pearls` auto-matches

- **kind:** entity_gap (weak) / reachability
- **category:** `missing_food_entity`
- **confidence:** medium

```
auto  tapioca pearls                     0.650  Tapioca, pearl, dry
none  sago                               -      (nothing)
none  sago pearls                        -      (nothing)
```

`ILIKE %sago%` -> 0 rows. Sago is sago-palm starch and tapioca is cassava
starch — different plants — but both are near-pure starch and the products are
used interchangeably in SE Asian desserts (sago gula melaka, bubur cha cha). The
substitution is defensible on macros and is recorded as **medium**, because it
is a botanical claim the data cannot support even though the nutrition is
effectively identical.


### F36 — the guards' fall-through picks honey-roasted peanuts over roasted peanuts

- **kind:** wrong_confident_match
- **category:** `bad_fallback`
- **confidence:** high

Found only by running the real guards, not by the probe. `resolve_items` takes
"the best candidate that survives all of them rather than only inspecting the
head" — and here the surviving candidate is worse than the blocked one:

```
== roasted peanuts
    0.762 Peanuts, roasted, salted -> BLOCK:qual
    0.727 Peanuts, honey roasted   -> SURVIVES
    RESULT: AUTO -> Peanuts, honey roasted
```

    2707515  Peanuts, roasted, salted    599 kcal, 28.0 g protein, 15.3 g carb,  4.2 g sugar
    2707516  Peanuts, roasted, unsalted  599 kcal, 28.0 g protein, 15.3 g carb,  4.2 g sugar
    2707520  Peanuts, honey roasted      574 kcal, 20.7 g protein, 30.0 g carb, 16.1 g sugar

`salted` is correctly treated as an unrequested qualifier and the row is blocked.
`honey roasted` is *also* an unrequested qualifier — a much more consequential
one, since it nearly quadruples the sugar and doubles the carbohydrate — but
"honey roasted" reads as a preparation phrase and passes. So the guard removes
the nearly-right row and admits the wrong one, with no model consulted, and
caches the alias.

Crushed roasted peanuts are the garnish on pad thai, gado-gado, satay and bun
cha, in 10-20 g quantities, so the absolute harm per meal is small. The
mechanism is the finding: **blocking the head can promote something worse**, and
nothing currently checks that the survivor is closer to the query than the
candidate it replaced. That is a general property of the guard design, not a
Southeast Asian fact, and is the most useful thing this domain turned up about
the resolver itself.

## Proposals


Format: `surface | relation | target | confidence | rationale`.
`relation` is one of synonym, parent_category, nutritional_fallback,
dish_ingredient. Only **high** is proposed for automatic encoding; **medium** is
proposed as a non-mandatory fallback and must not auto-match; **low** is not
proposed at all and appears under Deliberately rejected.

### P1 — highest priority: the three confirmed wrong autos

These are not synonyms to add, they are matches to *stop*. Each was confirmed
against the real guards (see Guard check) and each caches an alias.

```
coconut milk           | synonym | 2707568 Coconut milk, used in cooking   | high
santan                 | synonym | 2707568 Coconut milk, used in cooking   | high
gata                   | synonym | 2707568 Coconut milk, used in cooking   | high
kati                   | synonym | 2707568 Coconut milk, used in cooking   | high
tinned coconut milk    | synonym | 170173 Nuts, coconut milk, canned       | high
```
Rationale: F1. The current auto onto FNDDS 2705413 (31 kcal, the carton drink)
understates a 400 ml can by ~660 kcal. The word "coconut milk" in a cooking
context always means the pressed liquid. The carton beverage should stay
reachable as `coconut milk drink` / `coconut beverage`.
Caveat that must ship with this: 2705413 is genuinely what an American logging a
carton means. The right encoding is context-sensitive, and if the layer cannot
express context, the safer default is still the cooking row, because the failure
mode of the cooking row is over-counting a drink by 200 kcal per glass and the
failure mode of the drink row is under-counting a curry by 660.

```
coconut cream          | synonym | 170580 Nuts, coconut cream, raw         | high
kara                   | synonym | 170580 Nuts, coconut cream, raw         | high
cream of coconut       | synonym | 2707571 Coconut cream, canned, sweetened| high
```
Rationale: F2. Three distinct foods share these words and the resolver takes the
dessert pie. `cream of coconut` is separated out deliberately — it is the
sweetened pina-colada product (53 g carb) and is genuinely a different thing
from coconut cream (6.7 g carb).

```
brown rice             | synonym | 2708414 Rice, brown, cooked, no added fat | high
jasmine rice           | synonym | 2708407-family white rice, cooked        | high
```
Rationale: F25. `Flour, rice, brown` at 365 kcal against cooked brown rice at
123 is a 3x staple error, `auto`, confirmed through the guards. Filed as high on
the *identity* (brown rice is not brown rice flour); the exact cooked row to
point at is a state question the model tier should keep, so the encoding should
block the flour rather than pin one cooked row if the layer can express that.

```
sweet soy sauce        | synonym | (no target — block the Soy sauce auto)   | high
kecap manis            | synonym | (no target — block the Soy sauce auto)   | high
```
Rationale: F4. There is no kecap manis row (entity gap), so there is nothing to
point at. What must happen is that the `auto` onto `Soy sauce` stops: ~50 g of
sugar per 100 g is being zeroed. Escalating to the model, which can at least ask,
is strictly better than a confident wrong answer.

### P2 — pure synonyms onto rows that are already correct

Zero nutritional judgement in any of these: the target is right and reachable
from some other string, and the surface form is simply a word USDA does not use.

```
nam pla                | synonym | Fish sauce (2709748-family)     | high  F7
nuoc mam               | synonym | Fish sauce                      | high  F7
patis                  | synonym | Fish sauce                      | high  F7
prawn                  | synonym | Shrimp, NFS                     | high  F30
prawns                 | synonym | Shrimp, NFS                     | high  F30
king prawn             | synonym | Shrimp, NFS                     | high  F30
tiger prawn            | synonym | Shrimp, NFS                     | high  F30
dried prawns           | synonym | Shrimp, dried                   | high  F30
groundnut oil          | synonym | Peanut oil                      | high  F32
prawn cracker          | synonym | 2708246 Shrimp chips            | high  F19
prawn crackers         | synonym | 2708246 Shrimp chips            | high  F19
krupuk                 | synonym | 2708246 Shrimp chips            | high  F19
kerupuk                | synonym | 2708246 Shrimp chips            | high  F19
satay sauce            | synonym | Peanut sauce                    | high  F24
sate sauce             | synonym | Peanut sauce                    | high  F24
bumbu kacang           | synonym | Peanut sauce                    | high  F24
gai lan                | synonym | Broccoli, chinese, raw          | high  F27
long beans             | synonym | Yardlong bean, raw              | high  F27
snake beans            | synonym | Yardlong bean, raw              | high  F27
sitaw                  | synonym | Yardlong bean, raw              | high  F27
kacang panjang         | synonym | Yardlong bean, raw              | high  F27
gabi                   | synonym | Taro, raw / Taro, cooked        | high  F16
ube                    | synonym | Yam, raw / Yam, cooked          | high  F16
ube halaya             | synonym | Yam, cooked (+ sugar, milk)     | medium F16
purple yam             | synonym | Yam, raw / Yam, cooked          | high  F16
calamansi              | synonym | Lime, raw / Lime juice, raw     | high  F17
kalamansi              | synonym | Lime, raw / Lime juice, raw     | high  F17
philippine lime        | synonym | Lime, raw / Lime juice, raw     | high  F17
squid                  | synonym | 2706333 Calamari, cooked        | high  F31
sotong                 | synonym | 2706333 Calamari, cooked        | high  F31
pusit                  | synonym | 2706333 Calamari, cooked        | high  F31
pla muek               | synonym | 2706333 Calamari, cooked        | high  F31
ikan bilis             | synonym | 174183 Fish, anchovy, canned    | medium F32
dried anchovies        | synonym | 174183 Fish, anchovy, canned    | medium F32
tahu                   | synonym | Tofu (raw, firm)                | high  F21
tempe                  | synonym | Tempeh                          | high  F21
bihon                  | synonym | Rice noodles, dry               | high
sotanghon              | synonym | 174258 cellophane/long rice     | high  F3
glass noodles          | synonym | 174258 cellophane/long rice     | high  F3
cellophane noodles     | synonym | 174258 cellophane/long rice     | high  F3
mung bean noodles      | synonym | 174258 cellophane/long rice     | high  F3
bean thread noodles    | synonym | 174258 cellophane/long rice     | high  F3
woon sen               | synonym | 174258 cellophane/long rice     | high  F3
mien                   | synonym | 174258 cellophane/long rice     | high  F3
pho                    | synonym | 2707124 Soup, pho, with meat    | high  F9
pho bo                 | synonym | 2707124 Soup, pho, with meat    | high  F9
pho ga                 | synonym | 2707124 Soup, pho, with meat    | high  F9
pho chay               | synonym | 2707125 Soup, pho, no meat      | high  F9
adobo                  | synonym | 2708958 Adobo, with rice        | high  F14
chicken adobo          | synonym | 2708958 Adobo, with rice        | high  F14
pork adobo             | synonym | 2708958 Adobo, with rice        | high  F14
adobong manok          | synonym | 2708958 Adobo, with rice        | high  F14
durian                 | synonym | 168192 Durian, raw or frozen    | high  F26
bitter gourd           | synonym | Balsam-pear (bitter gourd), raw  | high  F26
ampalaya               | synonym | Balsam-pear (bitter gourd), raw  | high  F26
pare                   | synonym | Balsam-pear (bitter gourd), raw  | high  F26
custard apple          | synonym | Custard-apple, raw              | high  F26
turmeric               | synonym | Spices, turmeric, ground        | high  F32
cumin                  | synonym | Spices, cumin seed              | high  F32
anchovies              | synonym | Fish, anchovy                   | high  F32
```

The `pho bo`/`pho ga` -> "with meat" and `pho chay` -> "no meat" split is worth
noting as the one place in this domain where USDA's own distinction lines up
exactly with the native vocabulary. Everything else in P2 is a one-to-one word
swap.

### P3 — parent categories and nutritional fallbacks (non-mandatory)

Proposed as fallbacks that a resolver may offer to the model tier, never as
auto-matches.

```
sago                   | nutritional_fallback | Tapioca, pearl, dry   | medium F35
sago pearls            | nutritional_fallback | Tapioca, pearl, dry   | medium F35
palm sugar             | nutritional_fallback | Sugars, granulated    | medium
gula melaka            | nutritional_fallback | Sugars, granulated    | medium
coconut sugar          | nutritional_fallback | Sugars, granulated    | medium
thai basil             | nutritional_fallback | Basil, fresh          | high
holy basil             | nutritional_fallback | Basil, fresh          | high
horapha / krapow       | nutritional_fallback | Basil, fresh          | high
cha gio                | nutritional_fallback | Egg roll, with beef and/or pork | medium F11
lumpiang shanghai      | nutritional_fallback | Egg roll, with beef and/or pork | medium F11
fried spring roll      | nutritional_fallback | Egg roll, meatless    | medium F11
```

The basil group is `high` because all cultivars of *Ocimum* are the same leaf
herb used in the same gram quantities, and the difference between them is
aromatic, not nutritional. The sugar group is `medium` because palm sugar
carries trace minerals and slightly more moisture than refined sugar — close
enough to be a useful fallback, not close enough to assert.

`cha gio` -> egg roll is `medium` and deliberately not extended to `goi cuon`
(see Deliberately rejected): both are wrapped in rice paper, but one is
deep-fried and one is not, and that is the entire difference in the number.

## Deliberately rejected

## Notes
