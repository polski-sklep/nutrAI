-- What breaks a fast.
--
-- Every confirmed entry did, whatever was in it: a black coffee reset the
-- clock exactly as a steak did. That is wrong in the direction that matters
-- here, because `hours_fasted` is stamped onto every rating at the moment it
-- is made — so a 6 kcal lemon water at 07:00 was silently corrupting the
-- "focus vs hours fasted" and "effort vs hours fasted" correlations rather
-- than merely mis-stating a number on a card.
--
-- The threshold is a convention, not a finding. Insulin response is
-- continuous, and no experiment identifies a calorie count at which a fast
-- stops. Under about 25 kcal is the common practice and it is settable,
-- because it is a choice rather than a measurement.
--
-- Energy rather than a food list: "black coffee doesn't count" is a rule about
-- a category, and categories need maintaining forever. A number needs
-- justifying once.
ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS fast_break_kcal numeric NOT NULL DEFAULT 25;

-- Entries that actually end a fast. Everything else is still logged, still
-- counted toward the day, and simply does not reset the clock.
CREATE OR REPLACE VIEW v_fast_breaking AS
SELECT e.user_id, e.id AS entry_id, e.logged_at, e.local_date, e.name, e.slot,
       COALESCE(n.amount, 0) AS kcal
  FROM log_entry e
  JOIN app_user u ON u.id = e.user_id
  LEFT JOIN log_nutrient n ON n.entry_id = e.id AND n.nutrient_id = 1008
 WHERE e.status = 'confirmed'
   AND COALESCE(n.amount, 0) >= u.fast_break_kcal;

CREATE OR REPLACE FUNCTION current_fast_hours(p_user bigint)
RETURNS numeric LANGUAGE sql STABLE AS $$
    SELECT EXTRACT(epoch FROM (now() - max(logged_at))) / 3600.0
      FROM v_fast_breaking WHERE user_id = p_user;
$$;

CREATE OR REPLACE FUNCTION fast_hours_at(p_user bigint, p_at timestamptz)
RETURNS numeric LANGUAGE sql STABLE AS $$
    SELECT EXTRACT(epoch FROM (p_at - max(logged_at))) / 3600.0
      FROM v_fast_breaking
     WHERE user_id = p_user AND logged_at <= p_at;
$$;

-- The eating window is the same question asked over a day, so it uses the
-- same rule: a window that opens with a black coffee at 07:00 and a window
-- that opens with breakfast at 11:00 are different days.
CREATE OR REPLACE VIEW v_eating_window AS
SELECT user_id,
       local_date,
       min(logged_at) AS first_at,
       max(logged_at) AS last_at,
       count(*)       AS n_meals,
       EXTRACT(epoch FROM (max(logged_at) - min(logged_at))) / 3600.0 AS window_hours,
       min(logged_at) + (max(logged_at) - min(logged_at)) / 2 AS midpoint_at
  FROM v_fast_breaking
 GROUP BY user_id, local_date
HAVING count(*) >= 2;

-- Restamp every observation made under the old rule.
--
-- hours_fasted is stored rather than derived, deliberately: recomputing it at
-- read time would shift silently every time a meal's timestamp was corrected.
-- That same choice means a change to what breaks a fast has to be applied to
-- the history explicitly, and this is the one moment it is safe to do so —
-- the correlations these feed have not been drawn yet.
UPDATE observation o
   SET hours_fasted = fast_hours_at(o.user_id, o.observed_at)
 WHERE fast_hours_at(o.user_id, o.observed_at) IS DISTINCT FROM o.hours_fasted;
