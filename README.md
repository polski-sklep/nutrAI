# nutrai

Telegram-first nutrition tracker. Photo or text in, structured meal out, human
confirms, Postgres keeps the truth.

The one architectural claim worth stating up front: **the model never produces
a nutrient value.** It produces food identity, mass, and its own confidence.
Every calorie, gram of protein and microgram of selenium comes from USDA
FoodData Central via SQL. This is why tracking ~80 nutrients costs exactly the
same in tokens as tracking four, and why a hallucination can misidentify your
lunch but cannot invent its potassium content.

## Setup

```bash
cp .env.example .env && $EDITOR .env
docker compose up -d db

# Load the food database. Full CSV export from
# https://fdc.nal.usda.gov/download-datasets (public domain, CC0 1.0).
# Foundation + SR Legacy + FNDDS is enough; skip Branded unless you scan barcodes.
python scripts/load_usda.py ~/Downloads/FoodData_Central_csv_2025-04-24

python scripts/bootstrap.py --telegram-id 123456789 --sex male --age 34 \
  --height-cm 183 --weight-kg 74.4 --activity 1.55 --deficit 500 --protein-g 180

docker compose up -d bot

# After ~2 weeks of logging: pin your most-eaten foods to verified USDA rows.
# Forty minutes once, and the resolver stops being an error source for ~90%
# of what you eat. Flags any match whose row reports fewer than 15 of the 20
# core nutrients — those are measurement gaps, not dietary ones.
python scripts/pin_foods.py --telegram-id 123456789            # review
python scripts/pin_foods.py --telegram-id 123456789 --pin      # interactive
```

## Using it

Send a photo. Send text. Confirm or discard. Nothing is written to the log
until you press the button.

```
/r              numbered menu of what you actually eat
3               log #3 exactly as before          — zero tokens
3 250           set the whole dish to 250 g       — zero tokens
3 x1.5          scale it                          — zero tokens
3 -onion        drop a component                  — zero tokens
3 +50 rice      add one                           — zero tokens
3 rice 200      set one component                 — zero tokens
3 @14:00 #lunch time and slot                     — zero tokens
b               log a whole meal template         — zero tokens
3 but I used the leaner mince   → falls through to Haiku, ~0.08¢

/fast           current fast, duration and phase — zero tokens
/window         eating window, midpoint and stability, 14 days — zero tokens
/f 8            rate focus now (also /rate energy 6, /rate rpe 9)
/weight 78.2    log a weigh-in — the only input to the fat-loss rate
/insight        fat-loss rate from your weight trend; correlations, gated at n=20

/today  /today all  /yesterday
/spend          what the model layer has actually cost
```

Anything else beginning with `/` gets the list above back. Nothing is ever
dropped in silence.

## Cost

Measured, not estimated — `/spend` reads the `llm_call` table, which is written
from the `usage` block of every response.

| path | model | typical cost |
|---|---|---|
| repeat, summary, notification | none | $0 |
| repeat with an unparsed modifier | Haiku 4.5 | $0.0008 |
| novel dish from text | Sonnet 5 | $0.0038 |
| novel dish from photo (896 px) | Sonnet 5 | $0.0060 |
| photo escalated on low confidence | Opus 5 | $0.0149 |
| weekly improvement plan | Opus 5 | $0.055 |

Six logs a day, 80% of them repeats, plus a weekly plan: **about $0.42 a
month.** Which is the honest reason to stop optimising for tokens and start
optimising for grams — see `docs/ARCHITECTURE.md`.

## When you cannot weigh something

Weighed masses always win. When nothing was weighed:

1. **Your own history is used first.** Three or more past *weighed* masses for
   that food, inter-quartile spread under 25%, and the model's guess within
   0.4–2.5× of the median — then your median is used, marked `↺`. Estimates are
   never fed back into the history, so the system cannot bootstrap its guesses
   into fact.
2. **Every estimate carries a range.** The parser must supply `grams_low` and
   `grams_high`; σ = (high − low)/4. Defaults: weighed ±0.5%, stated ±5%,
   package ±3%, prior ±10%, bare visual guess ±35%.
3. **Uncertainty propagates in quadrature** into the day's totals, so one
   weighed component shrinks the whole error bar disproportionately.

```
████████░░ 1,720 ± 140 / 2,000 kcal
62% of today's mass was weighed or stated

  ⚖ minced beef — 250 g
  ✎ rice — 164 g
  ≈ olive oil — 18 g  (7–29 g)
```

That last line carries 160 kcal of range on a single item. It is the thing that
makes you reach for the scale next time.

## Fasting, and the three things it will not tell you

Fasting windows are a window function over meal timestamps: free, deterministic,
no new logging. Eating window, midpoint, midpoint stability, longest fast,
early/midday/late classification.

What it deliberately does **not** do:

- **Report "fat burning".** Substrate oxidation needs indirect calorimetry, and
  24-hour fat balance is set by energy balance regardless. `/insight` gives you
  the honest version — kg/week from your weight trend, the implied deficit, and
  your actual TDEE — and it contains no reference to when you ate.
- **Guess your optimal working times.** That needs an outcome variable. `/f 8`
  logs one in five seconds, stamped with the fasting hours at write time.
  `/insight` refuses below 20 paired observations, uses rank correlation with a
  permutation p-value, and flags when time of day explains the result better
  than food does — which it usually will.
- **Pretend small effects are large.** Window timing adds roughly −0.7 kg fat
  mass over matched calorie restriction. Real, replicated, and a rounding term
  on the deficit.

## Layout

```
sql/001_schema.sql     tables; nutrient snapshots; versioned targets
sql/002_views.sql      day_progress(), target_on(), v_dish_rank
sql/003_fasting.sql    v_eating_window, v_meal_gap, observation, fast_hours_at()
nutrai/config.py     model routing, prices, guardrail thresholds
nutrai/db.py         all SQL access
nutrai/core/dsl.py   the zero-token repeat grammar (+ 29 tests)
nutrai/core/estimate.py   portion priors, error bars, uncertainty propagation
nutrai/core/fasting.py    windows, midpoint, phases (with the hedging enforced)
nutrai/core/insight.py    n-of-1 correlation with refusal gate; fat-loss rate
nutrai/core/nutrition.py  deterministic nutrient arithmetic, energy check
nutrai/core/render.py     every outbound message, no model involved
nutrai/core/plan.py       evidence pack -> proposal -> human gate -> versioned write
nutrai/llm/schemas.py     tool schemas; the "no nutrient values" contract
nutrai/llm/parse.py       photo/text parse, 3-tier resolver, validation
nutrai/bot.py             aiogram handlers, album buffering, confirm gate
nutrai/jobs/notify.py     threshold rules, SQL-evaluated, template-rendered
```

## Tests

```bash
pytest -q
```

109 tests cover the repeat grammar, the nutrient arithmetic, the estimation
layer, the fasting/inference layer, the rendering and the command surface — the
places where a silent bug corrupts months of data rather than producing an
obvious error. Three exist purely to stop the system overclaiming: one asserts
the fasting phase gloss never says "you are burning", one asserts a correlation
at n=10 refuses to report, and one asserts a nutrient no logged food measures is
never displayed as a shortfall. Another asserts every command the bot advertises
has a handler behind it, because for a while three of them did not.

```bash
pytest -q                  # 109 tests, no database
pytest -q -m integration   # the end-to-end path, needs a loaded database
```

The integration suite drives the real aiogram dispatcher against a real Postgres
with the Anthropic client stubbed: text and photo in, resolver against real USDA
rows, confirm gate, snapshot, `/today`. It skips itself when there is no
database, so `pytest -q` stays offline.
