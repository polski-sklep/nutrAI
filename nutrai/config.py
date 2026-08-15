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
CONFIDENCE_ESCALATE = float(os.getenv("CONFIDENCE_ESCALATE", "0.75"))
# Atwater cross-check tolerance: |kcal_from_macros - kcal_from_db| / kcal_from_db
ENERGY_TOLERANCE = float(os.getenv("ENERGY_TOLERANCE", "0.12"))
# Trigram similarity above which a food match is accepted without a model call.
AUTO_MATCH_SIMILARITY = float(os.getenv("AUTO_MATCH_SIMILARITY", "0.62"))

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
]


@dataclass(frozen=True)
class Settings:
    database_url: str = DATABASE_URL
    telegram_token: str = TELEGRAM_TOKEN
    anthropic_api_key: str = ANTHROPIC_API_KEY
    tz: str = DEFAULT_TZ
    allowed_ids: frozenset[int] = field(default_factory=lambda: frozenset(ALLOWED_TELEGRAM_IDS))


settings = Settings()
