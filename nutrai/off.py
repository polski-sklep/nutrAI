"""OpenFoodFacts lookup, for the branded products USDA does not carry.

A third source, with a third level of authority, and the code says which is
which. USDA rows are laboratory assays. A label you photographed is a printed
panel you were holding. OpenFoodFacts is *crowd-sourced*: anyone may edit it,
completeness varies enormously between products, and a well-populated entry
sits beside one where somebody typed the energy in the wrong unit.

So nothing here is saved without being shown first, every product keeps the
barcode it came from, and the card says where the numbers are from. This is
still a lookup rather than an estimate — no model is involved, and ARCHITECTURE
§1 is untouched — but "looked it up" and "measured it" are different claims.

aiohttp because aiogram already depends on it. No new dependency.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

log = logging.getLogger("nutrai.off")

BASE = "https://world.openfoodfacts.org"
# Free-text search moved here; the old /cgi/search.pl endpoint answers 503
# under any load and is kept alive for compatibility, not for use.
SEARCH = "https://search.openfoodfacts.org"
# OFF asks every client to identify itself, and rate-limits those that do not.
USER_AGENT = "nutrai/0.1 (personal nutrition log; single user)"
TIMEOUT = aiohttp.ClientTimeout(total=8)

# OFF nutriment key -> (USDA nutrient id, multiplier to the USDA unit).
#
# OFF reports per 100 g in grams for most things; USDA wants mg for minerals
# and µg for some vitamins. Anything not listed is dropped rather than guessed
# at — a panel missing selenium is missing it, and inventing a zero would be
# the phantom-deficiency bug arriving from a new direction.
FIELDS: dict[str, tuple[int, float]] = {
    "energy-kcal_100g":  (1008, 1.0),
    "proteins_100g":     (1003, 1.0),
    "fat_100g":          (1004, 1.0),
    "carbohydrates_100g": (1005, 1.0),
    "fiber_100g":        (1079, 1.0),
    "sugars_100g":       (2000, 1.0),
    "saturated-fat_100g": (1258, 1.0),
    "sodium_100g":       (1093, 1000.0),      # g -> mg
    "calcium_100g":      (1087, 1000.0),      # g -> mg
    "iron_100g":         (1089, 1000.0),
    "magnesium_100g":    (1090, 1000.0),
    "zinc_100g":         (1095, 1000.0),
    "potassium_100g":    (1092, 1000.0),
    "vitamin-c_100g":    (1162, 1000.0),
    "vitamin-b12_100g":  (1178, 1_000_000.0),  # g -> µg
    "vitamin-d_100g":    (1114, 1_000_000.0),
    "vitamin-a_100g":    (1106, 1_000_000.0),
    "cholesterol_100g":  (1253, 1000.0),
    "caffeine_100g":     (1057, 1000.0),
}


async def _get(session: aiohttp.ClientSession, url: str, **params) -> dict | None:
    try:
        async with session.get(url, params=params, timeout=TIMEOUT,
                               headers={"User-Agent": USER_AGENT}) as r:
            if r.status != 200:
                log.warning("openfoodfacts %s returned %s", url, r.status)
                return None
            return await r.json(content_type=None)
    except Exception as exc:
        log.warning("openfoodfacts %s failed: %s", url, exc)
        return None


def _panel(product: dict) -> tuple[dict[int, float], list[str]]:
    """(nutrient_id -> per 100 g, names of fields that were absent).

    The absences are returned rather than swallowed, because "this panel has
    no fibre figure" and "this product has no fibre" look identical in a
    stored row and mean completely different things.
    """
    nut = product.get("nutriments") or {}
    out: dict[int, float] = {}
    for key, (nid, mult) in FIELDS.items():
        v = nut.get(key)
        if v in (None, ""):
            continue
        try:
            out[nid] = float(v) * mult
        except (TypeError, ValueError):
            continue

    # Salt is often given where sodium is not. 2.5 g salt = 1 g sodium.
    if 1093 not in out and nut.get("salt_100g") not in (None, ""):
        try:
            out[1093] = float(nut["salt_100g"]) / 2.5 * 1000.0
        except (TypeError, ValueError):
            pass

    missing = [k.replace("_100g", "") for k, (nid, _m) in FIELDS.items()
               if nid not in out]
    return out, missing


def _first_brand(brands: Any) -> str:
    """The product API returns a comma-joined string, search returns a list."""
    if isinstance(brands, list):
        return str(brands[0]).strip() if brands else ""
    return str(brands or "").split(",")[0].strip()


def summarise(product: dict) -> dict[str, Any]:
    panel, missing = _panel(product)
    return {
        "barcode": str(product.get("code") or ""),
        "name": (product.get("product_name") or "").strip(),
        "brand": _first_brand(product.get("brands")),
        "quantity": (product.get("quantity") or "").strip(),
        "serving": (product.get("serving_size") or "").strip(),
        "panel": panel,
        "missing": missing,
        # OFF's own completeness score, 0-1. Worth showing: it is the site's
        # opinion of its own entry, and a 0.3 is a warning in the source's
        # own terms rather than in ours.
        "completeness": float(product.get("completeness") or 0),
        "url": f"{BASE}/product/{product.get('code')}",
    }


async def by_barcode(code: str) -> dict[str, Any] | None:
    async with aiohttp.ClientSession() as s:
        data = await _get(s, f"{BASE}/api/v2/product/{code}.json")
    if not data or data.get("status") != 1 or not data.get("product"):
        return None
    return summarise(data["product"])


async def search(terms: str, limit: int = 5) -> list[dict[str, Any]]:
    """Best matches by name, ordered as OFF returns them.

    Against search.openfoodfacts.org rather than the older /cgi/search.pl,
    which now answers 503 under any load — the legacy endpoint is retained
    for compatibility rather than for use. Ordering is OFF's own relevance,
    which is a better prior for "the thing in your cupboard" than string
    distance would be.
    """
    async with aiohttp.ClientSession() as s:
        data = await _get(s, f"{SEARCH}/search", q=terms, page_size=limit)
    if not data:
        return []
    out = []
    for hit in (data.get("hits") or [])[:limit]:
        summary = summarise(hit)
        # A product with no energy figure is not a usable panel, however well
        # it matches the name.
        if 1008 in summary["panel"]:
            out.append(summary)
    return out
