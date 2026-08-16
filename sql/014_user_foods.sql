-- Foods you define yourself, kept in `food` rather than beside it.
--
-- "100 ml of pickle juice" matched "Relish, pickle" at 130 kcal because USDA
-- has no brine row at all. Some things you eat are simply not in a national
-- food database: home preparations, a local bakery's bun, a brand sold in one
-- country. Without somewhere to put them the resolver must pick the least-bad
-- wrong answer every single time you log them.
--
-- They live in `food` with data_type 'user_product', which is the whole point:
-- log_component.fdc_id, profiles_for, coverage, portion_history, the audit and
-- /why all keep working unchanged, because nothing downstream can tell the
-- difference between a row you made and a row USDA made.
ALTER TABLE food ADD COLUMN IF NOT EXISTS owner_user_id bigint REFERENCES app_user ON DELETE CASCADE;

-- Your own row outranks the generic one. Precedence is a generated column, so
-- it has to be rebuilt rather than altered: for a food you defined, the panel
-- is either off the packet in your hand or computed from ingredients you
-- listed, and both beat USDA's average of a category.
ALTER TABLE food DROP COLUMN precedence;
ALTER TABLE food ADD COLUMN precedence smallint GENERATED ALWAYS AS (
    CASE data_type
        WHEN 'user_product'       THEN 0
        WHEN 'foundation_food'    THEN 1
        WHEN 'sr_legacy_food'     THEN 2
        WHEN 'survey_fndds_food'  THEN 3
        WHEN 'branded_food'       THEN 4
        ELSE 9 END) STORED;

CREATE INDEX IF NOT EXISTS food_owner ON food (owner_user_id) WHERE owner_user_id IS NOT NULL;

-- Negative ids, from a sequence. USDA fdc_ids are positive and in the
-- millions, so a negative id can never collide however far FDC grows, and it
-- says what it is the moment you see one in a log line.
CREATE SEQUENCE IF NOT EXISTS user_food_id_seq START 1;
