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

from nutrai.config import CARB, DATABASE_URL, ENERGY_KCAL, FAT, PROTEIN, SODIUM
from nutrai.core.profile import derive_targets

async def main(a: argparse.Namespace) -> None:
    con = await asyncpg.connect(DATABASE_URL)
    today = dt.date.today()
    # Keep the inputs. Deriving targets from them and then discarding them left
    # the numbers unexplainable and unrecomputable — see sql/007_profile.sql.
    birth = a.birth_date or dt.date(today.year - a.age, today.month, today.day)
    user_id = await con.fetchval(
        """INSERT INTO app_user
             (telegram_id, display_name, tz, sex, birth_date, height_cm,
              activity_factor, deficit_kcal, goal, targets_set_at_kg, targets_set_on)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
           ON CONFLICT (telegram_id) DO UPDATE SET
             display_name = EXCLUDED.display_name, sex = EXCLUDED.sex,
             birth_date = EXCLUDED.birth_date, height_cm = EXCLUDED.height_cm,
             activity_factor = EXCLUDED.activity_factor,
             deficit_kcal = EXCLUDED.deficit_kcal, goal = EXCLUDED.goal,
             targets_set_at_kg = EXCLUDED.targets_set_at_kg,
             targets_set_on = EXCLUDED.targets_set_on
           RETURNING id""",
        a.telegram_id, a.name, a.tz, a.sex, birth, a.height_cm,
        a.activity, a.deficit, a.goal, a.weight_kg, today,
    )

    targets, w = derive_targets(
        sex=a.sex, weight_kg=a.weight_kg, height_cm=a.height_cm, age=a.age,
        activity=a.activity, deficit=a.deficit,
        protein_g=a.protein_g, fat_g=a.fat_g,
    )
    print(f"REE {w['ree']:.0f} · TDEE {w['tdee']:.0f} · target {w['kcal']:.0f} kcal")
    print(f"P {w['protein']:.0f} g · F {w['fat']:.0f} g · C {w['carb']:.0f} g")

    # The weigh-in that the targets were computed from belongs in the log too,
    # so the trend starts on day one rather than on the first manual /weight.
    await con.execute(
        """INSERT INTO body_metric (user_id, kind, value, local_date, measured_at)
           VALUES ($1,'weight_kg',$2,$3, now())
           ON CONFLICT DO NOTHING""",
        user_id, a.weight_kg, today,
    )

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
        rules: list[tuple[int, str, int, int]] = []

    print(f"user {user_id} ready: {len(targets)} targets, "
          f"{len(rules)} notification rules")
    await con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--telegram-id", type=int, required=True)
    p.add_argument("--name", default=None)
    p.add_argument("--tz", default="Europe/Warsaw")
    p.add_argument("--sex", choices=["male", "female"], required=True)
    p.add_argument("--age", type=int, required=True)
    p.add_argument("--birth-date", type=dt.date.fromisoformat, default=None,
                   help="exact date of birth; --age is used to approximate one if omitted")
    p.add_argument("--goal", choices=["lose", "maintain", "gain"], default=None)
    p.add_argument("--height-cm", type=float, required=True)
    p.add_argument("--weight-kg", type=float, required=True)
    p.add_argument("--activity", type=float, default=1.5,
                   help="1.2 sedentary, 1.375 light, 1.55 moderate, 1.725 heavy")
    p.add_argument("--deficit", type=float, default=500)
    p.add_argument("--protein-g", type=float, default=None)
    p.add_argument("--fat-g", type=float, default=None)
    asyncio.run(main(p.parse_args()))
