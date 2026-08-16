from __future__ import annotations

import datetime as dt
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


async def search_foods(query: str, limit: int = 5, data_types: Sequence[str] | None = None) -> list[asyncpg.Record]:
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
    dt_filter = "AND f.data_type = ANY($3::text[])" if data_types else ""
    sql = f"""
        SELECT f.fdc_id, f.description, f.data_type, f.brand, f.precedence,
               similarity(f.description, $1) AS sim,
               ts_rank(to_tsvector('english', f.description),
                       plainto_tsquery('english', $1)) AS rank
          FROM food f
         WHERE (to_tsvector('english', f.description) @@ plainto_tsquery('english', $1)
                OR f.description % $1)
               {dt_filter}
      ORDER BY (similarity(f.description, $1) + ts_rank(
                   to_tsvector('english', f.description),
                   plainto_tsquery('english', $1))) DESC, f.precedence ASC
         LIMIT $2"""
    args: list[Any] = [query, limit]
    if data_types:
        args.append(list(data_types))
    return await p.fetch(sql, *args)


async def profiles_for(fdc_ids: Iterable[int]) -> dict[int, dict[int, float]]:
    p = await pool()
    return await _profiles_con(p, list(fdc_ids))


# ------------------------------------------------------------------ dishes


async def top_dishes(user_id: int, limit: int = 8) -> list[asyncpg.Record]:
    p = await pool()
    # Only dishes actually eaten at least once.
    #
    # `_present` creates the dish before the entry is confirmed, so every meal
    # ever parsed leaves one behind whether or not it was logged — including the
    # ones discarded precisely because they were wrong. A cappuccino containing
    # a phantom whisky cocktail was sitting in this menu at ×0, one tap from
    # being logged again. "Repeat" means something you have eaten; a dish with
    # no confirmed entry has never been a meal.
    return await p.fetch(
        """SELECT id, slug, name, default_slot, times_logged, score
             FROM v_dish_rank WHERE user_id = $1 AND times_logged > 0
         ORDER BY score DESC, last_logged_at DESC NULLS LAST LIMIT $2""",
        user_id, limit,
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
        """SELECT fdc_id, label, grams, state, yield_factor, optional
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
                 (dish_id, position, fdc_id, label, grams, yield_factor)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            [(dish_id, i, c.fdc_id, c.label, c.grams, c.yield_factor)
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
            user_id, now, local_date_for(now, tz, rollover_hour), kind, value, note,
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


async def latest_pending(user_id: int, kind: str) -> dict | None:
    p = await pool()
    row = await p.fetchrow(
        """SELECT payload FROM pending_action
            WHERE user_id = $1 AND kind = $2 AND expires_at > now()
         ORDER BY created_at DESC LIMIT 1""",
        user_id, kind,
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


async def supplement_stack(user_id: int, active_only: bool = True) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        f"""SELECT s.*, (SELECT count(*) FROM supplement_nutrient sn
                          WHERE sn.supplement_id = s.id) AS n_nutrients
              FROM supplement s
             WHERE s.user_id = $1 {'AND s.active' if active_only else ''}
          ORDER BY s.name""",
        user_id,
    )


async def log_supplements(user_id: int, day: dt.date, supplement_ids: Sequence[int] | None = None) -> int:
    """Record today's stack. Idempotent: taking it twice is not taking double."""
    p = await pool()
    async with p.acquire() as con, con.transaction():
        if supplement_ids is None:
            rows = await con.fetch(
                "SELECT id, servings_per_day FROM supplement WHERE user_id=$1 AND active", user_id
            )
        else:
            rows = await con.fetch(
                """SELECT id, servings_per_day FROM supplement
                    WHERE user_id=$1 AND id = ANY($2::bigint[])""",
                user_id, list(supplement_ids),
            )
        for r in rows:
            await con.execute(
                """INSERT INTO supplement_log (user_id, supplement_id, local_date, servings)
                   VALUES ($1,$2,$3,$4)
                   ON CONFLICT (user_id, supplement_id, local_date)
                   DO UPDATE SET servings = EXCLUDED.servings, taken_at = now()""",
                user_id, r["id"], day, r["servings_per_day"],
            )
        return len(rows)


async def supplements_logged_on(user_id: int, day: dt.date) -> list[asyncpg.Record]:
    p = await pool()
    return await p.fetch(
        """SELECT s.name, sl.servings FROM supplement_log sl
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
        """SELECT s.id, s.schedule,
                  EXISTS (SELECT 1 FROM supplement_log l
                           WHERE l.supplement_id = s.id AND l.local_date = $2::date - 1) AS took_yesterday
             FROM supplement s
            WHERE s.user_id = $1 AND s.active""",
        user_id, day,
    )
    due = []
    for r in rows:
        if r["schedule"] == "daily":
            due.append(r["id"])
        elif r["schedule"] == "alternate" and not r["took_yesterday"]:
            due.append(r["id"])
    return due


# --------------------------------------------------------------- activity


async def record_activity(
    user_id: int, day: dt.date, kind: str, *,
    minutes: int | None = None, kcal_burned: float | None = None,
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
                  AND minutes IS NOT DISTINCT FROM $4""",
            user_id, day, kind, minutes,
        )
        if existing:
            return existing, False
        new_id = await con.fetchval(
            """INSERT INTO activity (user_id, local_date, kind, minutes, kcal_burned, note)
               VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""",
            user_id, day, kind, minutes, kcal_burned, note,
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
                   bool_or(a.kind = 'lifting')     AS lifted
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
                  "activity_factor", "goal", "goal_weight_kg", "deficit_kcal", "tz")


async def mark_targets_derived(user_id: int, weight_kg: float | None, day: dt.date) -> None:
    """Record what the standing targets were computed against.

    Separate from `set_profile_field` deliberately: these two are bookkeeping
    written by the recalculation, not settings a user edits, and putting them
    on the editable whitelist would let `/profile 12 60` claim the targets were
    derived from a weight they were not.
    """
    p = await pool()
    await p.execute(
        "UPDATE app_user SET targets_set_at_kg = $2, targets_set_on = $3 WHERE id = $1",
        user_id, weight_kg, day,
    )


async def set_profile_field(user_id: int, field: str, value: Any) -> None:
    """One field, whitelisted by name.

    The whitelist is the point: the field arrives from a user message, and
    interpolating it into SQL is the one place in this codebase where that
    would be possible.
    """
    if field not in PROFILE_FIELDS:
        raise ValueError(f"not a profile field: {field!r}")
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
    return {
        "user": u,
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
                user_id, nid, lo, hi, day, rationale,
            )
            applied += 1
    return applied
