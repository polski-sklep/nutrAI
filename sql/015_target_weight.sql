-- How much a floor counts toward the day's score.
--
-- Every floor weighed the same, so DHA at 0.25 g counted for as much as
-- protein at 165 g. For a recomposition goal that is hard to defend: the
-- protein floor is what the plan hangs on, and missing it by a third is not
-- the same event as missing vitamin A by a third, which is one carrot.
--
-- Defaults to 1, so nothing changes until asked. The weights are the user's
-- to set — a weight vector chosen by the software would be unfalsifiable
-- authority dressed as a score, which is the failure this codebase avoids
-- everywhere else.
ALTER TABLE target ADD COLUMN IF NOT EXISTS weight numeric NOT NULL DEFAULT 1;
ALTER TABLE target DROP CONSTRAINT IF EXISTS target_weight_ck;
ALTER TABLE target ADD CONSTRAINT target_weight_ck CHECK (weight > 0 AND weight <= 10);

-- target_on gates every read of a target, so the weight has to come through
-- it as well or day_progress cannot see the column that now exists.
DROP FUNCTION IF EXISTS day_progress(bigint, date);
DROP FUNCTION IF EXISTS target_on(bigint, date);
CREATE FUNCTION target_on(p_user bigint, p_day date)
RETURNS TABLE (nutrient_id integer, min_amount numeric, max_amount numeric,
               period text, weight numeric)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (t.nutrient_id, t.period)
           t.nutrient_id, t.min_amount, t.max_amount, t.period, t.weight
    FROM target t
    WHERE t.user_id = p_user
      AND t.effective_from <= p_day
      AND (t.effective_to IS NULL OR t.effective_to > p_day)
    ORDER BY t.nutrient_id, t.period, t.effective_from DESC;
$$;

CREATE FUNCTION day_progress(p_user bigint, p_day date)
RETURNS TABLE (
    nutrient_id integer,
    nutrient_name text,
    unit text,
    is_core boolean,
    amount numeric,
    amount_food numeric,
    amount_supplement numeric,
    min_amount numeric,
    max_amount numeric,
    pct_of_min numeric,
    pct_of_max numeric,
    state text,
    weight numeric
)
LANGUAGE sql STABLE AS $$
    SELECT n.id,
           n.name,
           n.unit,
           n.is_core,
           COALESCE(d.amount, 0) + COALESCE(s.amount, 0),
           COALESCE(d.amount, 0),
           COALESCE(s.amount, 0),
           t.min_amount,
           t.max_amount,
           CASE WHEN t.min_amount > 0
                THEN round(100 * (COALESCE(d.amount,0) + COALESCE(s.amount,0)) / t.min_amount, 1) END,
           CASE WHEN t.max_amount > 0
                THEN round(100 * (COALESCE(d.amount,0) + COALESCE(s.amount,0)) / t.max_amount, 1) END,
           CASE
               WHEN t.max_amount IS NOT NULL
                    AND COALESCE(d.amount,0) + COALESCE(s.amount,0) > t.max_amount THEN 'over'
               WHEN t.min_amount IS NOT NULL
                    AND COALESCE(d.amount,0) + COALESCE(s.amount,0) < t.min_amount THEN 'under'
               ELSE 'ok'
           END,
           t.weight
    FROM target_on(p_user, p_day) t
    JOIN nutrient n ON n.id = t.nutrient_id
    LEFT JOIN v_day_nutrient d
           ON d.user_id = p_user AND d.local_date = p_day AND d.nutrient_id = n.id
    LEFT JOIN v_day_supplement_nutrient s
           ON s.user_id = p_user AND s.local_date = p_day AND s.nutrient_id = n.id
    WHERE t.period = 'day';
$$;
