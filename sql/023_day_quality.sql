-- Days you know you did not log properly.
--
-- Every trend, correlation and measured-TDEE figure in this system reads the
-- diary as if it were complete. A day out with friends where three meals went
-- unlogged is not a 900 kcal day; it is a day with no usable number in it. Left
-- unmarked it drags a weight-trend deficit, weakens a real /insight
-- correlation, and — worst — makes measured TDEE look higher than it is, which
-- then raises the energy target off the back of a day nobody recorded.
--
-- The alternative was to guess at what was missed, which is the estimate the
-- rest of this design refuses everywhere else. A day is either recorded or it
-- is not, and saying so is cheap.
CREATE TABLE IF NOT EXISTS day_quality (
    user_id     bigint  NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    local_date  date    NOT NULL,
    complete    boolean NOT NULL DEFAULT true,
    note        text,
    marked_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, local_date)
);

-- Absence means complete. Marking every ordinary day would be a chore nobody
-- keeps up, and a flag people stop setting is worse than no flag: it turns
-- "not marked" from a default into a silent unknown.
COMMENT ON TABLE day_quality IS
    'Days explicitly marked. A missing row means the day is taken as complete.';
