from __future__ import annotations

import datetime as dt
import decimal
import json
from typing import Any, Iterable, Sequence

import asyncpg

from .config import AUTO_MATCH_SIMILARITY, CORE_NUTRIENTS, settings
from .core.nutrition import ResolvedComponent, normalise_energy, total_nutrients

_pool: asyncpg.Pool | None = None


async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url, min_size=1, max_size=8, command_timeout=30
        )
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ------------------------------------------------------------------- users


def num(v: float | int | None, places: int = 4) -> decimal.Decimal | None:
    """Float -> Decimal, on the way into a `numeric` column.

    asyncpg hands Postgres the float's exact binary expansion, so 75.2 stores
    itself as 75.2000000000000028421709430404007434844970703125 and 1.55 as
    1.5500000000000000444089209850062616169452667236328125. Rounding the float
    first does not help — those *are* those values in binary — so the fix is to
    leave float behind before the column, not to tidy it afterwards.

    Nothing measured here has four decimal places of meaning; the point is that
    a stored number should not claim more precision than the thing it measures.
    """
    if v is None:
        return None
    d = decimal.Decimal(f"{float(v):.{places}f}")
    # normalize() alone turns 180 into 1.8E+2, which is the same number and a
    # worse thing to find in a column you read by eye.
    return d.quantize(decimal.Decimal(1)) if d == d.to_integral_value() else d.normalize()


async def get_or_create_user(telegram_id: int, name: str | None = None) -> asyncpg.Record:
    p = await pool()
    row = await p.fetchrow("SELECT * FROM app_user WHERE telegram_id = $1", telegram_id)
    if row:
        return row
    return await p.fetchrow(
        """INSERT INTO app_user (telegram_id, display_name, tz)
           VALUES ($1, $2, $3) RETURNING *""",
        telegram_id, name, settings.tz,
    )


def local_date_for(when: dt.datetime, tz: str, rollover_hour: int) -> dt.date:
    """The 01:09 glass of milk belongs to the day that has not yet ended."""
    import zoneinfo

    local = when.astimezone(zoneinfo.ZoneInfo(tz))
    return (local - dt.timedelta(hours=rollover_hour)).date()


# ------------------------------------------------------------- food lookup


async def resolve_alias(user_id: int, name: str) -> asyncpg.Record | None:
    """Exact-then-fuzzy alias hit. This is the path that makes the system get
    cheaper over time: every confirmed novel food writes an alias, and every
    later mention of it resolves here for zero tokens."""
    p = await pool()
    return await p.fetchrow(
        """SELECT a.*, f.description
             FROM food_alias a JOIN food f ON f.fdc_id = a.fdc_id
            WHERE a.user_id = $1
              AND (a.alias = lower($2) OR similarity(a.alias, lower($2)) > $3)
         ORDER BY (a.alias = lower($2)) DESC, similarity(a.alias, lower($2)) DESC, a.hits DESC
            LIMIT 1""",
        user_id, name.strip(), AUTO_MATCH_SIMILARITY,
    )


async def bump_alias(alias_id: int) -> None:
    p = await pool()
    await p.execute(
        "UPDATE food_alias SET hits = hits + 1, last_used_at = now() WHERE id = $1", alias_id
    )


async def upsert_alias(user_id: int, alias: str, fdc_id: int, default_grams: float | None) -> None:
    """A pinned alias is never re-pointed by a later automatic resolution.

    Without the guard, one bad parse six months from now silently redirects
    'mince' at a different USDA row and every subsequent log is wrong in a way
    that leaves no trace."""
    p = await pool()
    await p.execute(
        """INSERT INTO food_alias (user_id, alias, fdc_id, default_grams, hits, last_used_at)
           VALUES ($1, lower($2), $3, $4, 1, now())
           ON CONFLICT (user_id, alias)
           DO UPDATE SET fdc_id = CASE WHEN food_alias.pinned THEN food_alias.fdc_id
                                       ELSE EXCLUDED.fdc_id END,
                         hits = food_alias.hits + 1,
                         last_used_at = now()""",
        user_id, alias.strip(), fdc_id, default_grams,
    )


async def portion_history(user_id: int, fdc_id: int, limit: int = 30) -> list[float]:
    """Your own weighed masses for one food, most recent first."""
    p = await pool()
    rows = await p.fetch("SELECT grams FROM portion_history($1,$2,$3)", user_id, fdc_id, limit)
    return [float(r["grams"]) for r in rows]


async def search_foods(query: str, limit: int = 5, data_types: Sequence[str] | None = None,
                       user_id: int | None = None) -> list[asyncpg.Record]:
    """Candidate generation for the resolver.

    Full-text rank plus trigram similarity, with data-type precedence as the
    tie-breaker so a well-measured Foundation row beats a manufacturer's
    self-reported label *at comparable relevance*.

    Precedence must not outrank relevance, which is what ordering by it first
    does. Measured on the real tables: for `rice, white, long-grain, regular,
    cooked`, precedence-first puts `Rice, white, long grain, unenriched, raw`
    (similarity 0.48, and no energy value in FDC at all) above `Rice, white,
    long-grain, regular, enriched, cooked` (similarity 0.84, 130 kcal/100 g).
    Two things go wrong from there: the top candidate falls below
    AUTO_MATCH_SIMILARITY so a model call gets paid for, and the model is then
    handed a candidate list ordered worst-first. Picking the head of it logs
    cooked rice as a raw row with no calories — the "wrong USDA row, right
    grams" failure that drifts your totals and raises no error anywhere.
    """
    p = await pool()
    dt_filter = "AND f.data_type = ANY($4::text[])" if data_types else ""
    sql = f"""
        SELECT f.fdc_id, f.description, f.data_type, f.brand, f.precedence,
               similarity(f.description, $1) AS sim,
               ts_rank(to_tsvector('english', f.description),
                       plainto_tsquery('english', $1)) AS rank,
               EXISTS (SELECT 1 FROM food_nutrient fn
                        WHERE fn.fdc_id = f.fdc_id
                          AND fn.nutrient_id IN (1008, 2048, 2047)) AS has_energy
          FROM food f
         WHERE (to_tsvector('english', f.description) @@ plainto_tsquery('english', $1)
                OR f.description % $1)
               -- Somebody else's private food must never be a candidate for
               -- your meal, and your own must always be one.
               AND (f.owner_user_id IS NULL OR f.owner_user_id = $3)
               {dt_filter}
      ORDER BY (similarity(f.description, $1) + ts_rank(
                   to_tsvector('english', f.description),
                   plainto_tsquery('english', $1))) DESC,
               -- A row with no energy figure, ahead of precedence.
               --
               -- 276 of 411 Foundation rows carry no 1008 and no Atwater
               -- variant to fill it from, and precedence ranks Foundation
               -- first — so "butter" resolved to Butter, stick, unsalted at
               -- 81.5 g of fat and zero calories, and a user food built from
               -- it was stored with no energy at all. Relevance still leads;
               -- this only decides between rows that matched equally well.
               (EXISTS (SELECT 1 FROM food_nutrient fn
                         WHERE fn.fdc_id = f.fdc_id
                           AND fn.nutrient_id IN (1008, 2048, 2047))) DESC,
               f.precedence ASC
         LIMIT $2"""
    args: list[Any] = [query, limit, user_id]
    if data_types:
        args.append(list(data_types))
    return await p.fetch(sql, *args)


async def profiles_for(fdc_ids: Iterable[int]) -> dict[int, dict[int, float]]:
    p = await pool()
    return await _profiles_con(p, list(fdc_ids))


# ------------------------------------------------------------------ dishes


async def top_dishes(user_id: int, limit: int = 8, *, tz: str = "UTC",
                     hour: int | None = None) -> list[asyncpg.Record]:
    p = await pool()
    # Only dishes actually eaten at least once.
    #
    # `_present` creates the dish before the entry is confirmed, so every meal
    # ever parsed leaves one behind whether or not it was logged — including the
    # ones discarded precisely because they were wrong. A cappuccino containing
    # a phantom whisky cocktail was sitting in this menu at ×0, one tap from
    # being logged again. "Repeat" means something you have eaten; a dish with
    # no confirmed entry has never been a meal.
    #
    # Ordered by the hour you are asking, not only by how often you eat it.
    # At 07:00 the useful list is what you have before, and a flat
    # frequency ranking buried the morning water at rank 11 of 11 behind
    # every dinner. Dishes eaten near this time of day come first; frequency
    # and recency break the tie, and everything else follows behind them.
    return await p.fetch(
        """WITH near AS (
               SELECT e.dish_id, count(*) AS n_near
                 FROM log_entry e
                WHERE e.user_id = $1 AND e.status = 'confirmed'
                  AND e.dish_id IS NOT NULL AND $4::int IS NOT NULL
                  AND LEAST(
                        abs(EXTRACT(hour FROM e.logged_at AT TIME ZONE $3) - $4),
                        24 - abs(EXTRACT(hour FROM e.logged_at AT TIME ZONE $3) - $4)
                      ) <= 3
             GROUP BY e.dish_id
           )
           SELECT r.id, r.slug, r.name, r.default_slot, r.times_logged, r.score,
                  COALESCE(near.n_near, 0) AS n_near
             FROM v_dish_rank r
             LEFT JOIN near ON near.dish_id = r.id
            WHERE r.user_id = $1 AND r.times_logged > 0
         ORDER BY (COALESCE(near.n_near, 0) > 0) DESC,
                  COALESCE(near.n_near, 0) DESC,
                  r.score DESC, r.last_logged_at DESC NULLS LAST
            LIMIT $2""",
        user_id, limit, tz, hour,
    )


async def dish_by_slug(user_id: int, slug: str) -> asyncpg.Record | None:
    p = await pool()
    return await p.fetchrow(
        """SELECT * FROM dish
            WHERE user_id = $1 AND NOT archived
              AND (slug = lower($2) OR similarity(name, $2) > 0.5)
         ORDER BY (slug = lower($2)) DESC, similarity(name, $2) DESC LIMIT 1""",
        user_id, slug,
    )


async def dish_components(dish_id: int) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        """SELECT fdc_id, label, grams, state, yield_factor, optional, grams_source
             FROM dish_component WHERE dish_id = $1 ORDER BY position""",
        dish_id,
    )


async def template_by_slug(user_id: int, slug: str) -> tuple[asyncpg.Record, list[asyncpg.Record]] | None:
    p = await pool()
    t = await p.fetchrow(
        "SELECT * FROM meal_template WHERE user_id = $1 AND slug = lower($2)", user_id, slug
    )
    if not t:
        return None
    items = await p.fetch(
        """SELECT i.dish_id, i.grams_override, d.name, d.slug
             FROM meal_template_item i JOIN dish d ON d.id = i.dish_id
            WHERE i.template_id = $1 ORDER BY i.position""",
        t["id"],
    )
    return t, items


async def upsert_dish(
    user_id: int, slug: str, name: str, slot: str | None, components: list[ResolvedComponent],
    labels_state: list[tuple[str, float]] | None = None,
) -> int:
    p = await pool()
    async with p.acquire() as con, con.transaction():
        dish_id = await con.fetchval(
            """INSERT INTO dish (user_id, slug, name, default_slot)
               VALUES ($1, lower($2), $3, $4)
               ON CONFLICT (user_id, slug)
               DO UPDATE SET name = EXCLUDED.name, archived = false
               RETURNING id""",
            user_id, slug, name, slot,
        )
        await con.execute("DELETE FROM dish_component WHERE dish_id = $1", dish_id)
        await con.executemany(
            """INSERT INTO dish_component
                 (dish_id, position, fdc_id, label, grams, yield_factor, grams_source)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            # Provenance goes into the snapshot. Without it a repeat had
            # nothing to inherit, every component was written as a guess, and
            # the day's measurement quality fell each time a well-specified
            # dish was correctly reused. See sql/008_repeat_provenance.sql.
            [(dish_id, i, c.fdc_id, c.label, c.grams, c.yield_factor, c.grams_source)
             for i, c in enumerate(components)],
        )
    return dish_id


# -------------------------------------------------------------------- log


async def create_pending_entry(
    user_id: int, name: str, components: list[ResolvedComponent], *, source: str,
    slot: str | None, confidence: float | None, model: str | None, parse: dict | None,
    photo_file_id: str | None, dish_id: int | None, when: dt.datetime | None = None,
    tz: str = "Europe/Warsaw", rollover_hour: int = 4, grams_sources: list[str] | None = None,
) -> int:
    """Write the entry as `pending`. Nothing counts until a human presses yes.

    Dry-run-by-default is not ceremony. A silently wrong 680 kcal entry poisons
    every average, every trend, and every recommendation built on top of them,
    and you will not notice for weeks.
    """
    when = when or dt.datetime.now(dt.timezone.utc)
    p = await pool()
    async with p.acquire() as con, con.transaction():
        entry_id = await con.fetchval(
            """INSERT INTO log_entry
                 (user_id, logged_at, local_date, slot, dish_id, name, total_grams,
                  source, confidence, model, parse, photo_file_id, status)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'pending') RETURNING id""",
            user_id, when, local_date_for(when, tz, rollover_hour), slot, dish_id, name,
            sum(c.grams for c in components), source, confidence, model,
            json.dumps(parse) if parse else None, photo_file_id,
        )
        await con.executemany(
            """INSERT INTO log_component
                 (entry_id, position, fdc_id, label, grams, yield_factor,
                  grams_source, grams_sigma)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            [(entry_id, i, c.fdc_id, c.label, c.grams, c.yield_factor,
              (grams_sources[i] if grams_sources and i < len(grams_sources) else c.grams_source),
              c.sigma)
             for i, c in enumerate(components)],
        )
    return entry_id


async def confirm_entry(entry_id: int) -> dict[int, float]:
    """Snapshot the nutrients and mark the entry confirmed.

    The snapshot is the point. USDA republishes; foods get recategorised; you
    fix a wrong match six weeks later. None of that may retroactively change
    what last March looked like.
    """
    p = await pool()
    async with p.acquire() as con, con.transaction():
        comps = await con.fetch(
            """SELECT fdc_id, label, grams, yield_factor, grams_sigma, grams_source
                 FROM log_component WHERE entry_id = $1 ORDER BY position""",
            entry_id,
        )
        resolved = [
            ResolvedComponent(
                r["label"], r["fdc_id"], float(r["grams"]), float(r["yield_factor"]),
                float(r["grams_sigma"] or 0), r["grams_source"],
            )
            for r in comps
        ]
        profs = await _profiles_con(con, [r.fdc_id for r in resolved])
        totals = total_nutrients(resolved, profs)

        await con.execute("DELETE FROM log_nutrient WHERE entry_id = $1", entry_id)
        await con.executemany(
            "INSERT INTO log_nutrient (entry_id, nutrient_id, amount) VALUES ($1,$2,$3)",
            [(entry_id, nid, amt) for nid, amt in totals.items()],
        )
        await con.execute("UPDATE log_entry SET status = 'confirmed' WHERE id = $1", entry_id)
        await con.execute(
            """UPDATE dish SET times_logged = times_logged + 1, last_logged_at = now()
                WHERE id = (SELECT dish_id FROM log_entry WHERE id = $1)""",
            entry_id,
        )
    return totals


async def _profiles_con(con: Any, fdc_ids: Iterable[int]) -> dict[int, dict[int, float]]:
    """Per-100 g nutrient profiles, keyed by fdc_id.

    The one place a food's nutrients enter the system, which is why the energy
    normalisation lives here: it then applies identically to the confirm-time
    snapshot, to the validation pass, and to anything else that reads a profile.
    """
    ids = list({int(i) for i in fdc_ids})
    if not ids:
        return {}
    rows = await con.fetch(
        "SELECT fdc_id, nutrient_id, amount FROM food_nutrient WHERE fdc_id = ANY($1::int[])", ids
    )
    out: dict[int, dict[int, float]] = {i: {} for i in ids}
    for r in rows:
        out[r["fdc_id"]][r["nutrient_id"]] = float(r["amount"])
    return {fid: normalise_energy(prof) for fid, prof in out.items()}


async def last_confirmed_entry(user_id: int, day: dt.date) -> asyncpg.Record | None:
    """Peek at what /undo would take, without taking it."""
    p = await pool()
    return await p.fetchrow(
        """SELECT e.*, COALESCE(k.amount, 0) AS kcal
             FROM log_entry e
             LEFT JOIN log_nutrient k ON k.entry_id = e.id AND k.nutrient_id = 1008
            WHERE e.user_id = $1 AND e.local_date = $2 AND e.status = 'confirmed'
         ORDER BY e.logged_at DESC, e.id DESC LIMIT 1""",
        user_id, day,
    )


async def confirmed_entries_on(user_id: int, day: dt.date) -> list[asyncpg.Record]:
    """Everything confirmed on a day, newest first, for picking one to undo."""
    p = await pool()
    return await p.fetch(
        """SELECT e.id, e.name, e.logged_at, COALESCE(k.amount, 0) AS kcal
             FROM log_entry e
             LEFT JOIN log_nutrient k ON k.entry_id = e.id AND k.nutrient_id = 1008
            WHERE e.user_id = $1 AND e.local_date = $2 AND e.status = 'confirmed'
         ORDER BY e.logged_at DESC, e.id DESC""",
        user_id, day,
    )


async def undo_entry(user_id: int, entry_id: int) -> asyncpg.Record | None:
    """Discard one confirmed entry by id, and correct its dish's counter."""
    p = await pool()
    async with p.acquire() as con, con.transaction():
        entry = await con.fetchrow(
            """SELECT * FROM log_entry
                WHERE id = $1 AND user_id = $2 AND status = 'confirmed' FOR UPDATE""",
            entry_id, user_id,
        )
        if not entry:
            return None
        await con.execute("UPDATE log_entry SET status = 'discarded' WHERE id = $1", entry_id)
        if entry["dish_id"]:
            await con.execute(
                """UPDATE dish d
                      SET times_logged = GREATEST(d.times_logged - 1, 0),
                          last_logged_at = (
                              SELECT max(e.logged_at) FROM log_entry e
                               WHERE e.dish_id = d.id AND e.status = 'confirmed')
                    WHERE d.id = $1""",
                entry["dish_id"],
            )
        return entry


async def undo_last_entry(user_id: int, day: dt.date) -> asyncpg.Record | None:
    """Discard the most recent confirmed entry of a day. Returns it, or None.

    Discarded, never deleted. `log_nutrient` is a snapshot and invariant 2 says
    it is never rewritten — every rollup already filters on status='confirmed',
    so flipping the status removes it from the arithmetic while leaving the
    record of what was logged and unlogged intact.

    Scoped to one day because "undo" means the thing you just did. A bare /undo
    reaching back into last week to silently remove a meal would be a worse
    failure than the one it was trying to fix.
    """
    p = await pool()
    async with p.acquire() as con, con.transaction():
        entry = await con.fetchrow(
            """SELECT * FROM log_entry
                WHERE user_id = $1 AND local_date = $2 AND status = 'confirmed'
             ORDER BY logged_at DESC, id DESC LIMIT 1
             FOR UPDATE""",
            user_id, day,
        )
        if not entry:
            return None
        await con.execute(
            "UPDATE log_entry SET status = 'discarded' WHERE id = $1", entry["id"]
        )
        if entry["dish_id"]:
            # times_logged gates the no-confirmation repeat path, so leaving it
            # inflated would let an undone dish log instantly next time.
            await con.execute(
                """UPDATE dish d
                      SET times_logged = GREATEST(d.times_logged - 1, 0),
                          last_logged_at = (
                              SELECT max(e.logged_at) FROM log_entry e
                               WHERE e.dish_id = d.id AND e.status = 'confirmed')
                    WHERE d.id = $1""",
                entry["dish_id"],
            )
        return entry


async def discard_entry(entry_id: int) -> None:
    p = await pool()
    await p.execute("UPDATE log_entry SET status = 'discarded' WHERE id = $1", entry_id)


async def entry_with_components(entry_id: int) -> tuple[asyncpg.Record, list[asyncpg.Record]]:
    p = await pool()
    e = await p.fetchrow("SELECT * FROM log_entry WHERE id = $1", entry_id)
    c = await p.fetch(
        "SELECT * FROM log_component WHERE entry_id = $1 ORDER BY position", entry_id
    )
    return e, c


# --------------------------------------------------------------- rollups


async def day_progress(user_id: int, day: dt.date, core_only: bool = True) -> list[asyncpg.Record]:
    p = await pool()
    rows = await p.fetch("SELECT * FROM day_progress($1, $2)", user_id, day)
    if core_only:
        core = set(CORE_NUTRIENTS)
        rows = [r for r in rows if r["nutrient_id"] in core]
    return rows


async def day_coverage(user_id: int, day: dt.date) -> dict[int, float]:
    """nutrient_id -> fraction of the day's mass whose food row reports it.

    Without this, a plate of beef reports "Vitamin B-12 0.0 µg, 0% of target"
    because the Foundation beef row does not carry B-12 — a measurement gap
    rendered as a dietary one. Skipping nulls keeps the arithmetic honest; only
    coverage keeps the *display* honest.
    """
    p = await pool()
    rows = await p.fetch("SELECT * FROM day_nutrient_coverage($1, $2)", user_id, day)
    return {r["nutrient_id"]: float(r["covered_frac"] or 0) for r in rows}


async def day_entries(user_id: int, day: dt.date) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        """SELECT e.id, e.logged_at, e.slot, e.name, e.total_grams, e.source, e.confidence,
                  COALESCE(k.amount,0) AS kcal, COALESCE(pr.amount,0) AS protein
             FROM log_entry e
             LEFT JOIN log_nutrient k  ON k.entry_id = e.id AND k.nutrient_id = 1008
             LEFT JOIN log_nutrient pr ON pr.entry_id = e.id AND pr.nutrient_id = 1003
            WHERE e.user_id = $1 AND e.local_date = $2 AND e.status = 'confirmed'
         ORDER BY e.logged_at""",
        user_id, day,
    )


async def day_mass_confidence(user_id: int, day: dt.date) -> asyncpg.Record | None:
    p = await pool()
    return await p.fetchrow(
        "SELECT * FROM v_day_mass_confidence WHERE user_id = $1 AND local_date = $2", user_id, day
    )


async def day_energy_sigma(user_id: int, day: dt.date, nutrient_id: int = 1008) -> float:
    """Quadrature-summed 1-sigma on one nutrient for a whole day.

    Computed from stored per-component sigma and the stored USDA profile, so it
    is reproducible from the database alone and does not depend on whatever the
    parser was thinking at the time."""
    p = await pool()
    val = await p.fetchval(
        """SELECT sqrt(sum((c.grams_sigma * c.yield_factor * fn.amount / 100.0) ^ 2))
             FROM log_entry e
             JOIN log_component c ON c.entry_id = e.id
             JOIN food_nutrient fn ON fn.fdc_id = c.fdc_id AND fn.nutrient_id = $3
            WHERE e.user_id = $1 AND e.local_date = $2 AND e.status = 'confirmed'""",
        user_id, day, nutrient_id,
    )
    return float(val or 0.0)


async def window_medians(user_id: int, days: int, nutrient_ids: Sequence[int]) -> dict[int, float]:
    """Median daily intake over the last N complete days. Medians, not means:
    one 2,441 kcal Saturday should not redefine your week."""
    p = await pool()
    rows = await p.fetch(
        """WITH d AS (
             SELECT local_date, nutrient_id, sum(amount) AS amt
               FROM v_day_nutrient
              WHERE user_id = $1 AND nutrient_id = ANY($2::int[])
                AND local_date >= (current_date - $3::int)
                AND local_date < current_date
           GROUP BY local_date, nutrient_id)
           SELECT nutrient_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY amt) AS med
             FROM d GROUP BY nutrient_id""",
        user_id, list(nutrient_ids), days,
    )
    return {r["nutrient_id"]: float(r["med"] or 0) for r in rows}


# ------------------------------------------------------------------ fasting


async def meal_times(user_id: int, days: int = 14) -> list[dt.datetime]:
    p = await pool()
    rows = await p.fetch(
        """SELECT logged_at FROM v_meal_time
            WHERE user_id = $1 AND local_date > current_date - $2::int
         ORDER BY logged_at""",
        user_id, days,
    )
    return [r["logged_at"] for r in rows]


async def eating_windows(user_id: int, days: int = 14) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        """SELECT * FROM v_eating_window
            WHERE user_id = $1 AND local_date > current_date - $2::int
         ORDER BY local_date""",
        user_id, days,
    )


async def current_fast_hours(user_id: int) -> float:
    p = await pool()
    return float(await p.fetchval("SELECT current_fast_hours($1)", user_id) or 0.0)


async def log_observation(
    user_id: int, kind: str, value: float, *, scale: str = "1-10",
    note: str | None = None, tz: str = "Europe/Warsaw", rollover_hour: int = 4,
) -> int:
    """Stamp the observation with the fasting state it was made in.

    Recomputing this later from the log would be subtly wrong the moment you
    correct a meal's timestamp, and the correlation would silently shift."""
    now = dt.datetime.now(dt.timezone.utc)
    p = await pool()
    async with p.acquire() as con, con.transaction():
        hours = await con.fetchval("SELECT fast_hours_at($1,$2)", user_id, now)
        kcal = await con.fetchval(
            """SELECT COALESCE(sum(ln.amount),0) FROM log_entry e
                 JOIN log_nutrient ln ON ln.entry_id = e.id AND ln.nutrient_id = 1008
                WHERE e.user_id = $1 AND e.local_date = $2 AND e.status = 'confirmed'""",
            user_id, local_date_for(now, tz, rollover_hour),
        )
        return await con.fetchval(
            """INSERT INTO observation
                 (user_id, observed_at, local_date, kind, value, scale,
                  hours_fasted, kcal_since_waking, note)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id""",
            user_id, now, local_date_for(now, tz, rollover_hour), kind, value, scale,
            hours, kcal, note,
        )


async def observations(user_id: int, kind: str, days: int = 90) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        """SELECT observed_at, value, hours_fasted, kcal_since_waking
             FROM observation
            WHERE user_id = $1 AND kind = $2
              AND observed_at > now() - ($3 || ' days')::interval
              AND hours_fasted IS NOT NULL
         ORDER BY observed_at""",
        user_id, kind, str(days),
    )


async def log_body_metric(
    user_id: int, kind: str, value: float, *, note: str | None = None,
    tz: str = "Europe/Warsaw", rollover_hour: int = 4,
) -> tuple[int, float | None]:
    """Write one body measurement. Returns its id and the previous value.

    Generic in `kind` because the table is: weight_kg today, bodyfat_pct and
    blood markers later, all read by the same window functions.

    The previous value comes back so the caller can show a delta without a
    second round trip — and so an implausible jump can be pointed out at the
    moment it is entered, which is the only moment anyone remembers what they
    actually saw on the scale.
    """
    now = dt.datetime.now(dt.timezone.utc)
    p = await pool()
    async with p.acquire() as con, con.transaction():
        prev = await con.fetchval(
            """SELECT value FROM body_metric
                WHERE user_id = $1 AND kind = $2
             ORDER BY measured_at DESC LIMIT 1""",
            user_id, kind,
        )
        new_id = await con.fetchval(
            """INSERT INTO body_metric (user_id, measured_at, local_date, kind, value, note)
               VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""",
            user_id, now, local_date_for(now, tz, rollover_hour), kind, num(value, 2), note,
        )
    return new_id, (float(prev) if prev is not None else None)


async def weight_span_days(user_id: int) -> int:
    """Calendar days between the first and last weigh-in. `/insight` needs 14."""
    p = await pool()
    row = await p.fetchrow(
        """SELECT min(local_date) AS lo, max(local_date) AS hi
             FROM body_metric WHERE user_id = $1 AND kind = 'weight_kg'""",
        user_id,
    )
    if not row or row["lo"] is None:
        return 0
    return (row["hi"] - row["lo"]).days + 1


async def weight_series(user_id: int, days: int = 42) -> list[tuple[dt.date, float]]:
    p = await pool()
    rows = await p.fetch(
        """SELECT local_date, avg(value) AS v FROM body_metric
            WHERE user_id = $1 AND kind = 'weight_kg'
              AND local_date > current_date - $2::int
         GROUP BY local_date ORDER BY local_date""",
        user_id, days,
    )
    return [(r["local_date"], float(r["v"])) for r in rows]


async def daily_energy(user_id: int, days: int = 42) -> list[float]:
    p = await pool()
    rows = await p.fetch(
        """SELECT sum(amount) AS kcal FROM v_day_nutrient
            WHERE user_id = $1 AND nutrient_id = 1008
              AND local_date > current_date - $2::int
              AND local_date < current_date
         GROUP BY local_date ORDER BY local_date""",
        user_id, days,
    )
    return [float(r["kcal"]) for r in rows]


# ---------------------------------------------------------- observability


async def record_llm_call(**kw: Any) -> None:
    p = await pool()
    await p.execute(
        """INSERT INTO llm_call
             (user_id, entry_id, purpose, model, input_tokens, output_tokens,
              cache_read_tokens, cache_write_tokens, latency_ms, cost_usd, ok, error)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
        kw.get("user_id"), kw.get("entry_id"), kw["purpose"], kw["model"],
        kw.get("input_tokens", 0), kw.get("output_tokens", 0),
        kw.get("cache_read_tokens", 0), kw.get("cache_write_tokens", 0),
        kw.get("latency_ms"), kw.get("cost_usd", 0), kw.get("ok", True), kw.get("error"),
    )


async def spend_report(user_id: int, days: int = 30) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        """SELECT purpose, model, count(*) AS calls,
                  sum(input_tokens) AS tin, sum(output_tokens) AS tout,
                  sum(cache_read_tokens) AS cached, round(sum(cost_usd),4) AS usd
             FROM llm_call
            WHERE user_id = $1 AND created_at >= now() - ($2 || ' days')::interval
         GROUP BY purpose, model ORDER BY usd DESC""",
        user_id, str(days),
    )


# ------------------------------------------------------------ pending actions


async def put_pending(user_id: int, kind: str, payload: dict) -> int:
    p = await pool()
    return await p.fetchval(
        "INSERT INTO pending_action (user_id, kind, payload) VALUES ($1,$2,$3) RETURNING id",
        user_id, kind, json.dumps(payload),
    )


async def take_pending(action_id: int) -> dict | None:
    p = await pool()
    row = await p.fetchrow(
        "SELECT payload FROM pending_action WHERE id = $1 AND expires_at > now()", action_id
    )
    return json.loads(row["payload"]) if row else None


async def clear_pending(user_id: int, kind: str) -> None:
    """Consume every outstanding action of a kind.

    A pending action that is read but never cleared turns into a mode: the next
    message, and every message after it, gets treated as a correction to a card
    from an hour ago."""
    p = await pool()
    await p.execute("DELETE FROM pending_action WHERE user_id = $1 AND kind = $2", user_id, kind)


async def replace_components(entry_id: int, components: list[ResolvedComponent],
                             grams_sources: list[str] | None = None) -> None:
    """Swap an entry's components. Only legal while it is still pending."""
    p = await pool()
    async with p.acquire() as con, con.transaction():
        status = await con.fetchval(
            "SELECT status FROM log_entry WHERE id = $1 FOR UPDATE", entry_id
        )
        if status != "pending":
            raise ValueError(f"entry {entry_id} is {status}, not pending")
        await con.execute("DELETE FROM log_component WHERE entry_id = $1", entry_id)
        await con.executemany(
            """INSERT INTO log_component
                 (entry_id, position, fdc_id, label, grams, yield_factor,
                  grams_source, grams_sigma)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            [(entry_id, i, c.fdc_id, c.label, c.grams, c.yield_factor,
              (grams_sources[i] if grams_sources and i < len(grams_sources) else c.grams_source),
              c.sigma)
             for i, c in enumerate(components)],
        )
        await con.execute(
            "UPDATE log_entry SET total_grams = $2 WHERE id = $1",
            entry_id, sum(c.grams for c in components),
        )


async def latest_pending(user_id: int, kind: str,
                         within_minutes: int | None = None) -> dict | None:
    """`within_minutes` narrows it to a recently-opened prompt.

    pending_action expires after two hours, which is right for "confirm this
    meal" and far too long for "the next photo is a supplement label" — a tap
    in the afternoon captured a plate of dinner.
    """
    p = await pool()
    row = await p.fetchrow(
        """SELECT payload FROM pending_action
            WHERE user_id = $1 AND kind = $2 AND expires_at > now()
              AND ($3::int IS NULL
                   OR created_at > now() - make_interval(mins => $3))
         ORDER BY created_at DESC LIMIT 1""",
        user_id, kind, within_minutes,
    )
    return json.loads(row["payload"]) if row else None


# -------------------------------------------------------------- supplements


async def nutrient_units(nutrient_ids: Sequence[int] | None = None) -> dict[int, str]:
    """nutrient_id -> the unit the rest of the system counts it in."""
    p = await pool()
    if nutrient_ids:
        rows = await p.fetch(
            "SELECT id, unit FROM nutrient WHERE id = ANY($1::int[])", list(nutrient_ids)
        )
    else:
        rows = await p.fetch("SELECT id, unit FROM nutrient")
    return {r["id"]: r["unit"] for r in rows}


async def upsert_supplement(
    user_id: int, name: str, nutrients: list[tuple[int, float]], *,
    brand: str | None = None, serving_desc: str = "1 serving",
    servings_per_day: float = 1.0, photo_file_id: str | None = None,
    source: str = "label_photo", schedule: str = "daily", note: str | None = None,
) -> int:
    """Create or replace one supplement and its whole panel.

    The panel is replaced wholesale rather than merged: a re-read of a label is
    a new statement of what the product contains, and merging would leave a
    nutrient behind from a previous reformulation with nothing to indicate it.
    """
    p = await pool()
    async with p.acquire() as con, con.transaction():
        sup_id = await con.fetchval(
            """INSERT INTO supplement
                 (user_id, name, brand, serving_desc, servings_per_day,
                  photo_file_id, source, schedule, note, verified_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, now())
               ON CONFLICT (user_id, name) DO UPDATE
                 SET brand = EXCLUDED.brand,
                     serving_desc = EXCLUDED.serving_desc,
                     servings_per_day = EXCLUDED.servings_per_day,
                     photo_file_id = EXCLUDED.photo_file_id,
                     source = EXCLUDED.source,
                     schedule = EXCLUDED.schedule,
                     note = COALESCE(EXCLUDED.note, supplement.note),
                     verified_at = now(),
                     active = true
               RETURNING id""",
            user_id, name.strip(), brand, serving_desc, servings_per_day,
            photo_file_id, source, schedule, note,
        )
        await con.execute("DELETE FROM supplement_nutrient WHERE supplement_id = $1", sup_id)
        await con.executemany(
            "INSERT INTO supplement_nutrient (supplement_id, nutrient_id, amount) VALUES ($1,$2,$3)",
            [(sup_id, nid, amt) for nid, amt in nutrients],
        )
    return sup_id


async def supplement_stack(user_id: int, active_only: bool = True,
                           on_day: dt.date | None = None) -> list[asyncpg.Record]:
    """`on_day` hides anything not started yet — for the daily picker.

    /stack and /schedule pass nothing, because a supplement you have decided on
    but not begun is exactly what those screens exist to show.
    """
    p = await pool()
    started = "AND (s.starts_on IS NULL OR s.starts_on <= $2)" if on_day else ""
    args: list[Any] = [user_id] + ([on_day] if on_day else [])
    return await p.fetch(
        f"""SELECT s.*, (SELECT count(*) FROM supplement_nutrient sn
                          WHERE sn.supplement_id = s.id) AS n_nutrients
              FROM supplement s
             WHERE s.user_id = $1 {'AND s.active' if active_only else ''} {started}
          ORDER BY s.name""",
        *args,
    )


async def log_supplements(user_id: int, day: dt.date,
                          supplement_ids: Sequence[int] | None = None,
                          *, via: str = "manual") -> int:
    """Record today's stack. Idempotent: taking it twice is not taking double."""
    p = await pool()
    async with p.acquire() as con, con.transaction():
        if supplement_ids is None:
            rows = await con.fetch(
                """SELECT id, servings_per_day FROM supplement
                    WHERE user_id=$1 AND active
                      AND (starts_on IS NULL OR starts_on <= $2)""",
                user_id, day,
            )
        else:
            # starts_on is checked here as well as in the picker. It was only
            # honoured where things are pre-ticked, so a supplement dated to
            # October could still be ticked by hand in August and logged —
            # and it contributed nothing, because a product you have not
            # started has no panel read off it yet either.
            rows = await con.fetch(
                """SELECT id, servings_per_day FROM supplement
                    WHERE user_id=$1 AND id = ANY($2::bigint[])
                      AND (starts_on IS NULL OR starts_on <= $3)""",
                user_id, list(supplement_ids), day,
            )
        for r in rows:
            await con.execute(
                """INSERT INTO supplement_log
                     (user_id, supplement_id, local_date, servings, logged_via)
                   VALUES ($1,$2,$3,$4,$5)
                   ON CONFLICT (user_id, supplement_id, local_date)
                   DO UPDATE SET servings = EXCLUDED.servings, taken_at = now()""",
                user_id, r["id"], day, r["servings_per_day"], via,
            )
        return len(rows)


async def supplements_logged_on(user_id: int, day: dt.date) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        """SELECT s.name, sl.servings, sl.taken_at, sl.logged_via
             FROM supplement_log sl
             JOIN supplement s ON s.id = sl.supplement_id
            WHERE sl.user_id = $1 AND sl.local_date = $2 ORDER BY s.name""",
        user_id, day,
    )


async def unlog_supplements(user_id: int, day: dt.date) -> int:
    p = await pool()
    return int(
        (await p.execute(
            "DELETE FROM supplement_log WHERE user_id = $1 AND local_date = $2", user_id, day
        )).split()[-1]
    )


async def supplements_due(user_id: int, day: dt.date) -> list[int]:
    """Which of the stack to pre-tick for a day.

    daily      always · alternate  only if it was not taken yesterday ·
    occasional never, because "occasional" pre-ticked every day is just daily
    with extra steps.

    Pre-ticking everything trains you to untick, and the day you forget is the
    day an untaken capsule lands in your totals.
    """
    p = await pool()
    rows = await p.fetch(
        """SELECT s.id, s.schedule, s.starts_on,
                  EXISTS (SELECT 1 FROM supplement_log l
                           WHERE l.supplement_id = s.id AND l.local_date = $2::date - 1) AS took_yesterday
             FROM supplement s
            WHERE s.user_id = $1 AND s.active""",
        user_id, day,
    )
    due = []
    for r in rows:
        # Decided on but not started. Pre-ticking it would put a capsule you
        # did not swallow into the day's totals, which is the one direction of
        # error this whole path is built to avoid.
        if r["starts_on"] and r["starts_on"] > day:
            continue
        if r["schedule"] == "daily":
            due.append(r["id"])
        elif r["schedule"] == "alternate" and not r["took_yesterday"]:
            due.append(r["id"])
    return due


# --------------------------------------------------------------- activity


async def record_activity(
    user_id: int, day: dt.date, kind: str, *,
    minutes: int | None = None, kcal_burned: float | None = None,
    intensity: str | None = None, rpe: float | None = None,
    note: str | None = None,
) -> tuple[int, bool]:
    """Append one session. Returns (id, created).

    Idempotent on (user, date, kind, minutes), because a workout bot that
    retries on a timeout will eventually retry on a success, and a duplicated
    training day would quietly double a covariate rather than fail loudly.
    """
    p = await pool()
    async with p.acquire() as con, con.transaction():
        existing = await con.fetchval(
            """SELECT id FROM activity
                WHERE user_id = $1 AND local_date = $2 AND kind = $3
                  AND minutes IS NOT DISTINCT FROM $4
                  AND intensity IS NOT DISTINCT FROM $5""",
            user_id, day, kind, minutes, intensity,
        )
        if existing:
            return existing, False
        new_id = await con.fetchval(
            """INSERT INTO activity
                 (user_id, local_date, kind, minutes, kcal_burned, intensity, rpe, note)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
            user_id, day, kind, minutes, kcal_burned, intensity, rpe, note,
        )
        return new_id, True


async def activity_on(user_id: int, day: dt.date) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        "SELECT * FROM activity WHERE user_id = $1 AND local_date = $2 ORDER BY id",
        user_id, day,
    )


async def sleep_predictors(user_id: int, days: int = 120) -> list[asyncpg.Record]:
    """Each sleep rating against the day *before* it.

    Sleep is the one rating whose cause precedes it by a whole day, and the
    snapshot taken at rating time is the wrong evidence entirely: rate at 08:00
    and `hours_fasted` records the overnight fast, which says nothing about the
    dinner that might have disturbed it. So the join goes backwards.

    The rollover hour does the right thing here for free — a 01:00 snack already
    belongs to the previous local_date, which is exactly the day whose eating
    could have affected that night.
    """
    p = await pool()
    return await p.fetch(
        """
        WITH sleep AS (
            SELECT o.local_date, o.value, o.observed_at
              FROM observation o
             WHERE o.user_id = $1 AND o.kind = 'sleep'
               AND o.local_date > current_date - $2::int
        ),
        tz AS (SELECT tz FROM app_user WHERE id = $1),
        intake AS (
            SELECT e.local_date,
                   sum(CASE WHEN ln.nutrient_id = 1008 THEN ln.amount END) AS kcal,
                   sum(CASE WHEN ln.nutrient_id = 1018 THEN ln.amount END) AS alcohol_g,
                   sum(CASE WHEN ln.nutrient_id = 1057 THEN ln.amount END) AS caffeine_mg,
                   -- Caffeine's half-life is about five hours, so a 16:00 coffee
                   -- is still half-present at 21:00. The total says little; the
                   -- afternoon share is the part that reaches bedtime.
                   -- In the user's own timezone. logged_at is stored UTC, and
                   -- reading its hour raw put the cutoff at 14:00 Warsaw in
                   -- summer and 13:00 in winter — a threshold that drifts with
                   -- daylight saving is not a threshold.
                   sum(CASE WHEN ln.nutrient_id = 1057
                             AND extract(hour from e.logged_at AT TIME ZONE (SELECT tz FROM tz)) >= 12
                            THEN ln.amount END)                            AS caffeine_pm_mg,
                   max(e.logged_at) FILTER (
                       WHERE ln.nutrient_id = 1057 AND ln.amount > 0)      AS last_caffeine_at,
                   max(e.logged_at)                                        AS last_meal_at
              FROM log_entry e
              JOIN log_nutrient ln ON ln.entry_id = e.id
             WHERE e.user_id = $1 AND e.status = 'confirmed'
          GROUP BY e.local_date
        ),
        load AS (
            SELECT a.local_date,
                   sum(COALESCE(a.minutes, 0))     AS minutes,
                   sum(COALESCE(a.kcal_burned, 0)) AS kcal_burned,
                   bool_or(a.kind = 'lifting')     AS lifted,
                   -- Hard sessions, not sessions. 45 minutes easy and 45
                   -- minutes at threshold demand different things afterwards,
                   -- and pooling them flattens the signal being looked for.
                   bool_or(a.intensity IN ('hard', 'max')) AS hard_session,
                   max(a.rpe)                      AS peak_rpe
              FROM activity a WHERE a.user_id = $1
          GROUP BY a.local_date
        )
        SELECT s.local_date,
               s.value                              AS sleep,
               COALESCE(i.kcal, 0)                  AS kcal_yesterday,
               COALESCE(i.alcohol_g, 0)             AS alcohol_yesterday,
               COALESCE(i.caffeine_mg, 0)           AS caffeine_yesterday,
               COALESCE(i.caffeine_pm_mg, 0)        AS caffeine_pm_yesterday,
               i.last_caffeine_at,
               i.last_meal_at,
               COALESCE(l.minutes, 0)               AS training_minutes,
               COALESCE(l.kcal_burned, 0)           AS training_kcal,
               COALESCE(l.lifted, false)            AS lifted
          FROM sleep s
          LEFT JOIN intake i ON i.local_date = s.local_date - 1
          LEFT JOIN load   l ON l.local_date = s.local_date - 1
         ORDER BY s.local_date
        """,
        user_id, days,
    )


async def is_first_entry_of_day(user_id: int, day: dt.date, entry_id: int) -> bool:
    """True when this is the only confirmed entry so far today."""
    p = await pool()
    return await p.fetchval(
        """SELECT count(*) = 0 FROM log_entry
            WHERE user_id = $1 AND local_date = $2 AND status = 'confirmed'
              AND id <> $3""",
        user_id, day, entry_id,
    )


async def week_rows(user_id: int, end_day: dt.date, days: int = 7) -> list[asyncpg.Record]:
    """Per-nutrient, per-day progress across a window.

    A lateral join over day_progress() rather than a second aggregation: the
    per-day arithmetic, the supplement split and the versioned target lookup are
    already correct there, and writing them again for the weekly view is how the
    two come to disagree.

    Days with nothing confirmed are excluded. A day you did not log is not a day
    you missed every floor, and counting it as one turns "did not use the app on
    Saturday" into "ate badly on Saturday".
    """
    p = await pool()
    return await p.fetch(
        """
        WITH span AS (
            SELECT generate_series($2::date - ($3::int - 1), $2::date, '1 day')::date AS d
        ),
        logged AS (
            SELECT s.d FROM span s
             WHERE EXISTS (SELECT 1 FROM log_entry e
                            WHERE e.user_id = $1 AND e.local_date = s.d
                              AND e.status = 'confirmed')
        )
        SELECT l.d AS day, p.*
          FROM logged l, LATERAL day_progress($1, l.d) p
      ORDER BY l.d, p.nutrient_id
        """,
        user_id, end_day, days,
    )


async def week_context(user_id: int, end_day: dt.date, days: int = 7) -> dict[str, Any]:
    """The non-nutrient facts a weekly report needs."""
    p = await pool()
    start = end_day - dt.timedelta(days=days - 1)
    row = await p.fetchrow(
        """
        SELECT (SELECT count(*) FROM log_entry
                 WHERE user_id = $1 AND status = 'confirmed'
                   AND local_date BETWEEN $2 AND $3)                       AS meals,
               (SELECT count(DISTINCT local_date) FROM log_entry
                 WHERE user_id = $1 AND status = 'confirmed'
                   AND local_date BETWEEN $2 AND $3)                       AS days_logged,
               (SELECT round(avg(pct_measured)) FROM v_day_mass_confidence
                 WHERE user_id = $1 AND local_date BETWEEN $2 AND $3)      AS pct_measured,
               (SELECT count(DISTINCT local_date) FROM supplement_log
                 WHERE user_id = $1 AND local_date BETWEEN $2 AND $3)      AS supp_days,
               (SELECT round(sum(cost_usd) * 100, 1) FROM llm_call
                 WHERE user_id = $1 AND created_at::date BETWEEN $2 AND $3) AS cents,
               (SELECT count(*) FROM activity
                 WHERE user_id = $1 AND local_date BETWEEN $2 AND $3)      AS sessions
        """,
        user_id, start, end_day,
    )
    weights = await p.fetch(
        """SELECT local_date, value FROM body_metric
            WHERE user_id = $1 AND kind = 'weight_kg' AND local_date BETWEEN $2 AND $3
         ORDER BY local_date""",
        user_id, start, end_day,
    )
    out = dict(row) if row else {}
    out["weights"] = [(r["local_date"], float(r["value"])) for r in weights]
    out["start"], out["end"] = start, end_day
    return out


async def latest_await(user_id: int, kinds: Sequence[str]) -> dict | None:
    """The most recent outstanding prompt among `kinds`, or None.

    Newest wins. If you press ✏️ and then send /weight, the weight prompt is the
    one you are answering — the older one has been superseded by your own next
    action, not abandoned.
    """
    p = await pool()
    row = await p.fetchrow(
        """SELECT kind, payload FROM pending_action
            WHERE user_id = $1 AND kind = ANY($2::text[]) AND expires_at > now()
         ORDER BY created_at DESC, id DESC LIMIT 1""",
        user_id, list(kinds),
    )
    if not row:
        return None
    return {"kind": row["kind"], "payload": json.loads(row["payload"])}


async def clear_awaits(user_id: int, kinds: Sequence[str]) -> None:
    """Drop every outstanding prompt of these kinds."""
    p = await pool()
    await p.execute(
        "DELETE FROM pending_action WHERE user_id = $1 AND kind = ANY($2::text[])",
        user_id, list(kinds),
    )


async def last_weight(user_id: int) -> list[asyncpg.Record]:
    """Recent weigh-ins, newest first."""
    p = await pool()
    return await p.fetch(
        """SELECT local_date, value, measured_at FROM body_metric
            WHERE user_id = $1 AND kind = 'weight_kg'
         ORDER BY measured_at DESC LIMIT 10""",
        user_id,
    )


PROFILE_FIELDS = ("display_name", "sex", "birth_date", "height_cm",
                  "activity_factor", "goal", "goal_weight_kg", "deficit_kcal", "tz",
                  "wake_hour", "fast_break_kcal")


async def mark_targets_derived(user_id: int, weight_kg: float | None, day: dt.date) -> None:  # noqa: D401
    """Record what the standing targets were computed against.

    Separate from `set_profile_field` deliberately: these two are bookkeeping
    written by the recalculation, not settings a user edits, and putting them
    on the editable whitelist would let `/profile 12 60` claim the targets were
    derived from a weight they were not.
    """
    p = await pool()
    await p.execute(
        "UPDATE app_user SET targets_set_at_kg = $2, targets_set_on = $3 WHERE id = $1",
        user_id, num(weight_kg), day,
    )


async def set_profile_field(user_id: int, field: str, value: Any) -> None:
    """One field, whitelisted by name.

    The whitelist is the point: the field arrives from a user message, and
    interpolating it into SQL is the one place in this codebase where that
    would be possible.
    """
    if field not in PROFILE_FIELDS:
        raise ValueError(f"not a profile field: {field!r}")
    if isinstance(value, float):
        value = num(value)
    p = await pool()
    await p.execute(f"UPDATE app_user SET {field} = $2 WHERE id = $1", user_id, value)


async def profile(user_id: int) -> dict[str, Any]:
    """Everything the profile card shows, including the live weight.

    Weight is read from `body_metric`, never copied onto `app_user`: one
    weight, one place, and `/weight` updates the profile by construction
    rather than by a trigger someone has to remember to write.
    """
    p = await pool()
    u = await p.fetchrow("SELECT * FROM app_user WHERE id = $1", user_id)
    w = await p.fetchrow(
        """SELECT value, local_date FROM body_metric
            WHERE user_id = $1 AND kind = 'weight_kg'
         ORDER BY measured_at DESC LIMIT 1""",
        user_id,
    )
    energy = await p.fetchrow(
        """SELECT max_amount, effective_from FROM target
            WHERE user_id = $1 AND nutrient_id = 1008 AND effective_to IS NULL""",
        user_id,
    )
    # Targets you set yourself, as opposed to the ones derived from the
    # profile. Kept apart because a recalculation must not silently overwrite
    # a number you chose deliberately.
    custom = await p.fetch(
        """SELECT t.nutrient_id, n.name, n.unit, t.min_amount, t.max_amount
             FROM target t JOIN nutrient n ON n.id = t.nutrient_id
            WHERE t.user_id = $1 AND t.effective_to IS NULL AND t.rationale = 'manual'
         ORDER BY n.name""",
        user_id,
    )
    return {
        "user": u,
        "supplements": await supplement_stack(user_id),
        "custom_targets": custom,
        "weight_kg": float(w["value"]) if w else None,
        "weighed_on": w["local_date"] if w else None,
        "energy_target": float(energy["max_amount"]) if energy and energy["max_amount"] else None,
        "targets_from": energy["effective_from"] if energy else None,
    }


async def apply_targets(
    user_id: int,
    targets: dict[int, tuple[float | None, float | None]],
    day: dt.date,
    rationale: str,
) -> int:
    """Close the standing rows, open new ones. Invariant 3: never an UPDATE.

    A target you changed on Tuesday must not silently rewrite what Monday was
    judged against, because `/today` for Monday is still a claim about Monday.
    """
    p = await pool()
    applied = 0
    async with p.acquire() as con, con.transaction():
        for nid, (lo, hi) in targets.items():
            if not await con.fetchval("SELECT 1 FROM nutrient WHERE id = $1", nid):
                continue
            await con.execute(
                """UPDATE target SET effective_to = $3
                    WHERE user_id=$1 AND nutrient_id=$2 AND effective_to IS NULL""",
                user_id, nid, day,
            )
            await con.execute(
                """INSERT INTO target
                     (user_id, nutrient_id, min_amount, max_amount, effective_from, rationale)
                   VALUES ($1,$2,$3,$4,$5,$6)""",
                user_id, nid, num(lo), num(hi), day, rationale,
            )
            applied += 1
    return applied


async def find_nutrients(term: str, limit: int = 6) -> list[asyncpg.Record]:
    """Resolve a nutrient by the name a person would type.

    Exact, then prefix, then contains — so "iron" finds Iron rather than
    "Iron, Fe" losing to some longer row that merely contains the word.
    """
    p = await pool()
    return await p.fetch(
        """SELECT id, name, unit FROM nutrient
            WHERE lower(name) LIKE '%' || lower($1) || '%'
         ORDER BY (lower(name) = lower($1)) DESC,
                  (lower(name) LIKE lower($1) || '%') DESC,
                  length(name)
            LIMIT $2""",
        term, limit,
    )


async def set_manual_target(
    user_id: int, nutrient_id: int, day: dt.date,
    minimum: float | None = None, maximum: float | None = None,
) -> None:
    """Invariant 3 again: close the standing row, insert a new one."""
    p = await pool()
    async with p.acquire() as con, con.transaction():
        await con.execute(
            """UPDATE target SET effective_to = $3
                WHERE user_id=$1 AND nutrient_id=$2 AND effective_to IS NULL""",
            user_id, nutrient_id, day,
        )
        await con.execute(
            """INSERT INTO target
                 (user_id, nutrient_id, min_amount, max_amount, effective_from, rationale)
               VALUES ($1,$2,$3,$4,$5,'manual')""",
            user_id, nutrient_id, num(minimum), num(maximum), day,
        )


async def standing_targets(user_id: int) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        """SELECT t.nutrient_id, n.name, n.unit, t.min_amount, t.max_amount, t.rationale
             FROM target t JOIN nutrient n ON n.id = t.nutrient_id
            WHERE t.user_id = $1 AND t.effective_to IS NULL
         ORDER BY (t.rationale = 'manual') DESC, n.name""",
        user_id,
    )


async def activity_range(user_id: int, start: dt.date, end: dt.date) -> list[asyncpg.Record]:
    """Sessions in a date window, oldest first."""
    p = await pool()
    return await p.fetch(
        """SELECT id, local_date, kind, minutes, kcal_burned, intensity, rpe, note
             FROM activity
            WHERE user_id = $1 AND local_date BETWEEN $2 AND $3
         ORDER BY local_date, id""",
        user_id, start, end,
    )


async def activity_by_id(user_id: int, activity_id: int) -> asyncpg.Record | None:
    """Scoped to the owner. The id arrives from callback data, which is a
    string the client controls, so it is never trusted on its own."""
    p = await pool()
    return await p.fetchrow(
        "SELECT * FROM activity WHERE id = $1 AND user_id = $2", activity_id, user_id
    )


async def delete_activity(user_id: int, activity_id: int) -> bool:
    """Remove one session. Returns whether a row went.

    A hard delete rather than a status column: `activity` is an append-only
    feed from another system, and a session that should not be there is a bad
    forward rather than a decision worth keeping a record of. Note the workout
    bot can re-post it — deduplication keys on (user, date, kind, minutes,
    intensity), and after a delete there is nothing left to match.
    """
    p = await pool()
    result = await p.execute(
        "DELETE FROM activity WHERE id = $1 AND user_id = $2", activity_id, user_id
    )
    return result.endswith(" 1")


async def set_supplement_active(user_id: int, supplement_id: int, active: bool) -> str | None:
    """Retire or restore one supplement. Returns its name, or None if not yours.

    Deactivated rather than deleted, and not because deletion is hard: every
    `supplement_log` row references it `ON DELETE CASCADE`, so removing the
    supplement would erase the record of every day you took it. Stopping a
    supplement is a fact about the future — it does not make the past untrue.
    """
    p = await pool()
    return await p.fetchval(
        """UPDATE supplement SET active = $3
            WHERE id = $1 AND user_id = $2 RETURNING name""",
        supplement_id, user_id, active,
    )


async def supplement_by_id(user_id: int, supplement_id: int) -> asyncpg.Record | None:
    """Owner-scoped: the id comes from callback data, which the client controls."""
    p = await pool()
    return await p.fetchrow(
        "SELECT * FROM supplement WHERE id = $1 AND user_id = $2", supplement_id, user_id
    )


SUPPLEMENT_SLOTS = ("fasted", "breakfast", "evening", "bed")


async def set_supplement_slot(user_id: int, supplement_id: int, slot: str | None) -> str | None:
    if slot is not None and slot not in SUPPLEMENT_SLOTS:
        raise ValueError(f"not a slot: {slot!r}")
    p = await pool()
    return await p.fetchval(
        "UPDATE supplement SET slot = $3 WHERE id = $1 AND user_id = $2 RETURNING name",
        supplement_id, user_id, slot,
    )


async def slot_times(user_id: int) -> dict[str, dt.time]:
    p = await pool()
    rows = await p.fetch(
        "SELECT slot, remind_at FROM supplement_slot_time WHERE user_id = $1 AND enabled",
        user_id,
    )
    return {r["slot"]: r["remind_at"] for r in rows}


async def set_slot_time(user_id: int, slot: str, when: dt.time | None) -> None:
    """A time, or None to switch that slot's reminder off."""
    if slot not in SUPPLEMENT_SLOTS:
        raise ValueError(f"not a slot: {slot!r}")
    p = await pool()
    if when is None:
        await p.execute(
            "DELETE FROM supplement_slot_time WHERE user_id = $1 AND slot = $2", user_id, slot)
        return
    await p.execute(
        """INSERT INTO supplement_slot_time (user_id, slot, remind_at)
           VALUES ($1,$2,$3)
           ON CONFLICT (user_id, slot) DO UPDATE
             SET remind_at = EXCLUDED.remind_at, enabled = true""",
        user_id, slot, when,
    )


async def supplements_in_slot(user_id: int, slot: str, day: dt.date) -> list[asyncpg.Record]:
    """Active supplements in one slot, with whether today's dose is logged."""
    p = await pool()
    return await p.fetch(
        """SELECT s.id, s.name, s.schedule, s.serving_desc, s.servings_per_day,
                  EXISTS (SELECT 1 FROM supplement_log l
                           WHERE l.supplement_id = s.id AND l.local_date = $3) AS logged
             FROM supplement s
            WHERE s.user_id = $1 AND s.active AND s.slot = $2
              AND (s.starts_on IS NULL OR s.starts_on <= $3)
         ORDER BY s.name""",
        user_id, slot, day,
    )


async def reminder_already_sent(user_id: int, slot: str, day: dt.date) -> bool:
    p = await pool()
    return bool(await p.fetchval(
        """SELECT 1 FROM supplement_reminder_log
            WHERE user_id = $1 AND slot = $2 AND local_date = $3""",
        user_id, slot, day,
    ))


async def mark_reminder_sent(user_id: int, slot: str, day: dt.date) -> bool:
    """False if it was already recorded — the insert is the lock."""
    p = await pool()
    result = await p.execute(
        """INSERT INTO supplement_reminder_log (user_id, slot, local_date)
           VALUES ($1,$2,$3) ON CONFLICT DO NOTHING""",
        user_id, slot, day,
    )
    return result.endswith(" 1")


async def dish_snapshots(user_id: int) -> dict[int, dict]:
    """Each repeatable dish and what it last actually contributed.

    Read from `log_nutrient` — the immutable snapshot of the last confirmed
    time you ate it — rather than recomputed from `dish_component` against
    current USDA rows. Invariant 2: the snapshot is the record, and a
    suggestion built on a recomputation would quietly disagree with the day
    card that logging it then produces.
    """
    p = await pool()
    rows = await p.fetch(
        """WITH latest AS (
               SELECT DISTINCT ON (e.dish_id) e.dish_id, e.id AS entry_id
                 FROM log_entry e
                WHERE e.user_id = $1 AND e.status = 'confirmed'
                  AND e.dish_id IS NOT NULL
                ORDER BY e.dish_id, e.logged_at DESC
           )
           SELECT d.id, d.name, d.slug, d.default_slot, d.times_logged,
                  ln.nutrient_id, ln.amount
             FROM latest l
             JOIN dish d ON d.id = l.dish_id
             JOIN log_nutrient ln ON ln.entry_id = l.entry_id
            WHERE NOT d.archived AND d.times_logged > 0""",
        user_id,
    )
    out: dict[int, dict] = {}
    for r in rows:
        d = out.setdefault(r["id"], {
            "id": r["id"], "name": r["name"], "slug": r["slug"],
            "slot": r["default_slot"], "times_logged": r["times_logged"],
            "nutrients": {},
        })
        d["nutrients"][r["nutrient_id"]] = float(r["amount"])
    return out


async def record_measured_tdee(user_id: int, tdee: float, days: int, day: dt.date) -> None:
    """Adopt a measured TDEE as the basis for the energy target."""
    p = await pool()
    await p.execute(
        """UPDATE app_user SET measured_tdee_kcal = $2, measured_tdee_days = $3,
                               measured_tdee_on = $4
            WHERE id = $1""",
        user_id, num(tdee), days, day,
    )


async def clear_measured_tdee(user_id: int) -> None:
    """Back to the equation. Kept as an explicit act rather than something a
    recalculation can do by accident."""
    p = await pool()
    await p.execute(
        """UPDATE app_user SET measured_tdee_kcal = NULL, measured_tdee_days = NULL,
                               measured_tdee_on = NULL
            WHERE id = $1""",
        user_id,
    )


async def nutrient_attribution(user_id: int, day: dt.date, nutrient_id: int) -> list[dict]:
    """Which entries produced one nutrient, and which components within them.

    Entry totals come from `log_nutrient` — the immutable snapshot taken when
    you confirmed. The per-component split has to be recomputed, because the
    snapshot is stored per entry and nothing recorded the breakdown at the
    time. So the parts are scaled to sum to the stored whole: current USDA
    figures may have drifted since, and a breakdown whose pieces disagreed
    with the total the day card shows would be worse than no breakdown.
    """
    p = await pool()
    entries = await p.fetch(
        """SELECT e.id, e.name, e.slot, e.logged_at, ln.amount
             FROM log_entry e JOIN log_nutrient ln ON ln.entry_id = e.id
            WHERE e.user_id = $1 AND e.local_date = $2
              AND e.status = 'confirmed' AND ln.nutrient_id = $3
              AND ln.amount > 0
         ORDER BY ln.amount DESC""",
        user_id, day, nutrient_id,
    )
    out: list[dict] = []
    for e in entries:
        parts = await p.fetch(
            """SELECT c.label, f.description,
                      c.grams * c.yield_factor * fn.amount / 100.0 AS amount
                 FROM log_component c
                 JOIN food f ON f.fdc_id = c.fdc_id
                 JOIN food_nutrient fn
                   ON fn.fdc_id = c.fdc_id AND fn.nutrient_id = $2
                WHERE c.entry_id = $1 AND fn.amount > 0
             ORDER BY amount DESC""",
            e["id"], nutrient_id,
        )
        total_parts = sum(float(r["amount"]) for r in parts)
        stored = float(e["amount"])
        scale = (stored / total_parts) if total_parts > 0 else 0.0
        out.append({
            "name": e["name"], "slot": e["slot"], "logged_at": e["logged_at"],
            "amount": stored,
            "parts": [
                {"label": r["label"], "food": r["description"],
                 "amount": float(r["amount"]) * scale}
                for r in parts
            ],
        })
    return out


async def supplement_contribution(user_id: int, day: dt.date, nutrient_id: int) -> list[dict]:
    """Supplements are not food rows and never appear in a food breakdown.
    A micronutrient met by a capsule has to be visible as one."""
    p = await pool()
    rows = await p.fetch(
        """SELECT s.name, sn.amount * sl.servings AS amount
             FROM supplement_log sl
             JOIN supplement s ON s.id = sl.supplement_id
             JOIN supplement_nutrient sn ON sn.supplement_id = s.id
            WHERE sl.user_id = $1 AND sl.local_date = $2 AND sn.nutrient_id = $3
         ORDER BY amount DESC""",
        user_id, day, nutrient_id,
    )
    return [{"name": r["name"], "amount": float(r["amount"])} for r in rows]


async def create_user_food(
    user_id: int, name: str, per_100g: dict[int, float],
    *, category: str | None = None, note: str | None = None,
) -> int:
    """Store a food you defined. Returns its (negative) fdc_id.

    `per_100g` is nutrient_id -> amount per 100 g, computed from constituents
    that are themselves USDA rows, or transcribed from a printed panel. It is
    never estimated by a model: this function is only ever handed arithmetic
    or a transcription, which is the same line ARCHITECTURE.md §1 draws
    everywhere else.
    """
    p = await pool()
    async with p.acquire() as con, con.transaction():
        existing = await con.fetchval(
            """SELECT fdc_id FROM food
                WHERE owner_user_id = $1 AND lower(description) = lower($2)""",
            user_id, name,
        )
        # Stored capitalised. "pickle juice" in a list of proper names looks
        # like a bug, and fixing it on the way out means every card has to
        # remember to.
        name = (name or "").strip()
        name = name[:1].upper() + name[1:]
        fdc_id = existing or -(await con.fetchval("SELECT nextval('user_food_id_seq')"))
        await con.execute(
            """INSERT INTO food (fdc_id, data_type, description, category, owner_user_id)
               VALUES ($1,'user_product',$2,$3,$4)
               ON CONFLICT (fdc_id) DO UPDATE
                 SET description = EXCLUDED.description, category = EXCLUDED.category""",
            fdc_id, name, category or note, user_id,
        )
        await con.execute("DELETE FROM food_nutrient WHERE fdc_id = $1", fdc_id)
        await con.executemany(
            "INSERT INTO food_nutrient (fdc_id, nutrient_id, amount) VALUES ($1,$2,$3)",
            [(fdc_id, nid, num(amount)) for nid, amount in per_100g.items()
             if amount is not None],
        )
    return fdc_id


async def user_foods(user_id: int) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        """SELECT f.fdc_id, f.description, f.category,
                  (SELECT count(*) FROM food_nutrient fn WHERE fn.fdc_id = f.fdc_id) AS n_nutrients,
                  (SELECT amount FROM food_nutrient fn
                    WHERE fn.fdc_id = f.fdc_id AND fn.nutrient_id = 1008) AS kcal_100g,
                  (SELECT count(*) FROM log_component c WHERE c.fdc_id = f.fdc_id) AS times_used
             FROM food f
            WHERE f.owner_user_id = $1 ORDER BY f.description""",
        user_id,
    )


async def delete_user_food(user_id: int, fdc_id: int) -> str | None:
    """Only if nothing has been logged against it. A food referenced by a
    log_component cannot go without taking the entry's history with it."""
    p = await pool()
    used = await p.fetchval("SELECT count(*) FROM log_component WHERE fdc_id = $1", fdc_id)
    if used:
        return None
    async with p.acquire() as con, con.transaction():
        # The alias created alongside it points here, so the food cannot go
        # while it remains — and an alias to a deleted food would resolve to
        # nothing on the next parse.
        await con.execute(
            "DELETE FROM food_alias WHERE user_id = $1 AND fdc_id = $2", user_id, fdc_id)
        return await con.fetchval(
            """DELETE FROM food WHERE fdc_id = $1 AND owner_user_id = $2
               RETURNING description""",
            fdc_id, user_id,
        )


async def set_target_weight(user_id: int, nutrient_id: int, weight: float,
                            day: dt.date) -> bool:
    """Change how much a floor counts, versioned like any other target change.

    Two statements rather than one data-modifying CTE: the UPDATE and the
    INSERT would share a snapshot, so the unique index on the live row sees
    the old row still open and rejects the new one.
    """
    p = await pool()
    async with p.acquire() as con, con.transaction():
        live = await con.fetchrow(
            """SELECT min_amount, max_amount, rationale FROM target
                WHERE user_id=$1 AND nutrient_id=$2 AND effective_to IS NULL""",
            user_id, nutrient_id,
        )
        if not live:
            return False
        await con.execute(
            """UPDATE target SET effective_to = $3
                WHERE user_id=$1 AND nutrient_id=$2 AND effective_to IS NULL""",
            user_id, nutrient_id, day,
        )
        await con.execute(
            """INSERT INTO target (user_id, nutrient_id, min_amount, max_amount,
                                   effective_from, rationale, weight)
               VALUES ($1,$2,$3,$4,$5,$6,$7)""",
            user_id, nutrient_id, live["min_amount"], live["max_amount"],
            day, live["rationale"], num(weight, 2),
        )
    return True


async def weak_labels(entry_id: int) -> list[str]:
    """Labels whose best food-database match was poor, recorded at parse time.

    Stored on the entry rather than read back off the Telegram message: the
    offer to define a missing food is a fact about the parse, and it has to
    survive a discard, which is the moment it matters most.
    """
    p = await pool()
    raw = await p.fetchval("SELECT parse FROM log_entry WHERE id = $1", entry_id)
    if not raw:
        return []
    import json

    data = json.loads(raw) if isinstance(raw, str) else raw
    return list(data.get("_weak") or [])


async def set_entry_time(entry_id: int, when: dt.datetime, tz: str,
                         rollover_hour: int) -> dt.date:
    """Move an entry to a different moment, and to the day that moment falls in.

    local_date is recomputed rather than left alone: a meal moved to 01:00
    belongs to the day that has not ended yet, and an entry whose timestamp and
    day disagree would show on one card and count toward another.
    """
    p = await pool()
    day = local_date_for(when, tz, rollover_hour)
    await p.execute(
        "UPDATE log_entry SET logged_at = $2, local_date = $3 WHERE id = $1",
        entry_id, when, day,
    )
    return day


async def note_first_contact(user_id: int, day: dt.date) -> None:
    """Record the first message of a local day. Silent if already recorded."""
    p = await pool()
    await p.execute(
        """INSERT INTO first_contact (user_id, local_date) VALUES ($1,$2)
           ON CONFLICT DO NOTHING""",
        user_id, day,
    )


async def wake_hour_estimate(user_id: int, tz: str) -> int | None:
    """The hour you are usually up, from when you usually first speak.

    A median, not a mean: one 03:00 insomnia message should not drag the whole
    estimate an hour earlier. Needs a week before it will say anything, because
    three days of data would move the note around at random.
    """
    p = await pool()
    row = await p.fetchrow(
        """SELECT count(*) AS n,
                  percentile_disc(0.5) WITHIN GROUP (
                      ORDER BY EXTRACT(hour FROM at AT TIME ZONE $2)) AS med
             FROM first_contact
            WHERE user_id = $1 AND local_date > current_date - 14""",
        user_id, tz,
    )
    if not row or (row["n"] or 0) < 7 or row["med"] is None:
        return None
    return int(row["med"])


async def morning_note_sent(user_id: int, day: dt.date) -> bool:
    """Claims the day. False means someone else already sent it."""
    p = await pool()
    result = await p.execute(
        """INSERT INTO morning_note_log (user_id, local_date) VALUES ($1,$2)
           ON CONFLICT DO NOTHING""",
        user_id, day,
    )
    return result.endswith(" 1")


async def top_components(user_id: int, limit: int = 6, *, tz: str = "UTC",
                         hour: int | None = None,
                         exclude_fdc: Sequence[int] = ()) -> list[asyncpg.Record]:
    """Single foods you eat often, for repeating one thing rather than a plate.

    A meal of six items becomes one dish you will never eat again in that
    combination, while the parts you actually repeat — three eggs, 60 g of rye
    bread — are stored and unreachable. This offers them.

    The usual portion comes from `portion_history` where there is one, which
    reads only weighed and stated masses: invariant 7. Where there is not, the
    median of what has been logged is used and the mass is marked `prior`, so
    an estimate never launders itself into a statement.
    """
    p = await pool()
    return await p.fetch(
        """WITH used AS (
               SELECT lc.fdc_id,
                      mode() WITHIN GROUP (ORDER BY lc.label) AS label,
                      count(*) AS n,
                      percentile_disc(0.5) WITHIN GROUP (ORDER BY lc.grams) AS median_grams,
                      count(*) FILTER (
                          WHERE $5::int IS NOT NULL AND LEAST(
                              abs(EXTRACT(hour FROM le.logged_at AT TIME ZONE $4) - $5),
                              24 - abs(EXTRACT(hour FROM le.logged_at AT TIME ZONE $4) - $5)
                          ) <= 3) AS n_near
                 FROM log_component lc
                 JOIN log_entry le ON le.id = lc.entry_id
                WHERE le.user_id = $1 AND le.status = 'confirmed'
                  AND le.local_date > current_date - 28
                  AND NOT (lc.fdc_id = ANY($3::int[]))
             GROUP BY lc.fdc_id
           )
           SELECT u.fdc_id, u.label, u.n, u.n_near, u.median_grams,
                  (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY grams)
                     FROM portion_history($1, u.fdc_id, 30)) AS stated_grams
             FROM used u
         ORDER BY (u.n_near > 0) DESC, u.n_near DESC, u.n DESC, u.fdc_id
            LIMIT $2""",
        user_id, limit, list(exclude_fdc) or [0], tz, hour,
    )


async def set_observation_note(user_id: int, obs_id: int, note: str) -> bool:
    """Attach the why to a rating already recorded."""
    p = await pool()
    result = await p.execute(
        "UPDATE observation SET note = $3 WHERE id = $1 AND user_id = $2",
        obs_id, user_id, note[:500],
    )
    return result.endswith(" 1")


async def rating_notes(user_id: int, days: int = 28) -> list[asyncpg.Record]:
    """Ratings that carry a note, for the weekly review.

    The note is the only part of an observation a correlation cannot recover.
    Passing it to the review is the whole reason for collecting it.
    """
    p = await pool()
    return await p.fetch(
        """SELECT local_date, kind, value, note FROM observation
            WHERE user_id = $1 AND note IS NOT NULL AND note <> ''
              AND local_date > current_date - $2::int
         ORDER BY local_date DESC, kind""",
        user_id, days,
    )


async def supplements_named_in(user_id: int, day: dt.date,
                               labels: Sequence[str]) -> list[int]:
    """Supplements whose name is exactly one of the meal's own ingredients.

    Exact, against component labels only, and never against the dish name.
    Substring matching looked reasonable and was not: "zinc-rich beef stew"
    contains "zinc", and a capsule recorded because a sentence happened to
    contain a word is worse than one not recorded at all — it puts
    micronutrients into a day's totals that were never swallowed.

    An ingredient the parser isolated and called "creatine" is strong
    evidence. A word inside a dish name is weak, so it is not used. That means
    "protein shake with creatine" only ticks creatine off when the parse gives
    creatine its own line, which is the right way round to be wrong.

    Only supplements already in your stack, already started, and not already
    logged today.
    """
    wanted = {label.strip().lower() for label in labels if label and label.strip()}
    if not wanted:
        return []
    p = await pool()
    rows = await p.fetch(
        """SELECT s.id, s.name FROM supplement s
            WHERE s.user_id = $1 AND s.active
              AND (s.starts_on IS NULL OR s.starts_on <= $2)
              AND NOT EXISTS (SELECT 1 FROM supplement_log l
                               WHERE l.supplement_id = s.id AND l.local_date = $2)""",
        user_id, day,
    )
    return [r["id"] for r in rows if r["name"].strip().lower() in wanted]
