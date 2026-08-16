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

# A ceiling is worth mentioning before it is crossed, not only after. 0.85 sits
# in the band where there is still a decision to make — at 92% of your energy
# you can choose a smaller dinner; at 104% the only thing left is to know.
CEILING_NEAR = 0.85



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
        count = getattr(c, "count", None)
        if count and float(count) > 1:
            # "3 × 300 g total" makes the reading checkable. Whether 300 g meant
            # per cup or across all three is exactly the kind of thing that is
            # obvious to you and invisible in a total.
            label = f"{float(count):g} × {label}"
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
    1057: "☕",  # Caffeine
    1018: "🍷",  # Alcohol
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
    first_of_day: bool = False,
) -> str:
    """What to say the moment something is written to the log.

    Three questions, in the order they are actually asked: where am I now, what
    did this meal do for me, and what is still missing. All of it is one SQL
    read plus arithmetic — no model, per invariant 4.
    """
    from ..config import CARB, ENERGY_KCAL, FAT, FIBER, PROTEIN

    by_id = {r["nutrient_id"]: r for r in progress}
    lines = [f"✅ <b>Logged</b> — {_esc(dish_name)}", ""]
    if first_of_day:
        lines.append("☀️ <i>Morning. First of the day.</i>")
        lines.append("")

    # --- where the day stands
    lines.append("📊 <b>Today so far</b>")
    for nid in (ENERGY_KCAL, PROTEIN, FIBER, CARB, FAT):
        r = by_id.get(nid)
        if not r:
            continue
        amount = float(r["amount"])
        target = r["min_amount"] if r["min_amount"] is not None else r["max_amount"]
        if target is None:
            lines.append(f"   • {_emoji(nid)} {_esc(_short(r['nutrient_name']))} — "
                         f"{fmt_amount(amount, r['unit'])}")
            continue
        target = float(target)
        pct = amount / target * 100 if target else 0
        cap = "ceiling" if r["min_amount"] is None else "target"
        lines.append(
            f"   • {_emoji(nid)} {_esc(_short(r['nutrient_name']))} — "
            f"{fmt_amount(amount, r['unit'])} of {fmt_amount(target, r['unit'])} "
            f"{cap} <b>({pct:.0f}%)</b>"
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
    # Not on the first entry of the day. "Still to go: protein 175 g" against a
    # cappuccino is arithmetically true and useless — everything is still to go
    # at breakfast, and leading with the shortfall makes the first interaction of
    # the day a reprimand for not having eaten yet.
    if shown and not first_of_day:
        lines.append("")
        lines.append("🎯 <b>Still to go today</b>")
        for _share, nid, remaining, r in shown:
            lines.append(
                f"   • {_emoji(nid)} {_esc(_short(r['nutrient_name']))} — "
                f"{fmt_amount(remaining, r['unit'])}"
            )
    elif by_id and not first_of_day:
        lines.append("")
        lines.append("🎯 Every floor met today.")

    return "\n".join(lines)


# USDA names are database entries, not English. The map is a module constant
# because it has to be invertible: the card prints "Fibre" and the column is
# "Fiber, total dietary", so anything that lets a user type a nutrient name has
# to be able to search the word it showed them.
_SHORT_NAMES: dict[str, str] = {
    "Carbohydrate, by difference": "Carbs",
    "Total lipid (fat)": "Fat",
    "Fiber, total dietary": "Fibre",
    "Fatty acids, total saturated": "Saturated fat",
    "Vitamin C, total ascorbic acid": "Vitamin C",
    "Vitamin D (D2 + D3)": "Vitamin D",
    "Vitamin A, RAE": "Vitamin A",
    "Folate, total": "Folate",
    "PUFA 22:6 n-3 (DHA)": "Omega-3 (DHA)",
    "Alcohol, ethyl": "Alcohol",
    "Energy": "Energy",
    # The chemical symbol is what the USDA column is called, and it reads as a
    # second word rather than as a restatement of the first.
    "Calcium, Ca": "Calcium",
    "Iron, Fe": "Iron",
    "Magnesium, Mg": "Magnesium",
    "Potassium, K": "Potassium",
    "Sodium, Na": "Sodium",
    "Zinc, Zn": "Zinc",
    "Phosphorus, P": "Phosphorus",
    "Selenium, Se": "Selenium",
    "Copper, Cu": "Copper",
    "Manganese, Mn": "Manganese",
    "Vitamin B-12": "Vitamin B12",
    "Vitamin B-6": "Vitamin B6",
    "Vitamin E (alpha-tocopherol)": "Vitamin E",
    "Vitamin K (phylloquinone)": "Vitamin K",
    "Cholesterol": "Cholesterol",
    "Sugars, total including NLEA": "Sugars",
    "Sugars, Total": "Sugars",
}

# Display name -> the USDA name to search for. Spellings people actually type
# are folded in: the card says Fibre and the database says Fiber, and a user
# who types the word on their screen should not be told it does not exist.
DISPLAY_TO_USDA: dict[str, str] = {v.lower(): k for k, v in _SHORT_NAMES.items()}
DISPLAY_TO_USDA.update({
    "fiber": "Fiber, total dietary",
    "carbs": "Carbohydrate, by difference",
    "carbohydrate": "Carbohydrate, by difference",
    "carbohydrates": "Carbohydrate, by difference",
    "sat fat": "Fatty acids, total saturated",
    "saturates": "Fatty acids, total saturated",
    "dha": "PUFA 22:6 n-3 (DHA)",
    "omega-3": "PUFA 22:6 n-3 (DHA)",
    "omega 3": "PUFA 22:6 n-3 (DHA)",
    "calories": "Energy",
    "kcal": "Energy",
    "b12": "Vitamin B-12",
    "b6": "Vitamin B-6",
    "sugar": "Sugars, total including NLEA",
    "salt": "Sodium, Na",
})


def _short(name: str) -> str:
    """USDA names are database entries, not English. Tidy the common ones."""
    return _SHORT_NAMES.get(name, name.split(",")[0])


def usda_name_for(term: str) -> str | None:
    """The database name behind a name shown on a card, if there is one."""
    return DISPLAY_TO_USDA.get(term.strip().lower())


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
    tz: str = "UTC",
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
        table.append("Worth a look" if not show_all else "Vitamins and minerals")
        for r in sorted(rest, key=lambda x: (x["state"] == "ok", _short(x["nutrient_name"]))):
            table.append(_row(r, cov.get(r["nutrient_id"])))

    if entries:
        table.append("")
        import zoneinfo

        zone = zoneinfo.ZoneInfo(tz)
        for e in entries:
            # In the user's own timezone. logged_at is stored in UTC and was
            # being formatted raw, so the day card said 14:09 for a meal every
            # other message called 16:09 — and the disagreement looked like an
            # entry that had failed to disappear.
            when = e["logged_at"].astimezone(zone).strftime("%H:%M")
            slot = (e["slot"] or "").upper()[:6]
            table.append(
                f"{when} {slot:<6} {_esc(e['name'])} — "
                f"{float(e['kcal']):,.0f} kcal, {float(e['protein']):.0f} g P"
            )

    score = score_line(progress, coverage)
    if score:
        lines.append(score)
        lines.append("")
    if table:
        lines.append("<pre>" + "\n".join(table) + "</pre>")

    if pct_measured is not None:
        # The number that decides whether anything above it is worth reading.
        # Said plainly: "mass was weighed or stated" is precise and opaque, and
        # the reader has to work out that the rest of it was guesswork.
        if pct_measured >= 80:
            note = f"⚖️ <b>{pct_measured:.0f}%</b> of today's food was weighed or you told me the amount — the numbers above are solid."
        elif pct_measured >= 50:
            note = f"⚖️ <b>{pct_measured:.0f}%</b> of today's food was weighed or you told me the amount. The rest is my estimate."
        else:
            note = f"⚖️ only <b>{pct_measured:.0f}%</b> of today's food was weighed or stated, so most of the above is guesswork. Stating amounts will sharpen it."
        lines.append(f"<i>{note}</i>")

    if unmeasured:
        lines.append("")
        lines.append("<b>not measured</b> — no food you logged today reports these")
        lines.append("  " + _esc(", ".join(sorted(_short(r["nutrient_name"]) for r in unmeasured))))

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
    # _short() existed and this never called it, so the raw database column
    # name was truncated mid-word instead: "Carbohydrate, by diffe".
    name = f"{_short(r['nutrient_name'])[:22]:<22}"
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
        # "(60% measured)" was read as "you have eaten 60% of it". It means
        # something quite different: 40% of what you ate sits in a USDA row
        # that never had this nutrient assayed, so the figure is a floor.
        line += f"  (only {covered:.0%} of food has data)"
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
    # The footer used to demonstrate every operator prefixed with a literal 3,
    # which reads as a reference to item 3 in the list above rather than as a
    # placeholder. Say the number once, then list what can follow it.
    lines += [
        "",
        "<i>Reply with the number alone to log it unchanged, or follow it with:</i>",
        "<code>x1.5</code> scale · <code>250</code> set total · <code>-onion</code> drop",
        "<code>+50 rice</code> add · <code>rice 200</code> set one",
        "<code>@14:00</code> time · <code>@yesterday</code> day · <code>#lunch</code> slot",
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


def supplement_stack_card(stack: Sequence[Any], retired: Sequence[Any] = ()) -> str:
    lines = ["💊 <b>Your daily stack</b>", ""]
    cadence = {"alternate": "every other day", "occasional": "occasional"}
    for i, s in enumerate(stack, start=1):
        serving = f"{float(s['servings_per_day']):g} × {s['serving_desc']}"
        extra = cadence.get(s["schedule"], "")
        lines.append(
            f"   <b>{i}. {_esc(s['name'])}</b> — {_esc(serving)}"
            + (f" · {extra}" if extra else "")
        )
        detail = [f"{s['n_nutrients']} tracked nutrient(s)"]
        if s["brand"]:
            detail.insert(0, _esc(s["brand"]))
        if not s["verified_at"]:
            detail.append("unverified")
        lines.append(f"     <i>{' · '.join(detail)}</i>")
        if s["note"]:
            lines.append(f"     <i>{_esc(s['note'])}</i>")
    if retired:
        # Shown, not hidden. A supplement you stopped still accounts for the
        # micronutrients in every past day, and a stack that silently forgets
        # it makes those days look unexplained.
        lines += ["", "<i>Stopped: " + _esc(", ".join(r["name"] for r in retired)) + "</i>"]
    lines += ["", "<code>/supp</code> logs the lot for today."]
    return "\n".join(lines)


def supplement_batch_card(parsed: Sequence[Any], names: dict, units: dict) -> str:
    """Every product read, with everything that was *not* counted named.

    A nutrient silently missing from a panel is indistinguishable from one the
    product does not contain, and this card is the only place the difference can
    be caught — these numbers go into every future daily total with no plate to
    check them against. So the rejected lines and the untracked actives are
    shown as prominently as the accepted ones.
    """
    lines = [f"💊 <b>{len(parsed)} product(s) read</b>", ""]
    for sup in parsed:
        if not sup["nutrients"]:
            lines.append(
                f"◽️ <b>{_esc(sup['name'])}</b> — saved, but nothing here maps to "
                f"a tracked nutrient"
            )
            if sup.get("not_tracked"):
                lines.append(f"     <i>{_esc(sup['not_tracked'])}</i>")
            lines.append("")
            continue
        cadence = {"alternate": " · every other day", "occasional": " · occasional"}.get(
            sup.get("schedule", "daily"), ""
        )
        dose = float(sup.get("servings_per_day", 1) or 1)
        taken = f"{dose:g} × {sup['serving_desc']}" if dose != 1 else sup["serving_desc"]
        lines.append(f"✅ <b>{_esc(sup['name'])}</b> — {_esc(taken)}{cadence}")
        if sup.get("note"):
            lines.append(f"     <i>{_esc(sup['note'])}</i>")
        for c in sup["_kept"]:
            lines.append(
                f"     • {_esc(names.get(c.nutrient_id, str(c.nutrient_id)))} — "
                f"{fmt_amount(c.amount, units.get(c.nutrient_id, ''))}"
            )
        for d in sup["_dropped"]:
            lines.append(f"     ⚠️ {_esc(d.printed_label or '?')} — {_esc(d.reason)}")
        if sup.get("not_tracked"):
            lines.append(f"     <i>not counted: {_esc(sup['not_tracked'])}</i>")
        lines.append("")
    lines.append("Check these against the packets. Nothing is saved until you confirm.")
    return "\n".join(lines)


def supplement_pick_card(stack: Sequence[Any], selected: Sequence[int]) -> str:
    """The question and the count. The buttons below are the list.

    This used to render every supplement as text *and* as a button, so a stack
    of nine appeared twice in one message with the same tick state in both
    places — which reads as a bug even though both halves were correct, and
    buries the buttons below a screen of text you have already read.
    """
    n, total = len(set(selected)), len(stack)
    lines = ["💊 <b>Which did you take?</b>", ""]
    if n == total:
        lines.append(f"<i>All {total} pre-ticked by their schedule. Tap any to remove.</i>")
    elif n:
        lines.append(
            f"<i>{n} of {total} pre-ticked by their schedule — the rest are every "
            f"other day or occasional. Tap to change.</i>"
        )
    else:
        lines.append(
            "<i>Nothing pre-ticked. Tap the ones you took, then “log these”.</i>"
        )
    return "\n".join(lines)














# ------------------------------------------------------------- day score


def day_score(
    progress: Sequence[Any], coverage: dict[int, float] | None = None
) -> tuple[int, int, list[str], list[str], list[str], int]:
    """(reached, assessable, short, breached, nearing, unmeasured).

    Floors and ceilings are counted separately because they are not the same
    kind of achievement, and mixing them produces nonsense. A ceiling is
    satisfied by eating nothing: on a glass of water you are under your energy,
    fat, carbohydrate, sugar, saturated fat, sodium and cholesterol limits all
    at once, which the first version of this reported as "7 of 20 targets met"
    at breakfast. Nor is a ceiling ever really "met" before the day ends — you
    can still breach it at dinner.

    A floor is different: reaching it is monotonic and means something the
    moment it happens. So the score counts floors, and ceilings appear only
    when one has actually been crossed.
    """
    cov = coverage or {}
    reached = assessable = unmeasured = 0
    short: list[str] = []
    breached: list[str] = []
    nearing: list[str] = []

    for r in progress:
        lo, hi = r["min_amount"], r["max_amount"]
        amount = float(r["amount"])
        c = cov.get(r["nutrient_id"])
        blind = c is not None and c <= 0 and amount <= 0

        if hi is not None and float(hi) > 0:
            share = amount / float(hi)
            if share > 1:
                breached.append(f"{_short(r['nutrient_name'])} {share * 100:.0f}%")
            elif share >= CEILING_NEAR:
                nearing.append(f"{_short(r['nutrient_name'])} {share * 100:.0f}%")

        if lo is None:
            continue
        if blind:
            unmeasured += 1
            continue
        assessable += 1
        if amount >= float(lo):
            reached += 1
        else:
            short.append(_short(r["nutrient_name"]))

    return reached, assessable, short, breached, nearing, unmeasured


def score_line(progress: Sequence[Any], coverage: dict[int, float] | None = None) -> str:
    """One bar for the day, counting the thing worth counting.

    Deliberately not a single number in isolation. A score that hides which
    target was missed invites optimising the score, and the number that is
    easiest to move is rarely the one worth moving.
    """
    reached, assessable, short, breached, nearing, unmeasured = day_score(progress, coverage)
    out: list[str] = []

    if assessable:
        pct = reached / assessable * 100
        face = "🟢" if pct >= 80 else "🟡" if pct >= 50 else "🔴"
        # "floors reached" is the internal word for it, and it reads as
        # jargon on a phone. What the number means is: of the daily minimums
        # that can be judged today, how many are already met.
        out.append(
            f"{face} <b>{reached} of {assessable} daily minimums met</b>  {bar(pct)}  {pct:.0f}%"
        )
        if short:
            shown = ", ".join(_esc(m) for m in short[:6])
            more = f" and {len(short) - 6} more" if len(short) > 6 else ""
            out.append(f"<i>still to go: {shown}{more}</i>")

    if breached:
        out.append(f"⚠️ <b>over:</b> {', '.join(_esc(b) for b in breached)}")
    if nearing:
        out.append(f"🔶 <b>close:</b> {', '.join(_esc(b) for b in nearing)}")

    if unmeasured:
        out.append(f"<i>{unmeasured} not counted — nothing you ate reports them</i>")
    return "\n".join(out)






















# ------------------------------------------------------------- day score






# --------------------------------------------------------- weekly report


def week_card(rows: Sequence[Any], ctx: dict) -> str:
    """The week, as the handful of facts worth acting on.

    Ordered by what can change next week rather than by nutrient id: the
    ceilings you crossed repeatedly, then the floors you kept missing, then the
    measurement quality that decides whether any of it is trustworthy. A weekly
    report that lists all twenty nutrients in database order is a report nobody
    reads twice.
    """
    from statistics import median

    if not rows:
        return (
            f"📅 <b>{ctx['start']:%-d %b} – {ctx['end']:%-d %b}</b>\n\n"
            "Nothing logged this week."
        )

    by_nutrient: dict[int, list[Any]] = {}
    for r in rows:
        by_nutrient.setdefault(r["nutrient_id"], []).append(r)

    over: list[tuple[int, int, str, float]] = []   # days over, nid, name, worst share
    under: list[tuple[float, int, str, int, str]] = []  # miss rate, nid, name, days met, median
    for nid, rs in by_nutrient.items():
        name = _short(rs[0]["nutrient_name"])
        unit = rs[0]["unit"]
        amounts = [float(r["amount"]) for r in rs]

        hi = rs[0]["max_amount"]
        if hi is not None and float(hi) > 0:
            shares = [a / float(hi) for a in amounts]
            n_over = sum(1 for sh in shares if sh > 1)
            if n_over:
                over.append((n_over, nid, name, max(shares)))

        lo = rs[0]["min_amount"]
        if lo is not None and float(lo) > 0:
            n_met = sum(1 for a in amounts if a >= float(lo))
            if n_met < len(rs):
                under.append((
                    n_met / len(rs), nid, name, n_met,
                    f"{fmt_amount(median(amounts), unit)} of {fmt_amount(float(lo), unit)}",
                ))

    n_days = len({r["day"] for r in rows})
    lines = [
        f"📅 <b>{ctx['start']:%-d %b} – {ctx['end']:%-d %b}</b>",
        f"<i>{n_days} day{'s' if n_days != 1 else ''} logged · "
        f"{ctx.get('meals') or 0} meals</i>",
    ]

    if over:
        lines += ["", "⚠️ <b>Over the ceiling</b>"]
        for n_over, nid, name, worst in sorted(over, reverse=True)[:6]:
            lines.append(
                f"   • {_emoji(nid)} {_esc(name)} — {n_over} of {n_days} days, "
                f"worst {worst * 100:.0f}%"
            )

    if under:
        lines += ["", "🎯 <b>Floors you kept missing</b>"]
        for _rate, nid, name, n_met, typical in sorted(under)[:6]:
            lines.append(
                f"   • {_emoji(nid)} {_esc(name)} — reached on {n_met} of {n_days} days "
                f"<i>(typical {_esc(typical)})</i>"
            )

    met_every_day = [
        _short(rs[0]["nutrient_name"])
        for rs in by_nutrient.values()
        if rs[0]["min_amount"] is not None and float(rs[0]["min_amount"]) > 0
        and all(float(r["amount"]) >= float(r["min_amount"]) for r in rs)
    ]
    if met_every_day:
        lines += ["", "✅ <b>Every day</b>", "   " + _esc(", ".join(sorted(met_every_day)[:8]))]

    lines += ["", "📊 <b>How much to trust this</b>"]
    pct = ctx.get("pct_measured")
    if pct is not None:
        verdict = "" if float(pct) >= 80 else "  ← the number to move" if float(pct) < 50 else ""
        lines.append(f"   • ⚖️ {float(pct):.0f}% of mass weighed or stated{verdict}")
    if ctx.get("supp_days") is not None:
        lines.append(f"   • 💊 supplements logged on {ctx['supp_days']} of {n_days} days")
    if ctx.get("sessions"):
        lines.append(f"   • 🏋 {ctx['sessions']} training session(s)")

    weights = ctx.get("weights") or []
    if len(weights) >= 2:
        change = weights[-1][1] - weights[0][1]
        lines.append(
            f"   • ⚖ weight {weights[0][1]:g} → {weights[-1][1]:g} kg ({change:+.1f})"
            + ("  <i>a week is mostly water; see /insight</i>" if abs(change) > 0.5 else "")
        )
    elif len(weights) < 2:
        lines.append("   • ⚖ too few weigh-ins to say anything about weight")

    if ctx.get("cents") is not None:
        lines.append(f"   • 💸 {float(ctx['cents']):.1f}¢")

    return "\n".join(lines)


def weight_card(rows: Sequence[Any], tz: str = "UTC") -> str:
    """What you last weighed, and whether there is a trend yet.

    Reading is the common case and the safe one: half the time the question is
    "what was I last?" rather than "record this", and a menu tap should not
    start a write.
    """
    import zoneinfo

    from .insight import MIN_TREND_DAYS

    if not rows:
        return (
            "⚖️ <b>No weigh-ins yet</b>\n\n"
            "<i>The weight trend is the only real measurement of your energy "
            "balance — Mifflin-St Jeor is a ±10% guess. It needs "
            f"{MIN_TREND_DAYS} days to say anything.</i>"
        )

    zone = zoneinfo.ZoneInfo(tz)
    latest = rows[0]
    when = latest["measured_at"].astimezone(zone)
    lines = [f"⚖️ <b>{float(latest['value']):g} kg</b> — {when:%a %-d %b, %H:%M}"]

    if len(rows) > 1:
        prev = rows[1]
        delta = float(latest["value"]) - float(prev["value"])
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "▬"
        lines.append(f"   {arrow} {delta:+.1f} kg since {prev['local_date']:%-d %b}")

    span = (rows[0]["local_date"] - rows[-1]["local_date"]).days + 1
    if span >= MIN_TREND_DAYS:
        first, last = float(rows[-1]["value"]), float(rows[0]["value"])
        lines += [
            "",
            f"📈 {last - first:+.1f} kg across {span} days · "
            "<code>/insight</code> can estimate a rate",
        ]
    else:
        need = MIN_TREND_DAYS - span
        lines += [
            "",
            f"📈 {len(rows)} weigh-in{'s' if len(rows) != 1 else ''}, "
            f"{need} more day{'s' if need != 1 else ''} before a rate means anything",
        ]
    return "\n".join(lines)


# The profile is numbered so a correction can name a line rather than a field:
# `/profile 4 183`. Order is stable — inserting a row in the middle would
# renumber everything below it and turn last week's muscle memory into a wrong
# edit — so new fields go on the end.
PROFILE_ROWS: list[tuple[str, str, str]] = [
    # (field, label, hint shown when setting it)
    ("display_name",    "Name",           "text"),
    ("sex",             "Sex",            "male / female"),
    ("birth_date",      "Date of birth",  "21/09/1991"),
    ("height_cm",       "Height",         "cm"),
    ("activity_factor", "Daily activity", "1 – 5, or tap a button below"),
    ("goal",            "Goal",           "lose / gain / recomp / maintain"),
    ("goal_weight_kg",  "Goal weight",    "kg — optional"),
    ("deficit_kcal",    "Daily deficit",  "kcal"),
    ("tz",              "Timezone",       "e.g. Europe/Warsaw"),
]


def profile_card(data: dict[str, Any], today: dt.date | None = None) -> str:
    """Who the system thinks you are, and what it derived from that."""
    from . import profile as prof

    u = data["user"]
    today = today or dt.date.today()
    age = prof.age_years(u["birth_date"], today)

    lines = ["👤 <b>Your profile</b>", ""]
    rows: list[tuple[str, str]] = []
    for i, (field, label, _hint) in enumerate(PROFILE_ROWS, start=1):
        v = u[field]
        if v is None or v == "":
            # Not everyone is aiming at a number on a scale, and a bare dash
            # reads as something you failed to fill in. Say which are optional.
            shown = "not set (optional)" if field == "goal_weight_kg" else "—"
        elif field == "birth_date":
            shown = f"{v:%-d %b %Y}" + (f"  ({age})" if age is not None else "")
        elif field == "height_cm":
            shown = f"{float(v):g} cm"
        elif field == "goal_weight_kg":
            shown = f"{float(v):g} kg"
        elif field == "deficit_kcal":
            shown = f"{float(v):g} kcal"
        elif field == "goal":
            shown = {"lose": "lose fat", "gain": "gain weight",
                     "recomp": "build muscle, lose fat",
                     "maintain": "maintain"}.get(str(v), str(v))
        elif field == "activity_factor":
            shown = prof.activity_label(float(v))
        else:
            shown = str(v)
        rows.append((f"{i}. {label}", shown))

    # Weight is not numbered: it is not edited here. It is a dated measurement
    # and /weight is where measurements go.
    w = data["weight_kg"]
    # Width from the content, not a constant: "8. Daily deficit" is exactly 16
    # characters, so a hardcoded 16 ran the label straight into its value.
    pad = max(len(lbl) for lbl, _v in rows) + 2
    body = [f"{lbl:<{pad}}{_esc(val)}" for lbl, val in rows]
    body.append("")
    body.append(
        f"{'Weight':<{pad}}{w:g} kg  ({data['weighed_on']:%-d %b})" if w
        else f"{'Weight':<{pad}}— no weigh-ins yet"
    )
    lines.append("<pre>" + "\n".join(body) + "</pre>")

    # The derivation inputs, checked independently of whether a target exists.
    # Bootstrap seeded targets without recording what they came from, so "has a
    # target" and "can explain it" are different questions and the card has to
    # answer the second one.
    missing = [lbl for (f, lbl, _h) in PROFILE_ROWS[:5] if u[f] is None]
    lines.append("")
    if data["energy_target"]:
        lines.append(
            f"🔥 Energy target <b>{data['energy_target']:,.0f} kcal</b>"
            + (f", set {data['targets_from']:%-d %b}" if data["targets_from"] else "")
        )
        set_at = u["targets_set_at_kg"]
        if missing:
            lines.append(
                "   ⚠️ nothing records what it was derived from — "
                + ", ".join(m.lower() for m in missing)
                + " missing. Fill those in to make it recomputable."
            )
        elif set_at and w and abs(w - float(set_at)) >= 3:
            lines.append(
                f"   ⚠️ derived at {float(set_at):g} kg — you are now {w:g} kg. "
                "Recalculate below."
            )
    elif missing:
        lines.append("🔥 No energy target: " + ", ".join(m.lower() for m in missing) + " missing.")

    stack = data.get("supplements") or []
    if stack:
        lines.append("")
        lines.append(f"💊 <b>Supplement stack</b> ({len(stack)})")
        cadence = {"daily": "every day", "alternate": "every other day",
                   "occasional": "now and then"}
        lines.append("<pre>" + "\n".join(
            f"{_esc(_short(s['name']))[:22]:<24}{cadence.get(s['schedule'], s['schedule'])}"
            for s in stack
        ) + "</pre>")
        lines.append("<i>Manage with <code>/supp</code>.</i>")

    custom = data.get("custom_targets") or []
    lines.append("")
    if custom:
        lines.append(f"🎯 <b>Targets you set yourself</b> ({len(custom)})")
        rows_t = []
        for t in custom:
            lo, hi = t["min_amount"], t["max_amount"]
            if lo is not None and hi is not None:
                v = f"{float(lo):g}–{float(hi):g} {t['unit']}"
            elif lo is not None:
                v = f"at least {float(lo):g} {t['unit']}"
            else:
                v = f"at most {float(hi):g} {t['unit']}"
            rows_t.append(f"{_esc(_short(t['name']))[:20]:<22}{_esc(v)}")
        lines.append("<pre>" + "\n".join(rows_t) + "</pre>")
        lines.append("<i>Everything else is derived. <code>/target</code> to change.</i>")
    else:
        lines.append(
            "🎯 Every target is derived from the profile above. "
            "<code>/target fibre 40</code> to set one yourself."
        )

    lines.append("")
    if missing:
        nxt = next(i for i, (f, _l, _h) in enumerate(PROFILE_ROWS, 1) if u[f] is None)
        field, label, hint = PROFILE_ROWS[nxt - 1]
        lines += [
            f"<b>Next: {_esc(label.lower())}</b> — reply <code>{nxt}. {_esc(hint)}</code>",
            "<i>You can send several at once, one per line.</i>",
        ]
    else:
        lines += [
            "Reply with a numbered line to change anything — "
            "<code>5. 1.4</code>. Several at once is fine.",
        ]
    return "\n".join(lines)


def profile_recalc_card(working: dict[str, float], applied: int, weight: float) -> str:
    return "\n".join([
        "✅ <b>Targets recalculated</b>",
        "",
        "<pre>"
        f"{'At weight':<12}{weight:g} kg\n"
        f"{'Resting':<12}{working['ree']:,.0f} kcal\n"
        f"{'Maintenance':<12}{working['tdee']:,.0f} kcal\n"
        f"{'Target':<12}{working['kcal']:,.0f} kcal\n"
        f"{'Protein':<12}{working['protein']:,.0f} g\n"
        f"{'Fat':<12}{working['fat']:,.0f} g\n"
        f"{'Carbs':<12}{working['carb']:,.0f} g"
        "</pre>",
        f"{applied} targets updated. Previous ones are closed, not overwritten — "
        "past days are still judged against what they were set to at the time.",
        "",
        "<i>Mifflin-St Jeor carries ~10% error. Treat it as a starting point and "
        "correct it against your weight trend — <code>/insight</code>.</i>",
    ])


def target_list_card(rows: Sequence[Any]) -> str:
    """Every standing target, with derived and chosen kept visibly apart."""
    if not rows:
        return "No targets set. <code>/profile</code> derives them from your details."
    mine = [r for r in rows if r["rationale"] == "manual"]
    derived = [r for r in rows if r["rationale"] != "manual"]

    def fmt(r: Any) -> str:
        lo, hi = r["min_amount"], r["max_amount"]
        if lo is not None and hi is not None:
            v = f"{float(lo):g}–{float(hi):g}"
        elif lo is not None:
            v = f"min {float(lo):g}"
        else:
            v = f"max {float(hi):g}"
        unit = {"UG": "µg", "MG": "mg", "G": "g", "KCAL": "kcal",
                "IU": "IU", "KJ": "kJ"}.get(r["unit"], r["unit"].lower())
        return f"{_short(r['name'])[:20]:<22}{v} {unit}"

    out = ["🎯 <b>Your targets</b>"]
    if mine:
        out += ["", "<b>Set by you</b>", "<pre>" + "\n".join(_esc(fmt(r)) for r in mine) + "</pre>"]
    if derived:
        out += ["", "<b>Derived from your profile</b>",
                "<pre>" + "\n".join(_esc(fmt(r)) for r in derived) + "</pre>"]
    out += [
        "",
        "• <code>/target fibre 40</code> — a daily minimum",
        "• <code>/target sodium max 2000</code> — a daily ceiling",
        "• <code>/target fibre clear</code> — back to derived",
    ]
    return "\n".join(out)


# Sessions are shown as they were reported, never re-derived. The training log
# is another system's record; nutrai stores it and reads it back, and inventing
# a number here would be the same mistake as letting a model return a calorie.
_INTENSITY_MARK = {"easy": "🟢", "moderate": "🟡", "hard": "🟠", "max": "🔴"}


def _hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} m" if h else f"{m} min"


def training_card(today_rows: Sequence[Any], week_rows: Sequence[Any],
                  day: dt.date, week_start: dt.date) -> str:
    lines = ["🏋️ <b>Training</b>", ""]

    lines.append(f"<b>{day:%a %-d %b}</b>")
    if today_rows:
        for i, r in enumerate(today_rows, start=1):
            # Numbered so the ❌ buttons below name a line rather than making
            # you count rows to work out which one you are about to remove.
            bits = [f"{i}. {r['kind']}"] if len(today_rows) > 1 else [r["kind"]]
            if r["minutes"]:
                bits.append(_hm(float(r["minutes"])))
            if r["intensity"]:
                bits.append(f"{_INTENSITY_MARK.get(r['intensity'], '')} {r['intensity']}")
            if r["rpe"] is not None:
                bits.append(f"RPE {float(r['rpe']):g}")
            if r["kcal_burned"]:
                bits.append(f"{float(r['kcal_burned']):,.0f} kcal")
            lines.append("   • " + _esc(" · ".join(bits)))
            if r["note"]:
                lines.append(f"     <i>{_esc(_short_note(r['note']))}</i>")
    else:
        lines.append("   <i>nothing logged yet</i>")

    lines.append("")
    lines.append(f"<b>This week</b>  <i>{week_start:%-d %b} – {day:%-d %b}</i>")
    if not week_rows:
        lines.append("   <i>no sessions yet this week</i>")
        return "\n".join(lines)

    total_min = sum(float(r["minutes"] or 0) for r in week_rows)
    by_kind: dict[str, int] = {}
    for r in week_rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    hard = sum(1 for r in week_rows if r["intensity"] in ("hard", "max"))
    days = len({r["local_date"] for r in week_rows})

    n = len(week_rows)
    lines.append(
        f"   • {n} session{'s' if n != 1 else ''} across {days} day{'s' if days != 1 else ''}"
        + (f" — {_hm(total_min)}" if total_min else "")
    )
    lines.append("   • " + _esc(", ".join(
        f"{k} ×{c}" for k, c in sorted(by_kind.items(), key=lambda kv: -kv[1]))))
    if hard:
        lines.append(f"   • {hard} at hard or above")
    kcal = sum(float(r["kcal_burned"] or 0) for r in week_rows)
    if kcal:
        # Reported, not spent. Energy targets are not raised by training — see
        # the activity-factor note in core/profile.py.
        lines.append(f"   • {kcal:,.0f} kcal reported burned "
                     "<i>(not added to your target)</i>")
    return "\n".join(lines)


def _short_note(note: str) -> str:
    return note if len(note) <= 60 else note[:57] + "…"
