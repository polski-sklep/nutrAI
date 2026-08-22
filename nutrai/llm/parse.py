from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any

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


def visual_tokens(w: int, h: int) -> int:
    return -(-w // 28) * -(-h // 28)


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


async def _candidates(it: dict[str, Any], label: str, user_id: int | None = None,
                      dish_name: str | None = None) -> list[asyncpg.Record]:
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
    """
    queries = [q for q in (str(it.get("search_terms") or "").strip(), label.strip(),
                           (dish_name or "").strip()) if q]
    pooled: dict[int, asyncpg.Record] = {}
    for q in dict.fromkeys(queries):
        for c in await db.search_foods(q, limit=5, user_id=user_id):
            best = pooled.get(c["fdc_id"])
            if best is None or float(c["sim"] or 0) > float(best["sim"] or 0):
                pooled[c["fdc_id"]] = c
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
    need_model: list[tuple[dict[str, Any], list[asyncpg.Record]]] = []
    cost = 0.0

    async def _accept(label: str, fdc_id: int, it: dict[str, Any], yf: float = 1.0) -> None:
        m = await _mass_for(user_id, fdc_id, it, text)
        count = it.get("count")
        comps.append(ResolvedComponent(
            label, fdc_id, m.grams, yf, m.sigma, m.source,
            float(count) if count else None,
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
        if alias:
            await db.bump_alias(alias["id"])
            await _accept(label, alias["fdc_id"], it)
            continue

        # On a one-ingredient meal the dish name is a third search term, and
        # often the only one that carries the distinguishing word. "Pickle
        # juice" parsed to a single component labelled "juice", which resolved
        # to Fruit juice, NFS at 51 kcal and 12 g of carbohydrate — while the
        # user's own pickle brine row sat unconsulted, because nothing ever
        # searched for the two words together.
        hint = dish_name if (dish_name and len(items) == 1) else None
        cands = await _candidates(it, label, user_id, dish_name=hint)
        # A candidate that negates the food is never auto-matched, however well
        # it scores. It drops to the model instead of being taken on trust —
        # tier 3 costs a fraction of a penny and can read the word "meatless".
        asked_for = f"{label} {it.get('search_terms') or ''}"
        if (
            cands
            and float(cands[0]["sim"] or 0) >= AUTO_MATCH_SIMILARITY
            and not inverts_meaning(asked_for, cands[0]["description"])
        ):
            await _accept(label, cands[0]["fdc_id"], it)
            await db.upsert_alias(user_id, label, cands[0]["fdc_id"], float(it.get("grams", 0) or 0))
            continue
        if not cands:
            unresolved.append(label)
            weak.append((label, 0.0))
            continue
        best = float(cands[0]["sim"] or 0)
        if best < WEAK_MATCH_SIMILARITY:
            weak.append((label, best))
        need_model.append((it, cands))

    if need_model:
        lines = []
        for n, (it, cands) in enumerate(need_model, 1):
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
        for n, (it, _cands) in enumerate(need_model, 1):
            label = str(it.get("label", ""))
            pick = by_index.get(n) or by_label.get(label.lower())
            if not pick or not pick.get("fdc_id"):
                unresolved.append(label)
                continue
            yf = float(pick.get("yield_factor", 1.0) or 1.0)
            await _accept(label, int(pick["fdc_id"]), it, yf)
            await db.upsert_alias(
                user_id, label, int(pick["fdc_id"]), float(it.get("grams", 0) or 0)
            )

    return Resolution(comps, sources, unresolved, cost, bool(need_model), notes, weak)


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
    *, user_id: int, image_b64: str | None = None, text: str | None = None
) -> tuple[dict[str, Any], float]:
    """Transcribe supplement panels from a photo or from written text.

    Text is a first-class source, not a fallback. Someone who has already
    written down what is on their packets is handing over better data than a
    photograph of a curved bottle in poor light, and refusing it would only push
    them to paste it somewhere that treats it as a meal.

    Either way it is transcription rather than estimation: the model is given
    the exact nutrient ids it may use and told to report what the source states.
    """
    if not image_b64 and not text:
        raise ValueError("a photo or some text is required")

    content: list[dict[str, Any]] = []
    if image_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
        })
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
        1079: "Fibre (g)", 2000: "Sugars (g)", 1258: "Saturated fat (g)", 1093: "Sodium (mg)",
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
    *, user_id: int, image_b64: str, name_hint: str = ""
) -> tuple[dict[str, Any], float]:
    """Transcribe a packaged food's panel into a per-100 g composition.

    Same amendment as the supplement panel: a model may transcribe a printed
    figure, never estimate one. The difference from a supplement is the
    per-serving column, which on cereal routinely means "with 125 ml milk" and
    describes a bowl rather than a product — so the tool is asked which column
    it read and told to prefer per 100 g.
    """
    content: list[dict[str, Any]] = [{
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
    }]
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
