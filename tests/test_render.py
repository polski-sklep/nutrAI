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
    assert "Vitamin B12" in out.split("<b>not measured</b>")[1]
    # It must not also appear in the shortfall list above.
    assert "▽ Vitamin B12" not in out
    # A genuine shortfall still reads as one.
    # Shown by its plain name: the USDA column is "Calcium, Ca", and the
    # chemical symbol reads as a second word rather than a restatement.
    assert "▽ Calcium " in out
    assert "Calcium, Ca" not in out


def test_partial_coverage_is_annotated_rather_than_hidden():
    coverage = {1008: 1.0, 1003: 1.0, 1005: 1.0, 1004: 1.0, 1178: 0.42, 1087: 1.0}
    out = day_card(DAY, PROGRESS, [], coverage=coverage)
    assert "(only 42% of food has data)" in out
    # Still listed — 42% covered and nothing found is real information.
    assert "▽ Vitamin B12" in out


def test_full_coverage_adds_no_noise():
    coverage = {nid: 1.0 for nid in (1008, 1003, 1005, 1004, 1178, 1087)}
    out = day_card(DAY, PROGRESS, [], coverage=coverage)
    assert "of food has data" not in out
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
    reached, assessable, short, breached, nearing, unmeasured = day_score(prog, {1178: 0.0})
    # Only Protein has a floor and is measured; B-12's floor is unmeasured.
    assert (reached, assessable, unmeasured) == (1, 1, 1)
    assert short == []
    # Fat is over its ceiling — reported, but not as a failed "target".
    assert breached == ["Fat 123%"]


def test_day_score_counts_a_real_shortfall():
    from nutrai.core.render import day_score

    prog = [row(1003, "Protein", "G", 50, lo=180, state="under")]
    reached, assessable, short, breached, nearing, unmeasured = day_score(prog, {1003: 1.0})
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
    assert "0 of 1 daily minimums met" in out
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
    assert "0 of 2 daily minimums met" in out, out
    assert "7 of" not in out
    assert "over:" not in out


def test_a_ceiling_is_flagged_before_it_is_crossed():
    """At 92% of your energy there is still a decision to make about dinner.
    At 104% the only thing left is to know."""
    from nutrai.core.render import score_line

    prog = [
        row(1008, "Energy", "KCAL", 2230, hi=2418),          # 92% — close
        row(1093, "Sodium, Na", "MG", 1150, hi=2300),        # 50% — silent
        row(1004, "Total lipid (fat)", "G", 90, hi=81),      # 111% — over
        row(1003, "Protein", "G", 190, lo=180),
    ]
    out = score_line(prog, {n: 1.0 for n in (1008, 1093, 1004, 1003)})
    assert "over:" in out and "Fat 111%" in out
    assert "close:" in out and "Energy 92%" in out
    assert "Sodium" not in out
    assert "1 of 1 daily minimums met" in out


def test_a_count_is_shown_so_the_reading_can_be_checked():
    """Whether "300 ml" meant per cup or across all three is obvious to the
    person who typed it and invisible in a total."""

    class C:
        label, grams, sigma, grams_source, count = "cappuccino", 300.0, 15.0, "stated", 3

    out = confirm_card("three cappuccinos", [C()], {1008: 190.0},
                       confidence=0.6, warnings=[])
    assert "3 × cappuccino" in out, out


def test_no_count_means_no_multiplier_shown():
    class C:
        label, grams, sigma, grams_source, count = "rice", 164.0, 1.0, "scale", None

    assert "×" not in confirm_card("rice", [C()], {1008: 213.0},
                                   confidence=0.95, warnings=[])


def test_database_column_names_never_reach_the_screen():
    """"Carbohydrate, by diffe" and "Vitamin C, total ascor" were raw USDA
    column names truncated mid-word. _short() existed the whole time; the row
    builder simply never called it."""
    from nutrai.core.render import _short

    for raw, expected in [
        ("Carbohydrate, by difference", "Carbs"),
        ("Vitamin C, total ascorbic acid", "Vitamin C"),
        ("PUFA 22:6 n-3 (DHA)", "Omega-3 (DHA)"),
        ("Iron, Fe", "Iron"),
        ("Fiber, total dietary", "Fibre"),
        ("Total lipid (fat)", "Fat"),
        ("Vitamin B-12", "Vitamin B12"),
    ]:
        assert _short(raw) == expected

    out = day_card(DAY, PROGRESS, [], coverage={nid: 1.0 for nid in
                                                (1008, 1003, 1005, 1004, 1178, 1087)})
    # Whole names, not substrings: ", Ca" also matches the comma in a list
    # like "Vitamin B12, Calcium".
    for leak in ("Carbohydrate, by diff", "Vitamin C, total ascor", "PUFA",
                 "Calcium, Ca", "Iron, Fe", "Total lipid", "Fiber, total"):
        assert leak not in out, leak


def _supp(sid, name, schedule="daily"):
    return {"id": sid, "name": name, "schedule": schedule, "brand": None,
            "serving_desc": "1 capsule", "servings_per_day": 1,
            "n_nutrients": 1, "verified_at": None, "note": None, "active": True}


def test_the_pick_card_does_not_blame_the_schedule_for_what_was_already_logged():
    """Eight of nine were on a daily schedule, six were ticked because they had
    been logged that morning, and the card said "the rest are every other day
    or occasional" — which was simply untrue."""
    from nutrai.core.render import supplement_pick_card

    stack = [_supp(i, f"Supp {i}") for i in range(1, 10)]
    out = supplement_pick_card(stack, [1, 2, 3, 4, 5, 6], reason="logged")
    assert "already logged today" in out
    assert "every other day" not in out


def test_the_schedule_branch_names_what_is_not_due():
    """A category claim you cannot check becomes a list you can."""
    from nutrai.core.render import supplement_pick_card

    stack = [_supp(1, "Boron"), _supp(2, "Zinc", "alternate"), _supp(3, "Creatine")]
    out = supplement_pick_card(stack, [1, 3], reason="schedule")
    assert "Zinc" in out
    assert "2 of 3 due today" in out


def _slot_supp(i, name, slot=None):
    return {"id": i, "name": name, "slot": slot, "schedule": "daily",
            "serving_desc": "1 capsule", "servings_per_day": 1, "brand": None,
            "n_nutrients": 1, "verified_at": None, "note": None, "active": True}


def test_the_settings_table_stays_narrow_enough_not_to_wrap():
    """"4. Chelated Magnesium   🌙 before sleeping" wrapped every row onto two
    lines on a phone. An emoji is two cells wide and "before sleeping" is
    fifteen characters."""
    from nutrai.core.render import slot_settings_card

    stack = [_slot_supp(1, "Chelated Magnesium", "bed"),
             _slot_supp(2, "Marine Collagen", "breakfast")]
    out = slot_settings_card(stack, {})
    table = out.split("<pre>")[1].split("</pre>")[0]
    for line in table.splitlines():
        assert len(line) <= 34, (len(line), line)


def test_assigning_without_scheduling_says_nothing_will_fire():
    """Nine tidy assignments read as finished when no reminder can ever fire."""
    import datetime as dt

    from nutrai.core.render import slot_settings_card

    stack = [_slot_supp(1, "Zinc", "evening"), _slot_supp(2, "Boron", "bed")]
    assert "No reminders will fire" in slot_settings_card(stack, {})

    partial = slot_settings_card(stack, {"evening": dt.time(21, 0)})
    assert "No reminders will fire" not in partial
    assert "bedtime" in partial.split("⚠️")[1]

    done = slot_settings_card(stack, {"evening": dt.time(21, 0), "bed": dt.time(22, 30)})
    assert "⚠️" not in done


def test_percentages_sum_to_exactly_one_hundred():
    """A real cholesterol breakdown printed 75+18+2+2+2+1+1 = 101. Every share
    was right to the nearest point and the column still looked broken."""
    from nutrai.core.render import percent_split

    assert sum(percent_split([560, 138, 12, 12, 12, 10, 5])) == 100
    assert percent_split([560, 138, 12, 12, 12, 10, 5])[0] == 75

    for case in ([1, 1, 1], [1] * 7, [99, 1], [1, 2, 3, 4, 5, 6, 7, 8, 9],
                 [0.1, 0.1, 0.1, 99.7]):
        assert sum(percent_split(case)) == 100, case

    assert percent_split([]) == []
    assert percent_split([0, 0]) == [0, 0]


def test_repeats_are_one_row_and_keep_their_count():
    """Three identical espressos listed separately came out 2%, 2%, 1%:
    largest-remainder must break the tie somewhere, and identical rows with
    different percentages read as a bug however correct the arithmetic is."""
    import datetime as dt

    from nutrai.core.render import why_card

    at = dt.datetime(2026, 8, 16, 6, 35, tzinfo=dt.timezone.utc)
    entries = [
        {"name": "Espresso with milk", "slot": "drink", "logged_at": at + dt.timedelta(minutes=i * 30),
         "amount": 12.0, "parts": [{"label": "full fat milk", "food": "Milk", "amount": 12.0}]}
        for i in range(3)
    ]
    entries.append({"name": "Boiled eggs", "slot": "lunch",
                    "logged_at": at + dt.timedelta(hours=6), "amount": 560.0,
                    "parts": [{"label": "boiled eggs", "food": "Egg", "amount": 560.0}]})
    out = why_card("Cholesterol", "MG", dt.date(2026, 8, 16), entries, [], 300, True)

    assert "×3" in out, out
    assert out.count("Espresso") == 1
    # The grouped row carries the summed amount, not one serving's.
    assert "36" in out
