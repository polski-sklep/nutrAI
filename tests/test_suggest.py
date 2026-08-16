"""What to eat next, ranked from your own dishes. No model in this path.

The obvious implementation asks a model and gets grilled salmon and quinoa —
a healthy-eating cliché about nobody. Ranking dishes you have already cooked
returns something in your kitchen, costs nothing, and cannot violate invariant
1 because there is no model in it to do so.
"""

from __future__ import annotations

from nutrai.core import suggest


def prog(nid, name, unit, amount, lo=None, hi=None):
    return {"nutrient_id": nid, "nutrient_name": name, "unit": unit,
            "amount": amount, "min_amount": lo, "max_amount": hi}


def dish(did, name, nutrients, times=3):
    return {"id": did, "name": name, "slug": name.lower().replace(" ", "-"),
            "slot": None, "times_logged": times, "nutrients": nutrients}


PROGRESS = [
    prog(1008, "Energy", "KCAL", 900, hi=2236),
    prog(1003, "Protein", "G", 40, lo=165),
    prog(1079, "Fiber, total dietary", "G", 5, lo=38),
    prog(1258, "Fatty acids, total saturated", "G", 18, hi=25),
]


def test_the_dish_that_closes_the_most_ranks_first():
    snapshots = {
        1: dish(1, "Chicken and rice", {1008: 600, 1003: 60, 1079: 3}),
        2: dish(2, "Lentil stew", {1008: 450, 1003: 20, 1079: 18}),
        3: dish(3, "Buttered toast", {1008: 300, 1003: 6, 1079: 2, 1258: 12}),
    }
    ranked = suggest.rank(snapshots, PROGRESS)
    assert ranked[0].name in ("Chicken and rice", "Lentil stew")
    assert [s.name for s in ranked][-1] == "Buttered toast"


def test_a_ceiling_breach_counts_against_the_score():
    """"Closes the protein gap" must not quietly outrank "and puts you 40%
    over saturated fat"."""
    clean = {1: dish(1, "Lean", {1003: 50, 1258: 1})}
    dirty = {1: dish(1, "Fatty", {1003: 50, 1258: 20})}
    assert suggest.rank(clean, PROGRESS)[0].score > suggest.rank(dirty, PROGRESS)[0].score
    breached = suggest.rank(dirty, PROGRESS)[0]
    assert breached.breaches and breached.breaches[0][0] == 1258


def test_overshooting_a_floor_is_not_rewarded_twice():
    """Filling a gap counts once. Nothing here treats more as better without
    limit — a dish with ten times the protein is not ten times the answer."""
    enough = {1: dish(1, "Enough", {1003: 125})}     # exactly closes the 125 g gap
    huge = {1: dish(1, "Huge", {1003: 1250})}
    assert suggest.rank(enough, PROGRESS)[0].score == suggest.rank(huge, PROGRESS)[0].score


def test_a_dish_that_closes_nothing_is_not_suggested():
    nothing = {1: dish(1, "Black coffee", {1008: 2})}
    assert suggest.rank(nothing, PROGRESS) == []


def test_met_floors_and_absent_targets_are_ignored():
    met = [prog(1003, "Protein", "G", 200, lo=165)]
    assert suggest.rank({1: dish(1, "Steak", {1003: 50})}, met) == []


def test_nothing_in_this_module_imports_a_model():
    """The constraint is structural rather than a promise: there is no model
    in this path to violate invariant 1."""
    import inspect

    src = inspect.getsource(suggest)
    for forbidden in ("llm", "anthropic", "call_tool", "MODEL_"):
        assert forbidden not in src, forbidden
