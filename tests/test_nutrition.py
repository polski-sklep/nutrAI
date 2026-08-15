import pytest

from nutrai.config import CARB, ENERGY_KCAL, FAT, FIBER, PROTEIN
from nutrai.core.nutrition import (
    ResolvedComponent,
    coverage,
    energy_cross_check,
    mass_sanity,
    scale_profile,
    total_nutrients,
)

# Per 100 g, roughly USDA raw 85/15 minced beef and raw white rice.
MINCE = {ENERGY_KCAL: 215.0, PROTEIN: 18.6, FAT: 15.0, CARB: 0.0, FIBER: 0.0, 1095: 4.2}
RICE = {ENERGY_KCAL: 365.0, PROTEIN: 7.1, FAT: 0.66, CARB: 80.0, FIBER: 1.3}
SAUCE = {ENERGY_KCAL: 60.0, PROTEIN: 1.0, FAT: 0.1, CARB: 14.0}  # no zinc row

PROFILES = {1: MINCE, 2: RICE, 3: SAUCE}


def test_scale_profile_is_linear():
    out = scale_profile(MINCE, 250.0)
    assert out[ENERGY_KCAL] == pytest.approx(537.5)
    assert out[PROTEIN] == pytest.approx(46.5)


def test_yield_factor_converts_cooked_mass_to_database_mass():
    """200 g of cooked mince came from ~267 g raw. Against a raw database row
    the cooked mass alone under-reports protein by a quarter."""
    naive = scale_profile(MINCE, 200.0)
    corrected = scale_profile(MINCE, 200.0, yield_factor=1.33)
    assert naive[PROTEIN] == pytest.approx(37.2)
    assert corrected[PROTEIN] == pytest.approx(49.48, rel=1e-3)
    assert corrected[PROTEIN] / naive[PROTEIN] == pytest.approx(1.33)


def test_total_nutrients_sums_across_components():
    comps = [
        ResolvedComponent("mince", 1, 200.0),
        ResolvedComponent("rice", 2, 80.0),
    ]
    t = total_nutrients(comps, PROFILES)
    assert t[ENERGY_KCAL] == pytest.approx(430 + 292)
    assert t[PROTEIN] == pytest.approx(37.2 + 5.68)


def test_missing_profile_is_skipped_not_zeroed():
    comps = [ResolvedComponent("mystery", 99, 100.0), ResolvedComponent("rice", 2, 100.0)]
    t = total_nutrients(comps, PROFILES)
    assert t[ENERGY_KCAL] == pytest.approx(365.0)


def test_coverage_reports_measured_fraction():
    comps = [ResolvedComponent("mince", 1, 200.0), ResolvedComponent("sauce", 3, 50.0)]
    assert coverage(comps, PROFILES, 1095) == pytest.approx(200 / 250)
    assert coverage(comps, PROFILES, ENERGY_KCAL) == pytest.approx(1.0)


def test_energy_cross_check_passes_on_consistent_food():
    t = total_nutrients([ResolvedComponent("mince", 1, 100.0)], PROFILES)
    ec = energy_cross_check(t)
    assert ec.ok, ec


def test_energy_cross_check_catches_a_wrong_match():
    """Grams right, food wrong: the macros no longer explain the energy."""
    broken = {ENERGY_KCAL: 215.0, PROTEIN: 18.6, FAT: 2.0, CARB: 0.0, FIBER: 0.0}
    ec = energy_cross_check(broken)
    assert not ec.ok
    assert ec.delta_pct < -50


def test_energy_cross_check_handles_missing_energy():
    ec = energy_cross_check({PROTEIN: 10.0})
    assert not ec.ok and ec.kcal_db == 0


def test_fibre_is_not_four_kcal_per_gram():
    high_fibre = {ENERGY_KCAL: 100.0, PROTEIN: 5.0, CARB: 20.0, FAT: 0.5, FIBER: 12.0}
    with_correction = energy_cross_check(high_fibre)
    naive = 5 * 4 + 20 * 4 + 0.5 * 9
    assert with_correction.kcal_atwater == pytest.approx(naive - 24.0)


def test_mass_sanity():
    comps = [ResolvedComponent("a", 1, 200.0), ResolvedComponent("b", 2, 200.0)]
    assert mass_sanity(comps, 402.0)
    assert mass_sanity(comps, None)
    assert not mass_sanity(comps, 700.0)
