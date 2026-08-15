"""Turning a printed panel into rows that can be summed against food.

The only real work here is units. A label says "25 µg" or "1000 IU" or
"400 mg"; `nutrient.unit` says what the rest of the system counts in. Getting
that wrong is not a rounding error — a factor of 1,000 in a micronutrient is
the difference between a deficiency and a toxicity, applied silently to every
day thereafter.

So conversion is explicit, total, and refuses rather than approximates.
"""

from __future__ import annotations

from dataclasses import dataclass

# Grams-relative scale for the mass units FDC uses.
_MASS = {"g": 1.0, "mg": 1e-3, "ug": 1e-6, "mcg": 1e-6}

# International Units are nutrient-specific and only some are unambiguous.
#
# Vitamin D is exactly 0.025 µg per IU by definition. Vitamin A and E are not:
# A depends on whether the source is retinol or beta-carotene (a 12x spread) and
# E on natural versus synthetic tocopherol. A label giving those in IU alone
# does not determine the metric amount, so those lines are refused rather than
# guessed — an unrecorded nutrient is a gap, a wrongly converted one is a lie.
_IU_TO_UNIT: dict[int, tuple[str, float]] = {
    1114: ("ug", 0.025),  # Vitamin D (D2 + D3)
}


@dataclass(frozen=True)
class Converted:
    nutrient_id: int
    amount: float
    note: str = ""


@dataclass(frozen=True)
class Rejected:
    nutrient_id: int
    printed_label: str
    reason: str


def convert(
    nutrient_id: int, amount: float, unit: str, target_unit: str
) -> tuple[float | None, str]:
    """Label amount to the nutrient's own unit. Returns (value, reason-if-None)."""
    u, t = unit.strip().lower(), target_unit.strip().lower()
    if amount < 0:
        return None, "negative amount"

    if u == "iu":
        mapping = _IU_TO_UNIT.get(nutrient_id)
        if not mapping:
            return None, "IU cannot be converted for this nutrient without knowing the form"
        iu_unit, factor = mapping
        value = amount * factor
        if iu_unit == t:
            return value, ""
        u = iu_unit
        amount = value

    if u == t:
        return amount, ""
    if u == "mcg":
        u = "ug"
    if t == "mcg":
        t = "ug"
    if u == t:
        return amount, ""
    if u in _MASS and t in _MASS:
        return amount * _MASS[u] / _MASS[t], ""
    if u == "kcal" and t == "kcal":
        return amount, ""
    return None, f"cannot convert {unit} to {target_unit}"


def normalise(
    lines: list[dict],
    units_by_nutrient: dict[int, str],
) -> tuple[list[Converted], list[Rejected]]:
    """Convert a transcribed panel. Anything unconvertible is rejected, loudly.

    `units_by_nutrient` comes from the `nutrient` table, so the target is
    whatever the rest of the system already counts that nutrient in.
    """
    kept: list[Converted] = []
    dropped: list[Rejected] = []
    seen: set[int] = set()

    for line in lines:
        try:
            nid = int(line["nutrient_id"])
            amount = float(line["amount"])
        except (KeyError, TypeError, ValueError):
            dropped.append(Rejected(0, str(line.get("printed_label", "?")), "unreadable line"))
            continue

        target = units_by_nutrient.get(nid)
        if target is None:
            dropped.append(Rejected(nid, line.get("printed_label", ""), "not a nutrient I track"))
            continue
        if nid in seen:
            dropped.append(Rejected(nid, line.get("printed_label", ""), "duplicate line"))
            continue

        value, why = convert(nid, amount, str(line.get("unit", "")), target)
        if value is None:
            dropped.append(Rejected(nid, line.get("printed_label", ""), why))
            continue

        seen.add(nid)
        kept.append(Converted(nid, value))

    return kept, dropped
