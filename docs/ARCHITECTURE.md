# nutrai: architecture, decisions, build plan

Status: v0 scaffold implemented, 60 tests passing. Spec current as of 15 August 2026.
Stack fixed by your choices: VPS + Postgres, full USDA nutrient parity, Anthropic-only routing.

---

## 0. Three objections to your brief, before anything else

### 0.1 "As few tokens as possible" is optimising a variable that does not bind

I priced it. Current Anthropic list prices: Opus 5 $5/$25 per Mtok, Sonnet 5
$2/$10, Haiku 4.5 $1/$5; cache reads are 0.1x input, 5-minute cache writes
1.25x; images cost `ceil(w/28) × ceil(h/28)` visual tokens.

Under the architecture below, at six logs a day with 80% repeats:

| path | model | cost per call |
|---|---|---|
| repeat / summary / notification | none | $0 |
| repeat modifier the grammar missed | Haiku 4.5 | $0.00082 |
| novel dish, text | Sonnet 5 | $0.00378 |
| novel dish, photo at 896 px | Sonnet 5 | $0.00598 |
| photo escalated on low confidence | Opus 5 | $0.01494 |
| weekly improvement plan | Opus 5 | $0.055 |

**Total: about $0.42 per month.** Even at 100% photo logging with no repeats at
all, you land near $1.10.

So the cost argument for token minimisation is dead. Three arguments survive,
and they are the ones the design actually serves:

1. **Latency.** A repeat that resolves in SQL answers in ~5 ms. The same
   repeat through a model answers in 2–4 s. Six times a day, that is the
   difference between an app you use and an app you abandon.
2. **Determinism.** "Log breakfast again" must produce byte-identical
   components every time. A model asked the same question twice will not
   guarantee that. Your longitudinal data is worth more than the flexibility.
3. **Failure surface.** Every model call is a call that can time out, get rate
   limited, or return something structurally valid but semantically wrong. The
   zero-token paths cannot fail in those ways.

Design consequence: minimise model calls where they add no information. Do not
contort the ones that do — a 500-token prompt that gets the mass right is worth
more than a 200-token prompt that does not.

Confidence: high on the arithmetic (it is computed from published prices in
`config.PRICES` and re-derivable), high on the conclusion.

### 0.2 The accuracy you admire in those screenshots is scale accuracy, not model accuracy

Read the Caltrack entries again: "250 g raw", "402 g", "263 g cooked", "164 g
cooked", "170 g cooked", "125 g cooked". One of the photo strips is a
close-up of a kitchen scale with a lit display. Those numbers were weighed.
The model transcribed and looked up; it did not estimate.

Photo-only portion estimation is the weakest component in every tracker of this
class, and the error is not random — it is biased low on calorie-dense items
(oil, sauces, cheese) because they are visually small and dimensionally hidden.
A 15 g error on olive oil is 135 kcal, which is a quarter of your deficit.

Design consequences, all implemented:

- The parse schema forces a `grams_source` field with `scale` as a distinct
  value, and the system prompt instructs the model to read a visible scale
  display in preference to any visual estimate.
- The confirmation card marks each component with its provenance (`⚖` weighed,
  `✎` you stated it, `≈` the model guessed) so you can see at a glance which
  numbers to trust.
- The fastest input path is text, not photo. "mince 250 rice 164" is ~15 tokens
  and is exactly correct. Photo is the fallback for food you did not cook.

If you take one thing from this document: **put the scale in the frame.** The
architecture is built to exploit that, and no model choice substitutes for it.

Confidence: high.

### 0.3 "Full Cronometer parity, ~80 nutrients" is partly a promise the data cannot keep

Cronometer's depth comes from the same public sources you will load: USDA
FoodData Central (Foundation, SR Legacy, FNDDS) plus the Canadian Nutrient File
and NCCDB. There is no proprietary moat. But nutrient coverage is wildly uneven
across those datasets, and the unevenness maps directly onto how you eat:

| dataset | download size (CSV, zipped) | nutrient depth |
|---|---|---|
| Foundation Foods | 3.3 MB | deepest — full panels, analytical values, provenance |
| SR Legacy | 6.7 MB | broad and deep; final release 2018, so no new foods |
| FNDDS (survey) | 200 MB | ~65 nutrients, covers composite and restaurant-style dishes |
| Branded | 423 MB | label data only: macros, sodium, sometimes a handful more |

If a component resolves to a Branded row, you get roughly the nutrients on the
package and nulls for everything else. Summing those nulls as zero produces the
classic micronutrient-tracker lie: "you got 0 µg of selenium today," when the
truth is nobody measured the selenium in that ready meal.

Design consequences, all implemented:

- `food.precedence` is a generated column that ranks Foundation > SR Legacy >
  FNDDS > Branded, and the resolver orders by it. You get the well-measured row
  unless you explicitly named a brand.
- `total_nutrients()` skips missing nutrients rather than zeroing them.
- `coverage(components, profiles, nutrient_id)` returns the fraction of the
  meal's mass whose food row actually reports that nutrient. Report it beside
  any micronutrient figure. "Selenium 41 µg (78% of the plate measured)" is
  honest. "41 µg" is not.
- Load Branded **only** if you scan barcodes. It is 3.1 GB unzipped and it will
  pollute your resolver's candidate set with thousands of near-duplicate label
  rows.

Confidence: high on the mechanism, high on the dataset sizes (taken from the
FDC download page), moderate on exactly which of your habitual foods will land
on thin rows — that is an empirical question the coverage metric answers after
two weeks of real logging.

**The decision, since you did not have one.** Your diet is narrow and
repetitive; that is the premise of the entire repeat system. Roughly forty
foods will account for something like 90% of everything you eat this year. So:

> **Load everything. Pin the top forty by hand, once.**

`scripts/pin_foods.py` ranks your aliases by use, shows each one's current USDA
match and how many of the twenty core nutrients that row actually reports, and
flags every match with fewer than fifteen. You confirm or re-point each. A
pinned alias is protected in `upsert_alias` and is never silently re-pointed by
a later parse.

Forty minutes of work, once. In exchange, the resolver stops being a source of
error for the overwhelming majority of your intake, and the micronutrient
figures for that majority come from rows with full analytical panels rather
than from label data.

The rule when pinning: **prefer a Foundation or SR Legacy row with a complete
panel over a Branded row that names your exact product.** The brand's macros
are marginally more accurate. Its nulls are catastrophic. You are trading a
2% error on protein for the difference between measuring selenium and not
measuring it.

The long tail — the restaurant meal, the thing you ate once at someone's house
— stays automatic, stays flagged with its coverage percentage, and matters
little because it is the tail.

---

## 1. The central contract

> The model returns **identity, mass, state, confidence**.
> It never returns a nutrient value.
> Nutrition is a SQL join against USDA.

Everything else follows from this line.

- Tracking 80 nutrients costs the same as tracking 4, because neither ever
  enters the context window. This is why your "full parity" choice is free.
- A hallucination can misidentify your lunch. It cannot invent your potassium.
- Nutrient values are reproducible and auditable: every number traces to an
  `fdc_id`, a gram figure and a yield factor stored in `log_component`.
- Swapping models cannot silently shift your calorie history, because models do
  not compute your calorie history.

The contract is enforced structurally, not by asking nicely: `PARSE_TOOL` has
no field in which a nutrient could be returned, and `tool_choice` is forced, so
the model cannot answer in prose instead.

---

## 2. Data model

Full DDL in `sql/001_schema.sql`. The parts that carry design weight:

**`log_nutrient` is a snapshot, not a view.** On confirmation, all ~80 nutrient
values are computed and written. USDA republishes; foods get recategorised; you
fix a wrong match six weeks later. None of that may retroactively rewrite what
last March looked like. Cost: ~250k rows a year, which Postgres does not
notice.

**`target` is versioned, never updated in place.** Each row has
`effective_from` / `effective_to`. An improvement plan closes the old row and
opens a new one starting tomorrow. Without this, "did the change I made in
August do anything" is unanswerable, because the change overwrote the evidence.

**`food_alias` is the learning substrate.** Every confirmed novel food writes
`(your word) → (fdc_id)`. "yopro" costs one Haiku call, once, ever. This is why
steady-state cost trends toward zero rather than being constant.

**`dish` + `dish_component` are what repeats operate on.** Every confirmed
parse upserts a dish. Dishes accumulate `times_logged` and `last_logged_at`,
and `v_dish_rank` scores them with a 14-day exponential recency decay, so the
`/r` menu is the eight things you are actually eating now, not the eight things
you ate most since installation.

**`yield_factor` is where the real error lives.** Multiply logged mass by it to
get mass of the USDA row as described. You weighed 200 g of cooked mince; the
USDA row is raw; raw mince loses roughly a quarter of its water, so 200 g
cooked came from about 267 g raw, and `yield_factor = 1.33`. Get this wrong and
you are 33% wrong on your largest protein source — an error that dwarfs every
token you will ever save. The disambiguation tool returns it explicitly.

**`llm_call` prices every request from the API's own `usage` block**, including
cache reads and visual tokens. `/spend` reads this table. Estimating cost from
your own token counts is how people discover in month three that caching was
never actually hitting.

---

## 3. The three-stage pipeline

```
photo/text ──▶ [1] PARSE ──▶ [2] RESOLVE ──▶ [3] COMPUTE ──▶ human gate ──▶ log
                Sonnet 5      alias→trgm      pure SQL        inline kb
                or Opus 5     →Haiku                          confirm/fix/discard
```

### Stage 1 — parse

`PARSE_TOOL`, forced. Returns `dish_name`, `slot` and a list of items, each
with `label`, `search_terms` (a precise USDA-style phrase), `grams`,
`grams_source`, `state` (raw/cooked/dry/as_sold/unknown) and per-item
`confidence`, plus `overall_confidence` and free-text `notes`.

The system prompt (`PARSE_SYSTEM`) is seven numbered rules, ordered by how much
damage violating them does. The ones that matter most:

- Read a visible scale display and use it. Say what digits you read.
- Trust stated text over the photograph.
- Raw vs cooked is as important as the number. If you cannot tell, say
  `unknown` and drop your confidence rather than guessing.
- Do not invent a split you cannot see. If you cannot tell how much butter is
  in the mash, log the composite and say so.
- Calibrate confidence honestly: weighed single ingredient 0.95; plated mixed
  dish shot from above with no scale, 0.4–0.6.
- Cooking oil is real and routinely forgotten. If the dish is glossy, include
  it.

The system prompt is `cache_control: ephemeral`. It is identical on every call
and runs a few hundred tokens; a cache read costs 10% of input and pays for
itself on the second log in any five-minute window.

**Escalation is conditional, not routine.** If `overall_confidence` comes back
below 0.75, the same image goes to Opus 5 once and the higher-confidence result
wins. On a clearly weighed single ingredient Sonnet is right and Opus costs
2.5× for nothing; on an ambiguous plate the escalation is the difference
between a usable number and a guess. Roughly 20–30% of photos should escalate.
If your rate is far outside that, the threshold is wrong for your photography.

**Image preprocessing is a real cost lever.** A stock Telegram photo at
1280×960 is 1,610 visual tokens on a high-resolution-tier model. Downscaled to
896×672 it is 768. Food identification does not improve above roughly 900 px.
The floor is 896 rather than 448 precisely because a scale display must stay
legible. `IMAGE_LONG_EDGE` is the dial.

**Albums are buffered.** Telegram sends each photo of a media group as its own
update. Without the 1.2 s `media_group_id` buffer in `bot.py`, a four-photo
meal becomes four meals. Only the first image escalates; the rest are
supplementary.

### Stage 2 — resolve

Three tiers, cheapest first:

1. **Alias hit** — exact, or trigram similarity above `AUTO_MATCH_SIMILARITY`.
   Free. This is where the steady state lives.
2. **High-similarity database hit** — full-text rank plus trigram, ordered by
   `precedence`. Free. Writes an alias.
3. **Haiku over the top-5 candidates** — ~$0.0008, once per genuinely new food.
   Returns `fdc_id`, `yield_factor` and confidence, and is instructed to return
   `fdc_id: 0` rather than force a bad match. Writes an alias.

A wrong row is worse than a missing one, because a wrong row is silently
counted forever. That asymmetry is stated in `DISAMBIGUATE_SYSTEM`.

### Stage 3 — compute and validate

Pure arithmetic in `core/nutrition.py`, then the guardrails that run in
`llm/parse.py:validate()` before anything is shown:

- **Atwater energy cross-check.** Recompute kcal from macros (4/4/9, with fibre
  at −2 kcal/g because fibre sits inside carbohydrate-by-difference but is not
  metabolised like it) and compare against the database energy figure.
  Disagreement beyond 12% means a component is matched to the wrong food, the
  grams are wrong, or the row is internally inconsistent. This is the cheapest
  correctness signal available and it catches the most damaging failure mode: a
  plausible-looking parse against the wrong USDA row.
- **A component that reports no energy.** Its grams add 0 kcal to the day and
  nothing else raises it, because the Atwater check cannot tell "no energy
  reported" from "zero-energy food". Named on the card instead.
- **Implausibility.** Any single component over 1,500 g, any yield factor
  outside 0.3–3.0.
- **Provenance flags.** `state: unknown` on anything over 80 g, or a
  low-confidence visual estimate, gets surfaced in the card.

Warnings do not block. They are printed above the confirm button, because the
person who can adjudicate is the one holding the plate.

---

## 4. The repeat system — the actual headline feature

You said most of what you eat repeats. That makes the repeat path, not the
vision path, the one that determines whether this thing survives contact with
daily use.

### The grammar

`core/dsl.py` implements a regular grammar parsed locally, with 29 tests.

```
<selector> [<op> ...]

selector   1..9        index into the last /r menu
           <slug>      a dish or meal-template slug

op         250 | 250g  total grams for the whole dish, applied proportionally
           x1.5 | *2   scale factor
           half|double word forms
           -onion      drop a component
           no onion    same
           +50 rice    add, with mass
           +rice       add, mass from the alias default
           rice 200    set one component
           @14:00      override the log time
           #dinner     override the meal slot
```

Composable and order-sensitive: `3 x1.5 -onion +50 rice #dinner @19:30` parses
to five operations, zero tokens, and `dsl.apply()` executes them against a copy
of the dish's component list. Dropping before scaling gives a different answer
than scaling before dropping, and the grammar preserves your ordering.

### The escalation

`RepeatCommand.needs_model` is true only when a token could not be accounted
for. Then, and only then, one Haiku call gets the component **label list** and
your phrase — not the photo, not the food database, not the conversation
history. About 200 input tokens. It returns explicit `set`/`add`/`drop`/
`scale_all` operations that join the locally-parsed ones.

**Watch that flag.** If `needs_model` fires on more than a few percent of
messages, the grammar is missing a shorthand you actually use. Extend the
grammar; do not pay a model to guess at it forever.

### The write policy

An unmodified repeat of a dish you have already confirmed is not a new claim
about the world. It logs immediately, no confirm button. Any modification goes
through the gate. This is the single biggest friction reduction available and
it is safe precisely because the components were human-confirmed the first
time.

### Meal templates

`meal_template` holds an ordered set of dishes. `b` logs the whole breakfast.
`b -egg @08:30` logs it minus the egg, timestamped. The ops apply to every dish
in the template, which is right for `x1.5` and `@time` and mildly blunt for
`-egg`; if that bites, the fix is per-dish addressing (`b.2 -egg`), which the
grammar has room for.

---

## 4.5 Estimation when nothing was weighed

You said weights will be provided where possible, and best-guess estimates
otherwise. The "otherwise" needs a real design, because an unmarked guess
sitting in the same column as a weighed value silently converts your log from a
measurement into an opinion.

Three mechanisms, in descending order of value. All implemented in
`core/estimate.py`, 14 tests in `tests/test_estimate.py`.

### Your own history beats vision

You have weighed a banana before. The median of your past weighings is a better
estimate of today's banana than any model looking at a photograph of it, and it
costs nothing. `portion_history()` pulls your weighed masses for a given
`fdc_id`; `portion_prior()` returns the median and spread.

The prior is used only when it deserves to be:

- at least three prior **weighed** samples (estimates are never fed back in, or
  the system would bootstrap its own guesses into fact);
- inter-quartile spread under 25% of the median — scattered history is real
  information, and "rice" varies because you serve it by eye;
- and the model's visual estimate is within 0.4×–2.5× of it. A threefold gap
  means today's portion genuinely was different, and the photo is the better
  witness.

Within about two weeks of normal logging this becomes the dominant estimator
for a repetitive diet, and it improves monotonically as you weigh more.

### An estimate without a range is a lie about precision

`PARSE_TOOL` now requires `grams_low` and `grams_high` whenever `grams_source`
is `estimate`, and the system prompt supplies reference dimensions to narrow
them (dinner plate 26–28 cm, fork 19–20 cm, egg 55–60 g, bread slice 35–40 g).
The range is read as a ~95% interval, so σ = (high − low) / 4.

Defaults when no range is given: weighed ±max(1 g, 0.5%), stated ±5%, package
±3%, prior ±10% or the observed spread, bare visual estimate ±35%. That last
figure is deliberately optimistic — published portion-estimation error for
untrained observers on composite plates is worse — because a pessimistic
default drowns the summary in error bars you stop reading.

### Propagation, so the day's total is honest

Per-component σ is stored in `log_component.grams_sigma` and combined in
quadrature, not linearly. Two components at ±35 g give a day at ±50 g, not
±70 g. That matters: it means **one weighed component disproportionately
shrinks the whole bar**, which is exactly the incentive you want. Weighing the
oil is worth more than weighing the rice.

The quadrature sum is computed in SQL, by `db.day_energy_sigma`, from the per-component sigma stored on each row — so it is reproducible from the database alone and does not depend on what the parser was thinking. A second implementation of it in `core/estimate.py` was removed once it became clear nothing called it.

The day card now prints two things it did not before:

```
████████░░ 1,720 ± 140 / 2,000 kcal
62% of today's mass was weighed or stated
```

The second line is the most useful number in the entire summary. Below about
50% it says: every trend under this is noise, and no improvement plan built on
it means anything. `core/plan.py` gets the same figure in its evidence pack, so
the weekly review can decline to draw conclusions rather than confidently
describing a diet you did not actually record.

Individual components show their range on the confirmation card when the
uncertainty exceeds 8%, marked by provenance: ⚖ weighed, ✎ stated, ▤ package,
↺ from your own history, ≈ guessed. Seeing `≈ olive oil — 18 g (7–29 g)` next
to the item that carries 160 kcal of that range is the thing that makes you
reach for the scale next time.

---

## 4.6 Fasting, and what timestamps can and cannot tell you

You asked for a fasting function that derives optimal working times, exercise
times, and moments of fat burning. One of those three is free, one is
answerable only if you start logging something you currently do not, and one is
not derivable from this data at any price. Taking them in reverse order of how
much you will like the answer.

### "Moments of fat burning" — not derivable, and not the question you want answered

Substrate oxidation is measured by indirect calorimetry: a mask, a gas
analyser, a respiratory quotient. A meal timestamp observes none of that. Any
app that draws you a fat-burning curve from your log is drawing a
population-average textbook figure and labelling it with your name.

Worse, the underlying question is malformed. Fat oxidised in hour 14 and
replaced by dietary fat in hour 15 is a round trip, not a loss. **Twenty-four-
hour fat balance is set by energy balance.** The network meta-analysis of
early, midday and late time-restricted eating is explicit that "energy deficit
appears to be the primary driver of anthropometric benefits", and the
TRE-plus-calorie-restriction meta-analysis (8 RCTs, 579 participants) puts the
*additional* effect of window timing at −1.40 kg body weight and −0.73 kg fat
mass (95% CI −1.39 to −0.07) over calorie restriction alone. Real, replicated,
low heterogeneity — and small. The window is a rounding term on the deficit.

So `phase_label()` returns a phase name and a hedged gloss, and its docstring
states plainly that it is a population timeline rather than a measurement of
you. `/fast` prints that disclaimer every time. A test asserts the gloss never
contains "you are burning", "grams of fat" or "your ketones are".

What is built instead, in `insight.fat_loss_rate()`, is the honest instrument:

```
fat loss
-0.48 kg/week over 26 days
implied energy balance -528 kcal/day
median intake 1,910 · implied TDEE 2,438
```

Regress weight on date, convert the slope at 7,700 kcal/kg, subtract from
median intake, and you have the TDEE your body actually has rather than the one
Mifflin-St Jeor guessed. Minimum fourteen days, because glycogen and water
swamp fat over shorter spans. Note what that output does not contain: any
reference to when you ate.

Confidence: high that meal timestamps cannot measure oxidation; high that
energy balance dominates; moderate-to-high on the specific meta-analytic
effect sizes, which are from two reviews rather than a settled literature.

### "Optimal working times" — answerable, but not from food logs

To find when you work best, something has to record how well you worked. The
app has inputs and no outcome. Correlating meal timing against nothing produces
nothing, and a system that produces a confident answer from nothing is worse
than one that stays silent, because you will act on it.

Two further problems, both handled explicitly:

1. **Time of day is a confound that eats the whole effect.** Hours-since-eating
   rises through the morning and so does most people's alertness. "I focus
   better fasted" and "I focus better at 10am" generate identical correlations
   from identical data. `insight.correlate()` therefore takes a `clock_hours`
   argument and, when clock time predicts the outcome about as well as fasting
   duration does, prints: *this effect is probably the clock, not the food.*
2. **The prior is that there is nothing to find.** A 2025 systematic review and
   meta-analysis in *Psychological Bulletin* found that short fasts do not
   impair cognitive performance in healthy adults, and a 2026 RCT found
   cognition stable while adapting to intermittent fasting. If your personal
   data shows a large effect where the trial literature shows none, the first
   hypothesis should be that you have found noise.

The mechanism is `/rate focus 8` — or `/f 8`, five seconds. Each rating is
stamped at write time with the fasting hours and the day's energy so far, the
same snapshot discipline as `log_nutrient`: if you later correct a meal's
timestamp, the fast you were actually in when you rated your focus at 7 does
not retroactively change.

`/insight` refuses below **20 paired observations** and tells you how many more
it needs. Above that it reports Spearman rho with a 2,000-resample permutation
p-value — rank-based because none of these relationships are plausibly linear,
permutation-based because a 1-10 rating with three used values violates every
distributional assumption a t-test makes.

### "Exercise times" — same shape, same requirement

`/rate rpe 9` after a session, or session load in `activity.kcal_burned`.
Identical correlation machinery, identical refusal gate. The one thing worth
knowing before you start: in the same network meta-analysis, early TRE
**combined with exercise** ranked first for fat mass (SUCRA 99%) and produced
−3.20 kg (95% CI −4.83 to −1.63) versus control. That is the largest timing-
adjacent effect in the literature, and it is an interaction with training, not
with fasting alone.

### What is free, and genuinely useful

All of this is a window function over `log_entry`. No new logging, no model, no
cost.

- **Fasts** — gaps between intakes, with a 3-hour floor so a second helping at
  14:45 is not counted as ending a fast that began at 14:41. Overnight fasts
  flagged, longest fast tracked.
- **Eating window** — first bite to last bite per day, in `v_eating_window`.
- **Window midpoint** — the metric nobody looks at and the one the trials
  actually separate. Length is what people discuss; position is what
  distinguishes early from late TRE.
- **Midpoint variability** — the number I would watch. A stable 10-hour window
  from 09:00 and a 10-hour average produced by alternating 07:00 and 13:00
  starts are not the same behaviour, and only the second is fighting its own
  circadian timing every other day. `/window` calls it out above ±1.5 h.
- **TRE class** — early / midday / late, by midpoint position. A bucket, not a
  diagnosis.

Fasting milestone notifications reuse the existing `notification_rule`
machinery with `kind='fast'` and a threshold in hours: same SQL evaluation,
same cooldown, same zero cost.

**Sources:** [TRE + CR meta-analysis, *Eur J Clin Nutr* 2023](https://www.nature.com/articles/s41430-023-01311-w) ·
[Early/midday/late TRE network meta-analysis, medRxiv 2026](https://www.medrxiv.org/content/10.64898/2026.01.29.26345140v1.full) ·
[Acute fasting and cognition meta-analysis, APA 2025](https://www.apa.org/news/press/releases/2025/11/short-fasts-do-not-impair-thinking) ·
[Cognitive performance while adapting to IF, RCT 2026](https://journals.sagepub.com/doi/10.1177/13591053251351204)

---

## 5. Summaries and notifications: no model, ever

`core/render.py` builds every outbound message from SQL plus a template.
`day_progress(user_id, date)` is one function call returning amount, target,
percentage and state per nutrient.

Routing summaries through a model is the most expensive mistake available in
this class of app: it costs money per view, adds seconds to the highest-
frequency interaction, and introduces the possibility that the sentence
disagrees with the number it is reporting. A template cannot get the arithmetic
wrong.

Notifications are rows in `notification_rule`: `(nutrient, direction,
threshold_pct, cooldown_minutes)`. Evaluation is pure SQL in
`jobs/notify.py:evaluate_user`, and it runs in two places:

- **Immediately after every write.** "You have consumed 80% of your carbs" is
  only actionable before the next meal, not at the next scheduled tick.
- **On a 20-minute sweep.** This catches `under` rules, which a write can never
  trigger — the reason you missed your protein floor is that you stopped
  eating.

`notification_log` plus per-rule cooldowns prevent the same threshold firing
six times an evening.

Defaults seeded by `bootstrap.py`: energy at 80% and 100% of ceiling, carbs at
80%, fat at 90%, sodium at 100%, protein under 60% with a 10-hour cooldown.

---

## 6. The improvement loop

`core/plan.py`. Structurally the pattern from your own vault note *Agent Fitness
Loop* — evidence pack, structured recommendation with confidence and risk,
human approval gate, dry-run default, versioned write.

1. **Evidence pack** (`evidence_pack`) is built in SQL and is under ~1,500
   tokens: 7-day and 28-day **medians** per nutrient against the target in
   force, logging coverage (days logged out of 28, mean entries per logged
   day), the twelve highest total-energy dishes, and the weight series.

   Medians, not means: one 2,441 kcal Saturday should not redefine your week.
   Coverage is in the pack because a model told only about the days you logged
   will confidently describe a diet you do not eat.

   The model never sees an individual log line. 28 days of raw entries is
   roughly 20k tokens and says nothing a median does not.

2. **Proposal** (Opus 5, `PLAN_TOOL`). Returns `findings` (each with cited
   evidence and a confidence level), numbered `recommendations` (each with a
   concrete action, expected effect, an explicit risk, and the machine-readable
   `target_changes` that implement it), and
   `what_the_data_cannot_tell_you`.

   The prompt requires: rank by magnitude of effect, not ease of fixing; no
   number, no finding; where database coverage is poor, say so rather than
   reporting a deficiency that is really a measurement gap; if the data
   supports no change, recommend nothing.

3. **Gate.** Numbered list back to you. `apply 1 3` or `apply all` or ignore.

4. **Write.** `apply_recommendations` closes the current `target` rows and
   inserts new ones effective tomorrow, with the rationale stored as JSON. The
   history stays intact.

At ~$0.055 a run this is the one place a frontier model earns its cost, because
the task is judgement under uncertainty rather than extraction.

---

## 7. Model routing

| purpose | model | why |
|---|---|---|
| photo parse | Sonnet 5 | vision plus structured output at $2/Mtok; the marginal accuracy of Opus on a *weighed* plate is small |
| photo escalation | Opus 5 | only when self-reported confidence < 0.75 |
| text parse | Sonnet 5 | same schema, no image |
| disambiguation | Haiku 4.5 | pick one of five strings; a frontier model is waste |
| repeat modifier | Haiku 4.5 | ~200 tokens of context, mechanical output |
| improvement plan | Opus 5 | genuine reasoning over conflicting evidence, weekly |

All IDs live in `config.py` and are pinned snapshots, not aliases. A model
swapping under you mid-experiment is how you end up unable to explain a
regression in parse accuracy.

**This table is a hypothesis, not a finding.** Section 8 is how you turn it
into one.

---

## 8. The evaluation you must build (phase 2, non-negotiable)

Everything above is architecture. None of it tells you whether the parse is
*accurate*, and you specified "uncompromisingly accurate". Accuracy is an
empirical claim and it requires a benchmark you own.

**Build it like this.** Over two weeks, for 40 meals: weigh every component on
the scale, record the true grams, then photograph the plate the way you
normally would. That is your ground truth set. It costs you a fortnight of mild
extra effort and it is the highest-value artefact in the entire project.

Then score, per candidate configuration:

- **Mean absolute percentage error on total mass** per meal.
- **MAPE on energy** — the number that actually drives your deficit.
- **Component identification F1** — did it find the oil?
- **Escalation precision** — of the photos where confidence < 0.75, how many
  did Opus actually improve? If that number is near zero, delete the escalation
  path.
- **Calibration** — bucket by reported confidence and plot actual error.
  A model reporting 0.9 that is wrong by 25% is worse than useless, because you
  will stop reading the warnings.

Configurations worth running: Sonnet vs Opus; 896 px vs 1,568 px vs full size;
scale-in-frame vs not; with vs without the "include cooking oil" rule.

I predict, at moderate confidence: scale-in-frame beats every other variable
combined; image resolution above ~900 px buys nothing; and Opus beats Sonnet by
a meaningful margin only on unweighted composite plates. Test it. Do not take
my prediction, or the routing table, on faith.

---

## 9. Build plan, mapped to your curriculum

Each phase names the vault module it exercises and what specifically you learn
by doing it rather than reading about it.

### Phase 1 — foundation (done, in this repo)
Schema, USDA loader, nutrient engine, repeat DSL, 29 tests.
**Module 13, Batch Processing Architecture.** The loader is a real streaming
ETL: 3 GB of CSV, batched `COPY`, deduplication, referential filtering, a
memory ceiling that does not move with input size. Also **module 11, AI
Guardrails Validation** — the Atwater cross-check is a validation layer that
costs nothing and catches the failure mode a schema check cannot.

### Phase 2 — parse and eval
Photo path end to end, then the 40-meal benchmark from section 8.
**Module 08, Structured Output Pipelines.** Forced tool use, schema design as
prompt engineering (the `grams_source` enum is doing more work than any
sentence in the system prompt), refusal-to-answer as a first-class output
(`fdc_id: 0`), calibrated confidence as a routing signal.
Also **module 14, LLM Observability Logging** — `llm_call` and `/spend` exist
so this phase produces numbers rather than impressions.

### Phase 3 — routing under measurement
Turn section 7's table from hypothesis into finding. Wire escalation thresholds
to measured escalation precision.
**Module 09, Model Routing Logic.** Cascade routing, confidence-gated
escalation, cost/accuracy Pareto fronts, and the discipline of measuring the
value of the expensive path instead of assuming it.

### Phase 4 — semantic food matching
Add pgvector. Embed `food.description` for the ~15k Foundation + SR Legacy +
FNDDS rows you actually keep. Hybrid retrieval: trigram for lexical, embedding
for semantic, reciprocal-rank fusion to merge.
**Modules 04, 05 and 03** — Vector Databases, Embedding Pipelines, RAG
Architecture. This is a genuinely well-scoped RAG problem: small corpus, hard
ground truth, and an evaluation set you already built in phase 2. You will
learn more from 15k food descriptions with a real answer key than from any
document-chat tutorial.
Expected gain: moderate. Trigram already handles "mince" → "beef, ground". It
will not handle "the green sauce from the Thai place".

### Phase 5 — memory and context discipline
Per-user learned preferences beyond aliases: your habitual portion sizes, which
brands you buy, that "coffee" means black and unsweetened. Injected into the
parse prompt as a compact cached block.
**Modules 06 and 07** — Agent Memory Systems, Context Window Optimization. The
interesting constraint is that this block must stay under ~300 tokens forever
while your history grows without bound. That forces the real lesson: memory is
a summarisation and eviction problem, not a storage problem.

### Phase 6 — the agentic loop
Weekly review runs on cron, builds the evidence pack, proposes, waits for your
gate. Optionally a second reviewer agent that argues against the first before
either reaches you.
**Module 06** again plus the *Agent Fitness Loop* and *Three tier agent stack
loop* notes. Adversarial review is the pattern worth internalising: a single
model asked to critique its own recommendation will mostly agree with itself.

### Phase 7 — exposure
MCP server over your own log, so Claude Code or the desktop app can query it
directly. Tools: `query_day`, `search_foods`, `log_meal`, `propose_targets`.
**Module 12, MCP Integration.** Your nutrition history becomes a resource any
agent can read, with the write path still gated.

Optional, later: **module 10, Local Model Deployment** — run the disambiguation
step on a small local model and measure what you lose. The task is
five-way classification over short strings and it is a fair test of whether
local inference is worth the operational weight.

---

## 10. What is deliberately not built

- **Barcode scanning.** Needs the Branded dataset (3.1 GB) and gives macros
  only. Add when you are logging packaged food often enough to care.
- **Health-platform sync.** Apple Health, Garmin, CGM. `activity` and
  `body_metric` are shaped for it. It is integration work, not architecture,
  and it should wait until the parse layer is measured.
- **A web dashboard.** Telegram plus `/today` covers the daily loop. Charts
  matching those screenshots are a Sunday afternoon with matplotlib against
  `v_day_nutrient`, once there is a month of data worth charting.
- **Multi-user anything.** One `app_user` row, one cron, `ALLOWED_TELEGRAM_IDS`
  as the whole authorisation model. Do not generalise before there is a second
  user.
- **Alembic migrations.** Two SQL files and a single deployment. Add migrations
  at the first schema change that must preserve production data.

---

## 11. Failure modes worth knowing about in advance

| failure | how it shows up | mitigation in place |
|---|---|---|
| wrong USDA row, right grams | totals drift, no error anywhere | Atwater cross-check; precedence ordering; `fdc_id: 0` escape |
| raw/cooked confusion | systematic 25–35% protein error | explicit `state`, explicit `yield_factor`, extreme-value warning |
| forgotten cooking oil | 100–200 kcal/day silently missing | explicit prompt rule; visible in the component list |
| null micronutrients read as zero | phantom deficiencies, bad plans | nulls skipped, not zeroed; `coverage()`; plan prompt told to distinguish; pinning pass flags thin rows |
| guesses laundered into measurements | trends built on opinion | `grams_sigma` stored per component; ± on the day total; "% weighed" on every summary |
| priors bootstrapping their own guesses | confident drift away from truth | `portion_history()` reads only `scale`/`stated`/`package` rows |
| a later bad parse re-points a good alias | silent, traceless corruption | `pinned` aliases are protected in `upsert_alias` |
| album split into four meals | four confirmation cards | `media_group_id` buffer |
| model over-confident | you stop reading warnings | calibration check in the eval; confidence surfaced on every card |
| targets overwritten by a plan | cannot evaluate your own changes | versioned `target`, never updated in place |
| bot token leaks | strangers billed to your key | `ALLOWED_TELEGRAM_IDS`, checked before any model call |

---

## 12. Open decisions

1. **Yield factors** are currently supplied per-resolution by Haiku. A curated
   lookup table for your twenty most-eaten foods would be strictly more
   accurate and free. Build it from the eval set in phase 2, and fold it into
   the pinning pass — the same forty foods, the same forty minutes.
2. **Day rollover** is set to 04:00, so a 01:09 glass of milk counts toward the
   day that has not ended. Matches the screenshots. Change `day_rollover_hour`
   if you disagree.
3. **Alcohol** is in the Atwater factors and has no default target. Decide
   whether you want it tracked and capped.
4. **Photo retention.** Currently only `photo_file_id` is stored, so images
   live on Telegram's servers rather than yours. If you want a local corpus for
   future fine-tuning or re-evaluation, write the bytes to `PHOTO_DIR` at parse
   time. That decision is easier to make now than after a year of logs.
