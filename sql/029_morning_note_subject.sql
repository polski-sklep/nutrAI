-- What the morning note talked about, so it can talk about something else.
--
-- The note names the worst breached ceiling, and a ceiling you are over every
-- day is the worst one every day: "fewer egg yolks" arrived every morning,
-- from a fixed table of advice, regardless of what was actually eaten. Advice
-- that repeats verbatim is advice you stop reading, and the fixed table made
-- it worse — it was not even a fact about yesterday.
ALTER TABLE morning_note_log
    ADD COLUMN IF NOT EXISTS subject_nutrient_id integer;
