# Assessment 4 — circular dependencies and import layering

Scope: every `.py` under `nutrai/` (25 modules, 4 of them empty `__init__.py`).
Date: 22 Aug 2026. Worktree: `.claude/worktrees/agent-abb9cbda7f63fd399`.

## Headline

**There are no import cycles.** Not at module level, not through function-local
imports, not through `TYPE_CHECKING` blocks. All three graph variants come back
empty.

The corollary matters more than the finding: **not one of the 22 function-local
internal imports in this tree is a cycle-breaker.** Every one of them has no
reverse edge — the module it defers importing does not import it back, at any
depth. They are lazy imports (or import-next-to-use style), not load-bearing
structure. The brief anticipated deliberate cycle-breakers; the evidence says
there are none to identify, and the honest answer is that the layering is
already acyclic without them.

One genuine layering violation exists (`core/plan.py` importing upward into
`db` and `llm/`), and it is deliberate-by-omission rather than accidental. See
MEDIUM below for why moving it is not obviously an improvement.

## Method

`ast`-based scan, written to this worktree's scratchpad rather than into the
repo. It walks every module, resolves relative imports (`from ..config import X`,
`from . import db`) against the package tree, and classifies each internal edge
three ways:

- `module` — executed at import time, the only kind that can deadlock an import
- `local` — inside a `def`/`async def`/class body, executed on first call
- `type_checking` — inside `if TYPE_CHECKING:`, never executed

Cycles are then searched over three graphs: module-only (real at import time),
module+local (reachable at runtime), and all edges (what a type checker sees).

`madge` does not apply (JS/TS). `pydeps`/`import-linter` were not installed:
the AST scan is exact here and a scratch venv adds nothing. Cross-checks run:

- `grep -rnE "^[[:space:]]*(from|import)[[:space:]]+\."` → 52 relative import
  statements, consistent with the 76 expanded edges (one `from .core import a, b, c`
  is three edges).
- `grep -rn "TYPE_CHECKING\|importlib\|__import__"` over `nutrai/` → **no hits**.
  There is no dynamic import and no deferred-typing block anywhere, so the AST
  graph is complete rather than a lower bound.

## The graph

Four `__init__.py` files (`nutrai/`, `core/`, `jobs/`, `llm/`) are **0 bytes**.
Edges pointing at those package nodes (`from . import db` also touches `nutrai`)
are inert — importing them executes nothing — and are dropped below.

Layers as the brief defines them, lowest first:

```
L0  config                      no internal imports
L0  off                         no internal imports (OpenFoodFacts HTTP client)
L1  core/                       pure logic
L2  db                          data layer
L3  llm/                        model layer
L4  bot, http_api, jobs/        top
```

Module-level edges (`->`), function-local edges (`~~>`):

```
L4  bot ──────────► db, off, config
        ──────────► core.{dsl,estimate,fasting,insight,nutrition,plan,profile,render,suggest}
        ──────────► jobs.report, llm.parse
        ~~~~~~~~~~► core.supplements      bot.py:4028  _handle_supplement_label
        ~~~~~~~~~~► http_api              bot.py:4300  run
        ~~~~~~~~~~► jobs.audit            bot.py:3081  audit_cmd
        ~~~~~~~~~~► jobs.notify           bot.py:4236  _check_thresholds
        ~~~~~~~~~~► jobs.notify           bot.py:4301  run

L4  http_api ─────► db

L4  jobs.notify ──► db, core.render
        ~~~~~~~~~~► jobs.audit            jobs/notify.py:310  start_scheduler
        ~~~~~~~~~~► jobs.report           jobs/notify.py:321  start_scheduler

L4  jobs.audit ───► db, config, core.nutrition, llm.parse
        ~~~~~~~~~~► core.render           jobs/audit.py:271   audit_and_report

L4  jobs.report ──► db, core.plan, core.render

L3  llm.parse ────► db, config, core.estimate, core.nutrition, llm.client, llm.schemas
L3  llm.client ───► config
L3  llm.schemas ──► (nothing)

L2  db ───────────► config, core.nutrition

L1  core.plan ────► db ⚠, llm.client ⚠, llm.schemas ⚠, config
L1  core.render ~~► config  ×7   (lines 94, 240, 452, 1258, 1943, 2149, 2317)
                ~~► core.insight   render.py:1458  weight_card
                ~~► core.profile   render.py:1521  profile_card
                ~~► core.profile   render.py:1661  profile_recalc_card
L1  core.nutrition ► config
L1  core.profile ─► config
L1  core.suggest ─► config
L1  core.dsl, core.estimate, core.fasting, core.insight, core.supplements
                    ► (nothing — pure leaves)

L0  config, off ──► (nothing)
```

Sinks: `config`, `off`, `llm.schemas`, and five `core/` leaves. Sources
(nothing imports them): `bot`, `http_api`, `jobs.notify`, `jobs.audit`.

## Cycles

```
=== CYCLES (module-level only: real at import time) ===  none
=== CYCLES (module + function-local: runtime)        ===  none
=== CYCLES (all edges incl TYPE_CHECKING)            ===  none
```

Nothing to untangle. Verified again after the changes below.

## Layering violations

### V1 — `core/plan.py` imports upward into `db` and `llm/` (real, import-time)

```
nutrai/core/plan.py:14   from .. import db              L1 -> L2
nutrai/core/plan.py:16   from ..llm.client import cached, call_tool    L1 -> L3
nutrai/core/plan.py:17   from ..llm.schemas import PLAN_SYSTEM, PLAN_TOOL  L1 -> L3
```

The only true upward edges in the tree, and they are module-level, so they are
real at import time. `core/plan.py` is not pure logic: it runs SQL, builds an
evidence pack, calls Opus, and writes versioned `target` rows. It is an
application-layer module filed under `core/`. It closes no cycle only because
neither `db` nor `llm/` has any reason to reach back for it.

Blast radius of its position: `jobs/report.py:21` and `bot.py:25` both import
it, so `import nutrai.core.render` is cheap but `import nutrai.core.plan` drags
in `asyncpg` and `anthropic`.

### V2 — intra-layer edges (legal, listed for completeness)

`bot -> http_api`, `bot -> jobs.{audit,notify,report}`,
`jobs.notify -> jobs.{audit,report}`, `llm.parse -> llm.{client,schemas}`,
`core.render -> core.{insight,profile}`. All within a layer, all one-directional.
None of them is a violation under the stated model.

### Not a violation, but worth knowing

`nutrai/jobs/audit.py:30` — `from ..llm.parse import INVERTING_TERMS`. Downward
(L4 → L3) and therefore legal, but `INVERTING_TERMS` is a nine-element tuple of
strings (`nutrai/llm/parse.py:336`) and importing it pulls `PIL` and `anthropic`
into a module that is otherwise SQL and arithmetic. It is a shared *constant*
sitting in the model layer. See MEDIUM-2.

## Function-local imports: full inventory and verdict

Method for the verdict: an edge `A ~~> B` is a cycle-breaker only if `B` reaches
`A` by some path. None does.

| site | target | verdict |
|---|---|---|
| `bot.py:3557` (was) | `core.nutrition` | **redundant** — duplicated `bot.py:27`; **removed** |
| `llm/parse.py:645` (was) | `config` | **dead** — imported then `del`-ed, never used; **removed** |
| `bot.py:4028` `_handle_supplement_label` | `core.supplements` | not a cycle-breaker; lazy |
| `bot.py:4300` `run` | `http_api` | not a cycle-breaker; defers `aiohttp` — but `bot.py:13` already imports `aiogram`, which requires `aiohttp`, so it defers nothing |
| `bot.py:3081` `audit_cmd` | `jobs.audit` | not a cycle-breaker; every transitive dep of `jobs.audit` is already a module-level dep of `bot` |
| `bot.py:4236`, `bot.py:4301` | `jobs.notify` | not a cycle-breaker; defers `apscheduler` — but `bot.py:32` imports `jobs.report`, which imports `apscheduler.triggers.cron` at `jobs/report.py:18`, so it defers nothing |
| `jobs/notify.py:310`, `:321` `start_scheduler` | `jobs.audit`, `jobs.report` | not cycle-breakers; import-next-to-`add_job` style. The comment above `:321` justifies the *separate module* (invariant 4), not the local placement |
| `jobs/audit.py:271` `audit_and_report` | `core.render` | not a cycle-breaker; lazy |
| `core/render.py` ×7 | `config` | not cycle-breakers. `config` is a leaf; a module-level `core.render -> config` edge can never close a cycle |
| `core/render.py:1458` | `core.insight` | not a cycle-breaker (`core.insight` imports nothing) |
| `core/render.py:1521`, `:1661` | `core.profile` | not cycle-breakers (`core.profile` imports only `config`) |

`core/render.py` also imports `zoneinfo` locally at lines 546, 716, 921, 1456,
2049. Stdlib, no bearing on the internal graph; `bot.py:7` imports it at module
level anyway.

## Recommendations

### HIGH confidence — implemented in this commit

**H1. `nutrai/bot.py:3557` — delete the redundant local re-import of
`ResolvedComponent`.** The name was already bound at `bot.py:27-31`; the local
statement re-imported the same symbol under the alias `_RC` inside `_try_fix`.
Provably behaviour-preserving. Removes a spurious `bot ~~> core.nutrition` edge
that made the graph look like it had a deferred dependency where it had none.

**H2. `nutrai/llm/parse.py:645` — delete the dead
`from ..config import CORE_NUTRIENTS` and the `del CORE_NUTRIENTS` at `:664`.**
The name is imported, never read, and explicitly deleted five lines later. It
has been dead since the line was written (commit `a03408d`, the supplements
commit — the import and the `del` arrived in the same diff). This removes a
second phantom edge, `llm.parse ~~> config`.

Note for the record: the first attempt at H2 hoisted the import to the
module-level `from ..config import (...)` block, which looked obviously safe and
was not — `del CORE_NUTRIENTS` then hit a module-level global and raised
`UnboundLocalError`, failing
`tests/test_supplements.py::test_the_nutrient_menu_disambiguates_vitamin_k_forms`.
Deleting both lines is the correct fix and is what shipped. This is the reason
the MEDIUM items below are not being done on the same "obviously safe"
reasoning.

### MEDIUM confidence — recommended, not done

**M1. Move `core/plan.py` to `nutrai/plan.py` (V1).** It is not core logic: it
holds SQL, a model call and a write path, which is the definition of the
application layer here. Moving it would leave `core/` genuinely pure and make
`import-linter`-style enforcement possible.

Against doing it now: it is a rename touching `bot.py:25`, `jobs/report.py:21`,
and any test that imports it; CLAUDE.md lists `core/plan.py` as deliberately
unwired code awaiting stage 5, and the module is due to be *wired*, not moved,
when that stage arrives. Moving a file that is about to be edited by someone
else's plan is churn with a merge conflict attached. Do it as part of wiring
`/improve`, not before.

**M2. Move `INVERTING_TERMS` down out of `llm/parse.py`.** A tuple of nine
strings is data, not model-layer machinery, and `jobs/audit.py` reaching into
`llm.parse` for it is what forces `PIL` and `anthropic` into the audit job's
import. The lower home would be `core/` — `core/nutrition.py` already holds
`ENERGY_FALLBACKS`, which `audit.py:29` imports for the same reason. This is
exactly the brief's preferred fix shape (move a shared definition down rather
than add indirection).

Against doing it now: the twenty-nine lines of comment above the constant
(`llm/parse.py:325-335`) are the design record for the "meatless chicken"
incident and are attached to `inverts_meaning()`, which lives in `parse.py` and
is the constant's real consumer. Splitting the constant from the function that
gives it meaning trades one kind of legibility for another. The import is legal
and closes no cycle, so the only real gain is a lighter `jobs.audit` import,
which nothing currently measures as a problem.

**M3. Hoist `core/render.py`'s seven local `from ..config import ...` to one
module-level import.** `config` is a graph leaf; the edge can never close a
cycle, so there is no structural reason for the deferral. Seven statements
collapse to one, and the defensive alias at `render.py:1943`
(`PROTEIN as _PROTEIN`) becomes unnecessary — checked, there is no module-level
name in `render.py` that would shadow `CARB`, `ENERGY_KCAL`, `FAT`, `FIBER`,
`PROTEIN`, `SODIUM`, `SAT_FAT` or `SUGAR`.

Against doing it now: it is a seven-site edit in a 2,400-line file that changes
no behaviour, which is the same churn CLAUDE.md refuses for `ruff --fix`
("churn that makes the next diff unreadable and fixes nothing"). And H2 above is
a live demonstration that "moving an import in this file is obviously safe" is a
claim this codebase has already falsified once today. Worth doing when
`render.py` is next opened for a real reason.

### LOW confidence — noted, no action recommended

**L1. Hoist the remaining lazy imports in `bot.py` and `jobs/notify.py`.** They
buy nothing (the deferred packages are already pulled in at module level via
other paths, as tabulated above) but they cost nothing either, and two of them
sit beside comments that would need rewording. Leave them.

**L2. Adopt `import-linter` with a contract encoding the L0–L4 layering.** It
would pin the current acyclic state and catch V1's recurrence. It is a new
dependency, which CLAUDE.md gates on a stated reason, and the tree is small
enough that the AST scan in this assessment can be re-run on demand instead.
Raise it if the module count grows.

**L3. `core/render.py`'s five local `import zoneinfo`.** Stdlib, no internal
edge, no cycle relevance. Ignore.

## Verification

```
$ .venv/bin/pytest -q -m "not integration"
294 passed, 88 deselected in 2.99s

$ .venv/bin/python -c "import nutrai.bot, nutrai.db, nutrai.http_api, \
    nutrai.jobs.notify, nutrai.jobs.audit, nutrai.jobs.report, \
    nutrai.core.plan, nutrai.llm.parse"
all import cleanly

$ ruff check nutrai --statistics    # identical output before and after
```

Cycle scan re-run after the changes: still none in all three graph variants, and
both phantom edges (`bot ~~> core.nutrition`, `llm.parse ~~> config`) are gone.

Integration tests were **not** run — they share one live Postgres with sibling
agents.
