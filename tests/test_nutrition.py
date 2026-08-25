import pytest

from nutrai.config import CARB, ENERGY_KCAL, FAT, FIBER, PROTEIN
from nutrai.core.nutrition import ResolvedComponent, coverage, energy_cross_check, normalise_energy, scale_profile, total_nutrients

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


def test_atwater_energy_fills_in_for_a_row_with_no_1008():
    """Most Foundation rows report energy only under 2047/2048.

    Without the fallback the component contributes 0 kcal, energy_cross_check
    cannot flag it (its guard skips kcal_db == 0), and the day silently loses
    its largest item. This is not invention: the number is the same USDA row's
    own energy under a different id.
    """
    foundation_beef = {PROTEIN: 18.6, FAT: 15.0, CARB: 0.0, 2047: 242.6, 2048: 247.8}
    filled = normalise_energy(foundation_beef)
    # Atwater *specific* factors are derived per food; general is the 4/4/9
    # approximation. Prefer specific.
    assert filled[ENERGY_KCAL] == pytest.approx(247.8)

    t = total_nutrients([ResolvedComponent("mince", 9, 250.0)], {9: filled})
    assert t[ENERGY_KCAL] == pytest.approx(619.5, rel=1e-3)


def test_normalise_energy_leaves_a_real_1008_alone():
    assert normalise_energy(MINCE)[ENERGY_KCAL] == pytest.approx(215.0)
    both = {ENERGY_KCAL: 215.0, 2048: 999.0}
    assert normalise_energy(both)[ENERGY_KCAL] == pytest.approx(215.0)


def test_normalise_energy_does_not_invent_energy():
    """A row that measured no energy at all still reports none — invariant 6."""
    assert ENERGY_KCAL not in normalise_energy({PROTEIN: 10.0})


def test_inverting_terms_block_an_auto_match():
    """A soy analogue is not the food, however similar the string.

    "Chicken, meatless, breaded, fried" scored high enough against a real
    breaded chicken to auto-match, and its macros are close enough that the
    Atwater cross-check passes — 400 g of fried chicken logged as a meat
    substitute, visible only as 17 g of fibre on a plate of chicken.
    """
    from nutrai.llm.parse import inverts_meaning

    asked = "panko-breaded fried chicken bites chicken breast, breaded, fried, panko crust"
    assert inverts_meaning(asked, "Chicken, meatless, breaded, fried")
    assert not inverts_meaning(asked, "Chicken, broilers or fryers, breast, breaded, fried")

    # Asking for the analogue still gets you the analogue.
    assert not inverts_meaning("vegan chicken nuggets", "Chicken, meatless, breaded, fried")
    assert not inverts_meaning("imitation crab salad", "Crab, imitation, made from surimi")

    for bad in ("Fish sticks, imitation", "Cheese, substitute, cheddar", "Bacon, vegetarian"):
        assert inverts_meaning("fish sticks cheese bacon", bad), bad


def test_stopword_labels_are_never_resolved_to_a_food():
    """A modifier parse produced a component labelled "and".

    The resolver matched it to "Seven and Seven" — a whisky cocktail — at 100 g
    and put it in a cappuccino. Trigram similarity has no notion of a stopword:
    "and" is a literal substring of that description, so it scored well and
    auto-accepted without a model ever reconsidering it.
    """
    from nutrai.llm.parse import is_non_food

    for junk in ("and", "the", " With ", "of", "a", "", "  ", "or,"):
        assert is_non_food(junk), junk

    # Short real foods must survive: length alone is not the test.
    for food in ("egg", "ham", "oil", "rye", "cod", "tea", "rice", "jam"):
        assert not is_non_food(food), food


def test_an_unmeasured_nutrient_is_not_reported_to_the_planner_as_zero():
    """The evidence pack's medians table must not zero-fill a missing median.

    `window_medians` returns a row only for a nutrient something logged in the
    window actually reports. Defaulting the miss to 0.0 turned "nothing you ate
    carries a selenium figure" into "you got no selenium", and the status column
    read "under by 55" — the phantom-deficiency failure invariant 6 exists to
    prevent, arriving in the one artefact a model draws conclusions from.
    """
    from nutrai.core.plan import _median_row

    absent = _median_row(1103, "Selenium, Se", "µg", None, None, 55.0, None)
    assert "no data" in absent
    assert "under by" not in absent
    # The median columns say nothing rather than saying nought.
    assert "0.0" not in absent

    # A real zero is still a real zero, and still reads as a shortfall.
    measured = _median_row(1103, "Selenium, Se", "µg", 0.0, 0.0, 55.0, None)
    assert "under by 55" in measured

    # And an ordinary in-range figure is untouched.
    ok = _median_row(1003, "Protein", "g", 142.0, 138.0, 130.0, None)
    assert ok.endswith("| ok")
    assert "142.0" in ok and "138.0" in ok


def test_a_slashed_label_is_searched_as_separate_foods():
    """"pancetta/guanciale" is two foods, and as one string it finds nothing.

    Searched whole it scores 0.200 at best — against `Guava paste` — which is
    under pg_trgm's 0.3 threshold, while plainto_tsquery treats the slashed
    string as a single token matching no description. Zero candidates, and a
    card telling you the database holds nothing like cured pork, which holds
    eleven bacon rows and a pork jowl.
    """
    from nutrai.llm.parse import _alternatives

    assert _alternatives("pancetta/guanciale") == ["pancetta", "guanciale"]
    assert _alternatives("olive oil/rendered fat") == ["olive oil", "rendered fat"]
    assert _alternatives("bacon or pancetta") == ["bacon", "pancetta"]

    # Only a genuine choice expands; an ordinary label is left alone, and a
    # trailing conjunction leaves one usable side, which is not a choice.
    assert _alternatives("chicken breast") == []
    assert _alternatives("cheese, parmesan, grated") == []
    assert _alternatives("bacon or") == []
