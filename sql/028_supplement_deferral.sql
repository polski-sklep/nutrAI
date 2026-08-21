-- "Not yet" is a promise, not a dismissal.
--
-- Pressing it closed the card and that was the end of it: the capsule was
-- neither logged nor mentioned again, so the honest answer at 08:00 quietly
-- became a missing dose at 22:00. The reminder is per slot per day, and a
-- morning supplement had no way to appear in the afternoon's.
--
-- Only explicit deferrals are carried. An ignored reminder stays ignored:
-- carrying those too would turn one unanswered notification into a stream of
-- them, which is the behaviour that gets a tracker muted.
CREATE TABLE IF NOT EXISTS supplement_deferral (
    user_id       bigint NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    supplement_id bigint NOT NULL REFERENCES supplement(id) ON DELETE CASCADE,
    local_date    date   NOT NULL,
    from_slot     text   NOT NULL,
    deferred_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, supplement_id, local_date)
);

COMMENT ON TABLE supplement_deferral IS
    'Supplements the user said "not yet" to today. Carried into the next '
    'reminder and dropped the moment one is logged — the log is the authority, '
    'this only decides what gets asked about.';
