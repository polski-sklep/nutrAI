"""Every message the bot sends is built here, from SQL, with no model call.

Summaries are the highest-frequency interaction in a tracker. Routing them
through a language model is the most expensive mistake available: it costs
money per view, adds seconds of latency, and introduces the possibility that
your daily total is wrong in a way you will not detect. A template cannot get
the arithmetic wrong.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

BAR_FULL = "█"
BAR_EMPTY = "░"


def bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def fmt_amount(value: float, unit: str) -> str:
    u = unit.upper()
    if u == "KCAL":
        return f"{value:,.0f} kcal"
    if u == "G":
        return f"{value:.1f} g" if value < 10 else f"{value:.0f} g"
    if u == "MG":
        return f"{value:.0f} mg" if value >= 1 else f"{value:.2f} mg"
    if u == "UG":
        return f"{value:.1f} µg" if value < 10 else f"{value:.0f} µg"
    return f"{value:.1f} {unit.lower()}"


# ------------------------------------------------------- confirmation card


def confirm_card(
    dish_name: str,
    components: Sequence[Any],
    totals: dict[int, float],
    *,
    confidence: float | None,
    warnings: Sequence[str],
    notes: str = "",
    cost_usd: float | None = None,
) -> str:
    from ..config import CARB, ENERGY_KCAL, FAT, FIBER, PROTEIN

    lines = [f"*{_esc(dish_name)}*"]
    for c in components:
        label = getattr(c, "label", None) or c["label"]
        grams = float(getattr(c, "grams", None) or c["grams"])
        src = getattr(c, "grams_source", "") or ""
        sigma = float(getattr(c, "sigma", 0) or 0)
        mark = {"scale": "⚖", "stated": "✎", "package": "▤", "prior": "↺"}.get(src, "≈")
        # An eyeballed mass is shown as the range it actually is. Seeing
        # "120-260 g" next to the oil is what makes you reach for the scale.
        if sigma > 0 and src in ("estimate", "prior") and sigma / max(grams, 1) > 0.08:
            span = f"{max(0, grams - 2*sigma):.0f}–{grams + 2*sigma:.0f} g"
            lines.append(f"  {mark} {_esc(str(label))} — {grams:.0f} g  _({span})_")
        else:
            lines.append(f"  {mark} {_esc(str(label))} — {grams:.0f} g")

    lines.append("")
    lines.append(
        f"{totals.get(ENERGY_KCAL,0):,.0f} kcal · "
        f"P {totals.get(PROTEIN,0):.0f} g · "
        f"C {totals.get(CARB,0):.0f} g · "
        f"F {totals.get(FAT,0):.0f} g · "
        f"fibre {totals.get(FIBER,0):.0f} g"
    )
    if confidence is not None:
        lines.append(f"confidence {confidence:.0%}")
    if notes:
        lines.append(f"_note: {_esc(notes)}_")
    for w in warnings:
        lines.append(f"⚠ {_esc(w)}")
    if cost_usd:
        lines.append(f"_{cost_usd*100:.2f}¢_")
    lines.append("")
    lines.append("Nothing is logged until you confirm.")
    return "\n".join(lines)


# --------------------------------------------------------------- day view


def day_card(
    day: dt.date,
    progress: Sequence[Any],
    entries: Sequence[Any],
    *,
    show_all: bool = False,
    pct_measured: float | None = None,
    energy_sigma: float = 0.0,
) -> str:
    from ..config import CARB, ENERGY_KCAL, FAT, PROTEIN

    by_id = {r["nutrient_id"]: r for r in progress}
    lines = [f"*{day:%a %-d %b}*"]

    head = by_id.get(ENERGY_KCAL)
    if head:
        cap = head["max_amount"] or head["min_amount"] or 0
        amount = float(head["amount"])
        pct = (amount / cap * 100) if cap else 0
        pm = f" ± {energy_sigma:,.0f}" if energy_sigma and amount and energy_sigma / amount > 0.03 else ""
        lines.append(f"`{bar(pct)}` {amount:,.0f}{pm} / {float(cap):,.0f} kcal")
    if pct_measured is not None:
        # The number that decides whether anything below it is worth reading.
        verdict = "" if pct_measured >= 80 else "  ← weigh more" if pct_measured < 50 else ""
        lines.append(f"_{pct_measured:.0f}% of today's mass was weighed or stated{verdict}_")

    for nid in (PROTEIN, CARB, FAT):
        r = by_id.get(nid)
        if not r:
            continue
        lines.append(_row(r))

    rest = [
        r for r in progress
        if r["nutrient_id"] not in (ENERGY_KCAL, PROTEIN, CARB, FAT)
        and (show_all or r["state"] != "ok")
    ]
    if rest:
        lines.append("")
        lines.append("*attention*" if not show_all else "*micronutrients*")
        for r in sorted(rest, key=lambda x: (x["state"] == "ok", x["nutrient_name"])):
            lines.append(_row(r))

    if entries:
        lines.append("")
        for e in entries:
            when = e["logged_at"].strftime("%H:%M")
            slot = (e["slot"] or "").upper()[:6]
            lines.append(
                f"`{when}` {slot:<6} {_esc(e['name'])} — "
                f"{float(e['kcal']):,.0f} kcal, {float(e['protein']):.0f} g P"
            )
    else:
        lines.append("\n_nothing logged yet_")
    return "\n".join(lines)


def _row(r: Any) -> str:
    amount = float(r["amount"])
    unit = r["unit"]
    target = r["min_amount"] if r["min_amount"] is not None else r["max_amount"]
    pct = (amount / float(target) * 100) if target else 0
    flag = {"over": "▲", "under": "▽", "ok": " "}[r["state"]]
    return (
        f"{flag} {r['nutrient_name'][:22]:<22} {fmt_amount(amount, unit):>12}"
        f"  {pct:>5.0f}% `{bar(pct, 8)}`"
    )


# ------------------------------------------------------------ repeat menu


def repeat_menu(dishes: Sequence[Any], templates: Sequence[Any] = ()) -> str:
    lines = ["*repeat* — reply with a number, or a number plus a change"]
    for i, d in enumerate(dishes, 1):
        slot = f" · {d['default_slot']}" if d["default_slot"] else ""
        lines.append(f"`{i}` {_esc(d['name'])}{slot}  ×{d['times_logged']}")
    if templates:
        lines.append("")
        for t in templates:
            lines.append(f"`{t['slug']}` {_esc(t['name'])}")
    lines += [
        "",
        "`3` as before · `3 250` set total · `3 x1.5` scale",
        "`3 -onion` drop · `3 +50 rice` add · `3 rice 200` set one",
        "`3 @14:00` time · `3 #lunch` slot",
    ]
    return "\n".join(lines)


# --------------------------------------------------------- notifications


def threshold_message(nutrient_name: str, amount: float, target: float, unit: str, direction: str) -> str:
    pct = amount / target * 100 if target else 0
    if direction == "over":
        return (
            f"▲ {nutrient_name}: {fmt_amount(amount, unit)} — {pct:.0f}% of your "
            f"{fmt_amount(target, unit)} ceiling."
        )
    remaining = max(0.0, target - amount)
    return (
        f"▽ {nutrient_name}: {fmt_amount(amount, unit)} — {pct:.0f}% of your floor. "
        f"{fmt_amount(remaining, unit)} to go."
    )


def _esc(s: str) -> str:
    for ch in ("_", "*", "[", "]", "`"):
        s = s.replace(ch, "\\" + ch)
    return s
