-- The good-morning note, and when it should arrive.
--
-- Either you tell it, or it learns: the hour you first speak to the bot is a
-- decent proxy for when you are up, and asking for a wake time is one more
-- setup question nobody wants. Set explicitly it wins; otherwise the median
-- of the last fortnight's first-contact hours decides, and the note lands
-- half an hour before that.
ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS wake_hour smallint,
    ADD COLUMN IF NOT EXISTS morning_note boolean NOT NULL DEFAULT true;

ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_wake_ck;
ALTER TABLE app_user ADD CONSTRAINT app_user_wake_ck
    CHECK (wake_hour IS NULL OR wake_hour BETWEEN 0 AND 23);

-- One note per day, and the record of it. Same reason the supplement reminder
-- has one: a sweep that runs every ten minutes must not say good morning six
-- times an hour.
CREATE TABLE IF NOT EXISTS morning_note_log (
    user_id    bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    local_date date   NOT NULL,
    sent_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, local_date)
);

-- When you first spoke each day, for the median above. Written by the bot on
-- the first message of a local day; cheap, and it makes the wake estimate a
-- measurement rather than a guess about a guess.
CREATE TABLE IF NOT EXISTS first_contact (
    user_id    bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    local_date date   NOT NULL,
    at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, local_date)
);
