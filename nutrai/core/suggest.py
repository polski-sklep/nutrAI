"""What to eat next, ranked by what today is still short of.

No model. Nothing here invents a food, a portion or a nutrient value: the
candidates are dishes you have already eaten and confirmed, and the numbers are
the `log_nutrient` snapshots taken when you ate them. Invariant 1 is not merely
respected, it is unreachable — there is no model in this path to violate it.

That constraint also makes the feature better rather than worse. Asked what to
eat, a model returns grilled salmon and quinoa: a healthy-eating cliché about
nobody. Ranking your own dishes returns something that is already in your
kitchen and that you have demonstrably been willing to cook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import ENERGY_KCAL


@dataclass(frozen=True)
class Suggestion:
    dish_id: int
    name: str
    slug: str
    score: float
    kcal: float
    # (nutrient_id, how much of the remaining shortfall this would close)
    closes: list[tuple[int, float]]
    # Ceilings this would push past, and by how much as a share of the ceiling.
    breaches: list[tuple[int, float]]


def rank(
    snapshots: dict[int, dict],
    progress: list[Any],
    *,
    limit: int = 3,
) -> list[Suggestion]:
    """Rank dishes by how much of the day's outstanding shortfall each closes.

    The score is deliberately simple and readable: for every floor still
    unmet, credit the fraction of the *remaining* gap a dish would close,
    capped at the gap itself so a dish is not rewarded for overshooting. Then
    subtract any ceiling it would push you past, weighted the same way, so
    "closes the protein gap" cannot quietly outrank "and puts you 40% over
    saturated fat".

    A weighting this crude is honest about itself. It is not a nutritionist;
    it is arithmetic on the gaps, and the card shows the gaps it used so the
    ranking can be argued with.
    """
    floors: dict[int, tuple[float, float]] = {}   # nid -> (remaining, target)
    ceilings: dict[int, tuple[float, float]] = {}  # nid -> (headroom, ceiling)
    for r in progress:
        nid = r["nutrient_id"]
        amount = float(r["amount"])
        if r["min_amount"] is not None:
            target = float(r["min_amount"])
            if target > 0 and amount < target:
                floors[nid] = (target - amount, target)
        if r["max_amount"] is not None:
            ceiling = float(r["max_amount"])
            if ceiling > 0:
                ceilings[nid] = (max(0.0, ceiling - amount), ceiling)

    out: list[Suggestion] = []
    for d in snapshots.values():
        nuts = d["nutrients"]
        closes: list[tuple[int, float]] = []
        score = 0.0
        for nid, (remaining, target) in floors.items():
            contributed = nuts.get(nid, 0.0)
            if contributed <= 0:
                continue
            # Capped at the gap: filling it counts once, exceeding it does not
            # count twice. Nothing here treats more as better without limit.
            credit = min(contributed, remaining) / target
            score += credit
            closes.append((nid, min(contributed, remaining) / remaining))

        breaches: list[tuple[int, float]] = []
        for nid, (headroom, ceiling) in ceilings.items():
            contributed = nuts.get(nid, 0.0)
            over = contributed - headroom
            if over > 0:
                breaches.append((nid, over / ceiling))
                score -= over / ceiling

        if not closes:
            continue
        closes.sort(key=lambda c: -c[1])
        breaches.sort(key=lambda b: -b[1])
        out.append(Suggestion(
            dish_id=d["id"], name=d["name"], slug=d["slug"], score=score,
            kcal=nuts.get(ENERGY_KCAL, 0.0), closes=closes, breaches=breaches,
        ))

    out.sort(key=lambda s: -s.score)
    return out[:limit]
