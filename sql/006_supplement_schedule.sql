-- Cadence, because a stack is not uniformly daily.
--
-- The first design assumed it was: one row per supplement, servings_per_day,
-- and /supp logs the lot. A real schedule has zinc every other day, some things
-- only when the largest fat-containing meal happens, and some occasionally. A
-- picker that pre-ticks everything every day quietly trains you to untick, and
-- the day you forget to untick is the day a number enters your totals that
-- never entered you.
ALTER TABLE supplement
    ADD COLUMN IF NOT EXISTS schedule text NOT NULL DEFAULT 'daily',
    ADD COLUMN IF NOT EXISTS note text;

-- daily      : pre-ticked every day
-- alternate  : pre-ticked only when it was not taken yesterday
-- occasional : never pre-ticked, always a deliberate choice
ALTER TABLE supplement DROP CONSTRAINT IF EXISTS supplement_schedule_ck;
ALTER TABLE supplement ADD CONSTRAINT supplement_schedule_ck
    CHECK (schedule IN ('daily', 'alternate', 'occasional'));
