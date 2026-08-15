# Working on nutrai

Read this before changing anything. `docs/ARCHITECTURE.md` is the reasoning;
this file is the operating constraints.

## What this repo is

A working scaffold, not a sketch. ~2,700 lines, 60 passing tests, every module
compiles. It has **never run against a live Postgres or a live Anthropic API**.
The remaining work is integration debugging, not construction.

If you find yourself writing a second version of something that already exists
here, stop. That is the failure mode this file exists to prevent.

## Invariants — do not break these without an explicit instruction

1. **The model never returns a nutrient value.** It returns identity, mass,
   state, confidence. Nutrition is a SQL join against USDA. If a change would
   let a model emit a calorie figure, the change is wrong.
2. **`log_nutrient` is an immutable snapshot.** Never convert it to a view.
   Never recompute historical entries from current USDA data.
3. **`target` rows are versioned, never UPDATEd in place.** Close the old row
   with `effective_to`, insert a new one.
4. **Summaries and notifications never call a model.** `core/render.py` and
   `jobs/notify.py` are template-and-SQL only. Adding an LLM call to either is
   a regression, not a feature.
5. **Nothing is logged without a human confirm**, except an unmodified repeat
   of an already-confirmed dish.
6. **Missing nutrients are skipped, never zeroed.** See `total_nutrients()`.
7. **Estimates never feed the portion prior.** `portion_history()` reads only
   `scale`/`stated`/`package` rows. Relaxing that filter makes the system
   bootstrap its own guesses into fact.
8. **`/insight` refuses below 20 paired observations.** Do not lower
   `MIN_PAIRS` to make the feature "work" during development. Seed fake data in
   a test instead.
9. **`phase_label()` never claims measurement.** There is a test asserting it.

## Order of work

Do not skip ahead. Each stage is gated on the one before it.

1. **Make it run.** Docker compose up, load USDA, bootstrap a user, send one
   text message, get one confirmation card, press confirm, see it in `/today`.
   Expect breakage in: asyncpg type coercion on `numeric` columns, the
   `day_progress()` function signature, aiogram 3 handler registration order,
   and Markdown parse errors on food names with underscores.
2. **Make the photo path work.** One photo, one parse, one card.
3. **Collect the eval set.** Two weeks. Do not build anything else during it.
4. **Score the models.** Only now touch the routing table in `config.py`.
5. **Everything else** — pgvector, MCP server, dashboard — after 4.

Features added before stage 3 are features added without knowing whether the
core works.

## Commands

```bash
docker compose up -d db                     # Postgres 16, schema auto-applied
pytest -q                                    # 60 tests, no DB needed
python scripts/load_usda.py <fdc_csv_dir>    # ~2 min for Foundation+SR+FNDDS
python scripts/bootstrap.py --telegram-id N ...
python -m nutrai.bot                       # run locally against local db
docker compose logs -f bot
```

## Style

- Raw SQL via asyncpg. No ORM. The schema is the source of truth.
- Comments explain *why*, not *what*. Existing comments carry design reasoning
  and cost real thought; do not strip them as noise.
- No new dependencies without a reason stated in the commit message.
- Tests for anything where a silent wrong answer is possible. That is the bar,
  not coverage percentage.

## Things that will look like bugs and are not

- `AUTO_MATCH_SIMILARITY = 0.62` looks arbitrary. It is. Tune it against the
  eval set, not against intuition.
- `ESTIMATE_SIGMA_REL = 0.35` is deliberately optimistic. The comment says why.
- The repeat DSL rejects `250 g of chicken and rice` by returning `None`. That
  is correct: it is a food description, not a repeat command.
- `_label_match` is loose on purpose. `-onion` should match `red onion`.
