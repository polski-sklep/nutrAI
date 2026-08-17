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

# A floor with less than this share of its target outstanding counts as met.
NEARLY_MET = 0.10
# A suggestion has to close at least this much of some gap to be worth making.
#
# Three drinks that each close 1% of potassium are not answers to "what should
# I eat next" — they are the least-bad rows in a thin list, and printing them
# with a tick beside them dresses noise as advice.
WORTH_SUGGESTING = 0.05
# Below this a ceiling breach is rounding, not a breach. "+0%" three times
# under every suggestion is noise that trains you to skip the warning line.
WORTH_WARNING = 0.01


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
    floors: dict[int, tuple[float, float, float]] = {}  # nid -> (remaining, target, weight)
    ceilings: dict[int, tuple[float, float]] = {}  # nid -> (headroom, ceiling)
    for r in progress:
        nid = r["nutrient_id"]
        amount = float(r["amount"])
        if r["min_amount"] is not None:
            target = float(r["min_amount"])
            remaining = target - amount
            # A floor 97% met is done. Leaving it in lets a dish be ranked for
            # "closing Calcium 100%" when the hundred per cent was 8 mg.
            if target > 0 and remaining > NEARLY_MET * target:
                w = float(r["weight"]) if "weight" in r and r["weight"] is not None else 1.0
                floors[nid] = (remaining, target, w)
        if r["max_amount"] is not None:
            ceiling = float(r["max_amount"])
            if ceiling > 0:
                ceilings[nid] = (max(0.0, ceiling - amount), ceiling)

    out: list[Suggestion] = []
    for d in snapshots.values():
        nuts = d["nutrients"]
        closes: list[tuple[int, float]] = []
        score = 0.0
        for nid, (remaining, target, w) in floors.items():
            contributed = nuts.get(nid, 0.0)
            if contributed <= 0:
                continue
            # Weighted by how unmet the nutrient still is.
            #
            # Without this, every floor counts the same and finishing a gap
            # counts as one whole point however small the gap was. On a day
            # 118 g short of a 165 g protein floor, that ranked a chia pudding
            # first for closing the last 2% of calcium — the score rewarded
            # tidying up nearly-met nutrients over denting the one that
            # mattered. Multiplying by the shortfall share makes the last 2%
            # of a floor worth about a fiftieth of the first.
            shortfall_share = remaining / target
            # Weighted like the day score is, so protein at x2.5 outranks a
            # micronutrient you happen to be equally short of.
            credit = (min(contributed, remaining) / target) * shortfall_share * w
            score += credit
            closes.append((nid, min(contributed, remaining) / remaining))

        breaches: list[tuple[int, float]] = []
        penalty = 0.0
        for nid, (headroom, ceiling) in ceilings.items():
            contributed = nuts.get(nid, 0.0)
            over = contributed - headroom
            if over > 0:
                breaches.append((nid, over / ceiling))
                penalty += over / ceiling
        # A breach can cost a suggestion at most half its value, never more.
        #
        # Unbounded, the penalty was on a different scale from the credit and
        # swamped it: with fat already at 97% of its ceiling everything
        # containing fat breaches, so a pickle juice closing 7% of potassium
        # outranked a shake closing 48% of a protein gap. A dish that shuts
        # the gap that matters is worth suggesting even when it nudges a
        # ceiling you have already crossed — the warning line says so, and
        # that is what the warning line is for.
        score -= min(penalty, score * 0.5)

        closes = [(nid, share) for nid, share in closes if share >= WORTH_WARNING]
        breaches = [(nid, share) for nid, share in breaches if share >= WORTH_WARNING]
        if not closes or max(share for _n, share in closes) < WORTH_SUGGESTING:
            continue
        closes.sort(key=lambda c: -c[1])
        breaches.sort(key=lambda b: -b[1])
        out.append(Suggestion(
            dish_id=d["id"], name=d["name"], slug=d["slug"], score=score,
            kcal=nuts.get(ENERGY_KCAL, 0.0), closes=closes, breaches=breaches,
        ))

    out.sort(key=lambda s: -s.score)
    return out[:limit]
