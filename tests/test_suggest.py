"""What to eat next, ranked from your own dishes. No model in this path.

The obvious implementation asks a model and gets grilled salmon and quinoa —
a healthy-eating cliché about nobody. Ranking dishes you have already cooked
returns something in your kitchen, costs nothing, and cannot violate invariant
1 because there is no model in it to do so.
"""

from __future__ import annotations

from nutrai.core import suggest


def prog(nid, name, unit, amount, lo=None, hi=None, state="ok", weight=1):
    return {"nutrient_id": nid, "nutrient_name": name, "unit": unit,
            "amount": amount, "min_amount": lo, "max_amount": hi,
            "state": state, "weight": weight}


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


def test_the_biggest_gap_outranks_a_nearly_met_one():
    """118 g short of a 165 g protein floor, and the top suggestion was a chia
    pudding with 4 g of protein — because it finished the last 2% of calcium
    and every floor counted the same."""
    progress = [
        prog(1003, "Protein", "G", 47, lo=165),        # 118 g short
        prog(1087, "Calcium, Ca", "MG", 992, lo=1000),  # 8 mg short
    ]
    snapshots = {
        1: dish(1, "Chia pudding", {1008: 211, 1003: 4, 1087: 341}),
        2: dish(2, "Chicken breast", {1008: 330, 1003: 62, 1087: 15}),
    }
    ranked = suggest.rank(snapshots, progress)
    assert ranked[0].name == "Chicken breast", [(s.name, round(s.score, 4)) for s in ranked]


def test_a_nearly_met_floor_is_not_a_gap_at_all():
    """"Closes Calcium 100%" is not an achievement when the hundred per cent
    was 8 mg of a 1,000 mg floor."""
    progress = [prog(1087, "Calcium, Ca", "MG", 992, lo=1000)]
    assert suggest.rank({1: dish(1, "Milk", {1087: 200})}, progress) == []

    # Still a gap at 15% outstanding.
    progress = [prog(1087, "Calcium, Ca", "MG", 850, lo=1000)]
    assert suggest.rank({1: dish(1, "Milk", {1087: 200})}, progress)


def test_a_breach_cannot_outweigh_closing_the_gap_that_matters():
    """With fat at 97% of its ceiling everything containing fat breaches, so an
    unbounded penalty put a pickle juice closing 7% of potassium above a shake
    closing 48% of a protein gap."""
    progress = [
        {**prog(1003, "Protein", "G", 116, lo=165, state="under"), "weight": 2.5},
        {**prog(1092, "Potassium, K", "MG", 1892, lo=3400, state="under"), "weight": 1},
        {**prog(1004, "Total lipid (fat)", "G", 76, hi=78), "weight": 1},
    ]
    snapshots = {
        1: dish(1, "Pickle juice", {1008: 51, 1092: 105}),
        2: dish(2, "Protein shake", {1008: 121, 1003: 24, 1092: 160, 1004: 3}),
    }
    ranked = suggest.rank(snapshots, progress)
    assert ranked[0].name == "Protein shake", [(s.name, round(s.score, 4)) for s in ranked]
    assert all(s.score >= 0 for s in ranked), "a penalty drove a score negative"


def test_a_suggestion_that_closes_almost_nothing_is_not_offered():
    """Three drinks each closing 1% of potassium are not an answer to 'what
    should I eat next' — a tick beside them dresses noise as advice."""
    progress = [prog(1092, "Potassium, K", "MG", 1892, lo=3400, state="under")]
    trivial = {1: dish(1, "Lemon water", {1008: 6, 1092: 20})}   # ~1% of the gap
    assert suggest.rank(trivial, progress) == []

    real = {1: dish(1, "Big salad", {1008: 200, 1092: 800})}
    assert suggest.rank(real, progress)


def test_the_protein_gap_leads_because_it_is_weighted():
    """Ordered by share of target alone, protein at 30% short sat below a
    micronutrient at 90% short — while carrying two and a half times the
    weight in the day's score."""
    from nutrai.core.render import suggest_card

    progress = [
        {**prog(1003, "Protein", "G", 116, lo=165, state="under"), "weight": 2.5},
        {**prog(1106, "Vitamin A, RAE", "UG", 489, lo=900, state="under"), "weight": 1},
    ]
    # The empty card names only the gap that matters, so that is the assertion:
    # protein, despite vitamin A being a larger share of its own target.
    out = suggest_card([], progress, 500)
    assert "The gap that matters is Protein" in out, out
    assert "Vitamin A" not in out
