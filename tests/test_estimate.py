import pytest

from nutrai.core.estimate import MassEstimate, choose_mass, portion_prior, sigma_for
from nutrai.core.nutrition import ResolvedComponent

ENERGY = 1008


def test_weighed_mass_is_near_certain():
    s = sigma_for(250.0, "scale")
    assert s == pytest.approx(1.25)
    assert s / 250 < 0.01


def test_visual_estimate_is_not():
    assert sigma_for(100.0, "estimate") == pytest.approx(35.0)


def test_explicit_range_overrides_the_default():
    """A model-supplied 120-260 g range is better information than our prior
    about how bad visual estimates are."""
    assert sigma_for(190.0, "estimate", low=120.0, high=260.0) == pytest.approx(35.0)
    assert sigma_for(190.0, "estimate", low=180.0, high=200.0) == pytest.approx(5.0)


def test_prior_needs_enough_consistent_history():
    assert portion_prior([118, 122]) is None                     # too few
    assert portion_prior([60, 118, 122, 400]) is None            # too scattered
    prior = portion_prior([115, 118, 120, 122, 124])
    assert prior is not None
    med, sd = prior
    assert med == pytest.approx(120.0)
    assert 0 < sd < 20


def test_weighed_beats_prior():
    m = choose_mass(248.0, "scale", history=[100, 101, 102, 103])
    assert m.source == "scale" and m.grams == 248.0


def test_prior_beats_a_visual_guess():
    m = choose_mass(150.0, "estimate", history=[115, 118, 120, 122, 124])
    assert m.source == "prior"
    assert m.grams == pytest.approx(120.0)
    assert "past weighings" in m.note


def test_prior_yields_when_today_is_genuinely_different():
    """Three times the usual portion is not a measurement error; the photo is
    the better witness and the prior must not overwrite it."""
    m = choose_mass(400.0, "estimate", history=[115, 118, 120, 122, 124])
    assert m.source == "estimate" and m.grams == 400.0


def test_range_is_two_sigma():
    m = MassEstimate(200.0, 20.0, "estimate")
    assert (m.low, m.high) == (160.0, 240.0)


