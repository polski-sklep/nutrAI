-- A supplement you have decided on but are not taking yet.
--
-- "Vitamin D3 + K2 — after breakfast, from 1 October" is a real thing to
-- record: the decision is made and the slot is chosen, and pre-ticking it in
-- August would put a capsule you did not swallow into the day's totals.
-- Nullable, because most supplements start the day you add them.
ALTER TABLE supplement
    ADD COLUMN IF NOT EXISTS starts_on date;
