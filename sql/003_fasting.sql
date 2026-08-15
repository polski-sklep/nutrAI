-- Fasting windows and the outcome variables without which "optimal working
-- times" and "best exercise times" are unanswerable.
--
-- Meal timestamps are already in log_entry, so fasting needs no new logging at
-- all: it is a window function over data you have. What it does need is
-- something to correlate against, which is what `observation` is for. A
-- tracker that records only inputs can never tell you what any input did.

CREATE TABLE observation (
    id           bigserial PRIMARY KEY,
    user_id      bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    observed_at  timestamptz NOT NULL DEFAULT now(),
    local_date   date NOT NULL,
    kind         text NOT NULL,   -- focus | energy | mood | hunger | sleep | rpe | session_load
    value        numeric NOT NULL,
    scale        text NOT NULL DEFAULT '1-10',
    -- Snapshotted, not recomputed. Same reasoning as log_nutrient: if you
    -- later correct a meal's timestamp, the fast you were actually in when you
    -- rated your focus at 7 does not retroactively change.
    hours_fasted numeric,
    kcal_since_waking numeric,
    note         text
);
CREATE INDEX observation_kind ON observation (user_id, kind, observed_at DESC);

-- Every intake time, confirmed only. The basis for every fasting figure.
CREATE OR REPLACE VIEW v_meal_time AS
SELECT user_id, id AS entry_id, logged_at, local_date, name, slot
  FROM log_entry
 WHERE status = 'confirmed';

-- Gap to the previous intake, in hours. Gaps under 3 h are second helpings,
-- not fasts, and are filtered downstream rather than here so the raw view
-- stays honest.
CREATE OR REPLACE VIEW v_meal_gap AS
SELECT user_id,
       entry_id,
       logged_at,
       local_date,
       lag(logged_at) OVER (PARTITION BY user_id ORDER BY logged_at) AS prev_at,
       EXTRACT(epoch FROM (logged_at - lag(logged_at)
               OVER (PARTITION BY user_id ORDER BY logged_at))) / 3600.0 AS gap_hours
  FROM v_meal_time;

-- One row per day: when eating started, when it stopped, how wide, where the
-- midpoint sits. Midpoint position is the metric the trial literature actually
-- separates, and it is the one people never look at.
CREATE OR REPLACE VIEW v_eating_window AS
SELECT user_id,
       local_date,
       min(logged_at) AS first_at,
       max(logged_at) AS last_at,
       count(*)       AS n_meals,
       EXTRACT(epoch FROM (max(logged_at) - min(logged_at))) / 3600.0 AS window_hours,
       min(logged_at) + (max(logged_at) - min(logged_at)) / 2 AS midpoint_at
  FROM v_meal_time
 GROUP BY user_id, local_date
HAVING count(*) >= 2;

-- Hours since the last confirmed intake, right now.
CREATE OR REPLACE FUNCTION current_fast_hours(p_user bigint)
RETURNS numeric LANGUAGE sql STABLE AS $$
    SELECT EXTRACT(epoch FROM (now() - max(logged_at))) / 3600.0
      FROM log_entry WHERE user_id = p_user AND status = 'confirmed';
$$;

-- Hours fasted at an arbitrary instant. Used to stamp an observation with the
-- fasting state it was made in.
CREATE OR REPLACE FUNCTION fast_hours_at(p_user bigint, p_at timestamptz)
RETURNS numeric LANGUAGE sql STABLE AS $$
    SELECT EXTRACT(epoch FROM (p_at - max(logged_at))) / 3600.0
      FROM log_entry
     WHERE user_id = p_user AND status = 'confirmed' AND logged_at <= p_at;
$$;
