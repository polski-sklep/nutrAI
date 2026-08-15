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

It has **never run against a live Anthropic API or a live Telegram**. Those need
your keys. Everything below the model call is exercised.

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
- **No live model call has ever been made.** The ids in `config.py` are
  unverified against `GET /v1/models`; nobody has had a key to hand. Verify with:

  ```bash
  curl -s "https://api.anthropic.com/v1/models?limit=100" \
    -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" \
    | grep -o '"id":"[^"]*"'
  ```

  `config.py` checks at import that every routed model has a `PRICES` entry and
  refuses to start otherwise — so pointing a `MODEL_*` env var at a model you
  have not priced is a startup failure, by design. That check validates the
  pricing table, not the id: only the call above tells you the id is real.

## Decided, not yet done

Agreed changes with the reasoning already settled. Do them when next in the
area; do not re-litigate them.

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

## Things that will look like bugs and are not

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
