-- What breaks a fast is carbohydrate and protein, not calories.
--
-- The first version used total energy, and energy cannot tell honey from
-- olive oil. A 33 kcal ginger tea is nine grams of sugar and unambiguously
-- ends a fast; a 120 kcal spoon of butter is essentially none. Raising the
-- energy threshold far enough to admit a pickle brine also admitted the
-- honey, which is the wrong answer arrived at from the wrong variable.
--
-- Carbohydrate is the dominant insulin secretagogue and protein is the
-- second; fat is a distant third and is deliberately not counted. Summing the
-- two rather than weighting them is a simplification, and an honest one: the
-- weights would be invented, and the sum already separates the real cases by
-- an order of magnitude.
--
--   lemon lime water   2.1 g   does not break
--   ginger tea, honey  9.2 g   breaks
--   whey shake        26.9 g   breaks
--
-- Five grams sits in the gap. It is still a convention — insulin response is
-- continuous and no experiment names a gram count — but it is a convention
-- about the right quantity.
ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS fast_break_cp_g numeric NOT NULL DEFAULT 5;

-- The views read the old column, so they go first.
DROP VIEW IF EXISTS v_eating_window;
DROP VIEW IF EXISTS v_fast_breaking;
ALTER TABLE app_user DROP COLUMN IF EXISTS fast_break_kcal;

CREATE VIEW v_fast_breaking AS
SELECT e.user_id, e.id AS entry_id, e.logged_at, e.local_date, e.name, e.slot,
       COALESCE(c.amount, 0) + COALESCE(p.amount, 0) AS carb_protein_g
  FROM log_entry e
  JOIN app_user u ON u.id = e.user_id
  LEFT JOIN log_nutrient c ON c.entry_id = e.id AND c.nutrient_id = 1005
  LEFT JOIN log_nutrient p ON p.entry_id = e.id AND p.nutrient_id = 1003
 WHERE e.status = 'confirmed'
   AND COALESCE(c.amount, 0) + COALESCE(p.amount, 0) >= u.fast_break_cp_g;

CREATE VIEW v_eating_window AS
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

UPDATE observation o
   SET hours_fasted = fast_hours_at(o.user_id, o.observed_at)
 WHERE fast_hours_at(o.user_id, o.observed_at) IS DISTINCT FROM o.hours_fasted;
