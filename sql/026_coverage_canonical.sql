-- Coverage has to fold the same ids the totals do, or the two disagree.
--
-- This function already carried one folding rule inline — energy is reported
-- under 1008, 2047 or 2048 depending on dataset — written as a special case.
-- Adding sugar as a second special case would be the point at which the rules
-- start living in more places than one, so the general one now comes from
-- v_nutrient_canonical and only energy stays hard-coded.
--
-- Energy stays hard-coded because it is a genuinely different relationship.
-- canonical_id means "these are the same measurement, add them up"; the Atwater
-- ids mean "these are alternative estimates of the same thing, use whichever
-- exists". Summing 1008 + 2047 + 2048 would treble a Foundation row's calories.
-- Two rules because there are two relationships, not because nobody unified
-- them.
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
                     JOIN v_nutrient_canonical c ON c.id = fn.nutrient_id
                    WHERE fn.fdc_id = m.fdc_id
                      AND (c.canonical_id = n.id
                           OR (n.id = 1008 AND fn.nutrient_id IN (2047, 2048)))
               )
           ), 0) / (SELECT g FROM total)
      FROM nutrient n
     CROSS JOIN mass m
  GROUP BY n.id;
$$;
