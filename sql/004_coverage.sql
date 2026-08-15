-- Per-nutrient measurement coverage for a day.
--
-- `total_nutrients()` skips a nutrient the food row does not report, rather
-- than summing it as zero. That is right, and on its own it is not enough:
-- the day card then shows "Vitamin B-12  0.0 µg  0%  ▽" for a plate built
-- around beef, because the Foundation beef row carries no B-12 value. Skipping
-- the null keeps the arithmetic honest and still produces a phantom deficiency
-- on screen — the exact failure docs/ARCHITECTURE.md §0.3 sets out to avoid.
--
-- This is the missing half: what fraction of the day's mass sat on food rows
-- that actually report the nutrient. "Selenium 41 µg (78% of the plate
-- measured)" is honest. "41 µg" is not, and "0 µg" is a lie.
CREATE OR REPLACE FUNCTION day_nutrient_coverage(p_user bigint, p_day date)
RETURNS TABLE (nutrient_id integer, covered_frac numeric)
LANGUAGE sql STABLE AS $$
    WITH mass AS (
        SELECT c.fdc_id, sum(c.grams * c.yield_factor) AS g
          FROM log_entry e
          JOIN log_component c ON c.entry_id = e.id
         WHERE e.user_id = p_user
           AND e.local_date = p_day
           AND e.status = 'confirmed'
      GROUP BY c.fdc_id
    ),
    total AS (SELECT NULLIF(sum(g), 0) AS g FROM mass)
    -- EXISTS rather than a LEFT JOIN on purpose: a food row that reports both
    -- 2047 and 2048 would match twice and count its mass twice, which is how
    -- energy coverage comes out at 158%.
    SELECT n.id,
           COALESCE(sum(m.g) FILTER (
               WHERE EXISTS (
                   SELECT 1 FROM food_nutrient fn
                    WHERE fn.fdc_id = m.fdc_id
                      -- Mirrors core.nutrition.normalise_energy: FDC reports
                      -- energy under 1008, 2047 or 2048 depending on the
                      -- dataset, and a row carrying only the Atwater ids is
                      -- still a row that measured energy.
                      AND (fn.nutrient_id = n.id
                           OR (n.id = 1008 AND fn.nutrient_id IN (2047, 2048)))
               )
           ), 0) / (SELECT g FROM total)
      FROM nutrient n
     CROSS JOIN mass m
  GROUP BY n.id;
$$;
