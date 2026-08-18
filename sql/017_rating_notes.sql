-- Why a rating was what it was.
--
-- "sleep 4" is a number. "sleep 4, woke at 3 and could not get back down" is
-- the same number plus the only part a correlation cannot recover: a 4 caused
-- by a late coffee, a 4 caused by a noisy street and a 4 caused by illness are
-- three different observations that the permutation test sees as one.
--
-- Free text on purpose. A dropdown of causes would be a guess at the space of
-- reasons, and the reasons are what is being collected.
ALTER TABLE observation ADD COLUMN IF NOT EXISTS note text;
