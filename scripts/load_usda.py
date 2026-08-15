#!/usr/bin/env python3
"""Load a FoodData Central bulk CSV export into Postgres.

    python scripts/load_usda.py /path/to/FoodData_Central_csv_2025-04-24

Get the export from https://fdc.nal.usda.gov/download-datasets — the full CSV
download is ~453 MB zipped, ~3.0 GB unzipped, and the data is public domain
(CC0 1.0). Foundation Foods alone is 3.3 MB and is enough to start; add SR
Legacy for breadth and Branded only if you scan barcodes, because Branded rows
are manufacturer-declared and carry macros with almost no micronutrients.

Loading Foundation + SR Legacy + FNDDS takes a couple of minutes and gives you
every nutrient Cronometer reports, from the same primary sources Cronometer
uses. There is no proprietary database to license.
"""

from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path
from typing import Iterator

import asyncpg

from nutrai.config import CORE_NUTRIENTS, DATABASE_URL

csv.field_size_limit(10_000_000)
BATCH = 20_000

# Branded is opt-in: 3.1 GB of self-reported label data whose micronutrient
# coverage is close to nil. Useful for barcodes, useless for a selenium target.
DEFAULT_TYPES = ("foundation_food", "sr_legacy_food", "survey_fndds_food")


def rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        yield from csv.DictReader(fh)


async def copy(con: asyncpg.Connection, table: str, columns: list[str], records: list[tuple]) -> None:
    """COPY into a staging table, then upsert into the real one.

    The obvious implementation — TRUNCATE then COPY straight in — is wrong here
    in a way that only shows up the second time you run it. `nutrient` is
    referenced by `target` and by `log_nutrient`, so `TRUNCATE nutrient CASCADE`
    silently takes your versioned targets and your immutable nutrient snapshots
    with it. Refreshing the food database must never be able to touch the log:
    that is the whole point of snapshotting nutrients at confirm time.

    So: stage, upsert, drop. Reference data is refreshed in place, and re-running
    the loader against a newer FDC export is a safe, ordinary thing to do.
    """
    if not records:
        return
    stage = f"_stage_{table}"
    # Not ON COMMIT DROP: asyncpg runs each execute() in its own implicit
    # transaction, so the table would vanish before the COPY that fills it.
    await con.execute(f"DROP TABLE IF EXISTS {stage}")
    await con.execute(f"CREATE TEMP TABLE {stage} (LIKE {table} INCLUDING DEFAULTS)")
    # A generated column cannot be COPYed into, and is recomputed on insert.
    generated = await con.fetch(
        """SELECT attname FROM pg_attribute
            WHERE attrelid = $1::regclass AND attgenerated <> '' AND NOT attisdropped""",
        table,
    )
    for g in generated:
        await con.execute(f"ALTER TABLE {stage} DROP COLUMN {g['attname']}")
    await con.copy_records_to_table(stage, columns=columns, records=records)
    cols = ", ".join(columns)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in PKEYS[table])
    conflict = ", ".join(PKEYS[table])
    await con.execute(
        f"""INSERT INTO {table} ({cols}) SELECT {cols} FROM {stage}
            ON CONFLICT ({conflict}) DO UPDATE SET {updates}"""
    )
    await con.execute(f"DROP TABLE {stage}")


PKEYS = {
    "nutrient": ("id",),
    "food": ("fdc_id",),
    "food_nutrient": ("fdc_id", "nutrient_id"),
    "food_portion": ("id",),
}


async def main(src: Path, include_branded: bool) -> None:
    types = set(DEFAULT_TYPES) | ({"branded_food"} if include_branded else set())
    con = await asyncpg.connect(DATABASE_URL)

    print("nutrient…")
    core = set(CORE_NUTRIENTS)
    recs = []
    for r in rows(src / "nutrient.csv"):
        recs.append((
            int(r["id"]),
            float(r["nutrient_nbr"]) if r.get("nutrient_nbr") else None,
            r["name"], r["unit_name"],
            # FDC writes rank as "280.0", not "280". int() rejects that string.
            int(float(r["rank"])) if r.get("rank") else None,
            int(r["id"]) in core,
        ))
    await copy(con, "nutrient", ["id", "nutrient_nbr", "name", "unit", "rank", "is_core"], recs)
    print(f"  {len(recs)} nutrients")

    # The survey (FNDDS) export numbers its food_nutrient rows with INFOODS
    # tagnames — 203 protein, 204 fat, 208 energy — where Foundation and SR
    # Legacy use FDC internal ids: 1003, 1004, 1008. Every one of FNDDS's
    # ~353k nutrient rows is numbered the old way, so without this map the load
    # dies on the foreign key, and a load that merely skipped them would be
    # worse: 5,432 survey foods would resolve happily and contribute zero of
    # every nutrient, which is the silent-zero failure the whole design exists
    # to avoid. nutrient.nutrient_nbr is exactly the mapping.
    known_ids = {int(r["id"]) for r in rows(src / "nutrient.csv")}
    by_nbr: dict[int, int] = {}
    for r in rows(src / "nutrient.csv"):
        if r.get("nutrient_nbr"):
            by_nbr.setdefault(int(float(r["nutrient_nbr"])), int(r["id"]))

    print("food_category…")
    cats = {r["id"]: r["description"] for r in rows(src / "food_category.csv")} \
        if (src / "food_category.csv").exists() else {}

    print("branded metadata…")
    branded: dict[str, tuple[str | None, str | None]] = {}
    bf = src / "branded_food.csv"
    if include_branded and bf.exists():
        for r in rows(bf):
            branded[r["fdc_id"]] = (r.get("brand_owner") or r.get("brand_name"), r.get("gtin_upc"))

    print("food…")
    keep: set[int] = set()
    recs = []
    n = 0
    for r in rows(src / "food.csv"):
        if r["data_type"] not in types:
            continue
        fid = int(r["fdc_id"])
        keep.add(fid)
        brand, gtin = branded.get(r["fdc_id"], (None, None))
        recs.append((fid, r["data_type"], r["description"],
                     cats.get(r.get("food_category_id", "")), brand, gtin))
        if len(recs) >= BATCH:
            await copy(con, "food", ["fdc_id", "data_type", "description", "category", "brand", "gtin_upc"], recs)
            n += len(recs)
            recs = []
    await copy(con, "food", ["fdc_id", "data_type", "description", "category", "brand", "gtin_upc"], recs)
    n += len(recs)
    print(f"  {n} foods")

    print("food_nutrient… (the big one)")
    recs, n, skipped, unmapped = [], 0, 0, 0
    seen: set[tuple[int, int]] = set()
    for r in rows(src / "food_nutrient.csv"):
        fid = int(r["fdc_id"])
        if fid not in keep:
            continue
        amt = r.get("amount")
        if not amt:
            skipped += 1
            continue
        nid = int(r["nutrient_id"])
        if nid not in known_ids:
            mapped = by_nbr.get(nid)
            if mapped is None:
                # Referential filtering: a nutrient this export never defined.
                # Skipping beats failing the whole load on the foreign key.
                unmapped += 1
                continue
            nid = mapped
        key = (fid, nid)
        if key in seen:          # FDC ships occasional duplicates
            continue
        seen.add(key)
        recs.append((fid, nid, float(amt)))
        if len(recs) >= BATCH:
            await copy(con, "food_nutrient", ["fdc_id", "nutrient_id", "amount"], recs)
            n += len(recs)
            recs = []
            if n % 500_000 == 0:
                print(f"    {n:,}")
    await copy(con, "food_nutrient", ["fdc_id", "nutrient_id", "amount"], recs)
    n += len(recs)
    print(
        f"  {n:,} nutrient rows ({skipped:,} skipped for null amount, "
        f"{unmapped:,} for an undefined nutrient id)"
    )

    print("food_portion…")
    units = {r["id"]: r["name"] for r in rows(src / "measure_unit.csv")} \
        if (src / "measure_unit.csv").exists() else {}
    recs = []
    fp = src / "food_portion.csv"
    if fp.exists():
        for r in rows(fp):
            fid = int(r["fdc_id"])
            if fid not in keep or not r.get("gram_weight"):
                continue
            recs.append((
                int(r["id"]), fid,
                float(r["amount"]) if r.get("amount") else None,
                units.get(r.get("measure_unit_id", "")) or r.get("portion_description"),
                r.get("modifier"), float(r["gram_weight"]),
            ))
            if len(recs) >= BATCH:
                await copy(con, "food_portion", ["id", "fdc_id", "amount", "unit", "modifier", "gram_weight"], recs)
                recs = []
        await copy(con, "food_portion", ["id", "fdc_id", "amount", "unit", "modifier", "gram_weight"], recs)

    print("ANALYZE…")
    await con.execute("ANALYZE food; ANALYZE food_nutrient; ANALYZE nutrient;")
    await con.close()
    print("done")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(Path(sys.argv[1]), "--branded" in sys.argv))
