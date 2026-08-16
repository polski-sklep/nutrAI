"""Who you are, and the arithmetic that turns that into targets.

This lived in `scripts/bootstrap.py` and was reachable only by re-running a CLI
script. It is here because two callers need it now — bootstrap at setup, and
`/profile` when an input changes — and two callers computing targets two
different ways is exactly how a system starts disagreeing with itself.

Nothing here is a measurement. Mifflin-St Jeor carries about 10% standard
error, an activity factor is a guess with a decimal point on it, and the RDAs
are population reference intakes rather than a prescription for one person.
The instrument is the weight trend over three weeks; see `core/insight.py`.
"""

from __future__ import annotations

import datetime as dt

from ..config import (
    ALCOHOL, CAFFEINE, CARB, ENERGY_KCAL, FAT, FIBER, PROTEIN, SAT_FAT,
    SODIUM, SUGAR,
)

# nutrient_id: (min, max) for an adult. None = unbounded on that side.
# Adult US RDA/AI values from the NIH Office of Dietary Supplements. They are
# the intake below which deficiency becomes likely across a population, which
# is not the same as the intake that is best for you. Edit them — that is what
# the versioned `target` table is for.
RDA_MALE: dict[int, tuple[float | None, float | None]] = {
    1092: (3400, None),   # Potassium, AI mg
    1087: (1000, 2500),   # Calcium mg (UL 2500)
    1089: (8, 45),        # Iron mg (UL 45)
    1090: (400, None),    # Magnesium mg (UL applies to supplements only)
    1095: (11, 40),       # Zinc mg (UL 40)
    1178: (2.4, None),    # B-12 µg
    1114: (15, 100),      # Vitamin D µg (UL 100)
    1162: (90, 2000),     # Vitamin C mg (UL 2000)
    1106: (900, 3000),    # Vitamin A µg RAE (UL 3000 preformed)
    1177: (400, None),    # Folate µg
    1253: (None, 300),    # Cholesterol mg — no RDA; conventional ceiling
    1272: (0.25, None),   # DHA g — no RDA; 250 mg EPA+DHA is the common floor
}
RDA_FEMALE: dict[int, tuple[float | None, float | None]] = RDA_MALE | {
    1089: (18, 45),       # Iron mg, premenopausal
    1090: (310, None),
    1095: (8, 40),
    1162: (75, 2000),
    1106: (700, 3000),
}

# Activity describes your ORDINARY DAY, deliberately excluding workouts.
#
# The textbook Mifflin multipliers fold exercise into the same number ("1.55 =
# training 3-5x a week"), which is fine when nothing else knows about your
# training. Workouts now arrive over HTTP, and the moment anything consumes
# activity.kcal_burned a multiplier that already contains them counts them
# twice. Splitting the two is the only version that stays correct as the
# system grows: this is your baseline life, and training is recorded separately.
#
# So the labels talk about how you spend the hours you are not training in.
ACTIVITY_LEVELS: list[tuple[float, str, str]] = [
    (1.25, "Seated",   "desk job, car, little walking"),
    (1.40, "Light",    "some walking, mostly seated"),
    (1.55, "Moderate", "on your feet a fair amount"),
    (1.70, "Active",   "on your feet most of the day"),
    (1.85, "Heavy",    "physical/manual work"),
]


def activity_label(factor: float | None) -> str:
    if factor is None:
        return "not set"
    # Nearest level, so a hand-typed 1.5 still reads as something.
    _f, name, gloss = min(ACTIVITY_LEVELS, key=lambda lv: abs(lv[0] - float(factor)))
    return f"{name} — {gloss}"


def age_years(birth_date: dt.date | None, on: dt.date | None = None) -> int | None:
    """Age on a given day. Stored as a birth date so it stays true."""
    if birth_date is None:
        return None
    on = on or dt.date.today()
    return on.year - birth_date.year - ((on.month, on.day) < (birth_date.month, birth_date.day))


def mifflin_st_jeor(sex: str, kg: float, cm: float, age: int) -> float:
    """Resting energy expenditure, kcal/day. Standard error is around 10%.

    Do not treat the output as a measurement. It is a starting estimate that
    you correct against three weeks of weight trend, which is the only
    energy-balance instrument you actually own.
    """
    base = 10 * kg + 6.25 * cm - 5 * age
    return base + (5 if sex == "male" else -161)


class IncompleteProfile(ValueError):
    """Raised rather than defaulted. A target computed from a made-up height is
    worse than no target, because it looks exactly like a real one."""


# Protein floor in g per kg of bodyweight, by goal. 1.8 is the general
# recommendation for an active adult; a recomposition or a deficit both raise
# it, because protein is what decides whether the weight you lose is fat.
PROTEIN_PER_KG = {"lose": 2.0, "recomp": 2.2, "gain": 1.8, "maintain": 1.6}
DEFAULT_PROTEIN_PER_KG = 1.8


def derive_targets(
    *,
    sex: str,
    weight_kg: float,
    height_cm: float,
    age: int,
    activity: float,
    deficit: float,
    goal: str | None = None,
    protein_g: float | None = None,
    fat_g: float | None = None,
) -> tuple[dict[int, tuple[float | None, float | None]], dict[str, float]]:
    """Returns (targets by nutrient id, the working shown as numbers)."""
    missing = [
        name for name, v in (
            ("sex", sex), ("weight", weight_kg), ("height", height_cm),
            ("age", age), ("activity factor", activity),
        ) if v in (None, "")
    ]
    if missing:
        raise IncompleteProfile(", ".join(missing))

    ree = mifflin_st_jeor(sex, weight_kg, height_cm, age)
    tdee = ree * activity
    kcal = tdee - (deficit or 0)
    protein = protein_g or round(
        PROTEIN_PER_KG.get(goal or "", DEFAULT_PROTEIN_PER_KG) * weight_kg)
    fat = fat_g or round(0.8 * weight_kg)
    carb = max(0, round((kcal - protein * 4 - fat * 9) / 4))

    targets: dict[int, tuple[float | None, float | None]] = {
        ENERGY_KCAL: (None, round(kcal)),
        PROTEIN: (protein, None),
        FAT: (None, round(fat * 1.3)),
        CARB: (None, round(carb * 1.15)),
        FIBER: (38 if sex == "male" else 25, None),
        SUGAR: (None, round(kcal * 0.10 / 4)),      # WHO: <10% of energy
        SAT_FAT: (None, round(kcal * 0.10 / 9)),    # <10% of energy
        SODIUM: (None, 2300),
        # EFSA and Health Canada both put habitual adult intake up to 400 mg/day
        # in the no-concern range, and 200 mg as a single dose. It is a ceiling
        # rather than a target: nobody has a caffeine requirement.
        CAFFEINE: (None, 400),
        # UK guidance is 14 units a week, about 112 g of ethanol; spread evenly
        # that is 16 g a day. A daily ceiling on a weekly guideline is a
        # simplification, and the honest use of this number is to notice a
        # pattern rather than to pass or fail a Friday.
        ALCOHOL: (None, 16),
        **(RDA_FEMALE if sex == "female" else RDA_MALE),
    }
    working = {
        "ree": ree, "tdee": tdee, "kcal": kcal,
        "protein": float(protein), "fat": float(fat), "carb": float(carb),
    }
    return targets, working
