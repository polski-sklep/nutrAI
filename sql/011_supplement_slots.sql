-- Supplements are taken in moments, not once a day.
--
-- The stack was modelled as a single daily event, so `/supp` asked about all
-- nine at whatever hour you happened to open it. In practice they go in three
-- or four groups — fasted, after breakfast, evening, before bed — and some of
-- those groupings are the point: magnesium at night, boron with a meal.
--
-- Nullable. A supplement with no slot belongs to no reminder and still logs
-- normally from `/supp`; unassigned is unassigned, not "morning".
ALTER TABLE supplement
    ADD COLUMN IF NOT EXISTS slot text;

ALTER TABLE supplement DROP CONSTRAINT IF EXISTS supplement_slot_ck;
ALTER TABLE supplement ADD CONSTRAINT supplement_slot_ck
    CHECK (slot IS NULL OR slot IN ('fasted', 'breakfast', 'evening', 'bed'));

-- When each moment is, per user, in their own local time. A table rather than
-- four columns on app_user because a slot you have not set a time for should
-- be absent, not a default hour that quietly starts sending notifications.
CREATE TABLE IF NOT EXISTS supplement_slot_time (
    user_id   bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    slot      text   NOT NULL,
    remind_at time   NOT NULL,
    enabled   boolean NOT NULL DEFAULT true,
    PRIMARY KEY (user_id, slot),
    CONSTRAINT supplement_slot_time_slot_ck
        CHECK (slot IN ('fasted', 'breakfast', 'evening', 'bed'))
);

-- One reminder per slot per day. Without this a sweep that runs every ten
-- minutes sends the same nudge six times an hour, which is how a useful
-- notification becomes one you turn off.
CREATE TABLE IF NOT EXISTS supplement_reminder_log (
    user_id    bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    slot       text   NOT NULL,
    local_date date   NOT NULL,
    sent_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, slot, local_date)
);
