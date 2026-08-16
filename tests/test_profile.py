"""The numbers behind the targets.

`bootstrap.py` took sex, age, height, activity and deficit, derived a day's
targets from them and discarded all five. A 2,418 kcal ceiling with nothing
behind it cannot be explained, checked, or recomputed when you change.
"""

from __future__ import annotations

import datetime as dt

import pytest

from nutrai.core import profile as prof
from nutrai.core import render


def test_age_is_derived_from_a_birth_date_not_stored():
    """An age is only true for a year, and nothing would know to increment it."""
    born = dt.date(1990, 6, 15)
    assert prof.age_years(born, dt.date(2026, 6, 14)) == 35
    assert prof.age_years(born, dt.date(2026, 6, 15)) == 36
    assert prof.age_years(None) is None


def test_derivation_matches_mifflin_st_jeor():
    targets, w = prof.derive_targets(
        sex="male", weight_kg=78, height_cm=183, age=34,
        activity=1.55, deficit=500,
    )
    assert w["ree"] == pytest.approx(10 * 78 + 6.25 * 183 - 5 * 34 + 5)
    assert w["tdee"] == pytest.approx(w["ree"] * 1.55)
    assert w["kcal"] == pytest.approx(w["tdee"] - 500)
    assert targets[1008] == (None, round(w["kcal"]))


def test_an_incomplete_profile_refuses_rather_than_defaults():
    """A target computed from a guessed height looks exactly like a real one."""
    with pytest.raises(prof.IncompleteProfile) as e:
        prof.derive_targets(
            sex="male", weight_kg=78, height_cm=None, age=34,
            activity=1.55, deficit=500,
        )
    assert "height" in str(e.value)


def test_female_rda_overrides_are_applied():
    targets, _ = prof.derive_targets(
        sex="female", weight_kg=62, height_cm=168, age=30,
        activity=1.4, deficit=300,
    )
    assert targets[1089][0] == 18       # iron, premenopausal
    assert targets[1079][0] == 25       # fibre


def test_bootstrap_uses_the_same_derivation():
    """Two callers computing targets two ways is how a system disagrees with
    itself. bootstrap must import this, not carry a copy."""
    import inspect

    import scripts.bootstrap as bs

    assert bs.derive_targets is prof.derive_targets
    assert "mifflin_st_jeor" not in inspect.getsource(bs)


# ------------------------------------------------------------------ the card


class _Row(dict):
    """asyncpg Records are read by key; a dict is close enough here."""


def _data(**over):
    user = _Row({
        "display_name": "Jacob", "sex": "male", "birth_date": dt.date(1991, 3, 2),
        "height_cm": 183, "activity_factor": 1.55, "goal": "lose",
        "goal_weight_kg": 74, "deficit_kcal": 500, "tz": "Europe/Warsaw",
        "targets_set_at_kg": 78.0,
        "measured_tdee_kcal": None, "measured_tdee_days": None,
        "measured_tdee_on": None,
    })
    user.update(over.pop("user", {}))
    d = {"user": user, "weight_kg": 78.0, "weighed_on": dt.date(2026, 8, 16),
         "energy_target": 2418.0, "targets_from": dt.date(2026, 8, 16)}
    d.update(over)
    return d


def test_the_card_numbers_every_editable_line():
    card = render.profile_card(_data(), dt.date(2026, 8, 16))
    for i in range(1, len(render.PROFILE_ROWS) + 1):
        assert f"{i}." in card


def test_weight_is_shown_but_not_numbered():
    """It is a dated measurement, not a setting. /weight is where it is edited,
    and a second editable copy would go stale the first time it is used."""
    assert "weight_kg" not in [f for f, _l, _h in render.PROFILE_ROWS]
    card = render.profile_card(_data(), dt.date(2026, 8, 16))
    assert "78 kg" in card


def test_an_empty_profile_says_what_is_missing_rather_than_showing_zeros():
    empty = {k: None for k in
             ("display_name", "sex", "birth_date", "height_cm", "activity_factor",
              "goal", "goal_weight_kg", "deficit_kcal", "tz", "targets_set_at_kg",
              "measured_tdee_kcal", "measured_tdee_days", "measured_tdee_on")}
    card = render.profile_card(
        _data(user=empty, weight_kg=None, weighed_on=None, energy_target=None,
              targets_from=None),
        dt.date(2026, 8, 16),
    )
    assert "0 cm" not in card and "0 kcal" not in card
    assert "—" in card
    assert "sex" in card and "height" in card


def test_a_drifted_weight_is_flagged_rather_than_silently_recomputed():
    """Invariant 3: targets are versioned, never rewritten under you. So the
    card raises it and a button applies it — a weigh-in must not change what
    yesterday was judged against."""
    card = render.profile_card(_data(weight_kg=71.0), dt.date(2026, 8, 16))
    assert "⚠️" in card and "78 kg" in card
    assert "Recalculate" in card

    steady = render.profile_card(_data(weight_kg=77.0), dt.date(2026, 8, 16))
    assert "⚠️" not in steady


def test_the_card_escapes_dynamic_text():
    card = render.profile_card(_data(user={"display_name": "Jacob & <b>Co</b>"}),
                               dt.date(2026, 8, 16))
    assert "&amp;" in card and "<b>Co</b>" not in card


def test_labels_do_not_run_into_their_values():
    """"8. Daily deficit" is exactly 16 characters, which a hardcoded 16-wide
    column swallowed whole. Pad from the content."""
    card = render.profile_card(_data(), dt.date(2026, 8, 16))
    for line in card.splitlines():
        if line[:1].isdigit() and ". " in line:
            label, _, rest = line.partition(". ")
            assert "  " in rest, line


# ------------------------------------------------- what a person actually types


@pytest.mark.parametrize("raw,expected", [
    ("M", "male"), ("m", "male"), ("male", "male"), ("Male", "male"),
    ("F", "female"), ("woman", "female"),
])
def test_sex_accepts_the_letter_people_type(raw, expected):
    from nutrai.bot import PROFILE_VALIDATORS
    assert PROFILE_VALIDATORS["sex"](raw) == expected


@pytest.mark.parametrize("raw", ["21/09/1991", "1991-09-21", "21.09.1991", "21-09-1991"])
def test_birth_date_accepts_day_first_forms(raw):
    from nutrai.bot import PROFILE_VALIDATORS
    assert PROFILE_VALIDATORS["birth_date"](raw) == dt.date(1991, 9, 21)


@pytest.mark.parametrize("raw,expected", [("176cm", 176.0), ("176 cm", 176.0), ("176", 176.0)])
def test_height_tolerates_the_unit(raw, expected):
    from nutrai.bot import PROFILE_VALIDATORS
    assert PROFILE_VALIDATORS["height_cm"](raw) == expected


def test_a_future_or_absurd_birth_date_is_refused():
    from nutrai.bot import PROFILE_VALIDATORS
    with pytest.raises(ValueError):
        PROFILE_VALIDATORS["birth_date"]("21/09/2099")


def test_numbered_lines_are_profile_edits():
    from nutrai.bot import _profile_edits
    assert _profile_edits("2. M\n3. 21/09/1991\n4. 176cm") == [
        (2, "M"), (3, "21/09/1991"), (4, "176cm"),
    ]


def test_a_meal_is_not_mistaken_for_a_profile_edit():
    """"2 eggs" and "2. M" differ only by punctuation, and guessing wrong
    either loses a meal or writes nonsense into the profile."""
    from nutrai.bot import _profile_edits
    assert _profile_edits("2 eggs, 3 rashers bacon") is None
    assert _profile_edits("250 g chicken and rice") is None
    assert _profile_edits("2. M\ngnocchi with pesto") is None   # partial: not profile


@pytest.mark.parametrize("raw,expected", [
    ("Moderate", 1.55), ("moderate", 1.55), ("3", 1.55),
    ("Seated", 1.25), ("1", 1.25), ("Heavy", 1.85), ("1.6", 1.6),
])
def test_activity_accepts_the_word_the_card_shows(raw, expected):
    """The card prints "Moderate" and the validator took only numbers, so the
    one word on screen was the one word it refused."""
    from nutrai.bot import PROFILE_VALIDATORS
    assert PROFILE_VALIDATORS["activity_factor"](raw) == expected


@pytest.mark.parametrize("raw", [
    "Muscle gain and fat loss", "recomp", "recomposition", "lose fat and build muscle",
])
def test_recomposition_is_a_goal_in_its_own_right(raw):
    """lose/maintain/gain had no room for it, and an enum that refuses the true
    answer collects false ones."""
    from nutrai.bot import PROFILE_VALIDATORS
    assert PROFILE_VALIDATORS["goal"](raw) == "recomp"


def test_the_goal_sets_the_protein_floor():
    base = dict(sex="male", weight_kg=78, height_cm=173, age=34,
                activity=1.55, deficit=400)
    recomp, _ = prof.derive_targets(**base, goal="recomp")
    cut, _ = prof.derive_targets(**base, goal="lose")
    assert recomp[1003][0] == round(2.2 * 78)
    assert cut[1003][0] == round(2.0 * 78)
    assert recomp[1003][0] > cut[1003][0]


def test_numeric_columns_do_not_store_a_floats_binary_expansion():
    """75.2 stored itself as
    75.2000000000000028421709430404007434844970703125, and 1.55 as
    1.5500000000000000444089209850062616169452667236328125. Rounding the float
    first cannot fix it — those *are* those values in binary."""
    from nutrai.db import num

    assert str(num(75.2, 2)) == "75.2"
    assert str(num(1.55)) == "1.55"
    assert str(num(9.2, 1)) == "9.2"
    assert num(None) is None
    # Integral values normalise without an exponent creeping in.
    assert str(num(180.0)) == "180"
    assert str(num(2000.0)) == "2000"


def test_a_goal_that_needs_a_deficit_says_so_when_none_is_set():
    """Goal "build muscle, lose fat", target 2,586, maintenance 2,586. Every
    number correct, and the result is not what was asked for — the arithmetic
    cannot see the contradiction, so it has to be named."""
    assert prof.goal_conflict("recomp", None) is not None
    assert prof.goal_conflict("recomp", 0) is not None
    assert prof.goal_conflict("lose", None) is not None
    assert "maintenance" in prof.goal_conflict("recomp", None)

    # Set, and it goes quiet.
    assert prof.goal_conflict("recomp", 350) is None
    assert prof.goal_conflict("lose", 500) is None
    # Maintaining on maintenance is not a conflict.
    assert prof.goal_conflict("maintain", None) is None
    assert prof.goal_conflict(None, None) is None


def test_gaining_needs_a_surplus_not_a_deficit():
    assert prof.goal_conflict("gain", 0) is not None
    assert prof.goal_conflict("gain", 500) is not None      # a deficit, while bulking
    assert prof.goal_conflict("gain", -300) is None


def test_the_recalculation_card_carries_the_warning():
    working = {"ree": 1668.0, "tdee": 2586.0, "kcal": 2586.0,
               "protein": 165.0, "fat": 60.0, "carb": 346.0}
    out = render.profile_recalc_card(working, 22, 75.2, goal="recomp", deficit=None)
    assert "⚠️" in out and "maintenance" in out
    quiet = render.profile_recalc_card(working, 22, 75.2, goal="recomp", deficit=350)
    assert "⚠️" not in quiet


def test_the_profile_card_flags_it_before_you_recalculate():
    card = render.profile_card(_data(user={"deficit_kcal": None, "goal": "recomp"}),
                               dt.date(2026, 8, 16))
    assert "⚠️" in card and "deficit" in card


# ------------------------------------------ the measurement beats the equation


def test_a_measured_tdee_replaces_the_equation_rather_than_blending_with_it():
    """A measurement and an estimate of the same quantity do not average into
    something better than the measurement. They average into something you can
    no longer explain."""
    base = dict(sex="male", weight_kg=75.2, height_cm=173, age=34,
                activity=1.55, deficit=350, goal="recomp")
    _t, equation = prof.derive_targets(**base)
    _t2, measured = prof.derive_targets(**base, measured_tdee=2410)

    assert measured["tdee"] == 2410
    assert measured["kcal"] == 2410 - 350
    # Untouched: the equation's REE is still reported, because the activity
    # factor is what the measurement replaces, not the resting rate.
    assert measured["ree"] == equation["ree"]
    assert measured["tdee_measured"] == 1.0
    assert equation["tdee_measured"] == 0.0


def test_the_implied_activity_factor_is_recovered_from_the_measurement():
    """The one free parameter nothing ever checked: you pick "Moderate" off a
    list and it multiplies your BMR forever."""
    ree = prof.mifflin_st_jeor("male", 75.2, 173, 34)
    assert prof.implied_activity_factor(ree * 1.42, ree) == 1.42
    assert prof.implied_activity_factor(2410, ree) == round(2410 / ree, 2)


def test_an_absurd_implied_factor_is_refused_rather_than_written_back():
    """Outside 1.0-2.5 the arithmetic has stopped describing activity and
    started absorbing an error — an unlogged week, a scale read in pounds —
    and writing it back would launder that error into the profile."""
    ree = prof.mifflin_st_jeor("male", 75.2, 173, 34)
    assert prof.implied_activity_factor(ree * 0.6, ree) is None
    assert prof.implied_activity_factor(ree * 3.1, ree) is None
    assert prof.implied_activity_factor(2400, 0) is None


def test_the_card_says_which_of_the_two_the_target_rests_on():
    card = render.profile_card(
        _data(user={"measured_tdee_kcal": 2410, "measured_tdee_days": 23}),
        dt.date(2026, 8, 16))
    assert "measured" in card and "2,410" in card
    assert "23 days" in card

    equation = render.profile_card(_data(), dt.date(2026, 8, 16))
    assert "measured" not in equation
