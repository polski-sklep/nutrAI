-- A slice of a tray you baked.
--
-- `/food` builds a per-100 g panel from an ingredient list, which is right,
-- and then leaves you to weigh every serving of it for ever. For a tray bake
-- that is the wrong unit twice over: you weighed the tray once, cut it into
-- sixteen, and every slice after that is arithmetic — not something to
-- estimate by eye each time.
--
-- `food_portion` already exists and holds exactly this (USDA ships 40,000-odd
-- rows of it), but nothing in the bot has ever read it and USDA's own ids are
-- positive. User portions get negative ids from their own sequence, the same
-- convention `food.fdc_id` already uses, so the loader and this can never
-- collide.
CREATE SEQUENCE IF NOT EXISTS user_portion_id_seq START 1;

-- One declared portion per food. A second "makes 16 slices" for the same
-- blondie is a correction, not an additional fact, and without this it would
-- silently become two rows and a coin toss over which one wins.
CREATE UNIQUE INDEX IF NOT EXISTS food_portion_user_one
    ON food_portion (fdc_id) WHERE id < 0;

-- What the tray weighed when it came out of the oven, kept beside the food it
-- describes. Not derivable from the portion: 16 slices of 53 g tells you the
-- tray was 850 g, but only if nobody ever edits one without the other.
ALTER TABLE food
    ADD COLUMN IF NOT EXISTS yield_grams numeric;

COMMENT ON COLUMN food.yield_grams IS
    'Finished mass of one batch, when stated. NULL means the per-100g panel '
    'was computed against the raw ingredient mass and does not account for '
    'water lost in cooking.';
