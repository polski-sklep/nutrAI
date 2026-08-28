-- A global vocabulary layer, separate from the per-user alias cache.
--
-- `food_alias.user_id` is NOT NULL and correctly so: an alias records what
-- THIS user's food resolved to last time. It is a cache. General knowledge --
-- "guanciale is cured pork jowl", "kebab is spelled kabob in USDA" -- is not
-- a cache and had nowhere to live, so every user rediscovers it and pays the
-- model tier for it. That is the gap docs/knowledge/RECONCILED-KNOWLEDGE.md
-- section 3.1 names.
--
-- Measured over 6,000+ probed terms across fifteen cuisines: roughly a third
-- of realistic food names return NOTHING at all -- not a weak match, nothing --
-- and only a `none` verdict genuinely starves the model tier, because
-- resolve_items escalates a weak match with its candidate list intact. The
-- eight commonest Polish food words (chleb, maslo, jajko, mleko, ser,
-- kurczak, wolowina, ryz) are all `none`. So is `kebab`, which USDA spells
-- `kabob` in all nine of its rows, breaking Persian, Turkish, Levantine,
-- Afghan and Uyghur queries with one token.
CREATE TABLE IF NOT EXISTS food_synonym (
    id          bigserial PRIMARY KEY,
    -- What a person types, lowercased and diacritic-folded on the way in, so
    -- lookup matches db.fold_query's output exactly.
    surface     text    NOT NULL,
    -- The phrase to ALSO search on. Text rather than a row id, because the
    -- most valuable entries are translations and spellings where no single row
    -- is the answer: `chleb` means "bread", and picking one bread row to point
    -- at would encode a bias -- Polish bread is rye, and USDA has no Bread, NFS,
    -- so the nearest handle is Bread, white. That is the culturally-wrong
    -- mapping the critics caught elsewhere (brown bread -> Bread, Boston Brown),
    -- committed on purpose. Expanding to the word instead lets the ordinary
    -- ranking pick the row, which is the whole point of expanding rather than
    -- deciding.
    expands_to  text    NOT NULL,
    -- Optional, and provenance only: the row this was verified against, so a
    -- later reader can check the claim rather than trust it. Never read by the
    -- resolver.
    fdc_id      integer REFERENCES food(fdc_id) ON DELETE SET NULL,
    -- synonym  : a different name for the same food (guanciale / cured pork jowl)
    -- spelling : the same name written differently (kebab / kabob, yoghurt / yogurt)
    -- regional : the same word meaning a different food by region (jelly)
    -- synonym    : another name for the same food (guanciale / cured pork jowl)
    -- spelling   : the same name written differently (kebab / kabob)
    -- translation: another language's word for it (chleb / bread)
    -- regional   : the same word naming a different food by region (jelly)
    relation    text    NOT NULL
        CHECK (relation IN ('synonym','spelling','translation','regional')),
    -- high may pre-empt; medium only ever contributes a search term. Nothing
    -- low-confidence is stored -- a refusal belongs in the critique files with
    -- its reason, not in a table something might later read as fact.
    confidence  text    NOT NULL CHECK (confidence IN ('high','medium')),
    source      text    NOT NULL,
    note        text,
    -- Corrected rather than deleted, for the same reason food.retired_at
    -- exists: a mapping that turned out wrong is history worth keeping, and
    -- the resolver must simply stop offering it.
    retired_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (surface, expands_to)
);

CREATE INDEX IF NOT EXISTS food_synonym_surface
    ON food_synonym (surface) WHERE retired_at IS NULL;

COMMENT ON TABLE food_synonym IS
  'Global food vocabulary. Expands the query; never decides the match.';
COMMENT ON COLUMN food_synonym.confidence IS
  'high may pre-empt the ranking; medium only adds a search term.';
