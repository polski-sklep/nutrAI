"""The display layer, where a true number can still tell a lie.

`total_nutrients()` skipping a null is arithmetic honesty. It does not stop the
day card printing "Vitamin B-12  0.0 µg  0% ▽" for a plate of beef whose USDA
row simply does not carry B-12. These tests hold that line.
"""

from __future__ import annotations

import datetime as dt

from nutrai.core.render import confirm_card, day_card


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
    assert out.startswith("<b>mince and rice</b>")
    assert "Nothing is logged until you confirm." in out
