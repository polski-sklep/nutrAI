"""Unit conversion on a supplement panel.

A factor of 1,000 in a micronutrient is the difference between a deficiency and
a toxicity, applied to every day thereafter without ever looking wrong. So the
rule is convert exactly or refuse — never approximate.
"""

from __future__ import annotations

import pytest

from nutrai.core.supplements import convert, normalise

UNITS = {1114: "UG", 1178: "UG", 1087: "MG", 1089: "MG", 1008: "KCAL", 1003: "G"}


def test_same_unit_passes_through():
    assert convert(1087, 400.0, "mg", "MG") == (400.0, "")


def test_mass_conversions_are_exact():
    assert convert(1178, 0.5, "mg", "UG")[0] == pytest.approx(500.0)
    assert convert(1087, 1.2, "g", "MG")[0] == pytest.approx(1200.0)
    assert convert(1089, 14000.0, "ug", "MG")[0] == pytest.approx(14.0)
    # mcg and ug are the same thing printed two ways.
    assert convert(1178, 2.4, "mcg", "UG")[0] == pytest.approx(2.4)


def test_vitamin_d_iu_is_exact_and_converted():
    """1 IU of vitamin D is 0.025 µg by definition — 4000 IU is 100 µg."""
    value, why = convert(1114, 4000.0, "IU", "UG")
    assert value == pytest.approx(100.0), why


def test_ambiguous_iu_is_refused_not_guessed():
    """Vitamin A in IU depends on retinol vs beta-carotene — a 12x spread."""
    value, why = convert(1106, 5000.0, "iu", "UG")
    assert value is None
    assert "form" in why


def test_normalise_keeps_what_it_can_and_reports_what_it_cannot():
    lines = [
        {"nutrient_id": 1114, "printed_label": "Vitamin D3", "amount": 4000, "unit": "iu"},
        {"nutrient_id": 1178, "printed_label": "Vitamin B12", "amount": 500, "unit": "mcg"},
        {"nutrient_id": 1087, "printed_label": "Calcium", "amount": 200, "unit": "mg"},
        {"nutrient_id": 9999, "printed_label": "Ashwagandha", "amount": 600, "unit": "mg"},
    ]
    kept, dropped = normalise(lines, UNITS)
    by_id = {c.nutrient_id: c.amount for c in kept}
    assert by_id[1114] == pytest.approx(100.0)
    assert by_id[1178] == pytest.approx(500.0)
    assert by_id[1087] == pytest.approx(200.0)
    # An untracked ingredient is reported, not silently discarded.
    assert [d.nutrient_id for d in dropped] == [9999]
    assert "not a nutrient I track" in dropped[0].reason


def test_duplicate_lines_do_not_double_count():
    lines = [
        {"nutrient_id": 1087, "printed_label": "Calcium", "amount": 200, "unit": "mg"},
        {"nutrient_id": 1087, "printed_label": "Calcium carbonate", "amount": 500, "unit": "mg"},
    ]
    kept, dropped = normalise(lines, UNITS)
    assert len(kept) == 1 and kept[0].amount == pytest.approx(200.0)
    assert dropped and "duplicate" in dropped[0].reason


def test_a_garbled_line_is_rejected_rather_than_zeroed():
    kept, dropped = normalise([{"nutrient_id": 1087, "printed_label": "Calcium"}], UNITS)
    assert not kept and dropped
