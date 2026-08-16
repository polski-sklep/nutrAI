-- Intensity, as a field rather than as prose in `note`.
--
-- 45 minutes of lifting is not one thing. A heavy session and an easy one
-- differ in what they demand afterwards, and as a sleep and rating covariate
-- the distinction is most of the signal — pooling them flattens exactly the
-- variation the correlation is trying to find.
--
-- Free text, kept small and checked, because a 1-10 RPE from one bot and a
-- "hard" from another are not comparable and averaging them would invent a
-- precision neither has. Nullable: a session with no intensity recorded is
-- unknown, not moderate.
ALTER TABLE activity
    ADD COLUMN IF NOT EXISTS intensity text,
    ADD COLUMN IF NOT EXISTS rpe numeric;

ALTER TABLE activity DROP CONSTRAINT IF EXISTS activity_intensity_ck;
ALTER TABLE activity ADD CONSTRAINT activity_intensity_ck
    CHECK (intensity IS NULL OR intensity IN ('easy', 'moderate', 'hard', 'max'));
ALTER TABLE activity DROP CONSTRAINT IF EXISTS activity_rpe_ck;
ALTER TABLE activity ADD CONSTRAINT activity_rpe_ck
    CHECK (rpe IS NULL OR (rpe >= 1 AND rpe <= 10));
