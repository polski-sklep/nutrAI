-- Phase 0 of the resolution rebuild: record what the resolver actually decided.
--
-- Nine specs converged on one blocker. Every threshold in this system is
-- untunable, and every claim about why a food matched is unfalsifiable, because
-- the deciding score is computed and thrown away. `docs/resolution/SPEC-7`
-- §7.4 and `SPEC-9` §6 both name this as the single change that has to land
-- before any other number is touched.
--
-- These are snapshots, for the same reason `grams_source` is one: they record
-- what was true when the component was written, not what the resolver would
-- decide about it today.

ALTER TABLE log_component
  -- 'alias' | 'own' | 'auto' | 'model' | 'repeat'. Which of the three tiers
  -- decided, or that the row was inherited from a dish without re-resolving.
  -- Established today only by the *absence* of a disambiguation call, which is
  -- reasoning available from reading the source and from nowhere in the data.
  ADD COLUMN IF NOT EXISTS match_tier text,

  -- Trigram similarity of the chosen row against the user's own words, and
  -- against the model's `search_terms`, kept apart.
  --
  -- `_candidates` pools both queries and ranks by whichever scored higher, so
  -- one number today means "the best any phrasing achieved" and cannot say
  -- which phrasing won. That matters more than it sounds: the model writes
  -- `search_terms` as a USDA-style description of the row it already believes
  -- in, so a high sim_model against a low sim_user is the model's own prior
  -- being scored as evidence for itself. On 25 Aug 2026 that mechanism logged
  -- an FNDDS porridge for a dry cereal while the user's own transcribed packet
  -- led 0.619 to 0.195 on his own words.
  ADD COLUMN IF NOT EXISTS sim_user numeric,
  ADD COLUMN IF NOT EXISTS sim_model numeric,

  -- The candidate that came second, and its score. A margin is the only honest
  -- input to a confidence figure, and it cannot be reconstructed afterwards
  -- because the candidate list is not kept anywhere.
  ADD COLUMN IF NOT EXISTS runner_up_fdc_id integer,
  ADD COLUMN IF NOT EXISTS runner_up_sim numeric;

COMMENT ON COLUMN log_component.match_tier IS
  'How this row was chosen: alias | own | auto | model | repeat. Snapshot.';
COMMENT ON COLUMN log_component.sim_user IS
  'Trigram similarity of the chosen row against the user''s label. Snapshot.';
COMMENT ON COLUMN log_component.sim_model IS
  'Trigram similarity against the model''s search_terms. Snapshot.';

-- The candidate list, kept out of log_component deliberately.
--
-- `replace_components` DELETEs component rows, so a `/fix` would destroy the
-- record of what it was fixing at the moment that record became interesting.
-- Keyed on entry_id with ON DELETE CASCADE so a discarded entry still carries
-- its resolution history, and a deleted one does not leak rows.
CREATE TABLE IF NOT EXISTS resolution_event (
    id            bigserial PRIMARY KEY,
    entry_id      bigint REFERENCES log_entry(id) ON DELETE CASCADE,
    position      smallint NOT NULL DEFAULT 0,
    label         text     NOT NULL,
    -- Every query that was searched on, in order, and every candidate any of
    -- them returned with its per-query scores. Ranking a pooled set by a max
    -- over heterogeneous queries compares numbers that are not on the same
    -- scale; nothing today can test that claim because the per-query scores
    -- are discarded inside `_candidates`.
    queries       jsonb    NOT NULL DEFAULT '[]'::jsonb,
    candidates    jsonb    NOT NULL DEFAULT '[]'::jsonb,
    chosen_fdc_id integer,
    match_tier    text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS resolution_event_entry ON resolution_event (entry_id, position);
