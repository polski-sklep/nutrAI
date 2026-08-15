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
    unresolved: Sequence[str] = (),
) -> str:
    from ..config import CARB, ENERGY_KCAL, FAT, FIBER, PROTEIN

    lines = [f"🍽 <b>{_esc(dish_name)}</b>", ""]

    # Unmatched items go first, before any total.
    #
    # They used to be one warning line among several, printed *below* a
    # confident "160 kcal". A real meal went through where three of four items
    # were missing and the card still led with a tidy number, so it got
    # confirmed — logging a fifth of what was eaten. A total computed from part
    # of a plate is not a small error, it is a different meal, and it has to be
    # impossible to read past.
    if unresolved:
        n = len(unresolved)
        total_items = n + len(components)
        lines.append(
            f"❗️ <b>{n} of {total_items} items are not in the food database.</b> "
            "The totals below do <b>not</b> include them:"
        )
        lines += [f"   • {_esc(str(u))}" for u in unresolved]
        lines.append("")
        lines.append("<b>Counted:</b>" if components else "")

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
            lines.append(f"   • {mark} {_esc(str(label))} — {grams:.0f} g <i>({span})</i>")
        else:
            lines.append(f"   • {mark} {_esc(str(label))} — {grams:.0f} g")

    lines.append("")
    lines.append(
        f"📊 <b>{totals.get(ENERGY_KCAL,0):,.0f} kcal</b>"
        f" · 🥩 {totals.get(PROTEIN,0):.0f} g protein"
        f" · 🍞 {totals.get(CARB,0):.0f} g carbs"
        f" · 🧈 {totals.get(FAT,0):.0f} g fat"
        f" · 🌾 {totals.get(FIBER,0):.0f} g fibre"
    )
    if confidence is not None:
        lines.append(f"🎯 confidence {confidence:.0%}")
    if notes:
        lines.append("")
        lines.append(f"📝 <i>{_esc(notes)}</i>")
    if warnings:
        lines.append("")
        lines += [f"⚠️ {_esc(w)}" for w in warnings]
    if cost_usd:
        lines.append("")
        lines.append(f"<i>💸 {cost_usd*100:.2f}¢</i>")
    lines.append("")
    lines.append("Nothing is logged until you confirm.")
    return "\n".join(lines)


# ------------------------------------------------------ after the confirm

# Emoji are load-bearing here, not decoration: they let a bulleted list be
# scanned by shape rather than read word by word. One per nutrient, stable, so
# the same nutrient always looks the same from one day to the next.
NUTRIENT_EMOJI: dict[int, str] = {
    1008: "🔥",  # Energy
    1003: "🥩",  # Protein
    1005: "🍞",  # Carbohydrate
    1004: "🧈",  # Fat
    1079: "🌾",  # Fibre
    2000: "🍬",  # Sugar
    1258: "🥓",  # Saturated fat
    1093: "🧂",  # Sodium
    1092: "🍌",  # Potassium
    1087: "🦴",  # Calcium
    1089: "🩸",  # Iron
    1090: "🌰",  # Magnesium
    1095: "🦪",  # Zinc
    1178: "🐟",  # B-12
    1114: "☀️",  # Vitamin D
    1162: "🍊",  # Vitamin C
    1106: "🥕",  # Vitamin A
    1177: "🥬",  # Folate
    1253: "🥚",  # Cholesterol
    1272: "🐠",  # DHA
}


def _emoji(nutrient_id: int) -> str:
    return NUTRIENT_EMOJI.get(nutrient_id, "•")


def logged_card(
    dish_name: str,
    meal: dict[int, float],
    progress: Sequence[Any],
    *,
    top_n: int = 4,
    gaps_n: int = 3,
) -> str:
    """What to say the moment something is written to the log.

    Three questions, in the order they are actually asked: where am I now, what
    did this meal do for me, and what is still missing. All of it is one SQL
    read plus arithmetic — no model, per invariant 4.
    """
    from ..config import CARB, ENERGY_KCAL, FAT, FIBER, PROTEIN

    by_id = {r["nutrient_id"]: r for r in progress}
    lines = [f"✅ <b>Logged</b> — {_esc(dish_name)}", ""]

    # --- where the day stands
    lines.append("📊 <b>Today so far</b>")
    for nid in (ENERGY_KCAL, PROTEIN, FIBER, CARB, FAT):
        r = by_id.get(nid)
        if not r:
            continue
        amount = float(r["amount"])
        target = r["min_amount"] if r["min_amount"] is not None else r["max_amount"]
        if target is None:
            lines.append(f"   • {_emoji(nid)} {_esc(r['nutrient_name'])} — "
                         f"{fmt_amount(amount, r['unit'])}")
            continue
        target = float(target)
        pct = amount / target * 100 if target else 0
        cap = "ceiling" if r["min_amount"] is None else "target"
        lines.append(
            f"   • {_emoji(nid)} {_esc(_short(r['nutrient_name']))} — "
            f"<b>{fmt_amount(amount, r['unit'])}</b> of {fmt_amount(target, r['unit'])} "
            f"{cap} ({pct:.0f}%)"
        )

    # --- what this meal actually brought
    # Ranked by share of the day's floor, not by absolute amount: 7 g of fibre
    # matters more than 300 mg of potassium, and only the target says so.
    brought = []
    for nid, amt in meal.items():
        r = by_id.get(nid)
        if not r or r["min_amount"] is None or nid == ENERGY_KCAL:
            continue
        floor = float(r["min_amount"])
        if floor <= 0 or amt <= 0:
            continue
        brought.append((amt / floor, nid, amt, r))
    brought.sort(reverse=True)
    if brought:
        lines.append("")
        lines.append("⭐ <b>What this meal brought most</b>")
        for share, nid, amt, r in brought[:top_n]:
            lines.append(
                f"   • {_emoji(nid)} {_esc(_short(r['nutrient_name']))} — "
                f"{fmt_amount(amt, r['unit'])} ({share*100:.0f}% of today's target)"
            )

    # --- what is still missing
    gaps = []
    for nid, r in by_id.items():
        if r["min_amount"] is None:
            continue
        floor = float(r["min_amount"])
        remaining = floor - float(r["amount"])
        if floor <= 0 or remaining <= 0:
            continue
        gaps.append((remaining / floor, nid, remaining, r))
    gaps.sort(reverse=True)

    # Protein and fibre are always named whether or not they are the worst
    # gaps — they are the two you can still act on with what you eat next.
    pinned = [g for g in gaps if g[1] in (PROTEIN, FIBER)]
    others = [g for g in gaps if g[1] not in (PROTEIN, FIBER)][:gaps_n]
    shown = pinned + others
    if shown:
        lines.append("")
        lines.append("🎯 <b>Still to go today</b>")
        for _share, nid, remaining, r in shown:
            lines.append(
                f"   • {_emoji(nid)} {_esc(_short(r['nutrient_name']))} — "
                f"{fmt_amount(remaining, r['unit'])}"
            )
    elif by_id:
        lines.append("")
        lines.append("🎯 Every floor met today.")

    return "\n".join(lines)


def _short(name: str) -> str:
    """USDA names are database entries, not English. Tidy the common ones."""
    return {
        "Carbohydrate, by difference": "Carbs",
        "Total lipid (fat)": "Fat",
        "Fiber, total dietary": "Fibre",
        "Fatty acids, total saturated": "Saturated fat",
        "Vitamin C, total ascorbic acid": "Vitamin C",
        "Vitamin D (D2 + D3)": "Vitamin D",
        "Vitamin A, RAE": "Vitamin A",
        "Folate, total": "Folate",
        "PUFA 22:6 n-3 (DHA)": "DHA",
        "Energy": "Energy",
    }.get(name, name.split(",")[0])


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
    # A micronutrient met by a capsule is different information from one met by
    # food, and the difference has to survive to the screen or it may as well
    # not be stored.
    supp = r["amount_supplement"] if "amount_supplement" in r else None
    if supp is not None and float(supp) > 0:
        line += f"  (+{fmt_amount(float(supp), unit)} 💊)"
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


def audit_card(findings: Sequence[Any]) -> str:
    """The daily self-check, grouped by how much it matters.

    Errors first because they mean a number in the log is wrong, not merely
    uncertain — and a wrong number that nobody corrects becomes a median, then
    a trend, then a recommendation.
    """
    if not findings:
        return "🩺 <b>Daily check</b>\n\nNothing to flag. The log looks sound."

    icons = {"error": "❌", "warn": "⚠️", "info": "💡"}
    titles = {
        "error": "Wrong, not just uncertain",
        "warn": "Worth a look",
        "info": "Would pay off later",
    }

    lines = ["🩺 <b>Daily check</b>"]
    for severity in ("error", "warn", "info"):
        group = [f for f in findings if f.severity == severity]
        if not group:
            continue
        lines.append("")
        lines.append(f"{icons[severity]} <b>{titles[severity]}</b>")
        for f in group:
            lines.append(f"   • <b>{_esc(f.summary)}</b>")
            lines.append(f"     {_esc(f.detail)}")

    if any(f.severity == "error" for f in findings):
        lines.append("")
        lines.append(
            "<i>Fix an entry by sending it again and pressing ✏️, or ignore this "
            "if the match was right after all.</i>"
        )
    return "\n".join(lines)


def threshold_message(
    nutrient_name: str,
    amount: float,
    target: float,
    unit: str,
    direction: str,
    nutrient_id: int = 0,
) -> str:
    """One threshold crossing, as HTML.

    Two lines rather than one: the headline is what happened, the second line is
    the number you would act on. A single run-on sentence made a ceiling breach
    and a floor reminder look identical at a glance, which is the opposite of
    what a notification is for.
    """
    pct = amount / target * 100 if target else 0
    icon = _emoji(nutrient_id)
    name = _esc(_short(nutrient_name))

    if direction == "over":
        over = amount - target
        return (
            f"⚠️ <b>{name} — {fmt_amount(amount, unit)}</b>\n"
            f"{icon} {pct:.0f}% of your {fmt_amount(target, unit)} ceiling"
            + (f" · {fmt_amount(over, unit)} over" if over > 0 else "")
        )

    remaining = max(0.0, target - amount)
    return (
        f"🔔 <b>{name} — {fmt_amount(amount, unit)}</b>\n"
        f"{icon} {pct:.0f}% of your {fmt_amount(target, unit)} floor · "
        f"{fmt_amount(remaining, unit)} to go"
    )


def _esc(s: str) -> str:
    """Escape text for Telegram HTML.

    quote=False on purpose: only `& < >` carry meaning in Telegram's HTML
    subset, and turning every apostrophe in "Farmer's cheese" into `&#x27;`
    makes the source unreadable for no gain.
    """
    return escape(str(s), quote=False)


def supplement_stack_card(stack: Sequence[Any]) -> str:
    lines = ["💊 <b>Your daily stack</b>", ""]
    for s in stack:
        serving = f"{float(s['servings_per_day']):g} × {s['serving_desc']}"
        mark = "" if s["verified_at"] else "  <i>(unverified)</i>"
        lines.append(f"   • <b>{_esc(s['name'])}</b> — {_esc(serving)}{mark}")
        lines.append(f"     {s['n_nutrients']} nutrient(s) from its label")
    lines += ["", "<code>/supp</code> logs the lot for today."]
    return "\n".join(lines)


def supplement_confirm_card(
    name: str, serving_desc: str, kept: Sequence[Any], dropped: Sequence[Any],
    names: dict[int, str], units: dict[int, str],
) -> str:
    """What was read off the label, before it is saved.

    Everything downstream trusts these numbers completely — they go straight
    into a daily total with no plate to check them against — so this card is the
    only place a misread digit can be caught. It shows every line, including the
    ones that were rejected, because a nutrient silently missing from a panel is
    indistinguishable from one the product does not contain.
    """
    lines = [f"💊 <b>{_esc(name)}</b>", f"per {_esc(serving_desc)}", ""]
    for c in kept:
        unit = units.get(c.nutrient_id, "")
        lines.append(
            f"   • {_esc(names.get(c.nutrient_id, str(c.nutrient_id)))} — "
            f"{fmt_amount(c.amount, unit)}"
        )
    if dropped:
        lines.append("")
        lines.append("⚠️ <b>Not recorded</b>")
        for d in dropped:
            label = d.printed_label or names.get(d.nutrient_id, str(d.nutrient_id))
            lines.append(f"   • {_esc(label)} — {_esc(d.reason)}")
    lines += ["", "Check these against the packet. Nothing is saved until you confirm."]
    return "\n".join(lines)


def supplement_pick_card(
    stack: Sequence[Any], selected: Sequence[int], *, had_yesterday: bool
) -> str:
    """Ask which of the stack was actually taken.

    Defaulting to yesterday's set and asking is the difference between a record
    and an assumption. A stack is a habit, not a rule, and the day you skip one
    is exactly the day a silent auto-log puts a number in your totals that never
    went in your mouth.
    """
    sel = set(selected)
    lines = ["💊 <b>Which did you take?</b>", ""]
    lines.append(
        "<i>Same as yesterday, pre-ticked. Tap any to remove.</i>"
        if had_yesterday
        else "<i>Your whole stack, pre-ticked. Tap any to remove.</i>"
    )
    lines.append("")
    for s in stack:
        mark = "✅" if s["id"] in sel else "⬜️"
        lines.append(
            f"   {mark} {_esc(s['name'])} — "
            f"{float(s['servings_per_day']):g} × {_esc(s['serving_desc'])}"
        )
    if not sel:
        lines += ["", "<i>Nothing selected — “log these” would record none.</i>"]
    return "\n".join(lines)
