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
    return await p.fetch(
        """SELECT id, slug, name, default_slot, times_logged, score
             FROM v_dish_rank WHERE user_id = $1
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


async def latest_pending(user_id: int, kind: str) -> dict | None:
    p = await pool()
    row = await p.fetchrow(
        """SELECT payload FROM pending_action
            WHERE user_id = $1 AND kind = $2 AND expires_at > now()
         ORDER BY created_at DESC LIMIT 1""",
        user_id, kind,
    )
    return json.loads(row["payload"]) if row else None
