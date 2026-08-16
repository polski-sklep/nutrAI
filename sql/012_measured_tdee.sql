-- Where the energy target came from, when it came from a measurement.
--
-- Mifflin-St Jeor carries about 10% standard error and is then multiplied by
-- an activity factor chosen off a list — so a "2,236 kcal" target is a guess
-- times a guess. Meanwhile insight.fat_loss_rate() already backs out the TDEE
-- your body actually has, from the slope of your own weight against your own
-- intake. The two numbers never met: targets were set from the equation while
-- the measurement sat in /insight being read and ignored.
--
-- These record that a target was set from the measurement instead, and what
-- the measurement was, so a later recalculation does not silently revert to
-- the equation and so the number remains explainable months later.
ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS measured_tdee_kcal numeric,
    ADD COLUMN IF NOT EXISTS measured_tdee_on   date,
    -- Days of weigh-ins the measurement rests on. A fortnight is the floor;
    -- three weeks is where glycogen and water stop dominating. Kept so the
    -- card can say how much to trust it rather than presenting every
    -- measurement as equally settled.
    ADD COLUMN IF NOT EXISTS measured_tdee_days integer;
