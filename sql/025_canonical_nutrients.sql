-- USDA ships the same measurement under two ids, and a day was split across
-- both.
--
-- 1063 "Sugars, Total" is what FNDDS reports; 2000 "Total Sugars" is what SR
-- Legacy reports; Foundation carries either. 5,594 foods here have one, 6,018
-- have the other. The target is set on 2000, so every FNDDS food's sugar was
-- simply not counted: a day whose stored snapshot totals 43.25 g displayed
-- 11 g, at 19% of a 57 g ceiling, with no error anywhere.
--
-- The coverage note was the only visible symptom — "(from 32% of food)" — and
-- it was accurate, which is the trouble: it reads as "most of this food has no
-- sugar data", when the truth is that most of it reports sugar under the other
-- id. A correct sentence about the wrong question.
--
-- Folded at read time rather than by rewriting food_nutrient. Rewriting would
-- put this end's opinion into a table that is meant to be a faithful copy of a
-- public dataset, and the next loader run would undo it. log_nutrient is not
-- touched at all — it is an immutable snapshot (invariant 2) and the rows
-- recorded under 1063 stay exactly as they were written; only the aggregate
-- above them changes.
ALTER TABLE nutrient
    ADD COLUMN IF NOT EXISTS canonical_id integer REFERENCES nutrient(id);

COMMENT ON COLUMN nutrient.canonical_id IS
    'Where two USDA ids are the same measurement, the id to aggregate under. '
    'NULL means the nutrient is its own canonical form.';

UPDATE nutrient SET canonical_id = 2000 WHERE id = 1063;

-- One definition, used by every aggregation.
CREATE OR REPLACE VIEW v_nutrient_canonical AS
    SELECT id, COALESCE(canonical_id, id) AS canonical_id FROM nutrient;

CREATE OR REPLACE VIEW v_day_nutrient AS
    SELECT e.user_id,
           e.local_date,
           c.canonical_id            AS nutrient_id,
           n.name                    AS nutrient_name,
           n.unit,
           n.is_core,
           sum(ln.amount)            AS amount
      FROM log_entry e
      JOIN log_nutrient ln            ON ln.entry_id = e.id
      JOIN v_nutrient_canonical c     ON c.id = ln.nutrient_id
      JOIN nutrient n                 ON n.id = c.canonical_id
     WHERE e.status = 'confirmed'
  GROUP BY e.user_id, e.local_date, c.canonical_id, n.name, n.unit, n.is_core;

CREATE OR REPLACE VIEW v_day_supplement_nutrient AS
    SELECT sl.user_id,
           sl.local_date,
           c.canonical_id      AS nutrient_id,
           sum(sn.amount * sl.servings) AS amount
      FROM supplement_log sl
      JOIN supplement_nutrient sn ON sn.supplement_id = sl.supplement_id
      JOIN v_nutrient_canonical c ON c.id = sn.nutrient_id
  GROUP BY sl.user_id, sl.local_date, c.canonical_id;
