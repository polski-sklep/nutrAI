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
    assert "(from 42% of food)" in out
    # Still listed — 42% covered and nothing found is real information.
    assert "▽ Vitamin B12" in out


def test_full_coverage_adds_no_noise():
    coverage = {nid: 1.0 for nid in (1008, 1003, 1005, 1004, 1178, 1087)}
    out = day_card(DAY, PROGRESS, [], coverage=coverage)
    assert "from" not in out
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
    sc = day_score(prog, {1178: 0.0})
    reached, assessable, short = sc.reached, sc.assessable, sc.short
    breached, nearing, unmeasured = sc.breached, sc.nearing, sc.unmeasured
    # Only Protein has a floor and is measured; B-12's floor is unmeasured.
    assert (reached, assessable, unmeasured) == (1, 1, 1)
    assert short == []
    # Fat is over its ceiling — reported, but not as a failed "target".
    assert breached == ["Fat 123%"]


def test_day_score_counts_a_real_shortfall():
    from nutrai.core.render import day_score

    prog = [row(1003, "Protein", "G", 50, lo=180, state="under")]
    sc = day_score(prog, {1003: 1.0})
    reached, assessable, short = sc.reached, sc.assessable, sc.short
    breached, nearing, unmeasured = sc.breached, sc.nearing, sc.unmeasured
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
    assert "0 of 1 fully met" in out
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
    assert "0 of 2 fully met" in out, out
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
    assert "1 of 1 fully met" in out


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
    assert "taken so far today" in out
    assert "every other day" not in out

    # And with nothing ticked it says what a tick means, rather than
    # implying the list is a plan you have failed to follow.
    fresh = supplement_pick_card(stack, [], reason="logged")
    assert "Nothing ticked yet today" in fresh
    assert "a tick is a record, not a plan" in fresh


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


def test_the_confirm_card_names_the_food_row_it_matched():
    """"pickle juice" resolved to "Relish, pickle" — a sweet condiment at
    130 kcal against a brine that is essentially water — and the card showed
    only the words you typed. Choosing the food row is the most error-prone
    step in the pipeline and it was the only one you could not see."""
    from nutrai.core.nutrition import ResolvedComponent
    from nutrai.core.render import confirm_card

    comps = [ResolvedComponent("pickle juice", 2710079, 100.0, grams_source="stated")]
    out = confirm_card("Pickle juice", comps, {1008: 130.0}, confidence=0.85,
                       warnings=[], matched={2710079: "Relish, pickle"})
    assert "Relish, pickle" in out

    # Silent when the row is plainly the thing you named.
    comps = [ResolvedComponent("chia seeds", 2707590, 24.0, grams_source="stated")]
    quiet = confirm_card("Chia pudding", comps, {1008: 117.0}, confidence=0.9,
                         warnings=[], matched={2707590: "Chia seeds"})
    assert "→" not in quiet


def test_the_score_weights_partial_progress_not_just_boxes_ticked():
    """"8 of 13 met" throws away the difference between a day at 95% of every
    remaining floor and one at nothing, which is most of what you want to know
    before deciding what to eat next."""
    from nutrai.core.render import day_score

    nearly = [row(1003, "Protein", "G", 160, lo=165, state="under"),
              row(1079, "Fiber, total dietary", "G", 36, lo=38, state="under")]
    barely = [row(1003, "Protein", "G", 8, lo=165, state="under"),
              row(1079, "Fiber, total dietary", "G", 2, lo=38, state="under")]

    a, b = day_score(nearly), day_score(barely)
    assert a.reached == b.reached == 0          # identical on the old measure
    assert a.covered > 0.9 and b.covered < 0.1  # and nothing like each other


def test_one_overshot_floor_cannot_cover_for_an_untouched_one():
    """Three times your protein does not make up for no iron, and a score that
    let it would reward the easy floor over the one you are missing."""
    from nutrai.core.render import day_score

    lopsided = [row(1003, "Protein", "G", 500, lo=165),
                row(1089, "Iron, Fe", "MG", 0, lo=8, state="under")]
    assert abs(day_score(lopsided).covered - 0.5) < 1e-9


def test_a_floor_barely_touched_is_not_called_part_way():
    """0.2 g of protein against a 180 g floor is 0.1%, and calling that
    "part-way" beside a headline of 0% reads as a contradiction."""
    from nutrai.core.render import day_score, score_line

    trace = [row(1003, "Protein", "G", 0.2, lo=180, state="under"),
             row(1079, "Fiber, total dietary", "G", 0.2, lo=38, state="under")]
    sc = day_score(trace)
    assert sc.partial == 0
    assert len(sc._untouched) == 2
    assert "not started" in score_line(trace, {1003: 1.0, 1079: 1.0})


def test_the_attention_list_says_how_many_are_fine():
    """The section shows only what needs attention, which is right — but with
    nothing said about the rest a short list reads as missing data rather than
    as good news."""
    prog = [
        row(1008, "Energy", "KCAL", 2143, hi=2286),
        row(1003, "Protein", "G", 114, lo=165, state="under"),
        row(1005, "Carbohydrate, by difference", "G", 250, hi=312),
        row(1004, "Total lipid (fat)", "G", 78, hi=78),
        row(1079, "Fiber, total dietary", "G", 30, lo=38, state="under"),
        row(1087, "Calcium, Ca", "MG", 1357, lo=1000),
        row(1089, "Iron, Fe", "MG", 13, lo=8),
        row(1095, "Zinc, Zn", "MG", 21, lo=11),
    ]
    out = day_card(DAY, prog, [], coverage={r["nutrient_id"]: 1.0 for r in prog})
    assert "Worth a look (1 of 4)" in out, out
    assert "3 other nutrients are where they should be" in out

    # /today all lists them instead of counting them.
    every = day_card(DAY, prog, [], show_all=True,
                     coverage={r["nutrient_id"]: 1.0 for r in prog})
    assert "where they should be" not in every
    assert "Calcium" in every


def test_a_ceiling_at_zero_is_not_a_row():
    """"Alcohol 0 g, 0% of a 16 g ceiling" tells you nothing you did not know
    from having drunk none. It belongs on the card only once there is some."""
    prog = [
        row(1008, "Energy", "KCAL", 2143, hi=2286),
        row(1003, "Protein", "G", 165, lo=165),
        row(1005, "Carbohydrate, by difference", "G", 250, hi=312),
        row(1004, "Total lipid (fat)", "G", 60, hi=78),
        row(1018, "Alcohol, ethyl", "G", 0, hi=16),
    ]
    cov = {r["nutrient_id"]: 1.0 for r in prog}
    assert "Alcohol" not in day_card(DAY, prog, [], show_all=True, coverage=cov)

    drank = prog[:-1] + [row(1018, "Alcohol, ethyl", "G", 24, hi=16, state="over")]
    assert "Alcohol" in day_card(DAY, drank, [], show_all=True,
                                 coverage={r["nutrient_id"]: 1.0 for r in drank})


def test_no_coverage_note_where_absence_means_zero():
    """A pear has no alcohol row because pears contain none, not because
    nobody looked. Annotating those invents a doubt that does not exist."""
    prog = [row(1057, "Caffeine", "MG", 191, hi=400),
            row(1087, "Calcium, Ca", "MG", 400, lo=1000, state="under")]
    out = day_card(DAY, prog, [], show_all=True, coverage={1057: 0.88, 1087: 0.88})
    # The table rows, not the "still to go" summary that also names them.
    caffeine_line = next(ln for ln in out.splitlines() if "Caffeine" in ln and "mg" in ln)
    calcium_line = next(ln for ln in out.splitlines() if "Calcium" in ln and "mg" in ln)
    assert "from" not in caffeine_line
    assert "from" in calcium_line


def test_a_weighted_floor_moves_the_score_and_is_named():
    """A headline that quietly means something different from yesterday's is
    worse than no headline."""
    from nutrai.core.render import day_score, score_line

    def prog(protein_weight):
        return [
            {**row(1003, "Protein", "G", 60, lo=165, state="under"), "weight": protein_weight},
            {**row(1089, "Iron, Fe", "MG", 8, lo=8), "weight": 1},
        ]

    plain, heavy = day_score(prog(1)), day_score(prog(2.5))
    assert plain.covered > heavy.covered      # the miss now costs more
    assert heavy.weighted_by == ("Protein ×2.5",)
    # Not repeated on the day card: it is stated when you set it and shown in
    # /target, and on a card read six times a day it is a standing footnote
    # about a decision already made.
    assert "weighted" not in score_line(prog(2.5), {1003: 1.0, 1089: 1.0})


def test_an_unbreached_ceiling_is_not_a_nutrient_that_is_fine():
    """With nothing logged, every ceiling is unbreached — and the card said
    "6 other nutrients are where they should be" on an empty day. Same
    category error as counting ceilings toward the score."""
    empty = [
        row(1008, "Energy", "KCAL", 0, hi=2286),
        row(1005, "Carbohydrate, by difference", "G", 0, hi=312),
        row(1004, "Total lipid (fat)", "G", 0, hi=78),
        row(1093, "Sodium, Na", "MG", 0, hi=2300),
        row(1253, "Cholesterol", "MG", 0, hi=300),
        row(1003, "Protein", "G", 0, lo=165, state="under"),
    ]
    out = day_card(DAY, empty, [], coverage={r["nutrient_id"]: 1.0 for r in empty})
    assert "where they should be" not in out, out


def test_the_morning_note_names_one_thing_not_five():
    """A morning message opening with five corrections is one you learn to
    swipe away, and the point of it is to be read."""
    from nutrai.core.render import morning_note

    heavy = [
        row(1253, "Cholesterol", "MG", 749, hi=300, state="over"),
        row(1093, "Sodium, Na", "MG", 2738, hi=2300, state="over"),
        row(1003, "Protein", "G", 114, lo=165, state="under"),
        row(1079, "Fiber, total dietary", "G", 30, lo=38, state="under"),
    ]
    out = morning_note("jacob", heavy, {r["nutrient_id"]: 1.0 for r in heavy})
    assert "Good morning, Jacob" in out
    assert out.count("went over") == 1
    assert "Cholesterol" in out and "Sodium" not in out
    assert "egg yolks" in out          # the lever, where an honest one exists


def test_the_morning_note_praises_a_clean_day_and_says_nothing_on_an_empty_one():
    from nutrai.core.render import morning_note

    clean = [row(1003, "Protein", "G", 170, lo=165),
             row(1093, "Sodium, Na", "MG", 1800, hi=2300)]
    assert "Hard to improve on" in morning_note(
        "jacob", clean, {r["nutrient_id"]: 1.0 for r in clean})
    assert "Nothing logged yesterday" in morning_note("jacob", [])


def test_a_shortfall_is_named_when_nothing_was_breached():
    from nutrai.core.render import morning_note

    short = [row(1003, "Protein", "G", 60, lo=165, state="under"),
             row(1093, "Sodium, Na", "MG", 1200, hi=2300)]
    out = morning_note(None, short, {r["nutrient_id"]: 1.0 for r in short})
    assert "came up short" in out and "Protein" in out
    assert "Good morning." in out      # no name, no dangling comma


def _entry(name, protein, kcal=200):
    import datetime as dt
    return {"name": name, "protein": protein, "kcal": kcal, "slot": "lunch",
            "logged_at": dt.datetime(2026, 8, 17, 12, 0, tzinfo=dt.timezone.utc)}


def test_protein_spread_reports_distribution_not_a_cap():
    """There is no absorption ceiling to model. Trommelen et al. (2023) found
    100 g produced a greater and longer response than 25 g, so discounting
    protein above a per-meal figure would understate what was eaten."""
    from nutrai.core.render import protein_spread

    out = protein_spread([_entry("eggs", 42), _entry("shake", 24), _entry("beef", 22)])
    assert "88 g" in out and "3 servings" in out
    assert "42 g · 24 g · 22 g" in out


def test_a_coffee_is_not_a_protein_serving():
    """3 g in a latte is not a fourth meal, and counting it as one makes an
    uneven day look even."""
    from nutrai.core.render import protein_spread

    out = protein_spread([_entry("beef", 60), _entry("coffee", 3), _entry("tea", 1)])
    assert out is None          # only one real serving


def test_a_lopsided_day_is_named_and_an_even_one_is_not():
    from nutrai.core.render import protein_spread

    lopsided = protein_spread([_entry("steak", 90), _entry("toast", 10)])
    assert "Most of it in one meal" in lopsided

    even = protein_spread([_entry("a", 40), _entry("b", 35), _entry("c", 35)])
    assert "Most of it in one meal" not in even


def test_the_worst_breach_is_named_first():
    """Unsorted, these came out in nutrient-id order — so the morning note
    named carbs at 103% on a day with cholesterol at 208%."""
    from nutrai.core.render import day_score

    prog = [
        row(1005, "Carbohydrate, by difference", "G", 321, hi=312, state="over"),
        row(1253, "Cholesterol", "MG", 623, hi=300, state="over"),
        row(1093, "Sodium, Na", "MG", 3703, hi=2300, state="over"),
    ]
    sc = day_score(prog, {r["nutrient_id"]: 1.0 for r in prog})
    assert sc.breached[0].startswith("Cholesterol"), sc.breached


def test_the_morning_note_leads_with_coverage():
    from nutrai.core.render import morning_note

    prog = [row(1003, "Protein", "G", 148, lo=165, state="under"),
            row(1253, "Cholesterol", "MG", 623, hi=300, state="over")]
    out = morning_note("jacob", prog, {r["nutrient_id"]: 1.0 for r in prog})
    assert out.index("covered") < out.index("went over"), out
    assert "floors fully met" in out


def test_the_icon_comes_from_the_food_not_the_hour():
    """The slot was doing this job and could not: a cereal, a hummus and a bun
    were all 🥗 because all three were eaten at lunch, and every drink was a
    coffee cup."""
    from nutrai.core.render import dish_icon

    assert dish_icon("Espresso with milk and sugar", "drink") == "☕"
    assert dish_icon("Ginger tea with honey and lemon", "dinner") == "🍵"
    assert dish_icon("Protein shake", "drink") == "🥤"
    assert dish_icon("Lemon lime water", "breakfast") == "💧"
    assert dish_icon("Nesquik cereal", "lunch") == "🥣"
    assert dish_icon("Blueberry bun (half)", "lunch") == "🍞"

    # Ordering matters: "pickle juice" is a brine, not a juice box, and
    # "coffee with milk" is a coffee.
    assert dish_icon("Pickle juice", "drink") == "🥒"
    assert dish_icon("Coffee with milk", "drink") == "☕"

    # And a name that says nothing falls back to the hour, visibly generic
    # rather than confidently wrong.
    assert dish_icon("Something I ate", "snack") == "🍪"
    assert dish_icon("", None) == "•"


def _macro_rows():
    return [
        dict(nutrient_id=1008, nutrient_name="Energy", unit="kcal",
             amount=794, min_amount=None, max_amount=2286, state="ok", amount_supplement=0),
        dict(nutrient_id=1003, nutrient_name="Protein", unit="g",
             amount=18, min_amount=165, max_amount=None, state="under", amount_supplement=0),
    ]


def test_ceilings_and_floors_are_grouped_not_suffixed():
    """"794 of 2,286 kcal ceiling" and "18 of 165 g target" are the same shape.

    The only thing separating "you have 1,492 kcal in hand" from "you need 147
    g more" was one word at the end of the line, after the number, where the
    eye arrives last. Five such rows read as one list of five things going the
    same way. A heading cannot be skimmed past, and it lets the row drop the
    word.
    """
    out = logged_card("Cake", {}, _macro_rows())
    assert "Stay under" in out and "Reach" in out
    assert "kcal ceiling" not in out and "g target" not in out
    # Floors lead — the first line of a card sets the agenda, and "eat more
    # protein" is a better agenda than "you have 2,128 kcal left".
    assert out.index("Reach") < out.index("Protein") < out.index("Stay under")
    assert out.index("Stay under") < out.index("Energy")


def test_a_ceiling_reports_headroom_and_then_the_breach():
    """"0 left" is true and useless. How far over is the number you act on."""
    rows = _macro_rows()
    assert "1,492 kcal left" in logged_card("Cake", {}, rows)
    rows[0]["amount"] = 2500
    out = logged_card("Cake", {}, rows)
    assert "214 kcal over" in out and "left" not in out.split("Reach")[0]


def test_history_card_says_what_it_is_not_showing():
    """A capped list that does not mention the cap reads as the whole diary.

    Then a week you logged but cannot see looks like a week you did not eat,
    which is the one thing a diary must never imply.
    """
    from nutrai.core.render import history_card

    rows = [dict(id=1, local_date=dt.date(2026, 8, 18),
                 logged_at=dt.datetime(2026, 8, 18, 8, 39, tzinfo=dt.timezone.utc),
                 slot="breakfast", name="espresso", source="text",
                 kcal=98, protein=5)]
    span = {"first_day": dt.date(2026, 8, 1), "last_day": dt.date(2026, 8, 18),
            "entries": 47, "days": 14}
    out = history_card(rows, span, 14, tz="Europe/Warsaw")
    assert "1 of 47 entries" in out
    # Local time, not UTC. logged_at is stored in UTC and 08:39 there is 10:39
    # in Warsaw; a diary in the wrong timezone is a diary of someone else's day.
    assert "10:39" in out

    span["entries"] = 1
    assert "That is everything" in history_card(rows, span, 14, tz="Europe/Warsaw")
