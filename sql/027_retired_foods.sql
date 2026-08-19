-- Retiring a food you can no longer delete.
--
-- A user food whose panel turns out to be wrong cannot simply be deleted once
-- anything has been logged against it: log_component references it, and
-- log_nutrient holds the snapshot that entry was actually scored on
-- (invariant 2). The row has to stay so history stays readable.
--
-- What it must stop doing is being offered. The first attempt at this renamed
-- the row to "Blondie (retired: energy figure was wrong)", which works in the
-- sense that the list says so, and fails in every other: it truncates in the
-- card, it sorts under B, it is a status encoded in a display string, and
-- nothing can filter on it without matching text.
ALTER TABLE food
    ADD COLUMN IF NOT EXISTS retired_at timestamptz,
    ADD COLUMN IF NOT EXISTS retired_reason text;

COMMENT ON COLUMN food.retired_at IS
    'Set on a user food that must no longer be offered or matched. The row '
    'stays because log_component references it and its snapshot is history.';

-- Undo the string hack, keeping what it said.
UPDATE food
   SET description = 'Blondie',
       retired_at = now(),
       retired_reason = 'energy figure was wrong: butter matched a row with no energy'
 WHERE fdc_id = -249 AND description LIKE 'Blondie (retired%';
