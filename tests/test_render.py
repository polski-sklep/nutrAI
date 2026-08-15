"""The display layer, where a true number can still tell a lie.

`total_nutrients()` skipping a null is arithmetic honesty. It does not stop the
day card printing "Vitamin B-12  0.0 µg  0% ▽" for a plate of beef whose USDA
row simply does not carry B-12. These tests hold that line.
"""

from __future__ import annotations

import datetime as dt

from nutrai.core.render import confirm_card, day_card, logged_card


def row(nid, name, unit, amount, lo=None, hi=None, state="ok"):
    return {
        "nutrient_id": nid, "nutrient_name": name, "unit": unit, "is_core": True,
        "amount": amount, "min_amount": lo, "max_amount": hi,
        "pct_of_min": None, "pct_of_max": None, "state": state,
    }


DAY = dt.date(2026, 8, 15)
PROGRESS = [
    row(1008, "Energy", "KCAL", 965, hi=2170),
    row(1003, "Protein", "G", 48, lo=180, state="under"),
    row(1005, "Carbohydrate, by difference", "G", 46, hi=262),
    row(1004, "Total lipid (fat)", "G", 64, hi=78),
    row(1178, "Vitamin B-12", "UG", 0.0, lo=2.4, state="under"),
    row(1087, "Calcium, Ca", "MG", 34, lo=1000, state="under"),
]


def test_unmeasured_nutrient_is_not_shown_as_a_deficiency():
    coverage = {1008: 1.0, 1003: 1.0, 1005: 1.0, 1004: 1.0, 1178: 0.0, 1087: 1.0}
    out = day_card(DAY, PROGRESS, [], coverage=coverage)

    assert "<b>not measured</b>" in out
    assert "Vitamin B-12" in out.split("<b>not measured</b>")[1]
    # It must not also appear in the shortfall list above.
    assert "▽ Vitamin B-12" not in out
    # A genuine shortfall still reads as one.
    assert "▽ Calcium, Ca" in out


def test_partial_coverage_is_annotated_rather_than_hidden():
    coverage = {1008: 1.0, 1003: 1.0, 1005: 1.0, 1004: 1.0, 1178: 0.42, 1087: 1.0}
    out = day_card(DAY, PROGRESS, [], coverage=coverage)
    assert "(42% measured)" in out
    # Still listed — 42% measured and nothing found is real information.
    assert "▽ Vitamin B-12" in out


def test_full_coverage_adds_no_noise():
    coverage = {nid: 1.0 for nid in (1008, 1003, 1005, 1004, 1178, 1087)}
    out = day_card(DAY, PROGRESS, [], coverage=coverage)
    assert "measured)" not in out
    assert "not measured" not in out


def test_day_card_without_coverage_still_renders():
    """Callers that pass no coverage map keep the old behaviour."""
    out = day_card(DAY, PROGRESS, [])
    assert "965" in out
    assert "not measured" not in out


def test_day_card_handles_decimal_targets():
    """asyncpg returns numeric as Decimal; the card divides by it."""
    from decimal import Decimal

    prog = [row(1008, "Energy", "KCAL", Decimal("965.5"), hi=Decimal(2170))]
    out = day_card(DAY, prog, [])
    assert "966" in out or "965" in out


def test_confirm_card_marks_provenance_and_shows_a_range_on_guesses():
    class C:
        def __init__(self, label, grams, sigma, source):
            self.label, self.grams, self.sigma, self.grams_source = label, grams, sigma, source

    comps = [
        C("minced beef", 250.0, 1.25, "scale"),
        C("olive oil", 15.0, 5.25, "estimate"),
    ]
    out = confirm_card(
        "mince and rice", comps, {1008: 965.0, 1003: 48.0, 1005: 46.0, 1004: 64.0},
        confidence=0.91, warnings=[],
    )
    assert "⚖ minced beef" in out
    assert "≈ olive oil" in out
    # The eyeballed item shows the range it actually is.
    assert "<i>(4–26 g)</i>" in out
    assert out.startswith("🍽 <b>mince and rice</b>")
    assert "Nothing is logged until you confirm." in out


def test_unmatched_items_appear_above_the_totals():
    """A total computed from part of a plate must not read as the meal's total.

    A real meal logged 160 kcal of an ~800 kcal plate because three of four
    items were missing and the card led with the tidy number, burying the
    mismatch in a warning underneath.
    """

    class C:
        label, grams, sigma, grams_source = "avocado", 100.0, 12.0, "estimate"

    out = confirm_card(
        "cheesy bread, pickle, avocado, salami", [C()], {1008: 160.0},
        confidence=0.5, warnings=["low overall confidence (50%)"],
        unresolved=["cheesy bread rolls", "pickle (dill gherkin)", "Italian salami slices"],
    )
    assert "3 of 4 items are not in the food database" in out
    # Above the number, not below it.
    assert out.index("not in the food database") < out.index("160 kcal")
    for missing in ("cheesy bread rolls", "pickle (dill gherkin)", "Italian salami slices"):
        assert missing in out


def test_confirm_card_without_unresolved_says_nothing_about_matching():
    class C:
        label, grams, sigma, grams_source = "rice", 164.0, 1.0, "scale"

    out = confirm_card("rice", [C()], {1008: 213.0}, confidence=0.95, warnings=[])
    assert "not in the food database" not in out


LOGGED_PROGRESS = [
    row(1008, "Energy", "KCAL", 160, hi=2170),
    row(1003, "Protein", "G", 2, lo=180, state="under"),
    row(1079, "Fiber, total dietary", "G", 7, lo=38, state="under"),
    row(1005, "Carbohydrate, by difference", "G", 9, hi=262),
    row(1004, "Total lipid (fat)", "G", 15, hi=78),
    row(1087, "Calcium, Ca", "MG", 34, lo=1000, state="under"),
    row(1177, "Folate, total", "UG", 81, lo=400, state="under"),
]


def test_logged_card_reports_progress_contributions_and_gaps():
    meal = {1008: 160.0, 1003: 2.0, 1079: 7.0, 1004: 15.0, 1177: 81.0, 1087: 34.0}
    out = logged_card("avocado on toast", meal, LOGGED_PROGRESS)

    assert out.startswith("✅ <b>Logged</b>")
    assert "Today so far" in out
    assert "What this meal brought most" in out
    assert "Still to go today" in out

    # Ranked by share of the day's floor: folate (20%) beats calcium (3%).
    assert out.index("Folate") < out.index("Calcium")
    # Energy is excluded from "brought most" — it is already in the progress block.
    brought = out.split("brought most")[1].split("Still to go")[0]
    assert "Energy" not in brought

    # Protein and fibre are always named in the gaps, and the remainder is what
    # is left, not what was eaten.
    gaps = out.split("Still to go today")[1]
    assert "Protein" in gaps and "178 g" in gaps
    assert "Fibre" in gaps and "31 g" in gaps


def test_logged_card_congratulates_rather_than_inventing_gaps():
    met = [
        row(1008, "Energy", "KCAL", 1800, hi=2170),
        row(1003, "Protein", "G", 200, lo=180),
    ]
    out = logged_card("big dinner", {1003: 200.0}, met)
    assert "Every floor met today." in out
    assert "Still to go today" not in out


def test_logged_card_survives_a_user_with_no_targets():
    assert "Logged" in logged_card("x", {1008: 100.0}, [])
