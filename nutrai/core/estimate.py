"""Portion estimation when nothing was weighed, and honest error bars when it was not.

Two ideas, in order of how much they are worth:

1. **Your own history beats vision.** You have weighed a banana before. The
   median of your past weighings is a far better estimate of today's banana
   than any model looking at a photograph of it, and it costs nothing. A
   narrow, repetitive diet — which is what you have — makes this the dominant
   estimator within about two weeks.

2. **An estimate without a range is a lie about precision.** 1,720 kcal is a
   claim the data does not support when half the plate was eyeballed. This
   module propagates per-component mass uncertainty into the day's totals so
   the summary can say 1,720 ± 140 and you can see which entries are doing the
   damage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median, quantiles

# A digital kitchen scale is accurate to roughly ±1 g on a plate-sized load.
# Treat a weighed component as near-certain but not perfectly so: the error
# that survives is the operator's, not the instrument's.
SCALE_SIGMA_ABS = 1.0
SCALE_SIGMA_REL = 0.005
STATED_SIGMA_REL = 0.05      # you said "about 250 g"
PACKAGE_SIGMA_REL = 0.03     # declared net weight, EU tolerance is wider than you think
# With no range from the model, assume a visual estimate is good to ±35%.
# Published portion-estimation studies put untrained visual error well above
# this for composite plates; 0.35 is optimistic and deliberately so, because a
# pessimistic default drowns the summary in error bars you stop reading.
ESTIMATE_SIGMA_REL = 0.35

# Prior is used instead of the model's guess when history is this consistent.
PRIOR_MIN_SAMPLES = 3
PRIOR_MAX_SPREAD = 0.25      # (p75 - p25) / median


@dataclass(frozen=True)
class MassEstimate:
    grams: float
    sigma: float
    source: str          # scale | stated | package | prior | estimate
    note: str = ""

    @property
    def low(self) -> float:
        return max(0.0, self.grams - 2 * self.sigma)

    @property
    def high(self) -> float:
        return self.grams + 2 * self.sigma


def sigma_for(grams: float, source: str, low: float | None = None, high: float | None = None) -> float:
    """Standard deviation of a component's mass, in grams."""
    if low is not None and high is not None and high > low:
        # Model gave an explicit range. Read it as a ~95% interval.
        return (high - low) / 4.0
    if source == "scale":
        return max(SCALE_SIGMA_ABS, grams * SCALE_SIGMA_REL)
    if source == "stated":
        return grams * STATED_SIGMA_REL
    if source == "package":
        return grams * PACKAGE_SIGMA_REL
    if source == "prior":
        return grams * 0.10
    return grams * ESTIMATE_SIGMA_REL


def portion_prior(weighings: list[float]) -> tuple[float, float] | None:
    """Median and spread of your own past weighings for one food.

    Returns None when history is too thin or too scattered to beat a fresh
    look at the plate. Scattered history is real information: 'rice' varies
    because you serve it by eye, and pretending otherwise would replace an
    honest wide estimate with a confident wrong one.
    """
    xs = sorted(w for w in weighings if w > 0)
    if len(xs) < PRIOR_MIN_SAMPLES:
        return None
    med = median(xs)
    if med <= 0:
        return None
    # Inclusive quartiles: with five samples, hand-rolled index arithmetic
    # silently ignores both tails and declares a bimodal history 'consistent'.
    p25, _, p75 = quantiles(xs, n=4, method="inclusive")
    spread = (p75 - p25) / med
    if spread > PRIOR_MAX_SPREAD:
        return None
    # Sigma from the observed spread, floored so a lucky run of identical
    # weighings does not claim impossible precision.
    return med, max(med * 0.06, (p75 - p25) / 1.35 or med * 0.06)


def choose_mass(
    model_grams: float,
    source: str,
    *,
    low: float | None = None,
    high: float | None = None,
    history: list[float] | None = None,
) -> MassEstimate:
    """Pick the best available mass for one component.

    Weighed and stated masses always win — you were there, the model was not.
    A prior only overrides a *visual estimate*, and only when the prior is
    tight and the estimate is not wildly different from it (a 3x gap means
    today's portion genuinely was different, and the photo is the better
    witness).
    """
    if source in ("scale", "stated", "package"):
        return MassEstimate(model_grams, sigma_for(model_grams, source, low, high), source)

    prior = portion_prior(history or [])
    if prior:
        med, sd = prior
        if model_grams <= 0 or 0.4 <= model_grams / med <= 2.5:
            return MassEstimate(
                med, sd, "prior",
                note=f"your median of {len(history or [])} past weighings",
            )

    return MassEstimate(model_grams, sigma_for(model_grams, "estimate", low, high), "estimate")


# ---------------------------------------------------------------- propagation


def propagate(
    masses: list[MassEstimate],
    per_gram: list[float],
) -> tuple[float, float]:
    """Total and 1-sigma uncertainty for one nutrient across components.

    `per_gram[i]` is that nutrient's amount per gram of component i, already
    including its yield factor. Errors are combined in quadrature on the
    assumption that mass errors are independent — which is right for separate
    ingredients on a plate and wrong if you systematically under-serve
    everything, so treat the bar as a floor on your true uncertainty.
    """
    total = sum(m.grams * g for m, g in zip(masses, per_gram))
    var = sum((m.sigma * g) ** 2 for m, g in zip(masses, per_gram))
    return total, math.sqrt(var)


def fmt_pm(value: float, sigma: float, unit: str = "kcal", rel_floor: float = 0.03) -> str:
    """Render a value with its error bar, and drop the bar when it is noise."""
    if value <= 0 or sigma / value < rel_floor:
        return f"{value:,.0f} {unit}"
    return f"{value:,.0f} ± {sigma:,.0f} {unit}"


def day_confidence(masses: list[MassEstimate]) -> float:
    """Fraction of the day's logged mass that was actually weighed or stated.

    The single most useful number in the whole summary. If it reads 40%, every
    trend below it is noise and no improvement plan built on it means anything.
    """
    total = sum(m.grams for m in masses) or 1.0
    hard = sum(m.grams for m in masses if m.source in ("scale", "stated", "package"))
    return hard / total
