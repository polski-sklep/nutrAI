#!/usr/bin/env python3
"""Run the golden resolution set and report what the resolver actually does.

    python scripts/golden.py                    # report
    python scripts/golden.py --verify-ids       # only check the fdc_ids exist
    python scripts/golden.py --stage candidates # one stage
    python scripts/golden.py --baseline         # rewrite the recorded floor

`docs/resolution/golden.yaml` is data and has been since it was written; this
is the runner it names. Until now every ranking change in this repo was checked
against a handful of queries typed by hand at the moment of changing them,
which tests the case you already have in mind and nothing else.

Two things it deliberately does not do.

It does not call a model. Sixty-four of the seventy-six cases carry a frozen
`parse` block — the model's contribution, recorded once — so the assertion is
reached by SQL alone. The twelve `needs_model` cases are reported as skipped
rather than quietly counted as passing.

It does not consult aliases. `_candidates` never does, and `resolve_items`
checks them first, so running the identity stages through the alias tier would
measure the cache rather than the resolver — which is why the file says the
suite must not run as a user with 132 of them. The alias tier is exercised by
the `alias_*` cases, which are marked `needs_model` and skipped here.

A failure is a finding, not a broken build. Several cases pin behaviour the
code does not have yet — `measure_slice_bread` expects USDA household portions
that `db.portion_for` filters out by design — so the pass count is compared
against a recorded baseline and a *drop* is what fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("TELEGRAM_TOKEN", "1:golden")
os.environ.setdefault("ANTHROPIC_API_KEY", "golden")

import yaml

from nutrai import db
from nutrai.config import AUTO_MATCH_SIMILARITY
from nutrai.llm import parse as parse_mod

ROOT = pathlib.Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "docs" / "resolution" / "golden.yaml"
BASELINE = ROOT / "docs" / "resolution" / "baseline.json"

# Stages whose assertion is "which row won". The rest need machinery this
# runner does not drive yet and are reported as unsupported rather than passed.
IDENTITY_STAGES = ("candidates", "select", "nutrient", "yield", "validate")


class Result:
    __slots__ = ("case", "detail", "status")

    def __init__(self, case: dict, status: str, detail: str = "") -> None:
        self.case, self.status, self.detail = case, status, detail


async def _chosen(case: dict, user_id: int) -> tuple[dict | None, list[dict], str]:
    """The row the resolver would take, and how it got there.

    Mirrors `resolve_items` minus the alias tier: own product first, then a
    head that clears the threshold and does not negate the food. Anything else
    is the model's decision, which this runner does not make for it.
    """
    item = dict(case["parse"])
    label = str(item.get("label") or "")
    cands = await parse_mod._candidates(item, label, user_id)
    if not cands:
        return None, [], "no_candidates"

    asked_for = f"{label} {item.get('search_terms') or ''}"
    own = next(
        (c for c in cands
         if c["precedence"] == 0
         and (c is cands[0] or float(c["sim"] or 0) >= AUTO_MATCH_SIMILARITY)),
        None)
    if own is not None and not parse_mod.inverts_meaning(asked_for, own["description"]):
        return own, cands, "own_product"
    auto = next(
        (c for c in cands
         if float(c["sim"] or 0) >= AUTO_MATCH_SIMILARITY
         and not parse_mod.inverts_meaning(asked_for, c["description"])
         and not parse_mod.state_conflicts(item.get("state"), c["description"])
         and not parse_mod.unrequested_qualifier(asked_for, c["description"])
         and not parse_mod.label_absent(label, c["description"])),
        None)
    if auto is not None:
        return auto, cands, "auto"
    return None, cands, "would_ask_model"


def _within(actual: float | None, disc: dict) -> bool:
    tol = disc.get("tol") or {}
    want = disc.get("per_100g")
    if want is None:
        return True
    if "max" in tol:
        return actual is not None and actual <= float(tol["max"])
    if actual is None:
        return False
    if tol.get("exact"):
        return abs(actual - float(want)) < 1e-6
    slack = 0.0
    if "pct" in tol:
        slack = max(slack, abs(float(want)) * float(tol["pct"]) / 100.0)
    if "abs" in tol:
        slack = max(slack, float(tol["abs"]))
    return abs(actual - float(want)) <= slack


async def _discriminators_hold(fdc_id: int, case: dict) -> str:
    """The nutrients that separate the right row from a plausible wrong one."""
    p = await db.pool()
    for disc in case.get("discriminators") or []:
        nid = disc.get("nutrient")
        if nid is None:
            continue
        got = await p.fetchval(
            """SELECT sum(fn.amount) FROM food_nutrient fn
                 JOIN v_nutrient_canonical c ON c.id = fn.nutrient_id
                WHERE fn.fdc_id = $1 AND c.canonical_id = $2""",
            fdc_id, int(nid))
        if not _within(float(got) if got is not None else None, disc):
            return (f"nutrient {nid}: row has "
                    f"{'none' if got is None else f'{float(got):.1f}'}, "
                    f"case wants {disc.get('per_100g')} ({disc.get('tol')})")
    return ""


async def run_case(case: dict, user_id: int) -> Result:
    if case.get("tier") != "model_free":
        return Result(case, "skip", "needs a live model")
    if case["stage"] not in IDENTITY_STAGES:
        return Result(case, "unsupported", f"stage {case['stage']} not driven yet")
    if not isinstance(case.get("parse"), dict):
        return Result(case, "unsupported", "no single frozen parse item")

    exp = case.get("expect") or {}
    want = exp.get("fdc_id")
    if want is None:
        return Result(case, "unsupported", "case asserts no fdc_id")
    ok_ids = {int(want), *(int(i) for i in exp.get("acceptable") or [])}
    banned = {int(i) for i in exp.get("forbidden") or []}

    chosen, cands, how = await _chosen(case, user_id)
    head = cands[0] if cands else None

    if case["stage"] == "candidates":
        # The assertion is about the list, not the decision: the right row has
        # to be reachable and a forbidden one must not lead it.
        if head is None:
            return Result(case, "fail", "no candidates at all")
        if int(head["fdc_id"]) in banned:
            return Result(case, "fail",
                          f"forbidden row leads: {head['description']!r}")
        if not any(int(c["fdc_id"]) in ok_ids for c in cands):
            return Result(case, "fail",
                          f"expected row absent; head {head['description']!r} "
                          f"sim={float(head['sim']):.2f}")
        bad = await _discriminators_hold(int(want), case)
        return Result(case, "fail", bad) if bad else Result(case, "pass", how)

    # select / nutrient / yield / validate: which row is actually taken.
    if chosen is None:
        # Declining to guess is not the same as guessing wrong, and a runner
        # that calls no model cannot tell them apart by outcome — so it tells
        # them apart by what was on offer. If the expected row is in the list
        # the resolver handed over, tier 3 has everything it needs and this is
        # the design working, not a defect. If it is not, the model is being
        # asked to choose between wrong answers and the failure is real.
        #
        # The distinction matters because the guards deliberately convert
        # confident wrong matches into escalations: `state_conflicts` turned
        # `near_chicken_breast_cooked` from taking a raw row into asking, and
        # scoring that as a regression would argue for putting the bug back.
        if any(int(c["fdc_id"]) in ok_ids for c in cands):
            return Result(case, "escalated",
                          f"declined to auto-match; {want} is on the list "
                          f"(head {head['description']!r} sim={float(head['sim']):.2f})")
        return Result(case, "fail", f"{how}: nothing auto-matched"
                      + (f", head {head['description']!r} sim={float(head['sim']):.2f}"
                         if head else ""))
    if int(chosen["fdc_id"]) in banned:
        return Result(case, "fail", f"took a forbidden row: {chosen['description']!r}")
    if int(chosen["fdc_id"]) not in ok_ids:
        return Result(case, "fail",
                      f"took {chosen['fdc_id']} {chosen['description']!r} "
                      f"(sim {float(chosen['sim']):.2f}), wanted {want}")
    bad = await _discriminators_hold(int(chosen["fdc_id"]), case)
    return Result(case, "fail", bad) if bad else Result(case, "pass", how)


async def verify_ids(cases: list[dict]) -> list[str]:
    """Every fdc_id a case can legitimately resolve to, still live.

    A *forbidden* row is allowed to be missing or retired — several are
    forbidden precisely because they were retired, and the file says so. Only
    the rows a case expects to win have to be there.
    """
    p = await db.pool()
    must_be_live: set[int] = set()
    for c in cases:
        exp = c.get("expect") or {}
        for key in ("fdc_id", "acceptable"):
            v = exp.get(key)
            if isinstance(v, int):
                must_be_live.add(v)
            elif isinstance(v, list):
                must_be_live.update(int(i) for i in v)
    rows = await p.fetch(
        "SELECT fdc_id, retired_at FROM food WHERE fdc_id = ANY($1::int[])",
        sorted(must_be_live))
    present = {r["fdc_id"]: r["retired_at"] for r in rows}
    problems = [f"{i} missing" for i in sorted(must_be_live) if i not in present]
    problems += [f"{i} retired, but a case expects it to win"
                 for i in sorted(must_be_live) if present.get(i) is not None]
    return problems


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-ids", action="store_true")
    ap.add_argument("--stage")
    ap.add_argument("--baseline", action="store_true",
                    help="rewrite the recorded pass floor")
    ap.add_argument("--user", type=int, default=2,
                    help="whose user_product rows are visible; aliases are "
                         "never consulted, so this does not short-circuit")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    doc = yaml.safe_load(GOLDEN.read_text())
    cases = doc["cases"]

    bad_ids = await verify_ids(cases)
    if bad_ids:
        print(f"⚠️  {len(bad_ids)} fdc_id(s) in the golden set no longer resolve:")
        for b in bad_ids:
            print(f"     {b}")
    if a.verify_ids:
        return 1 if bad_ids else 0

    if a.stage:
        cases = [c for c in cases if c["stage"] == a.stage]

    results = [await run_case(c, a.user) for c in cases]
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    if not a.quiet:
        for status, mark in (("fail", "✗"), ("escalated", "→"),
                             ("unsupported", "–"), ("skip", "·")):
            group = [r for r in results if r.status == status]
            if not group:
                continue
            print(f"\n{mark} {status.upper()} ({len(group)})")
            for r in group:
                print(f"   {r.case['id']:<34} [{r.case['stage']}] {r.detail}")
        print()

    by_stage: dict[str, tuple[int, int]] = {}
    for r in results:
        if r.status in ("pass", "fail", "escalated"):
            p_, n_ = by_stage.get(r.case["stage"], (0, 0))
            by_stage[r.case["stage"]] = (p_ + (r.status == "pass"), n_ + 1)
    for stage, (passed, total) in sorted(by_stage.items()):
        print(f"   {stage:<12} {passed}/{total}")
    print(f"\n{counts.get('pass', 0)} pass · {counts.get('fail', 0)} fail · "
          f"{counts.get('escalated', 0)} escalated with the right row on the list · "
          f"{counts.get('skip', 0)} need a model · "
          f"{counts.get('unsupported', 0)} not driven yet")

    # The failing ids are recorded alongside the count because a count alone
    # cannot see a swap: repair one case, break another, and the total holds
    # while the suite silently stops covering what it used to.
    record = {"pass": counts.get("pass", 0),
              "graded": counts.get("pass", 0) + counts.get("fail", 0),
              "by_stage": {k: list(v) for k, v in sorted(by_stage.items())},
              "escalated": counts.get("escalated", 0),
              "known_failures": sorted(r.case["id"] for r in results
                                       if r.status == "fail"),
              "known_escalations": sorted(r.case["id"] for r in results
                                          if r.status == "escalated")}
    if a.baseline:
        BASELINE.write_text(json.dumps(record, indent=2) + "\n")
        print(f"\nbaseline written: {BASELINE.relative_to(ROOT)}")
        return 0
    if BASELINE.exists():
        floor = json.loads(BASELINE.read_text())
        if record["pass"] < floor["pass"]:
            print(f"\n✗ REGRESSION: {record['pass']} passing, floor is {floor['pass']}")
            return 1
        if record["pass"] > floor["pass"]:
            print(f"\n↑ {record['pass'] - floor['pass']} more than the recorded floor "
                  f"— rerun with --baseline to lock it in")
    await db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
