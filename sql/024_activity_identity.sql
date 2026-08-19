-- A session's own identity, so dedup stops guessing.
--
-- Idempotency was keyed on (user, date, kind, minutes, intensity), which is a
-- heuristic standing in for an identity. The fitness side flagged where it
-- breaks: their lifting sessions cluster at 96-108 minutes and the intensity
-- bands are coarse, so two real sessions on one date can look identical and
-- the second is silently swallowed. Rare while training once a day, and they
-- batch-backfill, which is exactly when it would fire.
--
-- A retry carries the same session id; two sessions do not. That is the whole
-- problem, solved by the client saying which session it means rather than by
-- this end inferring it from a shape.
ALTER TABLE activity
    ADD COLUMN IF NOT EXISTS external_id text,
    -- When the session actually happened, as opposed to the day it belongs to.
    -- The row had no time at all, which is why an effort rating posted after
    -- the fact had no honest hour to correlate against.
    ADD COLUMN IF NOT EXISTS occurred_at timestamptz;

-- Partial, so rows without an id are unaffected and the old heuristic still
-- covers them.
CREATE UNIQUE INDEX IF NOT EXISTS activity_external
    ON activity (user_id, external_id) WHERE external_id IS NOT NULL;
