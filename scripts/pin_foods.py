#!/usr/bin/env python3
"""Pin your most-eaten foods to verified USDA rows, once, by hand.

    python scripts/pin_foods.py --telegram-id 123456789          # review
    python scripts/pin_foods.py --telegram-id 123456789 --pin     # interactive

Why this exists. Your diet is narrow and repetitive — that is the premise of
the whole repeat system. Forty foods will account for something like 90% of
everything you eat this year. Every one of those forty is currently matched by
an automatic resolver that is right most of the time.

Most of the time is not good enough for a row that will be multiplied by 300
meals. Spend forty minutes once, look at each match, confirm or correct it, and
the resolver stops being a source of error for the overwhelming majority of
your intake. A pinned alias is never re-pointed by a later parse.

This is also the answer to thin micronutrient coverage: when you pin, prefer a
Foundation or SR Legacy row with a full nutrient panel over a Branded row with
six label values, even when the Branded row names your exact product. The
brand's macros are marginally more accurate. Its nulls are catastrophic.
"""

from __future__ import annotations

import argparse
import asyncio

import asyncpg

from nutrai.config import CORE_NUTRIENTS, DATABASE_URL


async def main(a: argparse.Namespace) -> None:
    con = await asyncpg.connect(DATABASE_URL)
    user_id = await con.fetchval("SELECT id FROM app_user WHERE telegram_id = $1", a.telegram_id)
    if not user_id:
        raise SystemExit("no such user; run bootstrap.py first")

    rows = await con.fetch(
        """SELECT al.id, al.alias, al.fdc_id, al.hits, al.pinned,
                  f.description, f.data_type,
                  (SELECT count(*) FROM food_nutrient fn
                    WHERE fn.fdc_id = al.fdc_id) AS n_nutrients,
                  (SELECT count(*) FROM food_nutrient fn
                    WHERE fn.fdc_id = al.fdc_id AND fn.nutrient_id = ANY($2::int[])) AS n_core,
                  (SELECT count(*) FROM log_component lc JOIN log_entry e ON e.id = lc.entry_id
                    WHERE e.user_id = $1 AND lc.fdc_id = al.fdc_id AND e.status='confirmed') AS n_logged
             FROM food_alias al JOIN food f ON f.fdc_id = al.fdc_id
            WHERE al.user_id = $1
         ORDER BY al.hits DESC, al.alias LIMIT $3""",
        user_id, CORE_NUTRIENTS, a.limit,
    )

    print(f"{'alias':<24} {'pin':<4} {'hits':>5} {'core':>5} {'all':>5}  match")
    print("-" * 110)
    for r in rows:
        core_flag = "" if r["n_core"] >= 15 else "  ⚠ thin"
        print(
            f"{r['alias'][:23]:<24} {'📌' if r['pinned'] else '':<4} {r['hits']:>5} "
            f"{r['n_core']:>5} {r['n_nutrients']:>5}  {r['description'][:52]} "
            f"[{r['data_type'].replace('_food','')}]{core_flag}"
        )

    thin = [r for r in rows if r["n_core"] < 15]
    if thin:
        print()
        print(f"{len(thin)} of your foods report fewer than 15 of the 20 core nutrients.")
        print("Those are the ones whose micronutrient totals are measurement gaps,")
        print("not dietary gaps. Re-point them at a Foundation or SR Legacy row.")

    if not a.pin:
        await con.close()
        return

    for r in rows:
        if r["pinned"]:
            continue
        print(f"\n{r['alias']}  →  {r['description']} [{r['data_type']}] "
              f"({r['n_core']}/20 core nutrients)")
        ans = input("  [enter] keep and pin · s=skip · number=search again · q=quit > ").strip()
        if ans == "q":
            break
        if ans == "s":
            continue
        if ans:
            cands = await con.fetch(
                """SELECT f.fdc_id, f.description, f.data_type,
                          (SELECT count(*) FROM food_nutrient fn
                            WHERE fn.fdc_id = f.fdc_id AND fn.nutrient_id = ANY($2::int[])) AS n_core
                     FROM food f
                    WHERE to_tsvector('english', f.description) @@ plainto_tsquery('english', $1)
                 ORDER BY f.precedence, similarity(f.description, $1) DESC LIMIT 10""",
                ans, CORE_NUTRIENTS,
            )
            for i, c in enumerate(cands, 1):
                print(f"    {i}. [{c['n_core']:>2}/20] {c['description'][:70]} "
                      f"({c['data_type'].replace('_food','')})")
            pick = input("  pick number, or blank to skip > ").strip()
            if not pick.isdigit() or not (1 <= int(pick) <= len(cands)):
                continue
            chosen = cands[int(pick) - 1]["fdc_id"]
        else:
            chosen = r["fdc_id"]

        await con.execute(
            "UPDATE food_alias SET fdc_id = $2, pinned = true, verified_at = now() WHERE id = $1",
            r["id"], chosen,
        )
        print("  pinned")

    await con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--telegram-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--pin", action="store_true", help="interactive pinning pass")
    asyncio.run(main(p.parse_args()))
