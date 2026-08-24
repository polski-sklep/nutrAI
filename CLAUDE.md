# Working on nutrai

Read this before changing anything. `docs/ARCHITECTURE.md` is the reasoning;
this file is the operating constraints.

## What this repo is

A working scaffold, not a sketch. ~2,700 lines, 109 passing tests, every module
compiles.

It **has** now run against a live Postgres: schema applied, USDA Foundation +
SR Legacy loaded (8,204 foods), a user bootstrapped, and a text message driven
end to end to a confirmed entry visible in `/today`. `tests/test_integration.py`
holds that path open — it drives the real aiogram dispatcher against the real
database with the Anthropic client stubbed, and skips itself when no database is
present so `pytest -q` stays DB-free.

It has since run live, end to end, against real Telegram and real Anthropic:
photo and text parse, resolve, confirm, snapshot, repeat, correct, undo,
backdate, supplements. Roughly fifteen real bugs were found that way and only
that way — every one produced a plausible number and raised nothing. The ones
worth remembering are in `jobs/audit.py`, which now looks for them daily.

Backups run nightly via `~/Library/LaunchAgents/com.nutrai.backup.plist` and are
restore-tested with `make backup-check`.

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

1. **Make it run.** ~~Docker compose up, load USDA, bootstrap a user, send one
   text message, get one confirmation card, press confirm, see it in
   `/today`.~~ Done, against a live Postgres. Of the four predicted breakages,
   the `numeric`/Decimal one was real (`render.day_card`); `day_progress()` and
   aiogram registration order were fine; the Markdown one was resolved by moving
   every outgoing message to HTML parse mode rather than by guessing at legacy
   Markdown's undocumented escaping. Re-verify any time with
   `pytest -q -m integration`.
2. **Make the photo path work.** One photo, one parse, one card. Structurally
   done and covered by tests (download, downscale, largest-PhotoSize, album
   buffering, single conditional escalation), all against a stubbed model. What
   remains is one real photo through a real API key.
3. **Collect the eval set.** Two weeks. Do not build anything else during it.
4. **Score the models.** Only now touch the routing table in `config.py`.
5. **Everything else** — pgvector, MCP server, dashboard — after 4.

Features added before stage 3 are features added without knowing whether the
core works.

## Commands

```bash
docker compose up -d db                     # Postgres 16, schema auto-applied
pytest -q                                    # 109 tests, no DB needed
pytest -q -m integration                     # the end-to-end path, needs the DB
python scripts/load_usda.py <fdc_csv_dir>    # ~2 min for Foundation+SR+FNDDS
python scripts/bootstrap.py --telegram-id N ...
python -m nutrai.bot                       # run locally against local db
docker compose logs -f bot
```

The db service publishes `127.0.0.1:5432` so the loader, the bootstrap script
and a locally-run bot can reach it. Loopback only — never widen that binding.

`sql/*.sql` is applied by the Postgres entrypoint **on first boot only**. A new
file (like `004_coverage.sql`) has to be applied by hand to an existing volume:

```bash
docker compose exec -T db psql -U nutrai -d nutrai -f - < sql/004_coverage.sql
```

## Looking at the data

```bash
docker compose exec db psql -U nutrai -d nutrai     # \dt, \d log_entry, \q
docker compose --profile tools up -d adminer        # then the URL below
```

Open Adminer at **`http://127.0.0.1:8082/?pgsql=db&username=nutrai&db=nutrai`**,
not at the bare host and port. The driver has to be in the URL: adminer 5.5.1
ignores `ADMINER_DEFAULT_DRIVER`, so the login form defaults to MySQL and the
attempt fails with "Connection refused" — which looks exactly like a wrong
password and is not one.

It is behind the `tools` profile so an ordinary `docker compose up` does
not start it, and bound to loopback like everything else here: the database
holds a food diary, and a browser client for it has no business listening on a
laptop's wifi interface. Log in with server `db`, user and database `nutrai`,
password from `.env`. `docker compose stop adminer` when done.

The tables worth knowing: `log_entry` / `log_component` / `log_nutrient` are
the diary, and `log_nutrient` is the immutable snapshot everything reads.
`food` holds USDA plus your own rows at negative ids. `target` is versioned —
`effective_to IS NULL` is the live one. `food_nutrient` is a million rows of
USDA reference and is never written to outside the loader.

The test suite writes against this same database — there is no seam short of
one for the HTTP endpoint or the SQL views — and `tests/conftest.py` sweeps up
after itself. It did not for months, and `target` reached 11,330 superseded
rows for a user that does not exist, which is not a bug in anything and makes
every honest look at the database misleading.

## Backups

```bash
make backup          # dump, verify, rotate (keeps 30)
make backup-check    # rehearse a restore into a scratch db, then drop it
```

Full dump including the USDA tables. They are reproducible from a public
download, but at ~8 MB compressed the saving is not worth a backup that needs a
3 GB re-download and a working loader before it restores.

The dump is written to a temporary name and moved into place only after it is
verified to contain every table that matters, so an interrupted run cannot leave
a plausible-looking empty file. Run `make backup-check` occasionally: an
untested backup is a belief, and the moment you find out is the worst one.

Schedule it daily. On macOS, `launchd`:

```bash
cat > ~/Library/LaunchAgents/com.nutrai.backup.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.nutrai.backup</string>
  <key>ProgramArguments</key>
  <array><string>/Users/Jacob/Projects/nutrAI/scripts/backup.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardErrorPath</key><string>/tmp/nutrai-backup.log</string>
</dict></plist>
EOF
launchctl load ~/Library/LaunchAgents/com.nutrai.backup.plist
```

On the VPS, a cron line does the same. Either way the backups sit on the same
disk as the database, which protects you from a bad migration and not from a
dead disk — copy them somewhere else too.

## Known gaps

- **`/improve` and `/targets` are deliberately unwired.** `core/plan.py` is
  fully written and unreachable from the bot; wiring it is stage 5 by the order
  above. They are no longer advertised in `/start` or the README, and typing
  either now returns the list of commands that do exist. `/week` was never
  implemented at all. `tests/test_commands.py` fails if anything is advertised
  without a handler, so this cannot drift back.
- **Meal templates are unreachable.** `meal_template`, `template_by_slug` and
  `_log_template` all exist; nothing can create one. No longer advertised in the
  README. Least harmful of the dead paths — it fails by doing nothing.
- **Model ids were verified** against `GET /v1/models` on 15 Aug 2026:
  `claude-sonnet-5`, `claude-opus-5`, `claude-haiku-4-5-20251001` all resolve.
  Re-check after any routing change with:

  ```bash
  curl -s "https://api.anthropic.com/v1/models?limit=100" \
    -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" \
    | grep -o '"id":"[^"]*"'
  ```

  `config.py` checks at import that every routed model has a `PRICES` entry and
  refuses to start otherwise — so pointing a `MODEL_*` env var at a model you
  have not priced is a startup failure, by design. That check validates the
  pricing table, not the id: only the call above tells you the id is real.

## Supplements and label-derived nutrients

`sql/005_supplements.sql`. Supplements are their own tables rather than food
rows: taken by count not mass, and their authority is a printed label rather
than a USDA assay.

**The contract in ARCHITECTURE.md §1 is amended, not broken.** The model may
*transcribe* a nutrient value from a photographed panel. It may never *estimate*
one. The difference is that a transcription is checkable at the moment it is
made — against the packet in your hand, at the confirm gate — and an estimate is
checkable against nothing. Enforcement is threefold: the tool is given the exact
list of nutrient ids it may use, so an unlisted line is omitted rather than
approximated onto a neighbour; units are converted in Python and refused where
ambiguous (vitamin D IU is exact, vitamin A IU is not); and nothing is saved
until a human confirms the panel. `supplement.source` records which route the
numbers came in by, and must never say `model_estimate`.

`day_progress()` returns `amount`, `amount_food` and `amount_supplement`.
Supplements count toward targets — that is what they are for — but the split
must survive to the screen. A micronutrient met by a capsule is different
information from one met by food, and blending them lets `/improve` recommend
fixing a deficiency that is already treated.

Photo retention is *not* required for labels, and an earlier claim in this file
that it was has been removed. §12's argument is about meal photos, where
portion estimation is uncertain and re-scoring against a better parser later is
the point. A label is exact and finite: once transcribed and confirmed the
numbers are the record, and if one is wrong the packet is still in the cupboard.

## Decided, not yet done

Agreed changes with the reasoning already settled. Do them when next in the
area; do not re-litigate them.

- ~~**Remembered products.**~~ Built 17 Aug 2026. `/food` takes a photographed
  panel, a barcode (OpenFoodFacts) or an ingredient list, and stores the result
  in `food` with `data_type = 'user_product'` and a negative `fdc_id`, so
  `log_component.fdc_id`, `profiles_for`, coverage, `portion_history`, `/why`
  and the audit all work unchanged. `precedence` was rebuilt to rank
  `user_product` at 0, above Foundation. The "ask every time" decision was
  overtaken: a saved product wins on similarity and precedence, and the confirm
  card names the row it matched, which turned out to be the better answer to
  the same worry.

- **NOVA processing score.** Scoped 16 Aug 2026, to be built after the eval
  fortnight ends (on or after 30 Aug 2026). Decisions below are settled; do not
  re-litigate them.

  **Classification source: a model, lazily, cached per `fdc_id` forever.** The
  authoritative mapping is Steele et al.'s FNDDS-to-NOVA work, and NCI
  distributes it by proposal only — a form, an analysis plan, a steering
  committee, and unstated redistribution terms. Not usable here. A heuristic on
  `data_type` was checked and rejected: SR Legacy holds both "Butter, salted"
  (group 2) and "Cheeseburger, fast food" (group 4), so the column says which
  USDA dataset a row came from and almost nothing about processing.

  A NOVA group is a *classification*, not a nutrient value, so ARCHITECTURE.md
  §1 is not breached — same amendment as the supplement panel. But it is weaker
  than that one and the code must say so: a transcribed label is checkable
  against the packet in your hand, and "is this group 4" is a judgement
  checkable against nothing. It is therefore labelled a judgement wherever it
  is shown, and `/nova <food> <group>` must exist to correct it.

  Volume makes this nearly free. Twelve distinct foods had ever been logged
  when this was scoped, against 13,636 loaded. Classify at confirm time on
  first sight of an `fdc_id` and never again. Do not backfill the table.

  **The group is snapshotted onto `log_component`, not read from `food`.** This
  is the load-bearing decision. Left on `food` alone, correcting one
  classification silently rewrites what every past day scored — invariant 2's
  exact failure, arriving through a side door. `food` carries the current
  classification; the component carries what it was when you ate it, the same
  treatment `grams_source` has.

  **It does not go in `target`/`nutrient`.** A percentage is not a nutrient and
  a pseudo-nutrient id would put a non-USDA row into a namespace that
  `food_nutrient`, `day_progress`, `profiles_for`, coverage and the audit all
  join against. Separate view, `v_day_processing`.

  **Coverage is shown and never zero-filled**, as for micronutrients. A
  percentage computed over the classified third of a day and presented as the
  day's figure is the phantom-deficiency bug wearing a different hat.

  **It gets a ceiling: 20% of daily energy from group 4.** Requested
  explicitly, over a recorded objection that no defensible individual threshold
  exists — so be honest about what the number is. It is a convention, not a
  finding. For scale, ultra-processed food is about 57% of total energy for US
  adults (NHANES 2017-18), so 20% is demanding rather than typical. Set it as
  an ordinary editable target row so `/target` can move it, and never present
  it as evidence-based.

  The more defensible use is as an `/insight` covariate — does processing
  predict sleep or focus independently of energy? The permutation machinery
  already handles that correctly, and it asks a question rather than issuing a
  verdict.

  Building it during the fortnight was declined for the reason `/next` was
  overridden on: a visible processing score changes what you eat.

- **`llm/client.py:price()` must return `None`, not a Sonnet-priced guess.**
  Not raising is right — aborting after the API call has been made loses the
  parse and the money both. But a silent fallback in the cost layer is the same
  failure this design rejects everywhere else: nulls are not zeros, and a cost
  you cannot compute is *unknown*, not $0.006. So: return `None`, log a warning,
  store `llm_call.cost_usd` as NULL, and have `/spend` print "3 calls, cost
  unknown" rather than folding them into a total that looks complete.

  `cost_usd` is currently `NOT NULL DEFAULT 0`, which is the schema encoding the
  same mistake — dropping the constraint is part of the change, and `spend_report`
  has to separate a NULL from a zero rather than `sum()`-ing over both.

  After the import-time `PRICES` check this path is nearly unreachable, which is
  exactly the argument for making it honest rather than plausible when it does
  fire: the once-a-year case that reports a confident wrong number is worse than
  the one that admits it does not know.

## Training input

The training bot POSTs to `/activity`. An `rpe` in that payload is stored on
`activity.rpe` **and** written to `observation` as kind `rpe`, exactly as a
hand-typed `/rate` would be. `/insight` correlates over `observation`, so an
effort figure that only reached the activity row would be visible in
`/training` and invisible to every analysis.

Two rules hold that honest:

- **Only when `created` is true.** A re-posted session is the same effort
  asserted twice, and a second observation would firm up a correlation on its
  own echo — the failure `sql/008_repeat_provenance.sql` fixed for portions.
  Which makes idempotency load-bearing: `external_id` is the client's own id
  for the session and dedup keys on it where present. The older heuristic —
  (user, date, kind, minutes, intensity) — still covers clients that send no
  id, and is a shape standing in for an identity: sessions of similar length
  on one day collapse into one.
- **`hours_fasted` is withheld when the time is unknown.** The payload may
  carry `at` (an ISO instant); without it, a same-day post uses now and a
  backdated one is dated noon on its own day with no fasting figure. The
  fasting state at an invented hour is not a weak covariate, it is a fabricated
  one, and `db.observations()` filters `hours_fasted IS NOT NULL` so such a row
  is recorded and never correlated.

## Code that exists and cannot run

A cleanup sweep found eleven functions with tests and no production caller. The
ones that were provably unreachable, or a second implementation of something
production does in SQL, are gone: `mass_sanity` (the parse tool has no field
for a stated plate weight, so there was never a total to disagree with),
`propagate`, `fmt_pm`, `nutrient_uncertainty`, `day_confidence` (the day card's
`±` comes from `db.day_energy_sigma`, in SQL) and `fasting.eating_window` (the
`/window` screen reads `v_eating_window`).

Deleting them cost the only tests those guarantees had, because the tests were
written against the twin rather than the original. `test_day_energy_sigma_
combines_in_quadrature_not_linearly` restores the §4.5 promise against the
query that actually ships. If you remove a parallel implementation, check what
its tests were protecting before deleting them with it.

Four thin `db` accessors survive unused — `supplements_due`, `activity_on`,
`clear_measured_tdee`, `delete_user_food`. Each is one line from a command that
is plausibly wanted, and `delete_user_food` belongs to the retirement design
above.

## Unprompted messages

Threshold notifications are **deliberately off** and no longer seeded by
`bootstrap.py`. "You are at 60% of protein" at four in the afternoon is
arithmetic the user can do, arriving unasked, on a day that is not over. A
tracker that interrupts is one you mute, and the muting takes the useful
messages with it.

The 19:00 day card and the daily match check went the same way, for the same
reason. The match check is worth a second note: it was a wall of database
diagnostics arriving in the evening, about *matching* rather than about eating,
and mostly concerning foods logged days earlier — a class of message with no
moment it needs to be read. `/audit` runs exactly the same checks over the last
seven days, when somebody wants to know.

What still arrives unbidden earns it by being short and timely: the morning
note (07:30), supplement reminders at their scheduled slots, and the Sunday
report. Everything else is pull — `/today`, `/week`, `/next`, `/last`,
`/audit`. If you are about to schedule something, that list is the bar.

## Days that do not count

`/incomplete` marks a day the user knows they did not log properly. Absence of
a `day_quality` row means complete, deliberately: a flag that must be set on
every ordinary day is one people stop setting, which turns "not marked" from a
default into a silent unknown.

The exclusion has to reach **every** analysis or it is worse than none — a day
dropped from the weight trend but still feeding `/insight` is a flag that is
half true. Currently applied in `db.daily_energy` (which feeds measured TDEE,
which feeds the energy target) and `db.observations`. Anything new that draws a
conclusion across days must filter on it too.

The entries themselves stay visible in `/today` and `/history`. What stops is
inference.

## Outgoing message format

Telegram **HTML**, not Markdown. Legacy Markdown has no defined escape syntax,
so a food called `chicken_breast` either mangles the message or gets it rejected
with HTTP 400, and a rejected confirmation card leaves the entry in `pending`
while the user sees nothing. HTML needs three characters escaped and
`html.escape` does it correctly.

Rules when adding a message:

- Escape every piece of dynamic text with `render._esc` (or `html.escape`).
- Column-aligned output goes in **one** `<pre>` block. Per-line `<code>` spans
  do not preserve alignment — Telegram renders adjacent spans proportionally
  and the columns drift.
- No nested tags inside `<pre>`; Telegram rejects them. Section headings inside
  a table are plain text.
- Pad *before* escaping. `&` becomes `&amp;` — five source characters that
  render as one — so padding an escaped string aligns the source, not the screen.
- `bot.resend_unformatted` still catches a rejection and resends unformatted.
  It should now be unreachable; a "markup rejected by Telegram" line in the logs
  means something above was skipped.

## Style

- Raw SQL via asyncpg. No ORM. The schema is the source of truth.
- Comments explain *why*, not *what*. Existing comments carry design reasoning
  and cost real thought; do not strip them as noise.
- No new dependencies without a reason stated in the commit message.
- Tests for anything where a silent wrong answer is possible. That is the bar,
  not coverage percentage.

## Retiring a user food

A user food whose panel turns out to be wrong cannot be deleted once anything
has been logged against it: `log_component` references it and `log_nutrient`
holds the snapshot that entry was scored on. `food.retired_at` takes it out of
`user_foods`, out of `search_foods` and out of `resolve_alias`, so it stays
readable as history and stops being offered or matched.

The first version of this renamed the row to "Blondie (retired: energy figure
was wrong)". Do not do that again: a status encoded in a display string
truncates in the card, sorts under B, and cannot be filtered on.

## Photographs of one meal

Every photo of an album goes to the model in **one call**, with a line saying
they are views of one meal. They were parsed separately and the item lists
concatenated, which counted anything visible in two photographs twice: a
330 ml bottle photographed from both sides became "Coffee and orange juice
drink 330 g" plus "Coffee & orange juice beverage 330 g", 660 g in total, and
61 g of sugar — more than a day's ceiling from one drink.

Nothing downstream can catch it. Both items are plausible, both masses are
plausible, and the energy cross-check passes because the doubled food is
internally consistent. Only the model, seeing the photographs together, can
tell that it is one bottle.

`tests/test_integration.py::test_album_becomes_one_meal_not_four` asserts one
`record_meal` call per album, not merely one confirmation card. The card count
was the original guarantee and it stayed true while the contents doubled.

## Two USDA ids, one measurement

`nutrient.canonical_id` folds ids that report the same thing. Today it holds
one row: **1063 "Sugars, Total" → 2000 "Total Sugars"**. FNDDS reports sugar
under 1063, SR Legacy under 2000, Foundation under either, and with the target
on 2000 every FNDDS food's sugar went uncounted — a day totalling 53.8 g
displayed 11 g at 19% of its ceiling, and nothing raised anything.

The mapping lives in `v_nutrient_canonical` and is applied in exactly three
places: `v_day_nutrient`, `v_day_supplement_nutrient` and `db._profiles_con`.
The last is the write path — without it a new entry is still *stored* split and
the confirm card, which is read before anything is stored, stays wrong.

`food_nutrient` and `log_nutrient` are never rewritten. The first is a faithful
copy of a public dataset and the next loader run would undo any edit; the
second is an immutable snapshot (invariant 2). Only the aggregate above them
changes, which is why the fix reaches history at all.

**Energy is not in this table and must not be.** `canonical_id` means "the same
measurement, add them up". The Atwater ids (1008 / 2047 / 2048) mean
"alternative estimates of the same thing, use whichever exists" — summing them
would treble a Foundation row. `core.nutrition.normalise_energy` and the one
hard-coded branch in `day_nutrient_coverage` handle that. Two rules because
there are two relationships.

`tests/test_integration.py::test_no_targeted_nutrient_is_silently_split` fails
if a future load introduces another split. It detects them by *complementary
coverage* — foods carry one id or the other and almost never both — because
genuinely different nutrients are measured together and overlap almost
completely. Name similarity alone finds nothing but fatty acids. The test
carries an explicit exceptions list: 1119 Zeaxanthin and 1123 Lutein +
zeaxanthin look complementary and must not be folded, because 1123 is a sum
that already contains 1119.

## Things that will look like bugs and are not

- **Fruit ripeness is not modelled, and asked-and-declined on 20 Aug 2026.**
  USDA carries `Bananas, overripe, raw` (85 kcal) and `Bananas, ripe and
  slightly ripe, raw` (97 kcal), and typing "overripe banana" already resolves
  to the right one — so the case where the data exists is already handled by
  the words. It is not worth machinery: the 14% gap is almost entirely water,
  the sugars figure is identical at 15.8 g across all three banana rows, and so
  the starch-to-sugar conversion anyone actually means by "ripeness" is not in
  the dataset at all. For every fruit other than banana there is no ripeness
  row, and supplying one would mean a model estimating a nutrient value —
  invariant 1.

- **The 300 mg cholesterol ceiling is obsolete and is staying.** Reviewed on
  16 Aug 2026 and deliberately kept. The figure was dropped from the US
  Dietary Guidelines in the 2015-2020 edition, and the AHA dropped its numeric
  cap too, so `1253: (None, 300)` in `core/profile.py` has no current guidance
  behind it — the comment beside it already says "no RDA". It was raised with
  the user, who chose to leave it. Do not quietly remove or raise it. It is an
  ordinary standing target he can move with `/target cholesterol max <n>`.

- `AUTO_MATCH_SIMILARITY = 0.62` looks arbitrary. It is. Tune it against the
  eval set, not against intuition.
- `ESTIMATE_SIGMA_REL = 0.35` is deliberately optimistic. The comment says why.
- The repeat DSL rejects `250 g of chicken and rice` by returning `None`. That
  is correct: it is a food description, not a repeat command.
- `_label_match` is loose on purpose. `-onion` should match `red onion`.
- **`ruff check` reports around thirty findings and that is the resting state.**
  Nearly all are `UP017` (`dt.timezone.utc` rather than `datetime.UTC`) and a
  couple of deliberate broad `except` clauses. The datetime spelling is a
  consistency choice applied across every module, not an oversight. Do not run
  `ruff --fix` across the tree to make the number go down; it is churn that
  makes the next diff unreadable and fixes nothing.
- **`claude-sonnet-5` and `claude-opus-5` having no date suffix does not make
  them aliases.** From the 4.6 generation onward a dateless id *is* the pinned
  snapshot — there is no evergreen pointer behind it that can move under you
  mid-eval. Only pre-4.6 models carry a dateless alias distinct from their dated
  id, which is why `MODEL_CHEAP` is pinned to `claude-haiku-4-5-20251001` while
  the other two are correct as they stand. The comment above them in
  `config.py` is accurate. Do not "fix" this.
