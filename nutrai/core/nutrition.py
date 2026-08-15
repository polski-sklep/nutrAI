"""Deterministic nutrient arithmetic.

No model is involved past this line. A component carries (fdc_id, grams,
yield_factor); the nutrient profile comes from USDA. This is the whole reason
"full Cronometer parity" costs nothing extra in tokens: 80 nutrients and 4
nutrients are the same single SQL join.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import ATWATER, CARB, ENERGY_KCAL, ENERGY_TOLERANCE, FAT, FIBER, PROTEIN


@dataclass(frozen=True)
class ResolvedComponent:
    label: str
    fdc_id: int
    grams: float
    # Multiply logged grams by this to get grams of the USDA row as described.
    # You weighed 200 g of cooked mince; the USDA row is raw; raw mince loses
    # ~25% water, so 200 g cooked came from ~267 g raw -> yield_factor 1.33.
    # Get this wrong and you are wrong by 30% on your largest protein source,
    # which dwarfs every token you will ever save.
    yield_factor: float = 1.0
    # 1-sigma uncertainty on `grams`, and how the mass was arrived at. Carried
    # from the estimator through to the database so a day's error bar can be
    # recomputed from stored rows rather than re-derived from a guess.
    sigma: float = 0.0
    grams_source: str = "estimate"


def scale_profile(profile: dict[int, float], grams: float, yield_factor: float = 1.0) -> dict[int, float]:
    """profile is per 100 g of the USDA row. Returns absolute amounts."""
    k = (grams * yield_factor) / 100.0
    return {nid: amt * k for nid, amt in profile.items()}


def total_nutrients(
    components: list[ResolvedComponent],
    profiles: dict[int, dict[int, float]],
) -> dict[int, float]:
    """Sum every nutrient across every component.

    `profiles` maps fdc_id -> {nutrient_id: amount_per_100g}. Missing nutrients
    are treated as absent, not as zero, at the reporting layer — see
    `coverage()`. Silently summing nulls to zero is how micronutrient trackers
    tell you that you got 0 mcg of selenium when the truth is that nobody
    measured the selenium in your ready meal.
    """
    out: dict[int, float] = {}
    for c in components:
        prof = profiles.get(c.fdc_id)
        if not prof:
            continue
        for nid, amt in scale_profile(prof, c.grams, c.yield_factor).items():
            out[nid] = out.get(nid, 0.0) + amt
    return out


def coverage(
    components: list[ResolvedComponent],
    profiles: dict[int, dict[int, float]],
    nutrient_id: int,
) -> float:
    """Fraction of the meal's mass whose food row actually reports this nutrient.

    Report it next to any micronutrient total. 'Selenium 41 µg (78% of the
    plate measured)' is an honest number. '41 µg' alone is not.
    """
    total = sum(c.grams * c.yield_factor for c in components) or 1.0
    known = sum(
        c.grams * c.yield_factor
        for c in components
        if nutrient_id in profiles.get(c.fdc_id, {})
    )
    return known / total


# ---------------------------------------------------------------- guardrail


@dataclass(frozen=True)
class EnergyCheck:
    kcal_db: float
    kcal_atwater: float
    delta_pct: float
    ok: bool


def energy_cross_check(nutrients: dict[int, float]) -> EnergyCheck:
    """Recompute energy from macros and compare against the database figure.

    A mismatch means one of: the food row is inconsistent, a component was
    matched to the wrong food, or grams were misread. It is the cheapest
    correctness signal available, it costs nothing, and it catches the single
    most damaging failure mode — a plausible-looking parse against the wrong
    USDA row.
    """
    kcal_db = nutrients.get(ENERGY_KCAL, 0.0)
    kcal_atwater = sum(
        nutrients.get(nid, 0.0) * factor
        for nid, factor in ATWATER.items()
        if nid in (PROTEIN, CARB, FAT)
    )
    # Fibre is inside carbohydrate-by-difference but yields ~2 kcal/g, not 4.
    kcal_atwater += nutrients.get(FIBER, 0.0) * ATWATER[FIBER]
    if kcal_db <= 0:
        return EnergyCheck(kcal_db, kcal_atwater, 0.0, False)
    delta = (kcal_atwater - kcal_db) / kcal_db
    return EnergyCheck(kcal_db, kcal_atwater, delta * 100.0, abs(delta) <= ENERGY_TOLERANCE)


def nutrient_uncertainty(
    components: list[ResolvedComponent],
    profiles: dict[int, dict[int, float]],
    nutrient_id: int,
) -> float:
    """1-sigma on one nutrient total, from mass uncertainty alone.

    It ignores uncertainty in the food database itself, which is real but
    smaller and not quantified in FDC for most rows. So this is a floor on your
    true error, not an estimate of it.
    """
    var = 0.0
    for c in components:
        per_100 = profiles.get(c.fdc_id, {}).get(nutrient_id)
        if per_100 is None:
            continue
        per_gram = per_100 * c.yield_factor / 100.0
        var += (c.sigma * per_gram) ** 2
    return var ** 0.5


def mass_sanity(components: list[ResolvedComponent], stated_total: float | None) -> bool:
    """If a plate weight was stated or read off a scale, components must agree."""
    if not stated_total:
        return True
    s = sum(c.grams for c in components)
    return abs(s - stated_total) <= max(0.15 * stated_total, 20.0)
