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
              "goal", "goal_weight_kg", "deficit_kcal", "tz", "targets_set_at_kg")}
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
