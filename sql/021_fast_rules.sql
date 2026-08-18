-- Three ways to break a fast, any one of which is enough.
--
-- A single quantity could not express it. Energy alone cannot tell honey from
-- olive oil; carbohydrate alone lets a 24 g whey shake through at 3 g of
-- carbs; and a 120 kcal spoon of butter provokes little insulin but is not a
-- fast by any ordinary use of the word.
--
--   energy       >= 50 g kcal   any real intake, whatever it consists of
--   carbohydrate >=  5 g        the dominant insulin secretagogue
--   protein      >=  2 g        the second, and how a shake slips through
--
-- All three are the user's, all three are conventions, and the code says so:
-- insulin response is continuous and no experiment names a threshold in any
-- of these units. What they are not is arbitrary — each closes a case the
-- other two let through, and the cases are real ones from this log.
ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS fast_break_kcal      numeric NOT NULL DEFAULT 50,
    ADD COLUMN IF NOT EXISTS fast_break_carb_g    numeric NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS fast_break_protein_g numeric NOT NULL DEFAULT 2;

DROP VIEW IF EXISTS v_eating_window;
DROP VIEW IF EXISTS v_fast_breaking;
ALTER TABLE app_user DROP COLUMN IF EXISTS fast_break_cp_g;

CREATE VIEW v_fast_breaking AS
SELECT e.user_id, e.id AS entry_id, e.logged_at, e.local_date, e.name, e.slot,
       COALESCE(k.amount, 0) AS kcal,
       COALESCE(c.amount, 0) AS carb_g,
       COALESCE(p.amount, 0) AS protein_g,
       -- Which rule fired, so /fast can say what broke it rather than only
       -- that something did.
       CASE
           WHEN COALESCE(k.amount, 0) >= u.fast_break_kcal      THEN 'energy'
           WHEN COALESCE(c.amount, 0) >= u.fast_break_carb_g    THEN 'carbohydrate'
           ELSE 'protein'
       END AS broken_by
  FROM log_entry e
  JOIN app_user u ON u.id = e.user_id
  LEFT JOIN log_nutrient k ON k.entry_id = e.id AND k.nutrient_id = 1008
  LEFT JOIN log_nutrient c ON c.entry_id = e.id AND c.nutrient_id = 1005
  LEFT JOIN log_nutrient p ON p.entry_id = e.id AND p.nutrient_id = 1003
 WHERE e.status = 'confirmed'
   AND (COALESCE(k.amount, 0) >= u.fast_break_kcal
        OR COALESCE(c.amount, 0) >= u.fast_break_carb_g
        OR COALESCE(p.amount, 0) >= u.fast_break_protein_g);

CREATE VIEW v_eating_window AS
SELECT user_id, local_date,
       min(logged_at) AS first_at,
       max(logged_at) AS last_at,
       count(*)       AS n_meals,
       EXTRACT(epoch FROM (max(logged_at) - min(logged_at))) / 3600.0 AS window_hours,
       min(logged_at) + (max(logged_at) - min(logged_at)) / 2 AS midpoint_at
  FROM v_fast_breaking
 GROUP BY user_id, local_date
HAVING count(*) >= 2;

UPDATE observation o
   SET hours_fasted = fast_hours_at(o.user_id, o.observed_at)
 WHERE fast_hours_at(o.user_id, o.observed_at) IS DISTINCT FROM o.hours_fasted;
