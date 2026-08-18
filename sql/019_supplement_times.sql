-- When a supplement was actually taken, not merely which day.
--
-- The stack was a daily checklist: tick the lot, and the day's micronutrients
-- appeared with no time attached. That is enough for a daily total and not
-- enough for anything else — magnesium at 22:00 and magnesium at 08:00 are
-- the same row and a different intervention, and the sleep correlations
-- cannot tell them apart.
ALTER TABLE supplement_log
    ADD COLUMN IF NOT EXISTS taken_at timestamptz NOT NULL DEFAULT now(),
    -- How it came to be recorded: you ticked it, a reminder did, or it was
    -- named in a meal you logged. Kept because "I ticked this" and "the
    -- system inferred it from the word 'creatine' in a sentence" are
    -- different confidences and only one of them is your own testimony.
    ADD COLUMN IF NOT EXISTS logged_via text NOT NULL DEFAULT 'manual';

ALTER TABLE supplement_log DROP CONSTRAINT IF EXISTS supplement_log_via_ck;
ALTER TABLE supplement_log ADD CONSTRAINT supplement_log_via_ck
    CHECK (logged_via IN ('manual', 'reminder', 'from_meal'));
