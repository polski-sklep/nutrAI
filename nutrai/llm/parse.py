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

    conf = float(res.data.get("overall_confidence", 0) or 0)
    if escalate and conf < CONFIDENCE_ESCALATE:
        res2 = await call_tool(
            model=MODEL_PHOTO_ESCALATE,
            tool=PARSE_TOOL,
            system=[cached(PARSE_SYSTEM)],
            content=content,
        )
        await _log(res2, "photo_parse_escalated", user_id)
        if float(res2.data.get("overall_confidence", 0) or 0) > conf:
            res = res2

    return _to_meal(res)


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

        query = str(it.get("search_terms") or label)
        cands = await db.search_foods(query, limit=5)
        if cands and float(cands[0]["sim"] or 0) >= AUTO_MATCH_SIMILARITY:
            await _accept(label, cands[0]["fdc_id"], it)
            await db.upsert_alias(user_id, label, cands[0]["fdc_id"], float(it.get("grams", 0) or 0))
            continue
        if not cands:
            unresolved.append(label)
            continue
        need_model.append((it, cands))

    if need_model:
        lines = []
        for it, cands in need_model:
            opts = " | ".join(
                f"{c['fdc_id']}: {c['description']} [{c['data_type']}]" for c in cands
            )
            lines.append(
                f"- label: {it.get('label')} (logged as {it.get('state','unknown')}, "
                f"{it.get('grams')} g)\n  candidates: {opts}"
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
        by_label = {str(c.get("label", "")).lower(): c for c in res.data.get("choices", [])}
        for it, _cands in need_model:
            label = str(it.get("label", ""))
            pick = by_label.get(label.lower())
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

    for c in components:
        if c.grams > 1500:
            warnings.append(f"{c.label}: {c.grams:.0f} g is implausible for one sitting")
        if c.yield_factor > 3.0 or c.yield_factor < 0.3:
            warnings.append(f"{c.label}: yield factor {c.yield_factor:.2f} is extreme")

    for it in parsed.items:
        if str(it.get("state")) == "unknown" and float(it.get("grams", 0) or 0) > 80:
            warnings.append(
                f"{it.get('label')}: raw or cooked is unknown, and that is a 30-100% swing"
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
