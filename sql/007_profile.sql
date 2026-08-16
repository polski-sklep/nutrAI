-- The numbers your targets were derived from, kept rather than discarded.
--
-- bootstrap.py asked for sex, age, height, activity factor and deficit,
-- computed a target energy from them and then threw all five away. Only the
-- derived numbers survived. That has three consequences: nothing can recompute
-- a target when an input changes, nothing can show you what the target was
-- based on, and correcting a typo in your height means re-running a CLI script
-- against the database by hand.
--
-- Note what is NOT here: weight. There is exactly one weight and it lives in
-- body_metric, where every weigh-in is dated and the trend is the actual
-- instrument. A copy on app_user would be a second version of the truth that
-- goes stale the first time you use /weight.
ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS sex             text,
    -- Birth date, not age. An age is only true for a year and nothing in the
    -- system would know when to increment it; a birth date stays correct.
    ADD COLUMN IF NOT EXISTS birth_date      date,
    ADD COLUMN IF NOT EXISTS height_cm       numeric,
    ADD COLUMN IF NOT EXISTS activity_factor numeric,
    ADD COLUMN IF NOT EXISTS goal            text,
    ADD COLUMN IF NOT EXISTS goal_weight_kg  numeric,
    ADD COLUMN IF NOT EXISTS deficit_kcal    numeric,
    -- What weight the standing energy target was computed against, so
    -- /profile can say "set at 82.1 kg, you are now 77.6" rather than
    -- silently drifting. Targets are versioned and never recomputed
    -- automatically — see invariant 3.
    ADD COLUMN IF NOT EXISTS targets_set_at_kg numeric,
    ADD COLUMN IF NOT EXISTS targets_set_on    date;

ALTER TABLE app_user
    ADD CONSTRAINT app_user_sex_ck  CHECK (sex IS NULL OR sex IN ('male', 'female')),
    ADD CONSTRAINT app_user_goal_ck CHECK (goal IS NULL OR goal IN ('lose', 'maintain', 'gain'));
