from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

import asyncpg
from PIL import Image

from .. import db
from ..config import (
    AUTO_MATCH_SIMILARITY,
    WEAK_MATCH_SIMILARITY,
    CONFIDENCE_ESCALATE,
    ENERGY_KCAL,
    IMAGE_JPEG_QUALITY,
    IMAGE_LONG_EDGE,
    MODEL_CHEAP,
    MODEL_PHOTO,
    MODEL_PHOTO_ESCALATE,
    MODEL_TEXT,
)
from ..core.estimate import MEASURED_SOURCES, MassEstimate, choose_mass, sigma_for
from ..core.nutrition import ResolvedComponent, energy_cross_check, total_nutrients
from .client import ToolResult, cached, call_tool
from .schemas import (
    FOOD_LABEL_SYSTEM,
    FOOD_LABEL_TOOL,
    DISAMBIGUATE_SYSTEM,
    DISAMBIGUATE_TOOL,
    MODIFIER_SYSTEM,
    MODIFIER_TOOL,
    PARSE_SYSTEM,
    PARSE_TOOL,
    SUPPLEMENT_SYSTEM,
    SUPPLEMENT_TOOL,
)

log = logging.getLogger("nutrai")


# ------------------------------------------------------------------- images


def visual_tokens(w: int, h: int) -> int:
    return -(-w // 28) * -(-h // 28)


def prepare_image(raw: bytes, long_edge: int = IMAGE_LONG_EDGE) -> tuple[str, int, int]:
    """Downscale and re-encode before upload.

    Claude bills ceil(w/28) x ceil(h/28) visual tokens. A stock Telegram photo
    at 1280x960 is 1,610 visual tokens; the same photo at 896x672 is 768. The
    identification task does not improve above ~900 px for a plate of food, so
    the extra 842 tokens buy nothing. They do matter for a legible scale
    display, which is why the floor is 896 and not 448.
    """
    img = Image.open(io.BytesIO(raw))
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > long_edge:
        s = long_edge / max(w, h)
        img = img.resize((round(w * s), round(h * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True)
    return base64.standard_b64encode(buf.getvalue()).decode(), img.size[0], img.size[1]


# -------------------------------------------------------------------- parse


@dataclass
class ParsedMeal:
    dish_name: str
    slot: str | None
    items: list[dict[str, Any]]
    confidence: float
    notes: str
    model: str
    cost_usd: float
    raw: dict[str, Any]


async def parse_photo(
    images: list[str], caption: str | None, *, user_id: int,
    escalate: bool = True
) -> ParsedMeal:
    """Vision parse with one conditional escalation.

    Escalation is conditional on the model's own reported confidence rather
    than run always: on a clearly weighed single ingredient the small model is
    right and the large one costs 2.5x for nothing. On an ambiguous plate the
    escalation is the difference between a usable number and a guess.

    Every photo of one meal goes in one call. Parsing them separately and
    concatenating the results counted a drink twice: two photos of the same
    bottle produced "Coffee and orange juice drink, 330 g" and "Coffee &
    orange juice beverage, 330 g", and the day recorded 660 g and 61 g of
    sugar for a 330 ml drink. Nothing downstream can detect that — they are
    two plausible items with two plausible masses. The model can only avoid it
    if it sees the photographs together, which is also cheaper than a call
    each.
    """
    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        }
        for b64 in images
    ]
    if len(images) > 1:
        content.append({"type": "text", "text": (
            f"These {len(images)} photographs are of ONE meal, taken from "
            "different angles or at different moments. Report each food ONCE. "
            "A dish visible in more than one photograph is the same dish, not "
            "a second helping of it — use whichever view shows it best, and do "
            "not add the masses together.")})
    if caption:
        content.append({"type": "text", "text": f"The user says: {caption}"})

    res = await call_tool(
        model=MODEL_PHOTO, tool=PARSE_TOOL, system=[cached(PARSE_SYSTEM)], content=content
    )
    await _log(res, "photo_parse", user_id)

    # Cost is accumulated across both calls, not taken from whichever won.
    # `_to_meal` reads it off a single ToolResult, so an escalation that lost
    # was billed and then not shown: a card read 1.47p for a parse that actually
    # cost 5.63p. /spend was right the whole time, because llm_call records
    # every request — but the two disagreeing is worse than either being wrong,
    # since the card is the number you see six times a day.
    spent = res.cost_usd
    conf = float(res.data.get("overall_confidence", 0) or 0)
    if escalate and conf < CONFIDENCE_ESCALATE:
        res2 = await call_tool(
            model=MODEL_PHOTO_ESCALATE,
            tool=PARSE_TOOL,
            system=[cached(PARSE_SYSTEM)],
            content=content,
        )
        await _log(res2, "photo_parse_escalated", user_id)
        spent += res2.cost_usd
        if float(res2.data.get("overall_confidence", 0) or 0) > conf:
            res = res2

    meal = _to_meal(res)
    meal.cost_usd = spent
    return meal


async def parse_text(text: str, *, user_id: int) -> ParsedMeal:
    res = await call_tool(
        model=MODEL_TEXT,
        tool=PARSE_TOOL,
        system=[cached(PARSE_SYSTEM)],
        content=[{"type": "text", "text": text}],
    )
    await _log(res, "text_parse", user_id)
    return _to_meal(res)


def _to_meal(res: ToolResult) -> ParsedMeal:
    d = res.data
    return ParsedMeal(
        dish_name=d.get("dish_name", "meal"),
        slot=d.get("slot"),
        items=list(d.get("items", [])),
        confidence=float(d.get("overall_confidence", 0) or 0),
        notes=d.get("notes", "") or "",
        model=res.model,
        cost_usd=res.cost_usd,
        raw=d,
    )


# ---------------------------------------------------------------- resolution


@dataclass
class Resolution:
    components: list[ResolvedComponent]
    grams_sources: list[str]
    unresolved: list[str]
    cost_usd: float
    used_model: bool
    prior_notes: list[str] | None = None
    # Labels whose best candidate scored badly. USDA has ~13,600 rows and no
    # entry at all for a great many real foods — pickle brine, a local
    # bakery's bun — so a weak best match usually means the right answer was
    # never on the list, not that the wrong one was picked from it.
    weak_matches: list[tuple[str, float]] = field(default_factory=list)
    # Row ids in `resolution_event`, already written. `create_pending_entry`
    # sets their entry_id if this resolution becomes an entry; the ones that
    # do not are the record of what went wrong, which is the point.
    event_ids: list[int] = field(default_factory=list)


# "0.33 slice", "half a slice", "two slices" — read locally, not inferred.
#
# The schema asks the model to set `count` when a number of units is given, and
# on the first real use it did not: "0.33 slice of blondie" came back as a 30 g
# estimate with the note "standard slice assumed ~90g", which is a guess at a
# quantity the database already knew exactly (88 g). Asking the model more
# firmly would make that likelier, not certain, and the whole point of a
# declared portion is that it removes the guess. So the count is also read off
# the message directly, with the food's own unit word as the anchor.
_WORD_COUNTS = {"a": 1.0, "an": 1.0, "one": 1.0, "half": 0.5, "quarter": 0.25,
                "two": 2.0, "three": 3.0, "four": 4.0, "couple": 2.0}


def count_from_text(text: str | None, unit: str) -> float | None:
    """How many <unit> the message asks for, if it says so plainly."""
    if not text or not unit:
        return None
    pattern = (r"(\d+\s*/\s*\d+|\d+(?:[.,]\d+)?|" + "|".join(_WORD_COUNTS) + r")\s+"
               r"(?:of\s+)?(?:a\s+)?" + re.escape(unit) + r"s?\b")
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    tok = m.group(1).lower()
    if tok in _WORD_COUNTS:
        return _WORD_COUNTS[tok]
    if "/" in tok:
        num, _, den = tok.partition("/")
        try:
            n = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None
        return n if 0 < n <= 100 else None
    try:
        n = float(tok.replace(",", "."))
    except ValueError:
        return None
    # A "portion" of 400 slices is a misread, not an order.
    return n if 0 < n <= 100 else None


async def _mass_for(user_id: int, fdc_id: int, it: dict[str, Any],
                    text: str | None = None) -> MassEstimate:
    """Weighed beats stated beats your own history beats the model's eyes."""
    source = str(it.get("grams_source", "estimate"))
    grams = float(it.get("grams", 0) or 0)
    low = float(it["grams_low"]) if it.get("grams_low") else None
    high = float(it["grams_high"]) if it.get("grams_high") else None
    if source not in MEASURED_SOURCES:
        # A declared portion beats both the model's eyes and your own history.
        #
        # "One slice of blondie" is an estimate to a parser and arithmetic to
        # anyone who weighed the tray and counted the cuts: 850 g over 16 is
        # 53 g, exactly, for ever. It only applies when a count was actually
        # given — "some blondie" is not two slices — and the count multiplies,
        # so three slices is 159 g rather than three guesses.
        portion = await db.portion_for(fdc_id)
        if portion:
            count = it.get("count") or count_from_text(text, str(portion["unit"]))
            if count:
                grams_exact = float(count) * float(portion["gram_weight"])
                return MassEstimate(
                    grams_exact, sigma_for(grams_exact, "package"), "package",
                    note=f"{count:g} × your stated {portion['unit']} "
                         f"of {float(portion['gram_weight']):.0f} g",
                )
        history = await db.portion_history(user_id, fdc_id)
        return choose_mass(grams, source, low=low, high=high, history=history)
    return choose_mass(grams, source, low=low, high=high, history=[])


# A slash or an "or" is the model saying it cannot tell two foods apart.
#
# It is not a food name, and searching it as one finds nothing whatsoever:
# "pancetta/guanciale" scores 0.200 at best — against `Guava paste` — which is
# under pg_trgm's 0.3 threshold, while plainto_tsquery treats the slashed
# string as a single token that matches no description. Zero candidates, and a
# card saying the database holds nothing like cured pork, which holds eleven
# bacon rows and a pork jowl.
#
# Each side searched on its own reaches them: `Pork, belly` at 0.440 and
# `Pork, cured, bacon, cooked, baked` at 0.324. Still short of an auto-match,
# which is correct — the model was genuinely unsure and a human should pick —
# but it now asks with real candidates instead of claiming there are none.
_ALTERNATION = re.compile(r"\s*(?:/|\bor\b)\s*", re.IGNORECASE)


def _alternatives(query: str) -> list[str]:
    """The separate foods a query is offering a choice between."""
    parts = [p.strip(" ,;") for p in _ALTERNATION.split(query)]
    parts = [p for p in parts if len(p) > 2 and not is_non_food(p)]
    return parts if len(parts) > 1 else []


def _queries(it: dict[str, Any], label: str,
              dish_name: str | None = None,
              synonyms: Sequence[str] = ()) -> list[str]:
    """Every phrase the resolver searches on, in order, de-duplicated.

    Factored out of `_candidates` so provenance records what was actually
    asked. Reconstructing it at the call site would be a second implementation
    of the same list, and the two would drift the first time either changed —
    at which point the record would describe a search that never happened,
    which is worse than no record.

    `synonyms` are descriptions of rows the global vocabulary maps this label
    to. They go in **last and as ordinary queries**: a synonym expands the
    search and never decides the match, so ranking and all three guards judge
    what comes back exactly as they judge everything else. A wrong synonym
    therefore costs a bad candidate, not a silent auto-match that caches an
    alias forever — which is the failure mode this whole layer is routing
    around, and the reason it is not simply a second alias table.
    """
    base = [q for q in (str(it.get("search_terms") or "").strip(),
                        label.strip(),
                        (dish_name or "").strip()) if q]
    return list(dict.fromkeys(
        base + [side for q in base for side in _alternatives(q)]
        + [s for s in synonyms if s]))


async def _candidates(it: dict[str, Any], label: str, user_id: int | None = None,
                      dish_name: str | None = None) -> list[dict[str, Any]]:
    """Search on the model's `search_terms` *and* on the user's own label.

    Trigram similarity punishes a descriptive query. `PARSE_SYSTEM` asks for "a
    precise USDA-style phrase", so the model writes several clauses, and every
    clause the target row happens to lack drags the score down — the better the
    description, the worse it scores. Measured on a real meal:

        salami, Italian, organic, sliced  -> Salami, Italian, pork and beef  0.34
        Italian salami slices             -> Salami, Italian, pork           0.58

    Same food, same database, and only the short query is anywhere near the
    auto-match threshold. Both are asked, the union is ranked by the best score
    either achieved, and the threshold itself is untouched — it is eval-set
    work, not something to tune against one plate.

    Every candidate carries the score each query gave it, kept apart rather
    than collapsed. `sim` remains the pooled maximum so existing callers are
    unchanged, but a high `sim_model` against a low `sim_user` means the model's
    own paraphrase — written to look like a USDA description — outscored the
    words the user actually typed, which is the mechanism behind the 25 Aug
    cereal failure and is invisible in the maximum alone.
    """
    q_model = str(it.get("search_terms") or "").strip()
    q_user = label.strip()
    syn = [r["expands_to"] for r in await db.synonyms_for(q_user)] if q_user else []
    queries = _queries(it, label, dish_name, syn)
    pooled: dict[int, dict[str, Any]] = {}
    per_query: dict[int, dict[str, float]] = {}
    for q in dict.fromkeys(queries):
        for c in await db.search_foods(q, limit=5, user_id=user_id):
            fid, sim = c["fdc_id"], float(c["sim"] or 0)
            per_query.setdefault(fid, {})[q] = sim
            best = pooled.get(fid)
            if best is None or sim > float(best["sim"] or 0):
                pooled[fid] = dict(c)
    for fid, row in pooled.items():
        scores = per_query.get(fid, {})
        row["sim_user"] = scores.get(q_user)
        row["sim_model"] = scores.get(q_model)
    # Rank by similarity, precedence breaking ties — the same order
    # db.search_foods uses, applied across the pooled result.
    return sorted(
        pooled.values(),
        key=lambda c: (-float(c["sim"] or 0), int(c["precedence"] or 9)),
    )[:5]


# Labels that are never a food, however well they match.
#
# A natural-language modifier went through modifier_ops and came back with a
# component labelled "and". The resolver matched it to "Seven and Seven" — a
# whisky cocktail — at 100 g, and it went into a cappuccino. Trigram similarity
# has no notion of a stopword: "and" is a literal substring of that description,
# so the match scored well and auto-accepted without a model ever reconsidering.
#
# Length alone is not the test, since "egg", "ham", "oil" and "rye" are all real
# foods. The test is whether the label carries any meaning at all.
NON_FOOD_LABELS = {
    "and", "or", "the", "a", "an", "with", "of", "to", "in", "on", "plus",
    "some", "it", "that", "this", "then", "also", "for", "from", "at", "by",
    "was", "is", "are", "be", "as", "but", "if", "not", "no", "yes",
}


def is_non_food(label: str) -> bool:
    """A label with no food in it, whatever the database thinks it matches."""
    cleaned = label.strip().lower().strip(".,;:!?()[]\"'")
    return not cleaned or cleaned in NON_FOOD_LABELS


# Words that invert the meaning of a food rather than qualifying it.
#
# USDA carries "Chicken, meatless, breaded, fried" — a soy analogue — and it
# scores highly against "chicken breast, breaded, fried, panko crust", because
# lexically the two are nearly the same string. Its macros are close enough that
# the Atwater cross-check passes, so 400 g of real fried chicken auto-matched to
# it in silence and the only visible trace was 17 g of fibre on a plate of
# chicken.
#
# That is the "wrong USDA row, right grams" failure from ARCHITECTURE §11:
# totals drift and nothing raises. A trigram score cannot see it, because
# "meatless" is one short word in a long description. So it is named.
INVERTING_TERMS = (
    "meatless", "imitation", "substitute", "vegetarian", "vegan",
    "analog", "analogue", "meat-free", "plant-based",
)


def inverts_meaning(query: str, description: str) -> bool:
    """True when a candidate negates the food that was asked for.

    Only when the query did not ask for it — someone logging vegan chicken says
    so, and should get the analogue.
    """
    q, d = query.lower(), description.lower()
    # Any inversion word in the request means an analogue was wanted, not just
    # the same one: "vegan chicken nuggets" should be allowed to match
    # "Chicken, meatless, breaded, fried". Matching term-for-term would block it.
    if any(term in q for term in INVERTING_TERMS):
        return False
    return any(term in d for term in INVERTING_TERMS)


# Words in a USDA description that assert how the food was treated.
#
# "fresh" is deliberately absent: `Pork, fresh, belly` means uncured, not
# uncooked, and reading it as a raw marker would block the right row.
_RAW_WORDS = ("raw", "uncooked", "unprepared")
_COOKED_WORDS = (
    "cooked", "boiled", "baked", "fried", "roasted", "grilled", "broiled",
    "steamed", "stewed", "braised", "microwaved", "sauteed", "sautéed",
    "poached", "toasted", "heated", "prepared",
)
_DRY_WORDS = ("dry", "dried", "dehydrated", "powder", "powdered")

# What each declared state rules out. `as_sold` and `unknown` rule out nothing,
# which is the honest reading of them: they say the state was not established,
# not that it was neutral.
_STATE_EXCLUDES: dict[str, tuple[str, ...]] = {
    "cooked": _RAW_WORDS + _DRY_WORDS,
    "raw": _COOKED_WORDS + _DRY_WORDS,
    "dry": _COOKED_WORDS,
}


def _has_word(description: str, words: tuple[str, ...]) -> str | None:
    d = re.split(r"[^a-z]+", description.lower())
    return next((w for w in words if w in d), None)


def state_conflicts(state: str | None, description: str) -> str | None:
    """The word by which a candidate contradicts the state that was declared.

    `state` is the one field the parse schema calls out as "the largest error
    source in the system", and until now the resolver read it only to pick a
    mass — never to pick a row. It is the strongest signal available and it was
    being thrown away: on 25 Aug "egg white, fried" auto-matched `Egg, white,
    dried` at 0.625, roughly 380 kcal per 100 g against 52, and "broccoli,
    boiled" auto-matched `Broccoli, raw` at 0.692. Both are plausible numbers
    from the wrong row, which is the failure mode nothing downstream catches.

    Only a contradiction counts. A description that says nothing about its
    state is not evidence against anything, so it passes.
    """
    excluded = _STATE_EXCLUDES.get((state or "").lower())
    if not excluded:
        return None
    bad = _has_word(description, excluded)
    if bad is None:
        return None
    # A description asserting both — `Pasta, dry, enriched, cooked` — is not
    # contradicting anything; it is covering two forms in one row, and the
    # matching word is the one that decides.
    keep = {"cooked": _COOKED_WORDS, "raw": _RAW_WORDS, "dry": _DRY_WORDS}[
        (state or "").lower()]
    return None if _has_word(description, keep) else bad


def label_absent(label: str, description: str) -> bool:
    """True when none of the user's own words appear in the row at all.

    `_candidates` searches the model's `search_terms` as well as the label and
    ranks by whichever scored higher, so a row can win on a phrase the user
    never typed. The model writes `search_terms` as a USDA-style description of
    the row it already believes in, which makes a high pooled score evidence
    for the model's own prior rather than for the match.

    Measured, and this is the whole argument: "brownie" scores **0.022**
    against `Pie, chocolate creme, commercially prepared` and 0.286 against
    `Cookie, brownie, without icing`. The model's phrase scored 0.696 against
    the pie, cleared the 0.62 gate, auto-matched with no model consulted, and
    wrote an alias on 23 Aug 2026 that logged every brownie since as chocolate
    creme pie — 353 kcal against 405, and 27 g of sugar against 37.

    A similarity floor on `sim_user` cannot express this: "rice" scores badly
    against `Rice, white, long-grain, regular, enriched, cooked` too, and that
    is the right row. Presence is the question, not degree. Prefix matching
    stands in for stemming so "brownie" reaches "brownies"; a word under four
    characters must match exactly, or "oil" would match "oilseed".
    """
    words = [w for w in re.split(r"[^a-z0-9]+", label.lower())
             if w and w not in _QUALIFIER_STOP]
    if not words:
        return False
    d = [w for w in re.split(r"[^a-z0-9]+", description.lower()) if w]
    for w in words:
        if any(w == t or (len(w) >= 4 and (t.startswith(w) or w.startswith(t)))
               for t in d):
            return False
    return True


_QUALIFIER_STOP = frozenset({
    "and", "or", "with", "without", "in", "of", "the", "a", "an", "by", "as",
    "to", "ns", "nfs", "all", "types", "commercial", "commercially", "solids",
    "eaten", "not",
    # Fortification and grading, which qualify how the same food was processed
    # rather than which food it is. `search_foods` already names the case this
    # protects: `Rice, white, long-grain, regular, enriched, cooked` is the
    # right answer for plain cooked rice, and treating "enriched" as a
    # narrowing qualifier would have blocked it at 0.837.
    "enriched", "unenriched", "fortified", "unfortified", "regular", "plain",
    "generic", "unspecified", "prepared", "unprepared",
    # USDA's usage note on fats — `Oil, olive, salad or cooking` — which says
    # what the oil is for, not which oil it is. Only ever a later segment; a
    # first segment like `Chicken salad` is still judged as a name.
    "salad", "cooking",
})


# Head segments that name a dish or a processed product rather than a food.
#
# `unrequested_qualifier` assumes USDA writes `Food, qualifier, qualifier`, and
# SR Legacy does: `Spaghetti, spinach, cooked`. FNDDS inverts it. There the head
# is what the thing *is* and the food you asked for is the qualifier —
# `Pie, oatmeal` is a pie, `Oil, avocado` is an oil — so the head shares no word
# with the query, the first-segment branch finds nothing to narrow, and the row
# passes a guard written to catch exactly this.
#
# Measured on 28 Aug 2026, all auto-matching past all three guards:
#   sweet potato -> Pie, sweet potato   0.812  over Sweet potato, NFS  0.765
#   oatmeal      -> Cookie, oatmeal     0.667  three-way tie, cookie at the head
#   seaweed      -> Soup, seaweed       tied with Seaweed, raw
#
# A list rather than a rule, because the distinction is semantic and a rule gets
# it wrong in the expensive direction. `Cheese, brie` and `Spices, pepper, black`
# have exactly the same *shape* — head shares nothing with the query, the food
# is a later segment — and are the correct answers, because cheese and spices
# are what brie and pepper ARE. A pie is not what oatmeal is. Agent 2 of the
# resolution audit measured a head-noun rule wrongly rejecting 30 of 132 live
# aliases, which is why this names dishes instead of testing structure.
#
# Only blocks when the query did not ask for it: `avocado oil` still reaches
# `Oil, avocado`, because "oil" is then one of the query's own words.
_DISH_HEAD_WORDS = frozenset({
    "pie", "cookie", "cookies", "cake", "cupcake", "muffin", "brownie",
    "soup", "stew", "chowder", "chili", "casserole",
    "pizza", "taco", "burrito", "sandwich", "wrap", "salad",
    "roll", "bun", "biscuit", "cracker", "crackers", "pretzel", "pretzels",
    "chip", "chips", "popcorn", "bar", "candy", "pudding", "custard",
    "juice", "drink", "beverage", "soda", "smoothie", "shake", "tea", "coffee",
    "oil", "flour", "powder", "syrup", "sauce", "gravy", "dressing", "dip",
    "spread", "jam", "jelly", "butter",
    # Rendered or separated parts of an animal or plant, which are not the food
    # you named: `kurczak` expanded to "chicken" and surfaced `Fat, chicken`.
    "fat", "lard", "tallow", "broth", "stock", "gravy",
})


def unrequested_qualifier(query: str, description: str) -> str | None:
    """A qualifier the description adds that the query never asked for.

    USDA writes `Food, qualifier, qualifier`. A segment after the first comma
    that shares no word with the query narrows the row to a *different food*
    that happens to be spelled the same way: "spaghetti, cooked" auto-matched
    `Spaghetti, spinach, cooked` at 0.739 on 25 Aug, and 220 g of it went into
    a carbonara carrying no fibre figure at all.

    Preparation words are exempt — they are the state, which `state_conflicts`
    judges properly and which the query often leaves unstated.

    The first segment is the food's *name* and is judged differently, because
    exempting it outright was wrong in a way worth recording: blocking
    `Spaghetti, spinach, cooked` promoted `Spaghetti squash, cooked` — a
    vegetable at 49 kcal per 100 g — straight into the auto-match, which is a
    worse answer than the one being fixed. A name that shares nothing with the
    query is a different food and a weak match, judged by similarity like
    anything else; a name that repeats the query's word and *adds* one is
    narrowing it, and "spaghetti squash" is not spaghetti.
    """
    q = {w for w in re.split(r"[^a-z0-9]+", query.lower()) if w}
    prep = set(_RAW_WORDS + _COOKED_WORDS + _DRY_WORDS)
    segs = description.split(",")
    # Whether the food the user actually named turns up after the head. That is
    # what separates the inverted shape from an ordinary weak match: in
    # `Pie, oatmeal` the query's word is present, just not where the guard looks.
    food_is_a_qualifier = any(
        {w for w in re.split(r"[^a-z0-9]+", s.lower()) if w} & q for s in segs[1:]
    )
    for i, seg in enumerate(segs):
        words = {w for w in re.split(r"[^a-z0-9]+", seg.lower())
                 if w and w not in _QUALIFIER_STOP}
        if not words or words <= prep:
            continue
        extra = words - q - prep
        if i == 0:
            # Only a name that echoes the query can narrow it.
            if (words & q) and extra:
                return seg.strip()
            # FNDDS's inverted shape: a head that names a dish or a processed
            # product, does not appear in the query, and has the queried food
            # sitting behind it as a qualifier. That is a different food made
            # from yours, not a narrower version of it.
            if words <= _DISH_HEAD_WORDS and not (words & q) and food_is_a_qualifier:
                return seg.strip()
            continue
        if not (words & q) and extra:
            return seg.strip()
    return None


def _as_float(v: Any) -> float | None:
    """asyncpg hands back Decimal for a numeric; the dataclass wants a float."""
    return None if v is None else float(v)


async def resolve_items(user_id: int, items: list[dict[str, Any]],
                        dish_name: str | None = None,
                        text: str | None = None) -> Resolution:
    """Ingredient names to USDA rows.

    Three tiers, cheapest first:
      1. a user alias  -> free, and this is where the steady state lives
      2. a high-similarity database hit -> free
      3. a Haiku call over the top-5 candidates -> ~0.08 cents, once per new food

    Tier 3 always writes an alias, so a given ingredient can only ever cost you
    once. After a few weeks of normal eating the model is barely involved in
    resolution at all.
    """
    comps: list[ResolvedComponent] = []
    sources: list[str] = []
    unresolved: list[str] = []
    weak: list[tuple[str, float]] = []
    notes: list[str] = []
    need_model: list[tuple[dict[str, Any], list[asyncpg.Record], dict[str, Any]]] = []
    cost = 0.0
    events: list[dict[str, Any]] = []

    def _event(label: str, queries: list[str], cands: list[Any],
               *, chosen: int | None, tier: str | None) -> dict[str, Any]:
        """One item's resolution, recorded whatever became of it.

        Appended at every exit including the ones that resolve nothing, since
        an item that matched no row leaves no component and is exactly the case
        worth reading back. Candidates are trimmed to the fields a diagnosis
        needs — the full Record carries a `has_energy` and a `covers` that are
        derivable and a description that is the only text worth keeping.
        """
        ev = {
            "position": len(events),
            "label": label,
            "queries": queries,
            "candidates": [
                {"fdc_id": int(c["fdc_id"]), "description": c["description"],
                 "data_type": c["data_type"], "precedence": int(c["precedence"] or 9),
                 "sim": _as_float(c["sim"]),
                 "sim_user": _as_float(c.get("sim_user")),
                 "sim_model": _as_float(c.get("sim_model"))}
                for c in cands
            ],
            "chosen_fdc_id": chosen,
            "match_tier": tier,
        }
        events.append(ev)
        return ev

    async def _accept(label: str, fdc_id: int, it: dict[str, Any], yf: float = 1.0,
                      *, tier: str | None = None,
                      chosen: dict[str, Any] | None = None,
                      cands: list[dict[str, Any]] | None = None) -> None:
        m = await _mass_for(user_id, fdc_id, it, text)
        count = it.get("count")
        # The runner-up is the best candidate that is not the one taken. A
        # margin is the only honest input to a confidence figure and it cannot
        # be recovered later: the candidate list is not kept anywhere, so a
        # decision made on 0.001 and one made on 0.4 look identical afterwards.
        runner = next((c for c in (cands or []) if c["fdc_id"] != fdc_id), None)
        comps.append(ResolvedComponent(
            label, fdc_id, m.grams, yf, m.sigma, m.source,
            float(count) if count else None,
            state=str(it.get("state") or "as_logged"),
            match_tier=tier,
            sim_user=_as_float(chosen.get("sim_user")) if chosen else None,
            sim_model=_as_float(chosen.get("sim_model")) if chosen else None,
            runner_up_fdc_id=int(runner["fdc_id"]) if runner else None,
            runner_up_sim=_as_float(runner.get("sim")) if runner else None,
        ))
        sources.append(m.source)
        if m.note:
            notes.append(f"{label}: {m.grams:.0f} g from {m.note}")

    for it in items:
        # The tool schema says every item is an object, and the model returned
        # a bare string anyway — "0.33 slice of blondie" produced one, and the
        # AttributeError took down the whole handler, leaving "digesting…" on
        # screen. A malformed item costs one line of a parse; it must never
        # cost the parse.
        if not isinstance(it, dict):
            log.warning("dropping malformed item from parse: %r", it)
            continue
        label = str(it.get("label", "")).strip()
        if not label or float(it.get("grams", 0) or 0) <= 0:
            continue
        if is_non_food(label):
            # Dropped silently rather than reported: it was never something the
            # user said they ate, only a fragment a parse split badly.
            continue

        alias = await db.resolve_alias(user_id, label)
        # An alias is keyed on the label, and a label does not carry its state.
        # "pork chop" is raw one day and cooked the next, so a cached row that
        # contradicts what was declared today is a cache miss, not an answer.
        #
        # This is the one guard the alias tier needs. On 31 Aug 2026 a gnocchi
        # meal logged 200 g of "pork chop" against `Pork, chop, center cut,
        # raw` — 145 kcal and 22.8 g protein against 183 and 27.5 for a chop
        # that was eaten — because an alias written before the guards existed
        # is never re-examined. Skipping it sends the name back through search,
        # where `state_conflicts` applies as it does to anything else.
        if alias and state_conflicts(it.get("state"), alias["description"]):
            log.info("alias %r -> %r contradicts state %r; re-resolving",
                     label, alias["description"], it.get("state"))
            alias = None
        if alias:
            await db.bump_alias(alias["id"])
            # The alias tier is the steady state — most resolutions arrive here
            # and cost nothing — so leaving it unmeasured would keep the
            # dominant path invisible, which is the whole defect Phase 0 exists
            # to close. The score recorded is the alias string against what was
            # typed, not a row description against a label: a different
            # distribution through the same constant (SPEC-7 §7.3), which is
            # why `match_tier` has to be read alongside `sim_user`.
            await _accept(label, alias["fdc_id"], it, tier="alias",
                          chosen={"sim_user": alias["alias_sim"], "sim_model": None})
            # No candidate list: the alias tier never generates one, and
            # recording an empty one is the honest answer rather than a gap.
            _event(label, [], [], chosen=int(alias["fdc_id"]), tier="alias")
            continue

        # On a one-ingredient meal the dish name is a third search term, and
        # often the only one that carries the distinguishing word. "Pickle
        # juice" parsed to a single component labelled "juice", which resolved
        # to Fruit juice, NFS at 51 kcal and 12 g of carbohydrate — while the
        # user's own pickle brine row sat unconsulted, because nothing ever
        # searched for the two words together.
        hint = dish_name if (dish_name and len(items) == 1) else None
        expansions = [r["expands_to"] for r in await db.synonyms_for(label)]
        queries = _queries(it, label, hint, expansions)
        cands = await _candidates(it, label, user_id, dish_name=hint)
        # A candidate that negates the food is never auto-matched, however well
        # it scores. It drops to the model instead of being taken on trust —
        # tier 3 costs a fraction of a penny and can read the word "meatless".
        # The guards must judge against everything that was asked, including
        # what the vocabulary added. Without the expansions here the guards go
        # blind exactly where the expansion just widened the net: `porridge`
        # expands to "oatmeal cooked", surfaces `Cookie, oatmeal`, and
        # unrequested_qualifier cannot see that "oatmeal" was asked for, so the
        # FNDDS dish head walks through the check written to stop it. Measured
        # on the seed: porridge -> Cookie, oatmeal; ryz -> Soup, rice;
        # kurczak -> Fat, chicken.
        asked_for = " ".join(
            [label, str(it.get("search_terms") or ""), *expansions])

        # Your own food beats a generic row, whatever the pooling says.
        #
        # `_candidates` searches on the model's `search_terms` as well as on
        # your words, and ranks by the best score any query achieved. The
        # model's phrase describes what it thinks the food is, so it matches a
        # generic row almost exactly — "chicken cordon bleu" scoring against
        # `Chicken or turkey cordon bleu` beat the Devolay you had defined
        # yourself an hour earlier at 0.84, and the parse auto-matched the
        # wrong one without ever asking anything.
        #
        # precedence 0 is `user_product` and nothing else. A row you wrote from
        # a packet in your hand is not a candidate to be weighed against a
        # national average of a food you did not eat; it is the answer.
        #
        # The threshold was the wrong comparison, measured against the golden
        # set on 25 Aug 2026: authority is not a score. "Devolay chicken
        # (breaded stuffed chicken)" leads its own candidate list and still
        # scored 0.39, because trigram similarity falls with description
        # length (RECONCILED.md §1) and naming your own food precisely is what
        # makes it long. Gated on 0.62 the rule could not fire in the case it
        # was written for.
        #
        # So the comparison is against the pooled head, per §3.2. Your row at
        # the top of the list is the answer whatever its score; below the head
        # it still has to clear the threshold like anything else.
        own = next(
            (c for c in cands
             if c["precedence"] == 0
             and (c is cands[0] or float(c["sim"] or 0) >= AUTO_MATCH_SIMILARITY)),
            None)
        if own is not None and not inverts_meaning(asked_for, own["description"]):
            await _accept(label, own["fdc_id"], it,
                          tier="own", chosen=own, cands=cands)
            _event(label, queries, cands, chosen=int(own["fdc_id"]), tier="own")
            await db.upsert_alias(user_id, label, own["fdc_id"],
                                  float(it.get("grams", 0) or 0))
            continue

        # The best candidate that survives every guard, not merely the best
        # candidate. Reading the head alone meant one disqualifying word sent
        # the whole item to the model even when the row below it was right,
        # and — far worse — that a disqualified head was taken on trust
        # whenever its score cleared the bar.
        auto = next(
            (c for c in cands
             if float(c["sim"] or 0) >= AUTO_MATCH_SIMILARITY
             and not inverts_meaning(asked_for, c["description"])
             and not state_conflicts(it.get("state"), c["description"])
             and not unrequested_qualifier(asked_for, c["description"])
             and not label_absent(label, c["description"])),
            None)
        if auto is not None:
            await _accept(label, auto["fdc_id"], it,
                          tier="auto", chosen=auto, cands=cands)
            _event(label, queries, cands, chosen=int(auto["fdc_id"]), tier="auto")
            await db.upsert_alias(user_id, label, auto["fdc_id"], float(it.get("grams", 0) or 0))
            continue
        if not cands:
            # The failure this whole table exists for: every query searched,
            # nothing returned, and until now not a trace of it anywhere.
            _event(label, queries, [], chosen=None, tier="none")
            unresolved.append(label)
            weak.append((label, 0.0))
            continue
        best = float(cands[0]["sim"] or 0)
        if best < WEAK_MATCH_SIMILARITY:
            weak.append((label, best))
        # Provisional: the model tier below overwrites tier and chosen row if
        # it picks one, and leaves this standing if it declines.
        need_model.append((it, cands,
                           _event(label, queries, cands,
                                  chosen=None, tier="asked_model")))

    if need_model:
        lines = []
        for n, (it, cands, _ev) in enumerate(need_model, 1):
            opts = " | ".join(
                f"{c['fdc_id']}: {c['description']} [{c['data_type']}]" for c in cands
            )
            lines.append(
                f"[{n}] {it.get('label')} — logged as {it.get('state','unknown')}, "
                f"{it.get('grams')} g\n  candidates: {opts}"
            )
        res = await call_tool(
            model=MODEL_CHEAP,
            tool=DISAMBIGUATE_TOOL,
            system=[cached(DISAMBIGUATE_SYSTEM)],
            content=[{"type": "text", "text": "\n".join(lines)}],
            max_tokens=600,
        )
        await _log(res, "disambiguate", user_id)
        cost += res.cost_usd
        # Matched by index. Matching by label looked reasonable and silently
        # threw away every correct answer this tier produced: the model echoes
        # the prompt line rather than the bare name, so the exact-string lookup
        # never hit and a confident, correct match ("Salami, Italian, pork",
        # confidence 0.9) was recorded as unresolved. The label is kept only as
        # a fallback for a response that omits the index.
        choices = list(res.data.get("choices", []))
        by_index = {int(c["index"]): c for c in choices if c.get("index") is not None}
        by_label = {str(c.get("label", "")).lower(): c for c in choices}
        for n, (it, _cands, ev) in enumerate(need_model, 1):
            label = str(it.get("label", ""))
            pick = by_index.get(n) or by_label.get(label.lower())
            if not pick or not pick.get("fdc_id"):
                # The model saw the candidates and declined them all. The
                # event keeps its 'asked_model' tier and a null choice, which
                # is a different failure from having no candidates at all and
                # has to stay distinguishable from it.
                unresolved.append(label)
                continue
            yf = float(pick.get("yield_factor", 1.0) or 1.0)
            chosen = next((c for c in _cands if c["fdc_id"] == int(pick["fdc_id"])), None)
            await _accept(label, int(pick["fdc_id"]), it, yf,
                          tier="model", chosen=chosen, cands=_cands)
            ev["chosen_fdc_id"] = int(pick["fdc_id"])
            ev["match_tier"] = "model"
            await db.upsert_alias(
                user_id, label, int(pick["fdc_id"]), float(it.get("grams", 0) or 0)
            )

    # Written before returning, and never inside the loop: one round trip for
    # the meal rather than one per ingredient, and nothing half-recorded if a
    # later item raises.
    event_ids = await db.record_resolution_events(user_id, events)
    return Resolution(comps, sources, unresolved, cost, bool(need_model), notes, weak,
                      event_ids)


async def modifier_ops(component_labels: list[str], phrase: str, *, user_id: int) -> dict[str, Any]:
    """Fallback for a repeat modifier the local grammar could not parse.

    Context sent is the label list and the phrase. Not the photo, not the
    nutrient database, not the conversation. Roughly 200 input tokens."""
    res = await call_tool(
        model=MODEL_CHEAP,
        tool=MODIFIER_TOOL,
        system=[cached(MODIFIER_SYSTEM)],
        content=[{"type": "text", "text": f"Components: {', '.join(component_labels)}\nChange: {phrase}"}],
        max_tokens=400,
    )
    await _log(res, "modifier", user_id)
    return res.data


# ----------------------------------------------------------------- guardrail


@dataclass
class Verdict:
    ok: bool
    warnings: list[str]


async def validate(components: list[ResolvedComponent], parsed: ParsedMeal) -> Verdict:
    """Cheap, deterministic checks that run on every parse before it is shown."""
    warnings: list[str] = []
    profs = await db.profiles_for([c.fdc_id for c in components])
    totals = total_nutrients(components, profs)

    ec = energy_cross_check(totals)
    if not ec.ok and ec.kcal_db > 0:
        warnings.append(
            f"energy check: macros imply {ec.kcal_atwater:.0f} kcal, database says "
            f"{ec.kcal_db:.0f} ({ec.delta_pct:+.0f}%) — a component is probably matched wrong"
        )

    # A component whose USDA row reports no energy contributes nothing to the
    # day's total and raises nothing anywhere else: energy_cross_check's own
    # guard skips the case, because it cannot tell "no energy reported" from
    # "zero-energy food". Say it out loud instead — a plate that is quietly
    # missing its largest item is the failure this whole validation pass exists
    # to catch.
    for c in components:
        if ENERGY_KCAL not in profs.get(c.fdc_id, {}):
            warnings.append(
                f"{c.label}: this USDA row reports no energy, so its {c.grams:.0f} g "
                f"add 0 kcal to the total — pin it to a row that does"
            )

    for c in components:
        if c.grams > 1500:
            warnings.append(f"{c.label}: {c.grams:.0f} g is implausible for one sitting")
        if c.yield_factor > 3.0 or c.yield_factor < 0.3:
            warnings.append(f"{c.label}: yield factor {c.yield_factor:.2f} is extreme")

    # Which foods the question even applies to. "Was that weighed before or
    # after cooking?" is a real 2-3x question for rice, pasta and meat, and
    # nonsense for milk — asked of a cappuccino it makes the system look like it
    # does not know what milk is. USDA says which foods have the distinction:
    # if the matched row carries no state qualifier, there is nothing to resolve.
    STATEFUL = ("raw", "dry", "uncooked", "cooked", "boiled", "roasted", "prepared")
    descriptions = {}
    if components:
        p = await db.pool()
        descriptions = {
            r["fdc_id"]: (r["description"] or "").lower()
            for r in await p.fetch(
                "SELECT fdc_id, description FROM food WHERE fdc_id = ANY($1::int[])",
                [c.fdc_id for c in components],
            )
        }
    by_label = {c.label: c.fdc_id for c in components}

    for it in parsed.items:
        fdc = by_label.get(str(it.get("label", "")))
        desc = descriptions.get(fdc, "")
        if not any(w in desc for w in STATEFUL):
            continue
        if str(it.get("state")) == "unknown" and float(it.get("grams", 0) or 0) > 80:
            # Phrased as the question that is actually open. "Raw or cooked is
            # unknown" reads as though you might have eaten it raw, which is
            # absurd for rice and pasta; what is unknown is which side of the
            # pan the scale reading came from, and that is a 2-3x difference.
            warnings.append(
                f"{it.get('label')}: was that weighed before or after cooking? "
                f"say \u201cdry\u201d or \u201ccooked\u201d and I will use it"
            )
        if str(it.get("grams_source")) == "estimate" and float(it.get("confidence", 1)) < 0.5:
            warnings.append(f"{it.get('label')}: mass is a low-confidence visual estimate")

    return Verdict(ok=not warnings, warnings=warnings)


async def _log(res: ToolResult, purpose: str, user_id: int | None) -> None:
    await db.record_llm_call(
        user_id=user_id,
        purpose=purpose,
        model=res.model,
        input_tokens=res.input_tokens,
        output_tokens=res.output_tokens,
        cache_read_tokens=res.cache_read_tokens,
        cache_write_tokens=res.cache_write_tokens,
        latency_ms=res.latency_ms,
        cost_usd=res.cost_usd,
        ok=True,
    )


# --------------------------------------------------------------- supplements


async def read_supplement_label(
    *, user_id: int, image_b64: str | None = None, text: str | None = None,
    images: list[str] | None = None,
) -> tuple[dict[str, Any], float]:
    """Transcribe supplement panels from a photo or from written text.

    Text is a first-class source, not a fallback. Someone who has already
    written down what is on their packets is handing over better data than a
    photograph of a curved bottle in poor light, and refusing it would only push
    them to paste it somewhere that treats it as a meal.

    Either way it is transcription rather than estimation: the model is given
    the exact nutrient ids it may use and told to report what the source states.
    """
    if not image_b64 and not images and not text:
        raise ValueError("a photo or some text is required")

    # Every photograph of the packet, in one call. A panel is on the back and
    # the name is on the front, so the two arrive as an album — and sending
    # only the first meant the model was shown a front label and asked where
    # the nutrition panel was. On 31 Aug 2026 that read an 88 g/100 g fibre
    # panel as "no nutrition panel visible in this photo".
    shots = list(images or ([image_b64] if image_b64 else []))
    content: list[dict[str, Any]] = [
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/jpeg", "data": b}}
        for b in shots
    ]
    if len(shots) > 1:
        content.append({"type": "text",
                        "text": f"These {len(shots)} photographs are of the same "
                                "product — front, back and panel. Read them together."})
    if text:
        content.append({"type": "text", "text": f"Product information:\n\n{text}"})
    content.append({
        "type": "text",
        "text": "Transcribe every product. Use only these nutrient ids:\n" + _nutrient_menu(),
    })

    res = await call_tool(
        model=MODEL_PHOTO,
        tool=SUPPLEMENT_TOOL,
        system=[cached(SUPPLEMENT_SYSTEM)],
        content=content,
        max_tokens=4000,
    )
    await _log(res, "supplement_label", user_id)
    return res.data, res.cost_usd


def _nutrient_menu() -> str:
    """The ids the model is allowed to use, with their units.

    Supplied rather than left to the model's memory: this is the mechanism that
    keeps a transcription from becoming a guess. An id it was not given is an id
    it cannot return, so "vitamin B6" cannot quietly land on B12's row.
    """
    names = {
        1008: "Energy (kcal)", 1003: "Protein (g)", 1004: "Fat (g)", 1005: "Carbohydrate (g)",
        1079: "Fibre (g)", 2000: "Sugars (g)", 1258: "Saturated fat (g)", 
        # EU panels print "Salt", not sodium. That line is reported as 1093
        # with the unit "g salt" and converted in Python: a model asked to
        # divide by 2.5 is a model estimating a nutrient value, and one that
        # reads "Salt 0.30 g" as 0.30 mg of sodium is wrong by a factor of
        # 2.5 with nothing downstream able to tell.
        1093: "Sodium (mg) — for a 'Salt' line use unit 'g salt', do not convert",
        1092: "Potassium (mg)", 1087: "Calcium (mg)", 1089: "Iron (mg)", 1090: "Magnesium (mg)",
        1095: "Zinc (mg)", 1178: "Vitamin B-12 (ug)", 1114: "Vitamin D (ug)",
        1162: "Vitamin C (mg)", 1106: "Vitamin A RAE (ug)", 1177: "Folate (ug)",
        1253: "Cholesterol (mg)", 1272: "DHA (g)", 1109: "Vitamin E (mg)",
        # Named precisely. FDC has no id for menaquinone-7, which is what most
        # K2 supplements contain, and 1183 is specifically MK-4 — a different
        # molecule with a 1-2 hour half-life against MK-7's ~68, trialled at
        # 450x the dose. Labelling this "Vitamin K" invites exactly the
        # collapse rule 3 forbids, and the result would look entirely normal.
        1183: "Vitamin K, menaquinone-4 ONLY (ug)",
        1185: "Vitamin K, phylloquinone / K1 ONLY (ug)", 1165: "Thiamin (mg)", 1166: "Riboflavin (mg)",
        1167: "Niacin (mg)", 1175: "Vitamin B-6 (mg)", 1170: "Pantothenic acid (mg)",
        1176: "Biotin (ug)", 1098: "Copper (mg)", 1101: "Manganese (mg)",
        1103: "Selenium (ug)", 1100: "Iodine (ug)", 1091: "Phosphorus (mg)",
    }
    return "\n".join(f"  {nid} = {label}" for nid, label in sorted(names.items()))


async def read_food_label(
    *, user_id: int, image_b64: str | None = None, name_hint: str = "",
    images: list[str] | None = None, text: str | None = None,
) -> tuple[dict[str, Any], float]:
    """Transcribe a packaged food's panel into a per-100 g composition.

    Same amendment as the supplement panel: a model may transcribe a printed
    figure, never estimate one. The difference from a supplement is the
    per-serving column, which on cereal routinely means "with 125 ml milk" and
    describes a bowl rather than a product — so the tool is asked which column
    it read and told to prefer per 100 g.
    """
    shots = list(images or ([image_b64] if image_b64 else []))
    content: list[dict[str, Any]] = [
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/jpeg", "data": b}}
        for b in shots
    ]
    if len(shots) > 1:
        content.append({"type": "text",
                        "text": f"These {len(shots)} photographs are of the same "
                                "product — front, back and panel. Read them together."})
    # A caption is the panel typed out by someone holding the packet, which is
    # better evidence than a photograph of a curved foil bag, not a worse one.
    if text:
        content.append({"type": "text", "text": f"Product information:\n\n{text}"})
    if name_hint:
        content.append({"type": "text",
                        "text": f"The user calls this food: {name_hint}"})
    content.append({
        "type": "text",
        "text": "Transcribe the panel. Use only these nutrient ids:\n" + _nutrient_menu(),
    })
    res = await call_tool(
        model=MODEL_PHOTO,
        tool=FOOD_LABEL_TOOL,
        system=[cached(FOOD_LABEL_SYSTEM)],
        content=content,
        max_tokens=3000,
    )
    await _log(res, "food_label", user_id)
    return res.data, res.cost_usd


def per_100g(data: dict[str, Any]) -> tuple[dict[int, float], list[str]]:
    """(nutrient_id -> per 100 g, warnings).

    Conversion happens here rather than in the model, which is told to report
    what is printed and nothing else. A per-serving panel with no serving
    weight cannot be converted at all, and saying so beats dividing by a
    number nobody supplied.
    """
    warnings: list[str] = []
    basis = data.get("basis", "per_100g")
    grams = data.get("serving_grams")

    if data.get("serving_includes_additions"):
        warnings.append(
            "the serving column on this pack includes something added to it — "
            "milk, usually — so the per-100 g column was used instead")

    scale = 1.0
    if basis == "per_serving":
        if not grams or float(grams) <= 0:
            return {}, ["the panel gives only a per-serving column and no "
                        "serving weight, so it cannot be put on a per-100 g "
                        "footing — nothing was read"]
        scale = 100.0 / float(grams)
        warnings.append(f"read from the per-serving column and scaled up from "
                        f"{float(grams):g} g")

    out: dict[int, float] = {}
    for n in data.get("nutrients") or []:
        try:
            out[int(n["nutrient_id"])] = float(n["amount"]) * scale
        except (TypeError, ValueError, KeyError):
            continue

    # Folic acid on a label is the only stated contributor to total folate, and
    # the target sits on total. Recorded under both rather than either alone:
    # under 1186 only it would count toward nothing, under 1177 only it would
    # claim to be food folate, which it is not.
    if 1186 in out and 1177 not in out:
        out[1177] = out[1186]
    return out, warnings
