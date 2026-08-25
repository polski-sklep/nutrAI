"""The golden resolution set as a regression floor.

`scripts/golden.py` is the report you read while changing the resolver; this is
the guard that fires when you change something else.

It asserts two things, not one. The count of passing cases must not go down —
and no case that passed when the baseline was recorded may start failing, which
a count cannot see on its own: repair one case, break another, and the total
holds while the suite quietly stops covering what it used to.

What it deliberately does not assert is that everything passes. Eleven cases do
not, and each records a defect the runner found rather than a broken build.
Demanding green would mean deleting the failing cases or never writing one
until the fix exists, and both turn the golden set into a record of what
already works. Raise the floor with `python scripts/golden.py --baseline` once
a fix has earned it.

Skipped without a database, like every other integration test.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import pytest

from tests.test_integration import _READY, _WHY

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _READY, reason=_WHY)]


def test_golden_set_does_not_regress() -> None:
    import golden
    import yaml

    from nutrai import db

    floor = json.loads(golden.BASELINE.read_text())
    cases = yaml.safe_load(golden.GOLDEN.read_text())["cases"]

    async def run() -> tuple[list[str], list[str], list[str], list[str]]:
        # One loop for the whole suite: `db.pool()` caches a pool bound to the
        # running loop, so a second asyncio.run would inherit a dead one.
        try:
            bad_ids = await golden.verify_ids(cases)
            results = [await golden.run_case(c, 2) for c in cases]
            return (bad_ids,
                    [r.case["id"] for r in results if r.status == "pass"],
                    [r.case["id"] for r in results if r.status == "fail"],
                    [r.case["id"] for r in results if r.status == "escalated"])
        finally:
            await db.close()

    bad_ids, passed, failed, escalated = asyncio.run(run())

    assert not bad_ids, "golden set names rows that are gone: " + "; ".join(bad_ids)

    # Failing is the regression; escalating is not.
    #
    # A guard that converts a confident wrong match into a question is the
    # design working — `state_conflicts` moved near_chicken_thigh_cooked out of
    # auto-match, and that case exists precisely to say a cooked mass must not
    # land on a raw row at yield_factor 1.0. Counting that as a regression
    # would be an argument for putting the bug back.
    lost = sorted(set(failed) - set(floor["known_failures"]))
    assert not lost, ("these did not fail when the baseline was recorded and "
                      "now do: " + ", ".join(lost))

    settled = len(passed) + len(escalated)
    floor_settled = floor["pass"] + floor.get("escalated", 0)
    assert settled >= floor_settled, (
        f"{len(passed)} pass + {len(escalated)} escalated = {settled}, "
        f"floor is {floor_settled} — run scripts/golden.py to see which")
