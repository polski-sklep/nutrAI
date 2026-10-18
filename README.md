# nutrai

A Telegram bot that keeps one person's food diary. Send a photo or a description of what you ate. It proposes the meal. You confirm. Postgres stores it.

The model is asked for identity, mass, state, and confidence. Calories and nutrients for ordinary food come from a SQL join against USDA FoodData Central, snapshotted onto the entry when you confirm, so a later USDA refresh does not rewrite history. A photographed supplement or product label is different: the model may transcribe numbers printed on the panel, and nothing is saved until you confirm them. A barcode is looked up on OpenFoodFacts, shown, and saved only if you accept it. Missing nutrients are left missing. They are never stored as zero.

Nothing is written to the log until you confirm, except an unmodified repeat of a dish you have already confirmed.

## Stack

Python 3.11 or newer (`pyproject.toml`; the image is Python 3.12). The bot is [aiogram](https://docs.aiogram.dev/) talking to the Telegram Bot API with long polling. Postgres 16 holds the diary and the USDA tables. SQL is asyncpg, raw, no ORM. Photos are downscaled with Pillow. Scheduled jobs use APScheduler. Model calls go to Anthropic. The small HTTP server and the OpenFoodFacts client use aiohttp, which aiogram already depends on.

Direct dependencies, from `pyproject.toml`: `aiogram`, `anthropic`, `asyncpg`, `apscheduler`, `pillow`. Dev extra: `pytest`, `pytest-asyncio`, `ruff`.

## Layout

```
nutrai/bot.py            Telegram handlers, confirm gate, command list
nutrai/config.py         model routing, prices, thresholds, environment
nutrai/db.py             SQL access
nutrai/http_api.py       GET /health and POST /activity
nutrai/off.py            OpenFoodFacts barcode and name lookup
nutrai/core/             repeat grammar, portions, fasting, insight,
                         nutrition, targets, rendering, suggestions,
                         supplements, the weekly plan
nutrai/llm/              tool schemas, parse, Anthropic client
nutrai/jobs/             morning note, reminders, Sunday cards, audit
sql/                     schema and later migrations
scripts/                 USDA load, bootstrap, pin, backup, deploy, golden set
tests/                   unit tests, plus integration tests that need Postgres
docs/ARCHITECTURE.md     the design write-up
docs/resolution/         golden cases for the food resolver
docs/knowledge/          food-vocabulary audit notes
```

`sql/` is mounted into Postgres as `docker-entrypoint-initdb.d`. Those files run on the first boot of a data volume and not again. A file added later has to be applied by hand to a database that already exists.

## Setup

You need Docker (Compose v2), Python 3.11+, and a FoodData Central CSV export. The loader's own note: the full CSV download is public domain (CC0 1.0), from <https://fdc.nal.usda.gov/download-datasets>. Foundation, SR Legacy, and FNDDS are what `scripts/load_usda.py` loads by default. Branded is opt-in.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# fill in TELEGRAM_TOKEN, ANTHROPIC_API_KEY, ALLOWED_TELEGRAM_IDS
# see Configuration. The process does not read .env by itself.

docker compose up -d db
python scripts/load_usda.py /path/to/FoodData_Central_csv_<date>
python scripts/bootstrap.py --help
```

`scripts/bootstrap.py` creates the Telegram user and seeds versioned nutrient targets from sex, age, height, weight, activity, and an optional deficit. Its own example:

```bash
python scripts/bootstrap.py --telegram-id 12345 --sex male --age 34 \
  --height-cm 183 --weight-kg 74.4 --activity 1.55 --deficit 500 \
  --protein-g 180
```

The bot service joins an external Docker network named `nutrai-net` (`docker-compose.yml`). Create it once before starting the bot, or Compose will refuse:

```bash
docker network create nutrai-net
docker compose up -d bot
```

Postgres is published on `127.0.0.1:5432` only. Adminer is off unless you ask for it:

```bash
docker compose --profile tools up -d adminer
```

The compose file's comment on the URL: open `http://127.0.0.1:8082/?pgsql=db&username=nutrai&db=nutrai`. The driver has to be in the query string. Log in with server `db`, user and database `nutrai`, and the Postgres password from `.env`.

After you have aliases, `scripts/pin_foods.py` lists them and can pin a match so a later parse does not silently re-point it:

```bash
python scripts/pin_foods.py --telegram-id 12345          # review
python scripts/pin_foods.py --telegram-id 12345 --pin    # interactive
```

## Configuration

Copy `.env.example` to `.env`. Names only. Docker Compose reads `.env` for the variables it interpolates. `nutrai/config.py` and `nutrai/http_api.py` read the process environment. They do not load `.env`. `python -m nutrai.bot` therefore sees a variable only if you exported it. The bot container receives only what `docker-compose.yml` puts in its `environment` block. Model ids and the numeric thresholds below stay at the defaults in `nutrai/config.py` inside that container unless you add them there.

| Name | Read by | What it is |
|---|---|---|
| `TELEGRAM_TOKEN` | `nutrai/config.py`, compose | Bot token from BotFather. |
| `ANTHROPIC_API_KEY` | `nutrai/config.py`, compose | Anthropic API key. |
| `ALLOWED_TELEGRAM_IDS` | `nutrai/config.py`, compose | Comma-separated Telegram user ids allowed to talk to the bot. |
| `POSTGRES_PASSWORD` | `docker-compose.yml` | Password for the `nutrai` role. Applied when the data volume is first created. Changing it in `.env` later does not change an existing volume. |
| `DATABASE_URL` | `nutrai/config.py`, scripts, tests | Postgres URL. Compose builds one for the bot container. The code default points at localhost. |
| `DEFAULT_TZ` | `nutrai/config.py`, compose | Timezone used when a user row is created. |
| `MODEL_PHOTO` | `nutrai/config.py` | Model for a photo parse. |
| `MODEL_PHOTO_ESCALATE` | `nutrai/config.py` | Model used once when a photo parse is below `CONFIDENCE_ESCALATE`. |
| `MODEL_TEXT` | `nutrai/config.py` | Model for a novel text parse. |
| `MODEL_CHEAP` | `nutrai/config.py` | Model for a repeat modifier the local grammar could not read. |
| `MODEL_PLAN` | `nutrai/config.py` | Model for `/report` and the Sunday review. |
| `IMAGE_LONG_EDGE` | `nutrai/config.py` | Long edge, in pixels, photos are scaled to before upload. |
| `IMAGE_JPEG_QUALITY` | `nutrai/config.py` | JPEG quality of that downscale. Not listed in `.env.example`. |
| `CONFIDENCE_FLOOR` | `nutrai/config.py` | Below this, a parse is shown as a question. |
| `CONFIDENCE_ESCALATE` | `nutrai/config.py` | Below this on a photo, escalate once to `MODEL_PHOTO_ESCALATE`. The figure in `.env.example` and the default in `nutrai/config.py` are not the same, and compose does not pass the variable through. |
| `ENERGY_TOLERANCE` | `nutrai/config.py` | Tolerance for the Atwater cross-check. Not in `.env.example`. |
| `AUTO_MATCH_SIMILARITY` | `nutrai/config.py` | Trigram similarity above which a food match is accepted without another model call, subject to the guards in the resolver. |
| `WEAK_MATCH_SIMILARITY` | `nutrai/config.py` | Below this, the best candidate is treated as a missing food. Not in `.env.example`. |
| `PHOTO_DIR` | `nutrai/config.py` | Directory meal photos are written to. Compose mounts a volume at the default path. Not in `.env.example`. |
| `NUTRAI_HTTP_TOKEN` | `nutrai/http_api.py`, compose | Shared secret for `POST /activity`, sent as `X-Nutrai-Token`. If unset, that server does not start. |
| `NUTRAI_HTTP_BIND` | `nutrai/http_api.py` | Address the activity server binds. Compose sets the container's bind itself and does not use this variable for the published host port. |
| `NUTRAI_HTTP_PORT` | `nutrai/http_api.py`, compose | Port of the activity server. |
| `NUTRAI_HTTP_PUBLISH` | `docker-compose.yml` only | Host interface the activity port is published on. Not read by Python. Not in `.env.example`. |
| `NUTRAI_BACKUP_DIR` | `scripts/backup.sh`, `scripts/restore.sh`, `scripts/deploy.sh`, `Makefile` | Where dumps are written and where deploy looks for one. |
| `NUTRAI_BACKUP_KEEP` | `scripts/backup.sh` | How many dumps to retain. |

Startup checks that every routed model id has an entry in `PRICES` in `nutrai/config.py`. An unpriced id refuses to start. That check does not ask Anthropic whether the id exists.

## Running locally

Against the compose database, from a shell where the variables above are exported:

```bash
python -m nutrai.bot
```

Or the container, which is what `Dockerfile` runs (`python -m nutrai.bot`):

```bash
docker compose up -d bot
docker compose logs -f bot
```

`docker compose restart bot` restarts the existing image. It does not rebuild it. `make reload` builds and then compares `scripts/pkgdigest.py` on the host with the copy inside the container.

Makefile targets that match those steps: `make db`, `make load FDC=...`, `make bootstrap ID=...`, `make pin ID=...`, `make run`, `make logs`, `make test`.

### Tests

```bash
pytest -q
pytest -q -m integration
```

`pytest -q` collects the whole suite. Integration tests (`tests/test_integration.py`, `tests/test_golden.py`, `tests/test_knowledge.py`, and the database cases in `tests/test_http_api.py`) skip when they cannot reach a Postgres with USDA loaded and a bootstrapped user. The integration file drives the real aiogram dispatcher against that database with the Anthropic client stubbed.

The resolver's golden set is separate from pytest:

```bash
python scripts/golden.py
python scripts/golden.py --stage candidates
```

It expects the database. A failure there is recorded against `docs/resolution/baseline.json`. The script's header says a drop below that floor is what fails.

### Backups

```bash
make backup
make backup-check
```

`scripts/backup.sh` dumps the whole database, including the USDA tables, checks the dump contains the tables that matter, and rotates. `make backup-check` runs `scripts/restore.sh --check` against the newest dump.

## Using it

`/start` prints the command list. Any other `/` command that has no handler gets that same list back. The list lives in `COMMANDS` in `nutrai/bot.py`, and Telegram's menu is pushed from it on startup.

Logging and looking:

| Command | |
|---|---|
| `/again` | Menu of things you have had before. `/a` and `/r` are the same handler. |
| `/repeat` | Repeat a morning, afternoon, or evening, each meal as its own confirm card. `/block` is the same. |
| `/today` | The day. `/today brief` is the shorter card. |
| `/next` | Dishes you have already logged, ranked by what today is still short of. `/suggest` is the same. No model. |
| `/last` | The most recent entry. |
| `/yesterday` | File food on an earlier day. `/back` and `/backdate` are the same. |
| `/undo` | Unlog the last entry from today. |
| `/why` | Where a nutrient on today came from. `/breakdown` is the same. |
| `/history` | The diary. `/log` and `/diary` are the same. |
| `/export` | Two CSVs: every confirmed meal, and daily nutrient totals. |
| `/incomplete` | Mark a day that should not feed analysis. `/partial` is the same. |
| `/week` | Seven days, day by day. |

A number from the `/again` menu is the zero-token repeat grammar in `nutrai/core/dsl.py`. A few of the forms it accepts:

```
3                 log item 3 as confirmed before
3 250             set the whole dish to 250 g
3 x1.5            scale it (also half, double, and a directed percentage)
3 -onion          drop a component
3 +50 rice        add one
3 rice 200        set one component
3 @14:00          set the time
3 @yesterday      file it on an earlier day
3 #lunch          set the meal slot
```

A sentence the grammar does not recognise falls through to `MODEL_CHEAP` with that dish's component list as context.

Other records:

| Command | |
|---|---|
| `/weight` | A weigh-in. `/w` is the same. |
| `/rate` | focus, energy, mood, hunger, sleep, or rpe, on a 1–10 keypad or as `/rate energy 6`. |
| `/smoke` | `/smoke 3` records three now. `/smoke` shows the pattern. `/smoke 0` records a clear day. `/cig` and `/cigarettes` are the same. |
| `/training` | Sessions posted into the diary, and the week's total. `/train` is the same. |
| `/fast` | Hours since the last meal, with a phase label. |
| `/window` | Eating window over the last 14 days, once there are at least three days with two or more meals. |
| `/supp` | Tick off today's supplements. `/supplements` is the same. `/stack` and `/schedule` edit the stack and are not in the menu. |
| `/prompts` | `/prompts off` stops the unprompted rating asks. Not in the menu. |

Looking back and setting up:

| Command | |
|---|---|
| `/report` | Four weeks, read by `MODEL_PLAN`. `/review` is the same. It refuses below the logged-day minimum in `nutrai/jobs/report.py`. |
| `/insight` | Fat-loss rate from the weight trend, and correlations. A correlation is refused below `MIN_PAIRS` in `nutrai/core/insight.py`. |
| `/food` | Foods you define yourself: a recipe, a panel photo, a pasted panel, or a barcode. `/foods` is the same. |
| `/profile` | Sex, age, height, weight, activity. `/me` is the same. |
| `/target` | Set one nutrient target. The old row is closed. It is not updated in place. |
| `/audit` | The match checks in `nutrai/jobs/audit.py`, over the last seven days. No model. |
| `/spend` | Model spend over the last 30 days, from the `llm_call` table. |

On a confirmation card, mass marks come from `nutrai/core/render.py`: ⚖ scale, ✎ stated, ▤ package, ↺ your own prior, ≈ estimate. A prior replaces a visual estimate only when `nutrai/core/estimate.py` has enough consistent past masses from scale, stated, or package rows, and the model's guess is not far from that median. Estimates are not fed back into that history.

`phase_label()` in `nutrai/core/fasting.py` is a population-average gloss of how long you have gone without a meal. The fat-loss number is the weight trend on `/insight`.

What arrives on its own, from `nutrai/jobs/notify.py` and `nutrai/jobs/report.py`: a morning note about half an hour before your wake time, supplement reminders, up to three rating prompts a day (`/prompts off` stops those), a Sunday week card at 18:00 UTC, and a Sunday model review at 16:00 UTC. The scheduler's timezone is UTC. `scripts/bootstrap.py` deletes notification rules. Threshold messages are not seeded.

`POST /activity` is how a separate workout bot appends a session. It requires `NUTRAI_HTTP_TOKEN`. `GET /health` does not. Kinds and intensities are the closed sets in `nutrai/http_api.py`. Re-posting the same session does not double it.

## Deployment

The bot runs as a container on a machine you control.

`Dockerfile` is `python:3.12-slim`, installs the runtime dependencies, and starts `python -m nutrai.bot`.

`scripts/deploy.sh` rsyncs this tree to `/opt/nutrai` on a host you pass as `user@host`. It requires a local `.env`, SSH, Docker on the host, at least 4000 MB free, and a dump from `make backup`. It stops the local bot first, because Telegram allows one `getUpdates` consumer per token. It brings Postgres up, and refuses to restore if that database already has rows in `log_entry`. It then builds the bot, checks the package digest, and installs a cron line that runs `scripts/backup.sh` at 03:00.

```bash
make vps-check HOST=user@host    # preflight, changes nothing
make vps HOST=user@host          # scripts/deploy.sh
```

`make deploy` is the other target: `git pull --ff-only`, rebuild the bot image, start it, and show the logs. The header of `scripts/deploy.sh` says that target assumes a git remote on the host, which is why the script copies files with rsync instead.

## Status

This is a working personal bot, not a multi-user service. `ALLOWED_TELEGRAM_IDS` is the lock. The Sunday crons are one schedule for one timezone.

`/improve` and `/targets` are not commands. `nutrai/core/plan.py` is reached from `/report` and the Sunday review, and the tests assert those two names are not advertised.

`meal_template` can be repeated by slug if a row exists. Nothing in the Python or SQL inserts one, so there is no way to create a template from the bot.

`CREATE EXTENSION vector` is commented out in `sql/001_schema.sql`.

`docs/ARCHITECTURE.md` still describes itself as a scaffold with 60 tests, and the `make test` comment says the same. The files under `tests/` have grown past either line.

`llm/client.py` prices an unknown model id as Sonnet. The import-time `PRICES` check is what stops that path from being reached by a typo in the routed ids.
