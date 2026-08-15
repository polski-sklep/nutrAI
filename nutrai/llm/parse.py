from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any

from PIL import Image

from .. import db
from ..config import (
    AUTO_MATCH_SIMILARITY,
    CONFIDENCE_ESCALATE,
    ENERGY_KCAL,
    IMAGE_JPEG_QUALITY,
    IMAGE_LONG_EDGE,
    MODEL_CHEAP,
    MODEL_PHOTO,
    MODEL_PHOTO_ESCALATE,
    MODEL_TEXT,
)
from ..core.estimate import MassEstimate, choose_mass
from ..core.nutrition import ResolvedComponent, energy_cross_check, total_nutrients
from .client import ToolResult, cached, call_tool
from .schemas import (
    DISAMBIGUATE_SYSTEM,
    DISAMBIGUATE_TOOL,
    MODIFIER_SYSTEM,
    MODIFIER_TOOL,
    PARSE_SYSTEM,
    PARSE_TOOL,
)


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
    image_b64: str, caption: str | None, *, user_id: int, escalate: bool = True
) -> ParsedMeal:
    """Vision parse with one conditional escalation.

    Escalation is conditional on the model's own reported confidence rather
    than run always: on a clearly weighed single ingredient the small model is
    right and the large one costs 2.5x for nothing. On an ambiguous plate the
    escalation is the difference between a usable number and a guess.
    """
    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
        }
    ]
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


async def _mass_for(user_id: int, fdc_id: int, it: dict[str, Any]) -> MassEstimate:
    """Weighed beats stated beats your own history beats the model's eyes."""
    source = str(it.get("grams_source", "estimate"))
    grams = float(it.get("grams", 0) or 0)
    low = float(it["grams_low"]) if it.get("grams_low") else None
    high = float(it["grams_high"]) if it.get("grams_high") else None
    history: list[float] = []
    if source not in ("scale", "stated", "package"):
        history = await db.portion_history(user_id, fdc_id)
    return choose_mass(grams, source, low=low, high=high, history=history)


async def _candidates(it: dict[str, Any], label: str) -> list[Any]:
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
    queries = [q for q in (str(it.get("search_terms") or "").strip(), label.strip()) if q]
    pooled: dict[int, Any] = {}
    for q in dict.fromkeys(queries):
        for c in await db.search_foods(q, limit=5):
            best = pooled.get(c["fdc_id"])
            if best is None or float(c["sim"] or 0) > float(best["sim"] or 0):
                pooled[c["fdc_id"]] = c
    # Rank by similarity, precedence breaking ties — the same order
    # db.search_foods uses, applied across the pooled result.
    return sorted(
        pooled.values(),
        key=lambda c: (-float(c["sim"] or 0), int(c["precedence"] or 9)),
    )[:5]


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


async def resolve_items(user_id: int, items: list[dict[str, Any]]) -> Resolution:
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
    notes: list[str] = []
    need_model: list[tuple[dict[str, Any], list[Any]]] = []
    cost = 0.0

    async def _accept(label: str, fdc_id: int, it: dict[str, Any], yf: float = 1.0) -> None:
        m = await _mass_for(user_id, fdc_id, it)
        comps.append(ResolvedComponent(label, fdc_id, m.grams, yf, m.sigma, m.source))
        sources.append(m.source)
        if m.note:
            notes.append(f"{label}: {m.grams:.0f} g from {m.note}")

    for it in items:
        label = str(it.get("label", "")).strip()
        if not label or float(it.get("grams", 0) or 0) <= 0:
            continue

        alias = await db.resolve_alias(user_id, label)
        if alias:
            await db.bump_alias(alias["id"])
            await _accept(label, alias["fdc_id"], it)
            continue

        cands = await _candidates(it, label)
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
            continue
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

    return Resolution(comps, sources, unresolved, cost, bool(need_model), notes)


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

    for it in parsed.items:
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
