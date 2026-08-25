-- `resolution_event` was created by 030 with nothing writing to it.
--
-- The table shipped, the columns were right, and every resolution since has
-- gone unrecorded — so the one question it exists to answer ("why did it pick
-- that row?") still had to be reconstructed by hand, which is how 25 Aug was
-- spent. Two things were missing.

-- 1. Whose resolution it was.
--
-- 030 keyed only on entry_id, and the rows worth reading are exactly the ones
-- that never become an entry: a parse you discarded, an item that matched
-- nothing, a card you ignored. Those carry entry_id NULL forever, so without
-- user_id they cannot be attributed, cannot be swept by the test suite, and
-- cannot be read per-user at all.
--
-- The sweep matters more than it sounds. tests/conftest.py can only delete what
-- it can select by user, and a table it cannot reach is how `target` reached
-- 11,330 superseded rows for a user that does not exist.
ALTER TABLE resolution_event
  ADD COLUMN IF NOT EXISTS user_id bigint REFERENCES app_user(id) ON DELETE CASCADE;

-- 2. A way to read them in time order for one person, which is the only order
--    a diagnosis is ever made in: "what happened when I sent that photo".
CREATE INDEX IF NOT EXISTS resolution_event_user
  ON resolution_event (user_id, created_at DESC);

COMMENT ON COLUMN resolution_event.user_id IS
  'Who resolved. Present even when entry_id is NULL, which is the interesting case.';
COMMENT ON COLUMN resolution_event.entry_id IS
  'The entry this became, or NULL if it never became one — a discarded parse, '
  'an unresolved item, a card never confirmed. NULL is the diagnostic case.';
