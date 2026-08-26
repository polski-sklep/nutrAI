# Food knowledge audit — paused 26 Aug 2026, resume Friday 28 Aug

Paused mid-run at the user's request. Nothing here is finished; this file is
the handle to pick it up by.

## The task

Systematically eliminate the class of failure where nutrAI does not recognise
an obvious ingredient, alias, variant or relationship — carbonara/guanciale as
the symptom, not the target. Full brief is in the conversation; the operative
demands are: thousands of generated cases across world cuisines, independent
critic agents, fixes implemented rather than merely reported, a repeatable
regression suite, before/after metrics, and explicit confidence levels with
speculative mappings deliberately rejected rather than encoded.

## What is already established, and should not be re-derived

**The gap is architectural, not a missing USDA row.**

- `food_alias.user_id` is `NOT NULL` — every alias is per-user. There is no
  global synonym layer, so "guanciale is cured pork jowl" has nowhere to live.
- There is no taxonomy table. Nothing expresses "is a kind of".
- `-626 Pancetta/guanciale` is a hand-made `user_product` workaround and is
  itself wrong: it fuses jowl and belly, which differ materially in fat.

**The motivating case, measured.** USDA *has* the food:

    Pork, fresh, variety meats and by-products, jowl, raw   <- guanciale's raw material
    query "pork jowl"  ->  0.208 against that row
                           0.400 against "Pork jerky"        <- wins

**Retrieval, measured over 400 generated queries** (`scripts/eval_retrieval.py`):

    recall@1 53.0%   recall@5 84.5%
    short descriptions 75.2% | medium 54.5% | long (60+) 28.7%

**Ranking is not where the win is, and this was tested rather than assumed.**
Six formulas swept; none beat the shipped one by more than a point.
`COVERS_BOOST` stays 1.35 — the window that fixes `pork jowl` without
promoting "Pretzels, soft, ready-to-eat, unsalted, no butter" over
"Butter, salted" is 0.03 wide, and both cases sit at the same similarity ratio
to their competitor, so no similarity-derived rule separates them. See the
comment above `COVERS_BOOST` in `nutrai/db.py`.

**Where the win is.** recall@5 is 85%, so the right row is nearly always on the
list the model tier already sees. Terms like `guanciale`, `halloumi`,
`gochujang` return *nothing* — recall 0, unreachable by any ranking function.
The fix is a knowledge layer: global synonyms, a taxonomy with nutritional
fallbacks, and normalisation. That is the work Friday should build.

## Tools already built (use these, do not write second versions)

- `scripts/probe_knowledge.py` — the shared probe. Verdicts none/weak/ask/auto.
  Deliberately does not consult `food_alias`: that would measure the cache.
- `scripts/eval_retrieval.py` — self-supervised retrieval eval. Queries are
  generated from each row's own words, so no hand labelling is needed.
- `scripts/golden.py` + `docs/resolution/golden.yaml` — 76 cases. Baseline as
  of the pause: **25 pass, 9 fail, 3 escalated, 12 need a model**. The golden
  set does NOT cover this failure class; that is a known gap to close.

## Fleet state

Workflow `wf_0123e990-820`, 14 domain auditors each followed by an independent
critic. Stopped with **8 of 14 audits written**, critics mostly not run:

    done: african, british-german-nordic, chinese, eastern-europe-balkan,
          greek-turkish-levantine, iberian-lusophone, italian-french, south-asian
    not done: japanese-korean, southeast-asian, mexico-central-caribbean,
          south-america, middle-east-central-asia-america,
          taxonomy-fallback, normalization-orthography

The last two are cross-cutting and are the most load-bearing for the knowledge
layer — taxonomy/fallback quality and orthographic normalisation. Do not skip
them to save time.

**Resume without re-running the eight that finished** — completed agents return
cached results:

    Workflow({
      scriptPath: "/Users/Jacob/.claude/projects/-Users-Jacob-Projects-nutrAI/f835031d-2b38-483b-9378-8d33ee725507/workflows/scripts/nutrai-food-knowledge-audit-wf_0123e990-820.js",
      resumeFromRunId: "wf_0123e990-820"
    })

Read the run's `journal.jsonl` before assuming a cached result is non-empty.

## Order of work on Friday

1. Resume the workflow; let the remaining six audits and all critics finish.
2. Reconcile audit against critique. A mapping only survives if the critic
   upheld it. Encode `high` only; `medium` as non-mandatory fallback; never
   encode `low` — record it as deliberately rejected, with the reason.
3. Build the knowledge layer: global synonym table, taxonomy with parents and
   nutritional fallbacks, normalisation. Schema first, put it to the user.
4. Regression suite: invariant-style and generated, not a handful of hand-
   written foods. It must fail if `guanciale` stops reaching cured pork.
5. Re-run `eval_retrieval.py` and `golden.py` for the after numbers.

## Two standing cautions

- **Another Claude session works in this repo concurrently.** Commit `d359db5`
  ("Record the Epicure evaluation") swept this session's uncommitted work into
  itself without mentioning it. Check `git log` and `git status` before
  assuming the tree is yours.
- Agents must stay **read-only on the database** and must not run
  `pytest -m integration` — they share one Postgres.
