"""Every message the bot sends is built here, from SQL, with no model call.

Summaries are the highest-frequency interaction in a tracker. Routing them
through a language model is the most expensive mistake available: it costs
money per view, adds seconds of latency, and introduces the possibility that
your daily total is wrong in a way you will not detect. A template cannot get
the arithmetic wrong.

Output is Telegram HTML, not Markdown. Legacy Markdown has no defined escape
syntax, so a food called `chicken_breast` or a USDA row containing a lone `*`
either mangles the message or gets it rejected outright with HTTP 400 — and a
rejected confirmation card leaves the entry sitting in `pending` while the user
sees nothing at all. HTML needs exactly three characters escaped, `html.escape`
does it correctly, and there is no ambiguity about whether escaping is
supported.
"""

from __future__ import annotations

import datetime as dt
from html import escape
from typing import Any, Sequence

BAR_FULL = "█"
BAR_EMPTY = "░"

# Below this fraction of the day's mass, a nutrient total is materially
# incomplete and the row says so. 0.995 rather than 1.0 because floating-point
# mass sums land a hair under.
COVERAGE_FULL = 0.995


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

    lines = [f"<b>{_esc(dish_name)}</b>"]
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
            lines.append(f"  {mark} {_esc(str(label))} — {grams:.0f} g  <i>({span})</i>")
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
        lines.append(f"<i>note: {_esc(notes)}</i>")
    for w in warnings:
        lines.append(f"⚠ {_esc(w)}")
    if cost_usd:
        lines.append(f"<i>{cost_usd*100:.2f}¢</i>")
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
    coverage: dict[int, float] | None = None,
) -> str:
    from ..config import CARB, ENERGY_KCAL, FAT, PROTEIN

    by_id = {r["nutrient_id"]: r for r in progress}
    lines = [f"<b>{day:%a %-d %b}</b>"]

    # One <pre> for the whole nutrient table. Wrapping each line in its own
    # <code> span does not preserve column alignment: Telegram renders adjacent
    # spans in a proportional context, so the bars and percentages drift out of
    # line down the message. A single preformatted block is the only way the
    # columns stay columns, which means section headings inside it are plain
    # text rather than <b> — nested tags are not allowed in <pre>.
    table: list[str] = []

    head = by_id.get(ENERGY_KCAL)
    if head:
        # asyncpg hands back `numeric` as decimal.Decimal, which will not divide
        # into a float. Coerce at the boundary, as every other reader of these
        # rows does — this function is the only one that was taking the raw value.
        cap = float(head["max_amount"] or head["min_amount"] or 0)
        amount = float(head["amount"])
        pct = (amount / cap * 100) if cap else 0
        pm = f" ± {energy_sigma:,.0f}" if energy_sigma and amount and energy_sigma / amount > 0.03 else ""
        table.append(f"{bar(pct)} {amount:,.0f}{pm} / {cap:,.0f} kcal")

    cov = coverage or {}
    for nid in (PROTEIN, CARB, FAT):
        r = by_id.get(nid)
        if not r:
            continue
        table.append(_row(r, cov.get(nid)))

    # A nutrient nothing on the plate reports is not a shortfall, and listing it
    # under "attention" is the phantom-deficiency failure. It moves to a
    # separate, explicitly-labelled group instead of being dropped, because
    # "nobody measured this" is itself worth seeing.
    rest, unmeasured = [], []
    for r in progress:
        if r["nutrient_id"] in (ENERGY_KCAL, PROTEIN, CARB, FAT):
            continue
        c = cov.get(r["nutrient_id"])
        if c is not None and c <= 0 and float(r["amount"]) <= 0:
            unmeasured.append(r)
        elif show_all or r["state"] != "ok":
            rest.append(r)

    if rest:
        table.append("")
        table.append("attention" if not show_all else "micronutrients")
        for r in sorted(rest, key=lambda x: (x["state"] == "ok", x["nutrient_name"])):
            table.append(_row(r, cov.get(r["nutrient_id"])))

    if entries:
        table.append("")
        for e in entries:
            when = e["logged_at"].strftime("%H:%M")
            slot = (e["slot"] or "").upper()[:6]
            table.append(
                f"{when} {slot:<6} {_esc(e['name'])} — "
                f"{float(e['kcal']):,.0f} kcal, {float(e['protein']):.0f} g P"
            )

    if table:
        lines.append("<pre>" + "\n".join(table) + "</pre>")

    if pct_measured is not None:
        # The number that decides whether anything above it is worth reading.
        verdict = "" if pct_measured >= 80 else "  ← weigh more" if pct_measured < 50 else ""
        lines.append(f"<i>{pct_measured:.0f}% of today's mass was weighed or stated{verdict}</i>")

    if unmeasured:
        lines.append("")
        lines.append("<b>not measured</b> — no food you logged today reports these")
        lines.append("  " + _esc(", ".join(sorted(r["nutrient_name"][:24] for r in unmeasured))))

    if not entries:
        lines.append("\n<i>nothing logged yet</i>")
    return "\n".join(lines)


def _row(r: Any, covered: float | None = None) -> str:
    amount = float(r["amount"])
    unit = r["unit"]
    target = r["min_amount"] if r["min_amount"] is not None else r["max_amount"]
    pct = (amount / float(target) * 100) if target else 0
    flag = {"over": "▲", "under": "▽", "ok": " "}[r["state"]]
    # Pad before escaping. `&` in a nutrient name becomes `&amp;` — five source
    # characters that render as one — so padding the escaped string lines the
    # columns up in the source and not on screen.
    name = f"{r['nutrient_name'][:22]:<22}"
    line = (
        f"{flag} {_esc(name)} {fmt_amount(amount, unit):>12}"
        f"  {pct:>5.0f}% {bar(pct, 8)}"
    )
    # Below full coverage the figure is a lower bound, not a total. Say so, or
    # the number reads as a measurement of the plate rather than of part of it.
    # Plain parentheses, not <i>: this line lives inside a <pre> block, and
    # Telegram does not accept nested tags there.
    if covered is not None and covered < COVERAGE_FULL:
        line += f"  ({covered:.0%} measured)"
    return line


# ------------------------------------------------------------ repeat menu


def repeat_menu(dishes: Sequence[Any], templates: Sequence[Any] = ()) -> str:
    lines = ["<b>repeat</b> — reply with a number, or a number plus a change"]
    for i, d in enumerate(dishes, 1):
        slot = f" · {_esc(d['default_slot'])}" if d["default_slot"] else ""
        lines.append(f"<code>{i}</code> {_esc(d['name'])}{slot}  ×{d['times_logged']}")
    if templates:
        lines.append("")
        for t in templates:
            lines.append(f"<code>{_esc(t['slug'])}</code> {_esc(t['name'])}")
    lines += [
        "",
        "<code>3</code> as before · <code>3 250</code> set total · <code>3 x1.5</code> scale",
        "<code>3 -onion</code> drop · <code>3 +50 rice</code> add · <code>3 rice 200</code> set one",
        "<code>3 @14:00</code> time · <code>3 #lunch</code> slot",
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
    """Escape text for Telegram HTML.

    quote=False on purpose: only `& < >` carry meaning in Telegram's HTML
    subset, and turning every apostrophe in "Farmer's cheese" into `&#x27;`
    makes the source unreadable for no gain.
    """
    return escape(str(s), quote=False)
