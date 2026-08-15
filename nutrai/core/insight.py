"""n-of-1 analysis, with the refusals that make it worth anything.

You asked the app to tell you your optimal working times, your best exercise
times, and when you are burning fat. Two of those three are answerable, but
only if you log the outcome — and none of them are answerable from meal
timestamps alone. This module does the arithmetic and, more importantly,
declines to answer when the data cannot support an answer.

An n-of-1 correlation that reports a result at n=9 is not a weak finding. It is
a random number with a decimal point on it, and it is worse than silence
because you will act on it.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from dataclasses import dataclass
from statistics import median

# Below this many paired observations, report nothing but the shortfall.
MIN_PAIRS = 20
# Permutation resamples. 2,000 gives a p-value resolution of 0.0005, which is
# far finer than the inferential weight this data can carry.
PERMUTATIONS = 2000
# Energy in one kilogram of adipose tissue. The 7,700 figure is a convention
# derived from fat's energy density and tissue water content; real weight
# change also carries glycogen, water and gut contents, which is why the
# minimum window below is two weeks and not two days.
KCAL_PER_KG_FAT = 7700.0
MIN_TREND_DAYS = 14


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else 0.0


def spearman(xs: list[float], ys: list[float]) -> float:
    """Rank correlation. Rank, not Pearson, because none of these
    relationships are plausibly linear and one bad day should not drag a
    coefficient across zero."""
    return _pearson(_rank(xs), _rank(ys))


def permutation_p(xs: list[float], ys: list[float], seed: int = 0) -> float:
    """Two-sided p by shuffling the outcome. No distributional assumptions,
    which matters when the outcome is a 1-10 rating with three used values."""
    obs = abs(spearman(xs, ys))
    rng = random.Random(seed)
    shuffled = list(ys)
    hits = 0
    for _ in range(PERMUTATIONS):
        rng.shuffle(shuffled)
        if abs(spearman(xs, shuffled)) >= obs:
            hits += 1
    return (hits + 1) / (PERMUTATIONS + 1)


@dataclass
class Finding:
    label: str
    n: int
    rho: float | None
    p: float | None
    verdict: str
    caveat: str = ""

    @property
    def usable(self) -> bool:
        return self.rho is not None and self.p is not None and self.p < 0.05


def correlate(
    label: str,
    xs: list[float],
    ys: list[float],
    *,
    clock_hours: list[float] | None = None,
    min_pairs: int = MIN_PAIRS,
) -> Finding:
    """One predictor against one outcome, with the confound stated out loud.

    `clock_hours` is not optional in spirit. Time of day drives both hunger and
    alertness, so "I focus better when I have not eaten for six hours" and
    "I focus better at 10am" produce the same correlation from the same data.
    Reporting the first without checking the second is how self-quantification
    manufactures beliefs.
    """
    n = min(len(xs), len(ys))
    if n < min_pairs:
        return Finding(
            label, n, None, None,
            verdict=f"not enough data: {n} of {min_pairs} paired observations",
        )

    rho = spearman(xs[:n], ys[:n])
    p = permutation_p(xs[:n], ys[:n])

    caveat = ""
    if clock_hours and len(clock_hours) >= n:
        rho_clock = spearman(clock_hours[:n], ys[:n])
        if abs(rho_clock) >= abs(rho) * 0.8:
            caveat = (
                f"time of day correlates with the outcome about as strongly "
                f"(rho {rho_clock:+.2f}). This effect is probably the clock, not the food."
            )

    if p >= 0.05:
        verdict = f"no reliable relationship (rho {rho:+.2f}, p {p:.3f}, n {n})"
    else:
        strength = "weak" if abs(rho) < 0.3 else "moderate" if abs(rho) < 0.5 else "strong"
        direction = "higher" if rho > 0 else "lower"
        verdict = f"{strength}: {direction} outcome with more (rho {rho:+.2f}, p {p:.3f}, n {n})"

    return Finding(label, n, rho, p, verdict, caveat)


# ------------------------------------------------------------- the real one


@dataclass
class FatLossRate:
    days: int
    kg_per_week: float
    implied_deficit_kcal: float
    median_intake_kcal: float
    implied_tdee_kcal: float
    note: str


def _slope(days: list[float], kg: list[float]) -> float:
    n = len(days)
    mx, my = sum(days) / n, sum(kg) / n
    den = sum((d - mx) ** 2 for d in days)
    return sum((d - mx) * (w - my) for d, w in zip(days, kg)) / den if den else 0.0


def fat_loss_rate(
    weights: list[tuple[dt.date, float]],
    daily_intake_kcal: list[float],
) -> FatLossRate | None:
    """The only trustworthy answer to "am I burning fat".

    Regress weight on date, convert the slope to an energy rate, and back out
    the TDEE your body actually has rather than the one an equation predicted.
    Two weeks minimum, because glycogen and water swamp fat over shorter spans:
    a 1 kg drop across three days is almost entirely not fat.

    This is what you wanted when you asked about fat burning, and note what it
    does not contain: any reference to when you ate.
    """
    if len(weights) < 8:
        return None
    ws = sorted(weights)
    span = (ws[-1][0] - ws[0][0]).days + 1
    if span < MIN_TREND_DAYS:
        return None

    day0 = ws[0][0]
    slope_kg_day = _slope([(d - day0).days for d, _ in ws], [w for _, w in ws])
    kg_week = slope_kg_day * 7
    deficit = -slope_kg_day * KCAL_PER_KG_FAT     # positive when losing
    intake = median(daily_intake_kcal) if daily_intake_kcal else 0.0

    note = ""
    if abs(kg_week) < 0.1:
        note = "weight is flat: you are at maintenance, whatever the target says"
    elif kg_week < -1.2:
        note = "faster than about 1% of bodyweight a week costs lean mass"
    if span < 21:
        note = (note + " · " if note else "") + f"only {span} days: treat the rate as provisional"

    return FatLossRate(
        days=span,
        kg_per_week=round(kg_week, 3),
        implied_deficit_kcal=round(deficit),
        median_intake_kcal=round(intake),
        implied_tdee_kcal=round(intake + deficit) if intake else 0,
        note=note,
    )
