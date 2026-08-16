-- A repeated portion is not a guessed portion.
--
-- Three espressos, all stated at 30 g / 100 ml / 2 g, showed the day as "58%
-- of today's mass was weighed or stated" and told the user to weigh more. The
-- true figure is 100%: every gram of that coffee was stated. What happened is
-- that `dish_component` stored no provenance, so a repeat had nothing to
-- inherit and every component was written as `grams_source = 'repeat'`, which
-- `v_day_mass_confidence` counts as unmeasured.
--
-- Worse, the dilution grew with use: 432 g hard out of 615 g is 70%, out of
-- 747 g is 58%. The measurement-quality figure fell every time the user
-- correctly reused a well-specified dish — precisely backwards.
--
-- Note also that 'repeat' was never in `log_component.grams_source`'s
-- documented set (scale | stated | package | prior | estimate). It is an
-- entry-level fact about how the entry was created, and `log_entry.source`
-- already records it. Storing it per component conflated two different
-- questions: "how was this entry made" and "how was this mass arrived at".
ALTER TABLE dish_component
    ADD COLUMN IF NOT EXISTS grams_source text NOT NULL DEFAULT 'estimate';

-- Backfill from the most recent confirmed logging of each dish, which is where
-- the dish's masses came from in the first place.
UPDATE dish_component dc
   SET grams_source = src.grams_source
  FROM (
    SELECT DISTINCT ON (e.dish_id, c.fdc_id)
           e.dish_id, c.fdc_id, c.grams_source
      FROM log_entry e
      JOIN log_component c ON c.entry_id = e.id
     WHERE e.status = 'confirmed'
       AND e.dish_id IS NOT NULL
       AND c.grams_source IN ('scale', 'stated', 'package')
     ORDER BY e.dish_id, c.fdc_id, e.logged_at DESC
  ) src
 WHERE src.dish_id = dc.dish_id AND src.fdc_id = dc.fdc_id;

-- Same repair for entries already logged as repeats: adopt the provenance of
-- the dish they came from, now that the dish carries one.
UPDATE log_component c
   SET grams_source = dc.grams_source
  FROM log_entry e, dish_component dc
 WHERE c.entry_id = e.id
   AND e.dish_id = dc.dish_id
   AND dc.fdc_id = c.fdc_id
   AND c.grams_source = 'repeat'
   AND dc.grams_source IN ('scale', 'stated', 'package');

-- Anything still saying 'repeat' repeated a dish whose own masses were
-- estimated. That is an estimate, and it should read as one.
UPDATE log_component SET grams_source = 'estimate' WHERE grams_source = 'repeat';

-- Invariant 7 is preserved explicitly rather than by accident.
--
-- It used to hold because repeats were tagged 'repeat' and filtered out. Now
-- that a repeat of a stated portion is correctly tagged 'stated', the filter
-- has to say what it means: a repeat is not an independent observation of a
-- portion, it is the same observation asserted again. Three identical coffees
-- are one measurement of 100 ml of milk, not three, and letting them count as
-- three would make the prior confident on the strength of its own echo.
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
       AND e.source <> 'repeat'
  ORDER BY e.logged_at DESC
     LIMIT p_limit;
$$;
