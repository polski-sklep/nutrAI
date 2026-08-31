-- One honest figure per entry per nutrient, so an ad-hoc query cannot treble
-- the calories.
--
-- `log_nutrient` stores energy under 1008, 2047 and 2048 — 37 entries carry
-- all three — and they are *alternative estimates of one quantity*, not
-- components of it. The obvious query is
--
--     SELECT sum(amount) WHERE nutrient_id IN (1008, 2047, 2048)
--
-- and it is wrong by roughly 165%. It was written on 31 Aug 2026, by the
-- author of the comment in CLAUDE.md warning against it, and reported a day
-- as 2,632 kcal when the bot had always shown 2,287. Nothing in the data
-- looked odd: every number was real and the total was plausible.
--
-- Two different relationships between nutrient ids live in this schema and the
-- distinction is the whole point:
--
--   canonical_id  "the same measurement, add them up"  (1063 sugars -> 2000)
--   Atwater       "alternative estimates, use one"     (1008 / 2047 / 2048)
--
-- `v_nutrient_canonical` covers the first and deliberately does not cover the
-- second. This view covers the second, in the one place where a reader can
-- reach for it instead of getting it wrong by hand.

CREATE OR REPLACE VIEW v_entry_nutrient AS
WITH folded AS (
    -- The canonical fold first: FNDDS reports sugar under 1063 and SR Legacy
    -- under 2000, and those really do add up.
    SELECT ln.entry_id,
           c.canonical_id AS nutrient_id,
           sum(ln.amount) AS amount
      FROM log_nutrient ln
      JOIN v_nutrient_canonical c ON c.id = ln.nutrient_id
     GROUP BY ln.entry_id, c.canonical_id
),
energy AS (
    -- Whichever exists, in order of preference, and never the sum. 1008 is
    -- present on every logged entry today because `normalise_energy` writes
    -- it, but 218 USDA rows carry only 2047 or 2048 — so the preference is
    -- expressed rather than assumed.
    SELECT DISTINCT ON (entry_id)
           entry_id, 1008 AS nutrient_id, amount
      FROM folded
     WHERE nutrient_id IN (1008, 2047, 2048)
     ORDER BY entry_id, array_position(ARRAY[1008, 2047, 2048], nutrient_id)
)
SELECT e.id          AS entry_id,
       e.user_id,
       e.local_date,
       e.status,
       x.nutrient_id,
       n.name        AS nutrient_name,
       n.unit,
       n.is_core,
       x.amount
  FROM log_entry e
  JOIN (SELECT * FROM folded WHERE nutrient_id NOT IN (1008, 2047, 2048)
        UNION ALL
        SELECT * FROM energy) x ON x.entry_id = e.id
  JOIN nutrient n ON n.id = x.nutrient_id;

-- Food only. Supplements live in their own tables and reach a day total
-- through `day_progress`, which keeps `amount_food` and `amount_supplement`
-- apart on purpose — a micronutrient met by a capsule is different information
-- from one met by food. So this view read across a day is 20 kcal short of the
-- day card on 25 Aug 2026, and that gap is the capsules, not an error.

COMMENT ON VIEW v_entry_nutrient IS
  'One amount per entry per nutrient. Sugars folded (1063 -> 2000); energy '
  'resolved to a single 1008 by preference, never summed. Prefer this over '
  'log_nutrient for any query you write by hand.';
