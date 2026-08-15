-- Rollups. Every summary and every notification the bot sends is produced by
-- these views plus a string template. Zero tokens, single-digit milliseconds.

-- Daily nutrient totals from the immutable snapshot.
CREATE OR REPLACE VIEW v_day_nutrient AS
SELECT e.user_id,
       e.local_date,
       ln.nutrient_id,
       n.name  AS nutrient_name,
       n.unit,
       n.is_core,
       sum(ln.amount) AS amount
FROM log_entry e
JOIN log_nutrient ln ON ln.entry_id = e.id
JOIN nutrient n      ON n.id = ln.nutrient_id
WHERE e.status = 'confirmed'
GROUP BY e.user_id, e.local_date, ln.nutrient_id, n.name, n.unit, n.is_core;

-- The target in force on a given day, resolved from the versioned history.
CREATE OR REPLACE FUNCTION target_on(p_user bigint, p_day date)
RETURNS TABLE (nutrient_id integer, min_amount numeric, max_amount numeric, period text)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (t.nutrient_id, t.period)
           t.nutrient_id, t.min_amount, t.max_amount, t.period
    FROM target t
    WHERE t.user_id = p_user
      AND t.effective_from <= p_day
      AND (t.effective_to IS NULL OR t.effective_to > p_day)
    ORDER BY t.nutrient_id, t.period, t.effective_from DESC;
$$;

-- Progress against target for one day: the single query behind /today,
-- behind every threshold notification, and behind the evidence pack.
CREATE OR REPLACE FUNCTION day_progress(p_user bigint, p_day date)
RETURNS TABLE (
    nutrient_id integer,
    nutrient_name text,
    unit text,
    is_core boolean,
    amount numeric,
    min_amount numeric,
    max_amount numeric,
    pct_of_min numeric,
    pct_of_max numeric,
    state text
)
LANGUAGE sql STABLE AS $$
    SELECT n.id,
           n.name,
           n.unit,
           n.is_core,
           COALESCE(d.amount, 0) AS amount,
           t.min_amount,
           t.max_amount,
           CASE WHEN t.min_amount > 0
                THEN round(100 * COALESCE(d.amount,0) / t.min_amount, 1) END,
           CASE WHEN t.max_amount > 0
                THEN round(100 * COALESCE(d.amount,0) / t.max_amount, 1) END,
           CASE
               WHEN t.max_amount IS NOT NULL AND COALESCE(d.amount,0) > t.max_amount THEN 'over'
               WHEN t.min_amount IS NOT NULL AND COALESCE(d.amount,0) < t.min_amount THEN 'under'
               ELSE 'ok'
           END
    FROM target_on(p_user, p_day) t
    JOIN nutrient n ON n.id = t.nutrient_id
    LEFT JOIN v_day_nutrient d
           ON d.user_id = p_user AND d.local_date = p_day AND d.nutrient_id = n.id
    WHERE t.period = 'day';
$$;

-- How much of a day was actually weighed. Print it on every summary. If it
-- reads 40%, every trend below it is noise and no plan built on it means
-- anything.
CREATE OR REPLACE VIEW v_day_mass_confidence AS
SELECT e.user_id,
       e.local_date,
       sum(c.grams) AS total_grams,
       sum(c.grams) FILTER (WHERE c.grams_source IN ('scale','stated','package')) AS hard_grams,
       round(100.0 * COALESCE(sum(c.grams) FILTER
             (WHERE c.grams_source IN ('scale','stated','package')), 0)
             / NULLIF(sum(c.grams), 0), 0) AS pct_measured,
       -- Quadrature sum of component mass uncertainty for the day.
       sqrt(sum(c.grams_sigma ^ 2)) AS mass_sigma
FROM log_entry e
JOIN log_component c ON c.entry_id = e.id
WHERE e.status = 'confirmed'
GROUP BY e.user_id, e.local_date;

-- Your own weighed history for one food. The portion prior reads this.
CREATE OR REPLACE FUNCTION portion_history(p_user bigint, p_fdc integer, p_limit integer DEFAULT 30)
RETURNS TABLE (grams numeric)
LANGUAGE sql STABLE AS $$
    SELECT c.grams
      FROM log_component c
      JOIN log_entry e ON e.id = c.entry_id
     WHERE e.user_id = p_user
       AND e.status = 'confirmed'
       AND c.fdc_id = p_fdc
       AND c.grams_source IN ('scale','stated','package')
  ORDER BY e.logged_at DESC
     LIMIT p_limit;
$$;

-- Recency-weighted frequency. Drives the numbered /r menu: what you actually
-- eat, ranked so that the eight things you eat most are one keystroke away.
CREATE OR REPLACE VIEW v_dish_rank AS
SELECT d.id,
       d.user_id,
       d.slug,
       d.name,
       d.default_slot,
       d.times_logged,
       d.last_logged_at,
       d.times_logged
         * exp(-EXTRACT(epoch FROM (now() - COALESCE(d.last_logged_at, d.created_at)))
               / (14 * 86400.0)) AS score
FROM dish d
WHERE NOT d.archived;
