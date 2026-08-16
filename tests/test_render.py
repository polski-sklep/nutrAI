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


def test_day_card_shows_entry_times_in_the_users_timezone():
    """logged_at is UTC; the card was formatting it raw.

    A meal logged at 16:09 Warsaw appeared as 14:09 on the day card while every
    other message called it 16:09 — and the disagreement read as an entry that
    had failed to disappear after being undone.
    """
    import datetime as dt

    entries = [{
        "id": 1, "logged_at": dt.datetime(2026, 8, 15, 14, 9, tzinfo=dt.timezone.utc),
        "slot": "lunch", "name": "rice", "total_grams": 400, "source": "text",
        "confidence": 0.9, "kcal": 500, "protein": 20,
    }]
    warsaw = day_card(DAY, PROGRESS, entries, tz="Europe/Warsaw")
    assert "16:09" in warsaw, warsaw
    assert "14:09" not in warsaw

    # And the default stays UTC rather than guessing.
    assert "14:09" in day_card(DAY, PROGRESS, entries)


def test_day_score_excludes_what_nothing_measured():
    """Scoring a plate down for a nutrient its USDA row omits would make the
    score a measure of database coverage rather than of eating."""
    from nutrai.core.render import day_score

    prog = [
        row(1008, "Energy", "KCAL", 2000, hi=2418),
        row(1003, "Protein", "G", 200, lo=180),
        row(1004, "Total lipid (fat)", "G", 100, hi=81, state="over"),
        row(1178, "Vitamin B-12", "UG", 0.0, lo=2.4, state="under"),
    ]
    reached, assessable, short, breached, unmeasured = day_score(prog, {1178: 0.0})
    # Only Protein has a floor and is measured; B-12's floor is unmeasured.
    assert (reached, assessable, unmeasured) == (1, 1, 1)
    assert short == []
    # Fat is over its ceiling — reported, but not as a failed "target".
    assert breached == ["Fat"]


def test_day_score_counts_a_real_shortfall():
    from nutrai.core.render import day_score

    prog = [row(1003, "Protein", "G", 50, lo=180, state="under")]
    reached, assessable, short, breached, unmeasured = day_score(prog, {1003: 1.0})
    assert (reached, assessable, unmeasured) == (0, 1, 0)
    assert short == ["Protein"]


def test_score_line_names_the_misses_rather_than_hiding_them():
    """A score that hides which target was missed invites optimising the score,
    and the easiest number to move is rarely the one worth moving."""
    from nutrai.core.render import score_line

    prog = [
        row(1008, "Energy", "KCAL", 2000, hi=2418),
        row(1003, "Protein", "G", 50, lo=180, state="under"),
    ]
    out = score_line(prog, {1008: 1.0, 1003: 1.0})
    # Energy is a ceiling and is not counted as an achievement for being under it.
    assert "0 of 1 floors reached" in out
    assert "Protein" in out


def test_a_ceiling_is_not_an_achievement():
    """On a glass of water you are under your energy, fat, carbohydrate, sugar,
    saturated fat, sodium and cholesterol limits at once. The first version of
    this reported that as "7 of 20 targets met" at breakfast."""
    from nutrai.core.render import score_line

    barely_eaten = [
        row(1008, "Energy", "KCAL", 83, hi=2418),
        row(1005, "Carbohydrate, by difference", "G", 11, hi=328),
        row(1004, "Total lipid (fat)", "G", 3.3, hi=81),
        row(1093, "Sodium, Na", "MG", 55, hi=2300),
        row(1003, "Protein", "G", 0.2, lo=180, state="under"),
        row(1079, "Fiber, total dietary", "G", 0.2, lo=38, state="under"),
    ]
    out = score_line(barely_eaten, {n: 1.0 for n in (1008, 1005, 1004, 1093, 1003, 1079)})
    assert "0 of 2 floors reached" in out, out
    assert "7 of" not in out
    assert "over:" not in out
