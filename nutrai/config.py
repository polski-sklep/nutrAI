from __future__ import annotations

import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------- models
# Pinned snapshots, not aliases. A model swapping under you mid-experiment is
# how you end up unable to explain a regression in parse accuracy.
MODEL_PHOTO = os.getenv("MODEL_PHOTO", "claude-sonnet-5")
MODEL_PHOTO_ESCALATE = os.getenv("MODEL_PHOTO_ESCALATE", "claude-opus-5")
MODEL_TEXT = os.getenv("MODEL_TEXT", "claude-sonnet-5")
MODEL_CHEAP = os.getenv("MODEL_CHEAP", "claude-haiku-4-5-20251001")
MODEL_PLAN = os.getenv("MODEL_PLAN", "claude-opus-5")

# USD per million tokens, from platform.claude.com/docs/en/about-claude/pricing
# (input, output). Cache read = 0.1x input; 5m cache write = 1.25x input.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}
CACHE_READ_MULT = 0.1
CACHE_WRITE_MULT = 1.25  # 5-minute TTL


def _check_models_are_priced(configured: dict[str, str] | None = None) -> None:
    """Fail at import if a routed model has no entry in PRICES.

    `price()` falls back to Sonnet's rate for an unknown model, which is the
    right behaviour there — raising inside it would abort a request whose API
    call has already been made and already been billed, losing the parse and
    the money both. But that fallback means a typo in a model id shows up only
    as a `/spend` figure that is quietly wrong, and cost accounting you cannot
    trust is the same as no cost accounting.

    So the check happens here, at import, before anything can be spent: the
    process refuses to start rather than misreporting for a month.

    Note this validates the *pricing table*, not the model id. Only
    `GET /v1/models` can tell you the id is real.
    """
    configured = configured or {
        "MODEL_PHOTO": MODEL_PHOTO,
        "MODEL_PHOTO_ESCALATE": MODEL_PHOTO_ESCALATE,
        "MODEL_TEXT": MODEL_TEXT,
        "MODEL_CHEAP": MODEL_CHEAP,
        "MODEL_PLAN": MODEL_PLAN,
    }
    missing = {name: mid for name, mid in configured.items() if mid not in PRICES}
    if missing:
        raise ValueError(
            "model id not present in config.PRICES, so its calls would be priced "
            "as Sonnet and /spend would be wrong: "
            + ", ".join(f"{name}={mid!r}" for name, mid in sorted(missing.items()))
            + ". Add it to PRICES, or correct the id."
        )


_check_models_are_priced()

# Downscale before upload. Claude bills ceil(w/28)*ceil(h/28) visual tokens.
# A stock Telegram 1280x960 photo costs 1610 visual tokens on a high-res-tier
# model; 896x672 costs 768 and loses nothing that matters for identifying a
# plate of food. Do not go below ~700px on the long edge if a scale readout
# needs to stay legible.
IMAGE_LONG_EDGE = int(os.getenv("IMAGE_LONG_EDGE", "896"))
IMAGE_JPEG_QUALITY = int(os.getenv("IMAGE_JPEG_QUALITY", "82"))

# ---------------------------------------------------------------- guardrails
# Below this, the parse is presented as a question, not as a result.
CONFIDENCE_FLOOR = float(os.getenv("CONFIDENCE_FLOOR", "0.60"))
# Below this on a photo, escalate to the larger model once before asking.
#
# Was 0.75, on the assumption that 20-30% of photos would escalate. Measured
# against real plates it fired on essentially all of them: PARSE_SYSTEM tells
# the model to report 0.4-0.6 for "a plated mixed dish photographed from above
# with no scale", which is what most photos are. So the escalation was not
# conditional in practice, it was routine, and it is 74% of the cost of a photo
# — 4.2p of a 5.6p parse.
#
# The first measured instance also lost: Opus ran, returned lower confidence
# than Sonnet, and its answer was discarded. That is docs/ARCHITECTURE.md §8's
# escalation-precision question answered once, in the negative. Once is not an
# eval set, so this is set low rather than to zero: Opus still runs when a parse
# is genuinely poor, not merely when the plate is a plate.
#
# Provisional. Score it properly at stage 4 and set it from the numbers.
CONFIDENCE_ESCALATE = float(os.getenv("CONFIDENCE_ESCALATE", "0.45"))
# Atwater cross-check tolerance: |kcal_from_macros - kcal_from_db| / kcal_from_db
ENERGY_TOLERANCE = float(os.getenv("ENERGY_TOLERANCE", "0.12"))
# Trigram similarity above which a food match is accepted without a model call.
AUTO_MATCH_SIMILARITY = float(os.getenv("AUTO_MATCH_SIMILARITY", "0.62"))
# Below this, the best candidate is probably not the food at all.
#
# "pickle juice" scored 0.35 against "Relish, pickle" — the top of a list that
# never contained pickle brine, because USDA has no row for it. A weak best
# match is usually a missing food rather than a mistaken choice, so it is worth
# offering to define one rather than only warning about the match.
#
# Deliberately well below AUTO_MATCH_SIMILARITY: this is not a second matching
# threshold, it is the point past which the database itself looks like the
# problem. Like 0.62 it is a guess until the eval set says otherwise.
WEAK_MATCH_SIMILARITY = float(os.getenv("WEAK_MATCH_SIMILARITY", "0.45"))

# ---------------------------------------------------------------- runtime
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nutrai:nutrai@localhost:5432/nutrai")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ALLOWED_TELEGRAM_IDS = {
    int(x) for x in os.getenv("ALLOWED_TELEGRAM_IDS", "").replace(" ", "").split(",") if x
}
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "Europe/Warsaw")
PHOTO_DIR = os.getenv("PHOTO_DIR", "/var/lib/nutrai/photos")

# ---------------------------------------------------------------- nutrients
# FDC nutrient ids. These are the internal `nutrient.id` values in the bulk
# CSV, which for the modern rows coincide with the INFOODS number.
ENERGY_KCAL = 1008
PROTEIN = 1003
FAT = 1004
CARB = 1005
FIBER = 1079
SUGAR = 2000
ALCOHOL = 1018
CAFFEINE = 1057
SAT_FAT = 1258
SODIUM = 1093

# Atwater factors, kcal per gram. Used only as a cross-check on the database,
# never as the source of the energy figure.
ATWATER = {PROTEIN: 4.0, CARB: 4.0, FAT: 9.0, ALCOHOL: 7.0, FIBER: -2.0}

# The compact set shown in a normal summary. Everything else is still stored
# and still queryable with /nutrient <name>; it just does not belong in a
# message you read six times a day.
CORE_NUTRIENTS: list[int] = [
    ENERGY_KCAL, PROTEIN, CARB, FAT, FIBER, SUGAR, SAT_FAT, SODIUM,
    1092,  # Potassium
    1087,  # Calcium
    1089,  # Iron
    1090,  # Magnesium
    1095,  # Zinc
    1178,  # Vitamin B-12
    1114,  # Vitamin D (D2 + D3)
    1162,  # Vitamin C
    1106,  # Vitamin A, RAE
    1177,  # Folate, food
    1253,  # Cholesterol
    1272,  # DHA 22:6 n-3
    1057,  # Caffeine — recorded by every coffee row in USDA and, until now,
           # never shown. 127 mg went into a day's log without a word.
    1018,  # Alcohol, ethyl — already counts toward energy via ATWATER, so it
           # was affecting the calorie total while being invisible on its own.
]


@dataclass(frozen=True)
class Settings:
    database_url: str = DATABASE_URL
    telegram_token: str = TELEGRAM_TOKEN
    anthropic_api_key: str = ANTHROPIC_API_KEY
    tz: str = DEFAULT_TZ
    allowed_ids: frozenset[int] = field(default_factory=lambda: frozenset(ALLOWED_TELEGRAM_IDS))


settings = Settings()
