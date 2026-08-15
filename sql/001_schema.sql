-- nutribot schema, PostgreSQL 16+
-- Design rule: the LLM never produces a nutrient number. It produces
-- (food identity, grams, state). Every nutrient value below comes from USDA
-- FoodData Central and is computed in SQL. Nutrients are snapshotted at log
-- time so a later USDA refresh cannot silently rewrite your history.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
-- CREATE EXTENSION IF NOT EXISTS vector;  -- phase 4, semantic food matching

-- ---------------------------------------------------------------- reference
-- Loaded from FoodData Central bulk CSV. Public domain (CC0 1.0).

CREATE TABLE nutrient (
    id            integer PRIMARY KEY,          -- FDC internal nutrient id
    nutrient_nbr  numeric,                      -- INFOODS tagname number, e.g. 1008 = Energy
    name          text NOT NULL,
    unit          text NOT NULL,                -- G, MG, UG, KCAL, IU
    rank          integer,                      -- FDC display order
    is_core       boolean NOT NULL DEFAULT false  -- shown in the compact summary
);

CREATE TABLE food (
    fdc_id      integer PRIMARY KEY,
    data_type   text NOT NULL,                  -- foundation_food | sr_legacy_food | survey_fndds_food | branded_food
    description text NOT NULL,
    category    text,
    brand       text,
    gtin_upc    text,
    -- Precedence when several foods match a name. Lower wins.
    -- Foundation is best-measured; branded is self-reported by manufacturers.
    precedence  smallint GENERATED ALWAYS AS (
        CASE data_type
            WHEN 'foundation_food'    THEN 1
            WHEN 'sr_legacy_food'     THEN 2
            WHEN 'survey_fndds_food'  THEN 3
            WHEN 'branded_food'       THEN 4
            ELSE 9 END) STORED
);

CREATE INDEX food_desc_trgm ON food USING gin (description gin_trgm_ops);
CREATE INDEX food_fts       ON food USING gin (to_tsvector('english', description));
CREATE INDEX food_gtin      ON food (gtin_upc) WHERE gtin_upc IS NOT NULL;

-- Amount is always per 100 g of the food as described.
CREATE TABLE food_nutrient (
    fdc_id      integer NOT NULL REFERENCES food ON DELETE CASCADE,
    nutrient_id integer NOT NULL REFERENCES nutrient,
    amount      numeric NOT NULL,
    PRIMARY KEY (fdc_id, nutrient_id)
);

CREATE TABLE food_portion (
    id           bigint PRIMARY KEY,
    fdc_id       integer NOT NULL REFERENCES food ON DELETE CASCADE,
    amount       numeric,
    unit         text,          -- 'cup', 'tbsp', 'slice', ...
    modifier     text,
    gram_weight  numeric NOT NULL
);
CREATE INDEX food_portion_food ON food_portion (fdc_id);

-- ------------------------------------------------------------------- user

CREATE TABLE app_user (
    id                bigserial PRIMARY KEY,
    telegram_id       bigint UNIQUE NOT NULL,
    display_name      text,
    tz                text NOT NULL DEFAULT 'Europe/Warsaw',
    -- A 01:09 glass of milk belongs to the day that has not yet ended.
    day_rollover_hour smallint NOT NULL DEFAULT 4,
    locale_units      text NOT NULL DEFAULT 'metric',
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- The learned vocabulary. Once "yopro" resolves once, it never costs a token
-- again. This table is why the system gets cheaper the longer it runs.
CREATE TABLE food_alias (
    id           bigserial PRIMARY KEY,
    user_id      bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    alias        text NOT NULL,
    fdc_id       integer NOT NULL REFERENCES food,
    default_grams numeric,
    hits         integer NOT NULL DEFAULT 0,
    last_used_at timestamptz,
    -- A pinned alias was checked by a human against the USDA row and is never
    -- re-resolved, re-guessed, or overwritten by a later parse. Pin your forty
    -- most-eaten foods once and the resolver stops being a source of error for
    -- ~90% of what you eat.
    pinned       boolean NOT NULL DEFAULT false,
    verified_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, alias)
);
CREATE INDEX food_alias_trgm ON food_alias USING gin (alias gin_trgm_ops);

-- ------------------------------------------------------------------ dishes
-- A dish is a named, reusable composite. Every confirmed novel parse becomes
-- one. This is the substrate for the repeat DSL.

CREATE TABLE dish (
    id             bigserial PRIMARY KEY,
    user_id        bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    slug           text NOT NULL,
    name           text NOT NULL,
    default_slot   text,                 -- breakfast | lunch | dinner | snack
    times_logged   integer NOT NULL DEFAULT 0,
    last_logged_at timestamptz,
    archived       boolean NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, slug)
);
CREATE INDEX dish_recent ON dish (user_id, last_logged_at DESC NULLS LAST);
CREATE INDEX dish_name_trgm ON dish USING gin (name gin_trgm_ops);

CREATE TABLE dish_component (
    id           bigserial PRIMARY KEY,
    dish_id      bigint NOT NULL REFERENCES dish ON DELETE CASCADE,
    position     smallint NOT NULL DEFAULT 0,
    fdc_id       integer NOT NULL REFERENCES food,
    label        text NOT NULL,          -- what you call it: "onion", "rice"
    grams        numeric NOT NULL,
    state        text NOT NULL DEFAULT 'as_logged',  -- raw | cooked | as_logged
    -- Cooked weight / raw weight. Where most real-world error lives: 100 g raw
    -- mince is not 100 g cooked mince, and USDA rows differ on which they mean.
    yield_factor numeric NOT NULL DEFAULT 1.0,
    optional     boolean NOT NULL DEFAULT false
);
CREATE INDEX dish_component_dish ON dish_component (dish_id, position);

-- A meal template is an ordered set of dishes: "breakfast" = 3 dishes.
CREATE TABLE meal_template (
    id       bigserial PRIMARY KEY,
    user_id  bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    slug     text NOT NULL,             -- 'b', 'breakfast', 'shake'
    name     text NOT NULL,
    slot     text,
    UNIQUE (user_id, slug)
);

CREATE TABLE meal_template_item (
    id              bigserial PRIMARY KEY,
    template_id     bigint NOT NULL REFERENCES meal_template ON DELETE CASCADE,
    dish_id         bigint NOT NULL REFERENCES dish ON DELETE CASCADE,
    position        smallint NOT NULL DEFAULT 0,
    grams_override  numeric
);

-- -------------------------------------------------------------------- log

CREATE TABLE log_entry (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    logged_at     timestamptz NOT NULL DEFAULT now(),
    local_date    date NOT NULL,          -- after day_rollover_hour shift
    slot          text,
    dish_id       bigint REFERENCES dish ON DELETE SET NULL,
    name          text NOT NULL,
    total_grams   numeric,
    source        text NOT NULL,          -- photo | text | repeat | template | barcode | manual
    confidence    numeric,                -- 0..1, from the parser
    model         text,                   -- null on zero-token paths
    parse         jsonb,                  -- raw structured parse, for audit
    photo_file_id text,
    status        text NOT NULL DEFAULT 'pending',  -- pending | confirmed | discarded
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT log_entry_status_ck CHECK (status IN ('pending','confirmed','discarded'))
);
CREATE INDEX log_entry_day ON log_entry (user_id, local_date) WHERE status = 'confirmed';
CREATE INDEX log_entry_pending ON log_entry (user_id, status) WHERE status = 'pending';

CREATE TABLE log_component (
    id           bigserial PRIMARY KEY,
    entry_id     bigint NOT NULL REFERENCES log_entry ON DELETE CASCADE,
    position     smallint NOT NULL DEFAULT 0,
    fdc_id       integer NOT NULL REFERENCES food,
    label        text NOT NULL,
    grams        numeric NOT NULL,
    state        text NOT NULL DEFAULT 'as_logged',
    yield_factor numeric NOT NULL DEFAULT 1.0,
    -- scale | stated | package | prior | estimate
    grams_source text NOT NULL DEFAULT 'estimate',
    -- 1-sigma uncertainty on the mass, in grams. Zero-ish when weighed, large
    -- when eyeballed. Propagated into the day's totals so a summary built on
    -- guesses cannot present itself as if it were built on measurements.
    grams_sigma  numeric NOT NULL DEFAULT 0
);
CREATE INDEX log_component_entry ON log_component (entry_id, position);
-- Drives the portion prior: your own weighed history for a given food.
CREATE INDEX log_component_history ON log_component (fdc_id, grams_source);

-- Immutable nutrient snapshot. ~80 rows per entry; ~250k rows/year. Trivial.
CREATE TABLE log_nutrient (
    entry_id    bigint NOT NULL REFERENCES log_entry ON DELETE CASCADE,
    nutrient_id integer NOT NULL REFERENCES nutrient,
    amount      numeric NOT NULL,
    PRIMARY KEY (entry_id, nutrient_id)
);

-- ---------------------------------------------------------------- targets
-- Versioned, never overwritten. An improvement plan appends rows with a future
-- effective_from; the old row gets effective_to. Your target history stays
-- honest, which is the only way "am I actually improving" is answerable.

CREATE TABLE target (
    id             bigserial PRIMARY KEY,
    user_id        bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    nutrient_id    integer NOT NULL REFERENCES nutrient,
    min_amount     numeric,
    max_amount     numeric,
    period         text NOT NULL DEFAULT 'day',   -- day | week
    effective_from date NOT NULL,
    effective_to   date,
    rationale      text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT target_bounds_ck CHECK (min_amount IS NOT NULL OR max_amount IS NOT NULL)
);
CREATE UNIQUE INDEX target_active ON target (user_id, nutrient_id, period)
    WHERE effective_to IS NULL;

-- Non-food context. Weight, body fat, blood markers, sleep, whatever.
CREATE TABLE body_metric (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    measured_at timestamptz NOT NULL DEFAULT now(),
    local_date  date NOT NULL,
    kind        text NOT NULL,        -- weight_kg | bodyfat_pct | glucose_mmol | bp_systolic ...
    value       numeric NOT NULL,
    note        text
);
CREATE INDEX body_metric_day ON body_metric (user_id, kind, local_date DESC);

CREATE TABLE activity (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    local_date  date NOT NULL,
    kind        text NOT NULL,        -- lifting | cycling | rest | walk
    minutes     integer,
    kcal_burned numeric,
    note        text
);
CREATE INDEX activity_day ON activity (user_id, local_date);

-- ---------------------------------------------------------- notifications
-- Evaluated in SQL against log_nutrient. No model is ever called to decide
-- whether to notify, or to write the notification text.

CREATE TABLE notification_rule (
    id               bigserial PRIMARY KEY,
    user_id          bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    kind             text NOT NULL,      -- threshold | scheduled | streak
    nutrient_id      integer REFERENCES nutrient,
    direction        text,               -- over | under
    threshold_pct    numeric,            -- 80 = fire at 80% of target
    at_time          time,               -- for kind='scheduled'
    cooldown_minutes integer NOT NULL DEFAULT 240,
    enabled          boolean NOT NULL DEFAULT true,
    template         text                -- optional override of the default text
);

CREATE TABLE notification_log (
    id         bigserial PRIMARY KEY,
    rule_id    bigint NOT NULL REFERENCES notification_rule ON DELETE CASCADE,
    user_id    bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    local_date date NOT NULL,
    sent_at    timestamptz NOT NULL DEFAULT now(),
    payload    jsonb
);
CREATE INDEX notification_log_recent ON notification_log (rule_id, local_date, sent_at DESC);

-- --------------------------------------------------------- observability
-- Every model call is priced and stored. You cannot optimise a cost you do
-- not measure, and you cannot trust a parser whose failures you never see.

CREATE TABLE llm_call (
    id                  bigserial PRIMARY KEY,
    user_id             bigint REFERENCES app_user ON DELETE SET NULL,
    entry_id            bigint REFERENCES log_entry ON DELETE SET NULL,
    purpose             text NOT NULL,   -- photo_parse | text_parse | disambiguate | modifier | plan
    model               text NOT NULL,
    input_tokens        integer NOT NULL DEFAULT 0,
    output_tokens       integer NOT NULL DEFAULT 0,
    cache_read_tokens   integer NOT NULL DEFAULT 0,
    cache_write_tokens  integer NOT NULL DEFAULT 0,
    latency_ms          integer,
    cost_usd            numeric(12,6) NOT NULL DEFAULT 0,
    ok                  boolean NOT NULL DEFAULT true,
    error               text,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX llm_call_day ON llm_call (user_id, created_at DESC);

-- Short-lived state for the human approval gate and for numbered menus, so
-- callback payloads stay under Telegram's 64-byte limit.
CREATE TABLE pending_action (
    id         bigserial PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    kind       text NOT NULL,          -- confirm_entry | repeat_menu | plan_proposal
    payload    jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now() + interval '2 hours'
);
CREATE INDEX pending_action_user ON pending_action (user_id, kind, created_at DESC);
