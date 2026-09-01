-- Cigarettes, recorded as observations and read into one target.
--
-- Stored in `observation` rather than a table of its own: it is a count taken
-- at a moment, with a local_date and a fasting state, which is exactly what
-- that table already is. It also means `/insight` can correlate against it the
-- day there is enough of it, with no further work — which is the stated reason
-- for recording this at all.
--
-- `scale` is 'count' rather than the default '1-10'. A rating and a tally are
-- different measurements and the column exists to say which is which.

CREATE INDEX IF NOT EXISTS observation_kind_day
  ON observation (user_id, kind, local_date);

-- Smoking raises the vitamin C requirement, and the adjustment is applied at
-- read time rather than written into `target`.
--
-- Invariant 3 says target rows are versioned, never updated in place: a floor
-- that moved with each day's smoking would close and open a target row every
-- day, and `target` has reached five figures of superseded rows once already
-- from far less. So the stored floor stays put and the *day's* floor is
-- derived, which is also the honest shape — the requirement belongs to the
-- day, not to the person.
--
-- 35 mg is the Institute of Medicine's DRI increment for smokers (2000), the
-- same figure behind the 90 -> 125 mg and 75 -> 110 mg adult recommendations.
-- It is a population figure applied to one person, which is all any target
-- here is. `config.SMOKER_VITAMIN_C_MG` must match it and a test asserts so.

DROP FUNCTION IF EXISTS day_progress(bigint, date);
CREATE FUNCTION day_progress(p_user bigint, p_day date)
RETURNS TABLE(nutrient_id integer, nutrient_name text, unit text, is_core boolean,
              amount numeric, amount_food numeric, amount_supplement numeric,
              min_amount numeric, max_amount numeric,
              pct_of_min numeric, pct_of_max numeric, state text, weight numeric)
LANGUAGE sql STABLE AS $$
    WITH smoked AS (
        SELECT COALESCE(sum(o.value), 0) AS cigarettes
          FROM observation o
         WHERE o.user_id = p_user AND o.local_date = p_day
           AND o.kind = 'cigarettes'
    ),
    adjusted AS (
        SELECT t.*,
               t.min_amount + CASE
                   WHEN t.nutrient_id = 1162 AND (SELECT cigarettes FROM smoked) > 0
                   THEN 35 ELSE 0 END AS day_min
          FROM target_on(p_user, p_day) t
    )
    SELECT n.id,
           n.name,
           n.unit,
           n.is_core,
           COALESCE(d.amount, 0) + COALESCE(s.amount, 0),
           COALESCE(d.amount, 0),
           COALESCE(s.amount, 0),
           t.day_min,
           t.max_amount,
           CASE WHEN t.day_min > 0
                THEN round(100 * (COALESCE(d.amount,0) + COALESCE(s.amount,0)) / t.day_min, 1) END,
           CASE WHEN t.max_amount > 0
                THEN round(100 * (COALESCE(d.amount,0) + COALESCE(s.amount,0)) / t.max_amount, 1) END,
           CASE
               WHEN t.max_amount IS NOT NULL
                    AND COALESCE(d.amount,0) + COALESCE(s.amount,0) > t.max_amount THEN 'over'
               WHEN t.day_min IS NOT NULL
                    AND COALESCE(d.amount,0) + COALESCE(s.amount,0) < t.day_min THEN 'under'
               ELSE 'ok'
           END,
           t.weight
    FROM adjusted t
    JOIN nutrient n ON n.id = t.nutrient_id
    LEFT JOIN v_day_nutrient d
           ON d.user_id = p_user AND d.local_date = p_day AND d.nutrient_id = n.id
    LEFT JOIN v_day_supplement_nutrient s
           ON s.user_id = p_user AND s.local_date = p_day AND s.nutrient_id = n.id
    WHERE t.period = 'day';
$$;
