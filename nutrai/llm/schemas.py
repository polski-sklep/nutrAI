"""Tool schemas and the system prompts that go with them.

The contract, stated once so it cannot drift: the model returns identity, mass
and confidence. It never returns a calorie, a gram of protein, or any other
nutrient value. Those come from USDA via SQL. A model that is not asked to
estimate nutrition cannot hallucinate nutrition.
"""

from __future__ import annotations

PARSE_TOOL = {
    "name": "record_meal",
    "description": (
        "Record the identified food items and their masses. Do NOT estimate calories "
        "or any nutrient value; a nutrition database supplies those downstream."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "dish_name": {
                "type": "string",
                "description": "Short human name for the whole plate, e.g. 'beef stir-fry with rice'.",
            },
            "slot": {
                "type": "string",
                "enum": ["breakfast", "lunch", "dinner", "snack", "drink"],
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "description": "The ingredient as a person would name it: 'minced beef', 'jasmine rice', 'olive oil'.",
                        },
                        "search_terms": {
                            "type": "string",
                            "description": "A precise phrase for looking this up in USDA FoodData Central, e.g. 'beef, ground, 15% fat, raw'. Include the cut, fat percentage, and preparation if visible.",
                        },
                        "grams": {"type": "number", "description": "Best point estimate of mass in grams."},
                        "grams_low": {
                            "type": "number",
                            "description": "Low end of a plausible range, in grams. Required whenever grams_source is 'estimate'. Make this a real interval you would bet on, not a decoration around your point estimate: a plated portion you cannot weigh is routinely 30-40% either side.",
                        },
                        "grams_high": {
                            "type": "number",
                            "description": "High end of the plausible range, in grams.",
                        },
                        "grams_source": {
                            "type": "string",
                            "enum": ["scale", "stated", "package", "estimate", "reference_object"],
                            "description": "How the mass was determined. Use 'scale' ONLY if a scale display is legible in the photo; report the digits you read in `notes`.",
                        },
                        "state": {
                            "type": "string",
                            "enum": ["raw", "cooked", "dry", "as_sold", "unknown"],
                            "description": "The state the mass refers to. Cooked and raw masses differ by up to 35% for meat and 200%+ for rice and pasta. Getting this wrong is the largest error source in the system.",
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["label", "search_terms", "grams", "grams_source", "state", "confidence"],
                },
            },
            "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "notes": {
                "type": "string",
                "description": "Anything that materially affects accuracy: unreadable scale, hidden ingredients, obscured portion, sauce of unknown composition. Be blunt and brief — one or two sentences, 200 characters at the outside. An empty string is fine and is the right answer for a clearly weighed single ingredient.",
            },
        },
        "required": ["dish_name", "items", "overall_confidence"],
    },
}

PARSE_SYSTEM = """You convert a description or photograph of a meal into a list of ingredients with masses.

Rules, in priority order:
1. Never output a calorie or nutrient figure. You output identity, mass, state and confidence only.
2. If a kitchen scale display is visible, read the digits and use that number with grams_source='scale'. This is the most accurate signal available; prefer it over every visual estimate. State in `notes` what digits you read.
3. If the user states a mass in text, use it with grams_source='stated'. Trust the user over the photograph.
4. State matters as much as mass, but the question is what was *weighed*, not what was eaten. 100 g of dry rice becomes ~250 g cooked; 100 g of raw mince becomes ~70 g cooked. Nobody eats raw rice, so 'raw or cooked?' is never the question — 'was that 400 g on the scale before or after cooking?' is. Default to the food as served: a description of a meal refers to what was on the plate unless the user says 'dry', 'raw' or 'uncooked'. Reserve 'unknown' for a real ambiguity you cannot resolve, and never write an assumption into `notes` while setting state to 'unknown' — if you assumed it, record it.
5. Break composite dishes into ingredients only where the split is visible or stated. If you cannot see how much butter is in the mash, do not invent a number: report the dish as one item with a search term for the composite, and say so in `notes`.
6. Calibrate confidence honestly, against what is actually uncertain. Masses the user stated in text are not in doubt — they were there and you were not — so when every mass is stated or read off a scale, confidence reflects only whether you identified the foods correctly, and 0.85 to 0.95 is the honest range. Reserve 0.4 to 0.6 for what it is for: a plated mixed dish photographed from above with no scale and no stated masses. Overconfidence corrupts weeks of trend data; reflex under-confidence is its own failure, because a warning attached to every meal is a warning nobody reads.
7. Cooking fat and oil absorbed during cooking are real and routinely forgotten. If a dish is visibly fried or glossy, include an oil item and mark grams_source='estimate'.
8. Be terse. Output tokens are the dominant cost of this call and prose in `notes` is charged at five times the rate of the image you are reading. State what affects accuracy and stop; do not restate what the item list already says.
9. Whenever grams_source is 'estimate', give grams_low and grams_high as a genuine interval. A point estimate with no range asserts a precision the photograph does not contain. Use visible reference objects to narrow it: a standard dinner plate is 26-28 cm across, a dinner fork is 19-20 cm, a chicken egg is 55-60 g, a slice of sandwich bread is 35-40 g."""

DISAMBIGUATE_TOOL = {
    "name": "choose_food",
    "description": "Pick the best-matching database row for each ingredient from the supplied candidates.",
    "input_schema": {
        "type": "object",
        "properties": {
            "choices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        # Results are matched back by index, not by label. The
                        # label is free text the model re-types, and it reliably
                        # echoes more of the prompt line than just the name —
                        # "pickle (dill gherkin) (logged as as_sold, 45 g)" —
                        # which silently loses a correct match on lookup.
                        "index": {"type": "integer", "description": "The [n] of the item this choice is for."},
                        "label": {"type": "string"},
                        "fdc_id": {"type": "integer", "description": "Chosen candidate's fdc_id, or 0 if none is acceptable."},
                        "yield_factor": {
                            "type": "number",
                            "description": "Multiply the logged mass by this to get the mass of the chosen database row as described. 1.0 if they match. Example: logged 200 g cooked mince, chosen row is raw mince -> 1.33. Logged 100 g dry pasta, chosen row is cooked pasta -> 2.4.",
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["index", "label", "fdc_id", "yield_factor", "confidence"],
                },
            }
        },
        "required": ["choices"],
    },
}

DISAMBIGUATE_SYSTEM = """You map ingredient names to rows in USDA FoodData Central.

Each item is numbered [1], [2], .... Return the matching `index` for every item you were given.

Prefer Foundation and SR Legacy rows over Branded rows unless a specific brand was named. Prefer the row whose preparation state matches the logged state; when it does not match, set yield_factor to convert.

Choosing nothing is not the safe option. An unmatched ingredient is dropped from the meal entirely and contributes zero of every nutrient — a 100% error on that item, invisible in the total. A near neighbour of the same food is usually a few percent out. So:

- Match when a candidate is the same food in a different variety, cut, brand or preparation. "Salami, Italian, pork and beef" is a match for Italian salami. "Pickles, cucumber, dill or kosher dill" is a match for a dill gherkin. Set confidence to reflect the distance — 0.6 for a near neighbour is honest and useful.
- Return fdc_id 0 only when no candidate is the same food at all, or when the candidates are so different that a wrong nutrient profile would be worse than nothing. A cut of beef offered for a slice of bread is a refusal; a different fat percentage of the same mince is not."""

MODIFIER_TOOL = {
    "name": "modify_dish",
    "description": "Translate a free-text change to a known dish into explicit component edits.",
    "input_schema": {
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "enum": ["set", "add", "drop", "scale_all"]},
                        "label": {"type": "string"},
                        "grams": {"type": "number"},
                        "factor": {"type": "number"},
                    },
                    "required": ["op"],
                },
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["operations", "confidence"],
    },
}

MODIFIER_SYSTEM = """You are given the component list of a dish the user has eaten before, and a short phrase describing how today's version differed. Emit explicit edits. Use only labels that appear in the supplied component list, except for 'add'. Do not restate unchanged components."""

PLAN_TOOL = {
    "name": "propose_plan",
    "description": "Propose numbered dietary changes and the concrete target edits that implement them.",
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "description": "What the data actually shows. Ranked by size of effect, not by ease of fixing.",
                "items": {
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string"},
                        "evidence": {"type": "string", "description": "Cite the numbers from the evidence pack. No number, no finding."},
                        "confidence": {"type": "string", "enum": ["high", "moderate", "low"]},
                    },
                    "required": ["statement", "evidence", "confidence"],
                },
            },
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer"},
                        "action": {"type": "string", "description": "One specific behavioural change. 'Eat more fibre' is useless. 'Add 40 g of oats to the morning yoghurt' is a recommendation."},
                        "expected_effect": {"type": "string"},
                        "target_changes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "nutrient_id": {"type": "integer"},
                                    "min_amount": {"type": "number"},
                                    "max_amount": {"type": "number"},
                                    "rationale": {"type": "string"},
                                },
                                "required": ["nutrient_id"],
                            },
                        },
                        "risk": {"type": "string", "description": "What could go wrong or what this trades off. Say 'none identified' only if that is true."},
                    },
                    "required": ["n", "action", "expected_effect", "risk"],
                },
            },
            "what_the_data_cannot_tell_you": {
                "type": "string",
                "description": "Coverage gaps, short windows, unlogged days, micronutrients with poor database coverage.",
            },
        },
        "required": ["findings", "recommendations", "what_the_data_cannot_tell_you"],
    },
}

PLAN_SYSTEM = """You are reviewing a person's own nutrition log against their own stated targets.

You are given an evidence pack of medians, target comparisons and coverage figures. Work only from it. Do not invent numbers, do not assume unlogged days were typical, and do not soften a finding because it is unwelcome.

Rank findings by magnitude of effect. State confidence explicitly. Where database coverage for a micronutrient is poor, say so rather than reporting a deficiency that is really a measurement gap — this is the most common way micronutrient tracking misleads people.

Every recommendation must be a concrete, executable change to what is eaten, and must name the target edits that implement it. Include the trade-off. If the data supports no change, say so and recommend nothing."""


# --------------------------------------------------------------- supplements

SUPPLEMENT_TOOL = {
    "name": "read_supplement_label",
    "description": (
        "Transcribe the nutrition panel of every supplement described. Report only "
        "what the source states. Do not supply typical values from memory."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "supplements": {
                "type": "array",
                "description": "One entry per distinct product. A photo of one packet gives one; a written list may give several.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "What the supplement IS, not what it is sold as. 'Chelated Magnesium', 'Zinc', 'Omega 3', 'Creatine'. No brand, no dose, no marketing series name — those go in `brand` and `serving_desc`.",
                        },
                        "brand": {"type": "string", "description": "Manufacturer or range: 'Solgar', 'HSN EssentialSeries'."},
                        "serving_desc": {
                            "type": "string",
                            "description": "The serving the panel is stated per, as printed: '1 capsule', '2 capsules', '1 scoop (5 g)'.",
                        },
                        "servings_per_day": {
                            "type": "number",
                            "description": "Servings in the stated daily dose. 1 if not given.",
                        },
                        "nutrients": {
                            "type": "array",
                            "description": "Only lines that map to a nutrient id you were given. Omit anything else — do not approximate onto a neighbouring nutrient.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "nutrient_id": {"type": "integer", "description": "Must be one of the ids supplied. Never invent one."},
                                    "printed_label": {"type": "string", "description": "The line as stated, e.g. 'elemental zinc as bisglycinate'."},
                                    "amount": {"type": "number", "description": "The number as stated, per serving."},
                                    "unit": {"type": "string", "enum": ["g", "mg", "ug", "mcg", "iu", "kcal"]},
                                },
                                "required": ["nutrient_id", "printed_label", "amount", "unit"],
                            },
                        },
                        "schedule": {
                            "type": "string",
                            "enum": ["daily", "alternate", "occasional"],
                            "description": "How often it is taken. 'alternate' for every other day. Default 'daily' if the source does not say.",
                        },
                        "note": {
                            "type": "string",
                            "description": "Anything about how it is actually taken that the panel does not say: 'with the largest fat-containing meal', 'before sleep', a dose that differs from the label serving.",
                        },
                        "not_tracked": {
                            "type": "string",
                            "description": "Actives with no nutrient id — ashwagandha, CoQ10, collagen, curcumin, alpha-GPC. Name them so the user can see they were read and deliberately not counted.",
                        },
                    },
                    "required": ["name", "serving_desc", "nutrients"],
                },
            },
            "unreadable": {"type": "string", "description": "Anything you could see but not read. Empty string if none."},
        },
        "required": ["supplements"],
    },
}

SUPPLEMENT_SYSTEM = """You transcribe a supplement's nutrition panel from a photograph.

This is transcription, not estimation. The difference matters more here than anywhere else in this system: every other number a model produces here is an identity or a mass that a human then checks against a plate, but these numbers go straight into a daily total. So:

1. Report only what is printed on the label in the photograph. If you happen to know what this product usually contains, that knowledge is not evidence and must not appear in the output.
2. Do not convert units. Report the number and the unit exactly as printed; 'ug' and 'mcg' both mean micrograms and either is fine.
3. Use only the nutrient ids supplied to you. A panel line with no id in that list is omitted, not approximated onto a neighbouring nutrient. Vitamin B6 is not vitamin B12.
4. If a digit is unclear, put the line in `unreadable` rather than guessing it. A wrong digit in a supplement panel is a wrong daily total every day thereafter, silently, until somebody notices.
5. Amounts are per serving as the panel states them, not per daily dose, unless the panel only gives a daily dose — in which case set serving_desc to that dose.
6. Where a line gives both a compound weight and an elemental weight — "82 mg zinc gluconate, of which 10 mg elemental zinc", "1667 mg magnesium bisglycinate providing 350 mg elemental magnesium" — record the elemental figure. That is what the body receives and what a nutrient target is expressed in; the compound weight is several times larger and recording it would overstate the dose by that factor.
7. Many supplement actives have no nutrient id here: ashwagandha, CoQ10, collagen, curcumin, alpha-GPC, piperine, hyaluronic acid. Name them in `not_tracked` rather than omitting them silently, so the user can see they were read and deliberately not counted.
8. The source may be a photograph of one packet or a written description of several products. Return one entry per distinct product either way.
9. The dose someone takes is not always the label's serving. "Magnesium 175 mg, 1 capsule" against a panel stating 350 mg per 2-capsule serving means half a serving: set servings_per_day to 0.5 and leave the per-serving amounts as printed. Getting this backwards doubles the recorded dose every day.
10. Record cadence where the source gives it. "Zinc 22 mg, every other day" is schedule 'alternate', not 'daily'. Assuming daily overstates a nutrient by half, permanently, and nothing downstream can detect it."""
