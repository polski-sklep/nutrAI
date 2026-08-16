#!/usr/bin/env python3
"""Create a user, seed targets, seed notification rules.

    python scripts/bootstrap.py --telegram-id 12345 --sex male --age 34 \
        --height-cm 183 --weight-kg 74.4 --activity 1.55 --deficit 500 \
        --protein-g 180

Micronutrient defaults are the adult US RDA/AI values published by the NIH
Office of Dietary Supplements. They are population reference intakes, not a
prescription: they are the number below which deficiency becomes likely across
a population, which is not the same as the number that is optimal for you. Edit
them. That is what the versioned `target` table is for.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt

import asyncpg

from nutrai.config import (
    ALCOHOL, CAFFEINE, CARB, DATABASE_URL, ENERGY_KCAL, FAT, FIBER, PROTEIN,
    SAT_FAT, SODIUM, SUGAR,
)

# nutrient_id: (min, max) for an adult. None = unbounded on that side.
# Sex-specific where it matters; the male column is used unless --sex female.
RDA_MALE = {
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
RDA_FEMALE = RDA_MALE | {
    1089: (18, 45),       # Iron mg, premenopausal
    1090: (310, None),
    1095: (8, 40),
    1162: (75, 2000),
    1106: (700, 3000),
}


def mifflin_st_jeor(sex: str, kg: float, cm: float, age: int) -> float:
    """Resting energy expenditure, kcal/day. Standard error is around 10%.

    Do not treat the output as a measurement. It is a starting estimate that
    you correct against three weeks of weight trend, which is the only
    energy-balance instrument you actually own."""
    base = 10 * kg + 6.25 * cm - 5 * age
    return base + (5 if sex == "male" else -161)


async def main(a: argparse.Namespace) -> None:
    con = await asyncpg.connect(DATABASE_URL)
    user_id = await con.fetchval(
        """INSERT INTO app_user (telegram_id, display_name, tz)
           VALUES ($1,$2,$3)
           ON CONFLICT (telegram_id) DO UPDATE SET display_name = EXCLUDED.display_name
           RETURNING id""",
        a.telegram_id, a.name, a.tz,
    )

    ree = mifflin_st_jeor(a.sex, a.weight_kg, a.height_cm, a.age)
    tdee = ree * a.activity
    kcal = tdee - a.deficit
    protein = a.protein_g or round(1.8 * a.weight_kg)
    fat = a.fat_g or round(0.8 * a.weight_kg)
    carb = max(0, round((kcal - protein * 4 - fat * 9) / 4))

    print(f"REE {ree:.0f} · TDEE {tdee:.0f} · target {kcal:.0f} kcal")
    print(f"P {protein} g · F {fat} g · C {carb} g")

    rda = RDA_FEMALE if a.sex == "female" else RDA_MALE
    targets: dict[int, tuple[float | None, float | None]] = {
        ENERGY_KCAL: (None, round(kcal)),
        PROTEIN: (protein, None),
        FAT: (None, round(fat * 1.3)),
        CARB: (None, round(carb * 1.15)),
        FIBER: (38 if a.sex == "male" else 25, None),
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
        **rda,
    }

    today = dt.date.today()
    async with con.transaction():
        for nid, (lo, hi) in targets.items():
            exists = await con.fetchval("SELECT 1 FROM nutrient WHERE id = $1", nid)
            if not exists:
                print(f"  skip nutrient {nid}: not in the loaded USDA set")
                continue
            await con.execute(
                "UPDATE target SET effective_to = $3 WHERE user_id=$1 AND nutrient_id=$2 AND effective_to IS NULL",
                user_id, nid, today,
            )
            await con.execute(
                """INSERT INTO target
                     (user_id, nutrient_id, min_amount, max_amount, effective_from, rationale)
                   VALUES ($1,$2,$3,$4,$5,'bootstrap')""",
                user_id, nid, lo, hi, today,
            )

        await con.execute("DELETE FROM notification_rule WHERE user_id = $1", user_id)
        rules = [
            (ENERGY_KCAL, "over", 80, 240),
            (ENERGY_KCAL, "over", 100, 240),
            (CARB, "over", 80, 240),
            (FAT, "over", 90, 240),
            (SODIUM, "over", 100, 480),
            (PROTEIN, "under", 60, 600),
        ]
        for nid, direction, pct, cooldown in rules:
            await con.execute(
                """INSERT INTO notification_rule
                     (user_id, kind, nutrient_id, direction, threshold_pct, cooldown_minutes)
                   VALUES ($1,'threshold',$2,$3,$4,$5)""",
                user_id, nid, direction, pct, cooldown,
            )

    print(f"user {user_id} ready: {len(targets)} targets, 6 notification rules")
    await con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--telegram-id", type=int, required=True)
    p.add_argument("--name", default=None)
    p.add_argument("--tz", default="Europe/Warsaw")
    p.add_argument("--sex", choices=["male", "female"], required=True)
    p.add_argument("--age", type=int, required=True)
    p.add_argument("--height-cm", type=float, required=True)
    p.add_argument("--weight-kg", type=float, required=True)
    p.add_argument("--activity", type=float, default=1.5,
                   help="1.2 sedentary, 1.375 light, 1.55 moderate, 1.725 heavy")
    p.add_argument("--deficit", type=float, default=500)
    p.add_argument("--protein-g", type=float, default=None)
    p.add_argument("--fat-g", type=float, default=None)
    asyncio.run(main(p.parse_args()))
