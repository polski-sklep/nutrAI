-- Supplements.
--
-- A supplement is not a food and forcing it through the food tables would be
-- contortion: it is taken by count rather than by mass, and its authority is a
-- printed label rather than a USDA lab assay. So it gets its own tables, its
-- own provenance, and its own column in every total.
--
-- The values here enter the system by transcription, not estimation. That is a
-- real distinction and the reason it does not breach the contract in §1 of
-- docs/ARCHITECTURE.md: a transcribed panel is checkable at the moment it is
-- read — against the packet in your hand, at the confirm gate — where an
-- estimated nutrient value is checkable against nothing. `source` records which
-- happened, and nothing may write 'model_estimate' into it.

CREATE TABLE IF NOT EXISTS supplement (
    id           bigserial PRIMARY KEY,
    user_id      bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    name         text NOT NULL,
    brand        text,
    -- Free text as printed: "1 capsule", "2 tablets", "1 scoop (5 g)".
    serving_desc text NOT NULL DEFAULT '1 serving',
    -- How many servings the daily stack takes. Not enforced; it is what `/supp`
    -- logs by default.
    servings_per_day numeric NOT NULL DEFAULT 1,
    active       boolean NOT NULL DEFAULT true,
    photo_file_id text,
    -- label_photo | manual. A supplement whose numbers nobody read off a packet
    -- should be visibly different from one whose numbers were.
    source       text NOT NULL DEFAULT 'label_photo',
    verified_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

-- Per serving, in the nutrient's own FDC unit. Converted on the way in, never
-- stored as printed, so that summing against food needs no unit logic at all.
CREATE TABLE IF NOT EXISTS supplement_nutrient (
    supplement_id bigint NOT NULL REFERENCES supplement ON DELETE CASCADE,
    nutrient_id   integer NOT NULL REFERENCES nutrient,
    amount        numeric NOT NULL,
    PRIMARY KEY (supplement_id, nutrient_id)
);

-- One row per supplement per day. Taking the stack is a deliberate act with a
-- deliberate record, per invariant 5 — the alternative, assuming the stack was
-- taken because it usually is, would put numbers into your targets that nobody
-- ever confirmed.
CREATE TABLE IF NOT EXISTS supplement_log (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    supplement_id bigint NOT NULL REFERENCES supplement ON DELETE CASCADE,
    local_date    date NOT NULL,
    servings      numeric NOT NULL DEFAULT 1,
    taken_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, supplement_id, local_date)
);
CREATE INDEX IF NOT EXISTS supplement_log_day ON supplement_log (user_id, local_date);

CREATE OR REPLACE VIEW v_day_supplement_nutrient AS
SELECT sl.user_id,
       sl.local_date,
       sn.nutrient_id,
       sum(sn.amount * sl.servings) AS amount
FROM supplement_log sl
JOIN supplement_nutrient sn ON sn.supplement_id = sl.supplement_id
GROUP BY sl.user_id, sl.local_date, sn.nutrient_id;

-- day_progress gains two columns rather than changing one.
--
-- `amount` stays the total, so every existing caller keeps working and the
-- targets reflect what actually reached you. `amount_food` and
-- `amount_supplement` are what keep the two legible: a micronutrient met by a
-- capsule is different information from one met by food, and a system that
-- blended them would let /improve recommend fixing a deficiency you are already
-- treating — or, worse, conclude your diet supplies something it does not.
DROP FUNCTION IF EXISTS day_progress(bigint, date);
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
    state text
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
           END
    FROM target_on(p_user, p_day) t
    JOIN nutrient n ON n.id = t.nutrient_id
    LEFT JOIN v_day_nutrient d
           ON d.user_id = p_user AND d.local_date = p_day AND d.nutrient_id = n.id
    LEFT JOIN v_day_supplement_nutrient s
           ON s.user_id = p_user AND s.local_date = p_day AND s.nutrient_id = n.id
    WHERE t.period = 'day';
$$;
