-- "Muscle gain and fat loss" is a real goal, and lose/maintain/gain has no
-- room for it. Asked what he was aiming at, the honest answer did not fit the
-- enum, and an enum that refuses the true answer collects false ones.
ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_goal_ck;
ALTER TABLE app_user ADD CONSTRAINT app_user_goal_ck
    CHECK (goal IS NULL OR goal IN ('lose', 'maintain', 'gain', 'recomp'));
