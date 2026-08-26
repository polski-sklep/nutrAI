-- Asking for a rating, at most three times a day.
--
-- 25 observations in ten days across six kinds, best kind at 7, and /insight
-- refuses under 20 paired observations — so at the volunteered rate the
-- feature never turns on. Remembering to type /rate is the binding constraint,
-- not willingness to answer.
--
-- This is a deliberate exception to "Unprompted messages" in CLAUDE.md, and it
-- has to earn the exception the same way the morning note does: one line, one
-- tap, about *now*, and silenceable.

-- Where the number came from.
--
-- A rating you volunteer and a rating you are prodded for are not the same
-- measurement. Volunteered ones cluster on notable moments — you type /rate
-- when focus is unusually bad — while a prompt at a random hour samples the
-- ordinary. /insight correlates over this table, so mixing two sampling
-- processes without recording which is which would put a bias into every
-- correlation and leave nothing able to detect it afterwards.
--
-- Nothing filters on this yet, deliberately: halving the data to remove a bias
-- nobody has measured would be trading a known loss for a hypothetical gain.
-- It is recorded so the question can be asked later.
ALTER TABLE observation
  ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'volunteered';

COMMENT ON COLUMN observation.source IS
  'volunteered (typed /rate) | prompted (answered a random ask) | activity (posted by the training bot)';

ALTER TABLE app_user
  ADD COLUMN IF NOT EXISTS rating_prompts boolean NOT NULL DEFAULT true;

-- The plan, not a counter.
--
-- "No more than three a day" as a running tally would depend on every send
-- path incrementing it correctly. Three planned rows per day makes the cap
-- structural: there is no fourth row to fire, whatever the code does.
--
-- due_at is stored because the times are drawn once. A sweep that re-rolled a
-- probability every ten minutes would cluster prompts unpredictably and could
-- not be tested.
CREATE TABLE IF NOT EXISTS rating_prompt (
    id           bigserial PRIMARY KEY,
    user_id      bigint NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    local_date   date   NOT NULL,
    kind         text   NOT NULL,
    due_at       timestamptz NOT NULL,
    asked_at     timestamptz,
    -- The observation it produced, or NULL if it was ignored or declined.
    -- An ignored prompt is worth keeping: a kind nobody ever answers is a
    -- kind not worth asking about, and that is invisible if unanswered rows
    -- are deleted.
    observation_id bigint REFERENCES observation(id) ON DELETE SET NULL,
    declined     boolean NOT NULL DEFAULT false,
    UNIQUE (user_id, local_date, kind)
);

CREATE INDEX IF NOT EXISTS rating_prompt_due
  ON rating_prompt (due_at) WHERE asked_at IS NULL;
