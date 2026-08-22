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
from dataclasses import dataclass, field
from html import escape
from typing import Any, Sequence

BAR_FULL = "█"
BAR_EMPTY = "░"

# Below this fraction of the day's mass, a nutrient total is materially
# incomplete and the row says so. 0.995 rather than 1.0 because floating-point
# mass sums land a hair under.
COVERAGE_FULL = 0.995
# Below this share of a floor, nothing meaningful has gone in yet.
BARELY_STARTED = 0.05
# Nutrients whose absence from a food row means the food has none of it,
# rather than that it was never assayed.
ABSENT_MEANS_ZERO = frozenset({1018, 1057, 1253})   # alcohol, caffeine, cholesterol

# A ceiling is worth mentioning before it is crossed, not only after. 0.85 sits
# in the band where there is still a decision to make — at 92% of your energy
# you can choose a smaller dinner; at 104% the only thing left is to know.
CEILING_NEAR = 0.85



def bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def fmt_usd(usd: float) -> str:
    """Money as money. Cents were being printed as "104.4¢", which is a unit
    nobody quotes a monthly bill in and reads as a typo beside every other
    figure on the card.

    Below a cent the two-decimal form rounds to "$0.00" and hides the whole
    point of a per-parse cost, so those keep the digits that distinguish them.
    """
    if usd >= 0.01:
        return f"${usd:,.2f}"
    if usd > 0:
        return f"${usd:.4f}".rstrip("0")
    return "$0.00"


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
    matched: dict[int, str] | None = None,
    weak: Sequence[tuple[str, float]] = (),
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

        # Which USDA row this actually became, when that is not obvious from
        # the name. "pickle juice" resolved to "Relish, pickle" — a sweet
        # chopped-pickle condiment at 130 kcal against a brine that is
        # essentially water — and the card showed only the words you typed, so
        # the one fact that would have caught it was invisible until after it
        # was logged. Choosing the food row is the most error-prone step in
        # the pipeline and it was the only one you could not see.
        fdc = getattr(c, "fdc_id", None)
        if fdc is None:
            try:
                fdc = c["fdc_id"]
            except (TypeError, KeyError, IndexError):
                fdc = None
        desc = (matched or {}).get(fdc)
        if desc and str(label).lower().strip() not in desc.lower():
            lines.append(f"     <i>→ {_esc(desc)}</i>")

    lines.append("")
    lines.append(
        f"📊 <b>{totals.get(ENERGY_KCAL,0):,.0f} kcal</b>"
        f" · 🥩 {totals.get(PROTEIN,0):.0f} g protein"
        f" · 🍞 {totals.get(CARB,0):.0f} g carbs"
        f" · 🧈 {totals.get(FAT,0):.0f} g fat"
        f" · 🌾 {totals.get(FIBER,0):.0f} g fibre"
    )
    if weak:
        # A weak best match usually means the food is not in USDA at all, not
        # that the wrong row was chosen from a list containing the right one.
        # Saying which is the difference between a warning you can act on and
        # one you can only distrust.
        names = ", ".join(_esc(lbl) for lbl, _sim in weak)
        lines.append("")
        lines.append(
            f"🔍 <b>Nothing in the food database is much like {names}.</b> "
            "The row above is the closest of a bad set — if this is something "
            "you eat often, defining it yourself will be right every time."
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
        lines.append(f"<i>💸 {fmt_usd(cost_usd)}</i>")
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
    # Grouped by direction rather than distinguished by a trailing word.
    #
    # Every row used to end in "target" or "ceiling", which is the whole
    # difference between "you need 147 g more of this" and "you have 1,492 kcal
    # left before you should stop" — carried by one word at the end of the
    # line, after the number, in the position the eye reaches last. Five rows
    # of identical shape read as one list of five things going the same way.
    #
    # A heading cannot be skimmed past in the same way, and it lets each row
    # drop the word and get shorter. Ceilings lead so energy stays the first
    # number on the card.
    ceilings, floors, plain = [], [], []
    for nid in (ENERGY_KCAL, PROTEIN, FIBER, CARB, FAT):
        r = by_id.get(nid)
        if not r:
            continue
        amount = float(r["amount"])
        target = r["min_amount"] if r["min_amount"] is not None else r["max_amount"]
        if target is None:
            plain.append(f"   • {_emoji(nid)} {_esc(_short(r['nutrient_name']))} — "
                         f"{fmt_amount(amount, r['unit'])}")
            continue
        target = float(target)
        pct = amount / target * 100 if target else 0
        is_ceiling = r["min_amount"] is None
        # A crossed ceiling loses its own emoji. 🧈 beside "125%" reads as a
        # fact about butter; ⚠️ reads as the thing you need to know.
        mark = "⚠️" if is_ceiling and pct > 100 else _emoji(nid)
        row = (f"   • {mark} {_esc(_short(r['nutrient_name']))} — "
               f"{fmt_amount(amount, r['unit']).rsplit(' ', 1)[0]} of "
               f"{fmt_amount(target, r['unit'])} "
               f"<b>({pct:.0f}%)</b>")
        if is_ceiling:
            # What is left, not what is spent: a ceiling is only useful as the
            # room you have before it. Past it, "0 left" understates — say by
            # how much, because that is the number you would act on.
            row += (f" · {fmt_amount(amount - target, r['unit'])} over"
                    if amount > target
                    else f" · {fmt_amount(target - amount, r['unit'])} left")
            ceilings.append(row)
        else:
            floors.append(row)
    # Floors lead. A floor is a thing to go and do something about; a ceiling
    # is a thing to not do. Energy was put first originally because it is the
    # number people check, but the first line of a card is also the one that
    # sets the agenda, and "eat more protein" is a better agenda than "you have
    # 2,128 kcal left".
    if floors:
        lines.append("  ⬆️ <b>Reach</b>")
        lines += floors
    if ceilings:
        lines.append("  ⬇️ <b>Stay under</b>")
        lines += ceilings
    lines += plain

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
        lines.append("⭐ <b>Biggest share of a daily target</b>")
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
    "sugar": "Total Sugars",
    "sugars": "Total Sugars",
    "salt": "Sodium, Na",
})


def _short(name: str) -> str:
    """USDA names are database entries, not English. Tidy the common ones."""
    return _SHORT_NAMES.get(name, name.split(",")[0])


def usda_name_for(term: str) -> str | None:
    """The database name behind a name shown on a card, if there is one."""
    return DISPLAY_TO_USDA.get(term.strip().lower())


SLOT_ABBREV = {"breakfast": "bfast", "lunch": "lunch", "dinner": "dinner",
               "snack": "snack", "drink": "drink"}


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
    # Three groups, always computed the same way. `show_all` decides whether
    # the on-track ones are listed or counted, not how they are sorted: the
    # off-target rows lead either way, because flattening everything into one
    # alphabetical block buried the four that needed reading.
    rest, fine, unmeasured, settled = [], [], [], 0
    for r in progress:
        if r["nutrient_id"] in (ENERGY_KCAL, PROTEIN, CARB, FAT):
            continue
        c = cov.get(r["nutrient_id"])
        if c is not None and c <= 0 and float(r["amount"]) <= 0:
            unmeasured.append(r)
        elif r["min_amount"] is None and float(r["amount"]) <= 0:
            # "Alcohol 0 g, 0% of a 16 g ceiling" is a row that tells you
            # nothing you did not know from having eaten nothing containing it.
            continue
        elif r["state"] != "ok":
            rest.append(r)
        else:
            # Listed if there is anything to list — caffeine at 191 mg of a
            # 400 mg ceiling is on track and worth seeing. Counted only if it
            # is a floor: an unbreached ceiling is not a nutrient "where it
            # should be", which is how an empty day claimed six were fine.
            fine.append(r)
            if r["min_amount"] is None:
                continue
            # Counted, not listed. The section shows only what needs
            # attention, which is right — but with nothing said about the rest
            # a short list reads as missing data rather than as good news.
            #
            # Floors only. A ceiling you have not crossed is not a nutrient
            # "where it should be" — on an empty day every ceiling is
            # unbreached, which is how a card with nothing logged claimed six
            # nutrients were fine. Same category error as counting ceilings
            # toward the score.
            settled += 1

    if rest:
        table.append("")
        table.append(f"Worth a look ({len(rest)} of {len(rest) + settled})")
        for r in sorted(rest, key=lambda x: (x["state"] == "ok", _short(x["nutrient_name"]))):
            table.append(_row(r, cov.get(r["nutrient_id"])))

    if fine and show_all:
        # Two headings, not one. "On track · Caffeine 48%" reads as a floor
        # you are half-way to when caffeine is a ceiling you are half-way
        # *under* — the same percentage means opposite things and only the
        # heading can say which. Floors are met; ceilings are stayed within.
        met = [r for r in fine if r["min_amount"] is not None]
        under = [r for r in fine if r["min_amount"] is None]
        for heading, group in (("Met", met), ("Within limits", under)):
            if not group:
                continue
            table.append("")
            table.append(f"{heading} ({len(group)})")
            for r in sorted(group, key=lambda x: _short(x["nutrient_name"])):
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
            # Abbreviated deliberately rather than truncated: "breakfast"
            # cut to six characters reads "BREAKF", which looks like a bug.
            slot = SLOT_ABBREV.get(e["slot"] or "", "")
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

    spread = protein_spread(entries)
    if spread:
        lines.append(spread)

    if settled and not show_all:
        # No pointer to /today from a card that *is* /today, and none from
        # /yesterday either — it is the same command one line up in the menu.
        lines.append(f"<i>✅ {settled} other nutrients are where they should be.</i>")

    if pct_measured is not None:
        # The number that decides whether anything above it is worth reading.
        # Said plainly: "mass was weighed or stated" is precise and opaque, and
        # the reader has to work out that the rest of it was guesswork.
        # One clause. The long version explained the same fact three ways
        # depending on the number, and the number already says it.
        tail = "" if pct_measured >= 80 else \
            " — the rest is my estimate" if pct_measured >= 50 else \
            " — most of the rest is guesswork"
        lines.append(f"<i>⚖️ <b>{pct_measured:.0f}%</b> weighed or stated{tail}.</i>")

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
    # Not every nutrient can be "unmeasured". A pear has no row for alcohol
    # because pears contain none, not because nobody looked — so annotating
    # those with a coverage figure invents a doubt that does not exist.
    if r["nutrient_id"] in ABSENT_MEANS_ZERO:
        covered = None
    if covered is not None and covered < COVERAGE_FULL:
        # Neutral, and short enough not to wrap.
        #
        # "(60% measured)" read as "you have eaten 60% of it". "(only 93% of
        # food has data)" fixed that and introduced the opposite problem:
        # "only" is a complaint, and at 93% there is nothing to complain
        # about — it made a good figure look like a warning. So state it, and
        # let the number carry its own weight.
        line += f"  (from {covered:.0%} of food)"
    return line


# ------------------------------------------------------------ repeat menu


# What a dish is, not when it is eaten.
#
# The slot was doing this job and could not: a cereal, a hummus and a bun were
# all 🥗 because all three were eaten at lunch, and every drink was a coffee
# cup. The slot is a time of day and the icon is about the food, so they were
# never the same question.
#
# Ordered, and the first match wins, so "coffee" beats "milk" in "coffee with
# milk" and "protein shake" beats "milk" in itself. Longer, more specific
# phrases therefore go first.
DISH_ICONS: list[tuple[tuple[str, ...], str]] = [
    (("espresso", "coffee", "latte", "cappuccino", "americano", "flat white"), "☕"),
    (("green tea", "herbal tea", "ginger tea", "tea"), "🍵"),
    (("protein shake", "smoothie", "shake"), "🥤"),
    (("beer", "lager", "ale"), "🍺"),
    (("wine", "prosecco", "champagne"), "🍷"),
    (("whisky", "gin", "vodka", "rum", "cocktail"), "🥃"),
    (("pickle", "gherkin"), "🥒"),
    (("juice",), "🧃"),
    (("water",), "💧"),
    (("milk", "kefir"), "🥛"),
    (("cereal", "porridge", "oats", "granola", "muesli"), "🥣"),
    (("yogurt", "yoghurt", "pudding", "skyr"), "🍮"),
    (("egg", "omelette", "frittata"), "🍳"),
    (("cake", "pastry", "croissant", "brownie", "biscuit", "cookie"), "🍰"),
    (("chocolate",), "🍫"),
    (("marshmallow", "sweets", "candy", "haribo"), "🍬"),
    (("bun", "bread", "toast", "sandwich", "roll", "bagel"), "🍞"),
    (("hummus", "dip", "guacamole"), "🫓"),
    (("salad", "greens"), "🥗"),
    (("soup", "broth", "stew"), "🍲"),
    (("noodle", "pasta", "spaghetti", "ramen", "stir fry"), "🍜"),
    (("rice", "risotto"), "🍚"),
    (("potato", "chips", "fries"), "🥔"),
    (("chicken", "turkey", "poultry"), "🍗"),
    (("steak", "beef", "pork", "lamb", "mince", "salami", "bacon"), "🥩"),
    (("fish", "salmon", "tuna", "cod", "prawn", "shrimp"), "🐟"),
    (("cheese", "halloumi", "feta"), "🧀"),
    (("nuts", "almond", "peanut", "seeds", "chia"), "🥜"),
    (("banana", "apple", "berries", "fruit", "orange"), "🍎"),
    (("avocado",), "🥑"),
]

# Only when the name says nothing. A time of day is a poor guess at a food and
# a visibly generic one is better than a confidently wrong one.
SLOT_FALLBACK = {"breakfast": "🌅", "lunch": "🍽", "dinner": "🍽",
                 "snack": "🍪", "drink": "🥤"}


def dish_icon(name: str, slot: str | None = None) -> str:
    low = (name or "").lower()
    for words, icon in DISH_ICONS:
        if any(w in low for w in words):
            return icon
    return SLOT_FALLBACK.get(slot or "", "•")


def history_card(rows: Sequence[Any], span: Any, days: int,
                 tz: str = "UTC") -> str:
    """The diary itself, newest first, grouped by day.

    Everything else in the bot answers "where am I now": /today, /week, the
    logged card. Nothing answered "what have I actually eaten", which is the
    question you ask when you want to check the record rather than be scored
    against it. It was only reachable by opening Adminer and reading
    `log_entry`, which is not a feature, it is the absence of one.

    Totals only. Per-component detail is `/why`'s job and would make this
    unreadable at a fortnight's length.
    """
    import zoneinfo

    zone = zoneinfo.ZoneInfo(tz)
    if not rows:
        if span and span["entries"]:
            return (f"Nothing logged in the last {days} days. "
                    f"Your diary runs {span['first_day']:%-d %b} to "
                    f"{span['last_day']:%-d %b} — <code>/history 90</code> to reach back.")
        return "Nothing logged yet."

    lines = [f"📔 <b>Your diary</b> — last {days} days", ""]
    by_day: dict[Any, list[Any]] = {}
    for r in rows:
        by_day.setdefault(r["local_date"], []).append(r)

    for day, entries in by_day.items():
        kcal = sum(float(e["kcal"] or 0) for e in entries)
        protein = sum(float(e["protein"] or 0) for e in entries)
        lines.append(f"<b>{day:%a %-d %b}</b> — {kcal:,.0f} kcal · {protein:.0f} g protein")
        for e in entries:
            when = e["logged_at"].astimezone(zone).strftime("%H:%M")
            icon = dish_icon(e["name"] or "", e["slot"])
            lines.append(f"   {when} {icon} {_esc(_title(e['name'] or 'unnamed'))}"
                         f" — {float(e['kcal'] or 0):,.0f} kcal")
        lines.append("")

    # What is not on screen, said plainly. A capped list that does not mention
    # the cap reads as the whole diary, and then a missing week looks like a
    # week you did not eat.
    if span and span["entries"]:
        shown = len(rows)
        if int(span["entries"]) > shown:
            lines.append(
                f"<i>{shown} of {span['entries']} entries, over {span['days']} logged "
                f"days from {span['first_day']:%-d %b %Y}. "
                f"<code>/history 60</code> for more, "
                f"<code>/history 2026-08-14</code> for one day in full.</i>"
            )
        else:
            lines.append("<i>That is everything. <code>/history 2026-08-14</code> "
                         "for one day in full.</i>")
    return "\n".join(lines)


def repeat_menu(dishes: Sequence[Any], templates: Sequence[Any] = (),
                components: Sequence[Any] = ()) -> str:
    """Ordered by the hour, so breakfast is at the top at breakfast time.

    No counts beside the names: "x3" invited reading the number as how many
    would be logged, when it was only how often the dish had ever been eaten.
    One tap logs one serving; two coffees is two taps.
    """
    lines = ["🔁 <b>Repeat</b>", ""]
    for i, d in enumerate(dishes, 1):
        lines.append(f"<code>{i}</code> {dish_icon(d['name'], d['default_slot'])} "
                     f"{_esc(_title(d['name']))}")
    if templates:
        lines.append("")
        for t in templates:
            lines.append(f"<code>{_esc(t['slug'])}</code> 📋 {_esc(_title(t['name']))}")

    if components:
        # A plate of six things becomes one dish you will never eat again in
        # that combination, while the parts you do repeat sit in it
        # unreachable. Numbering continues from the dishes, so one reply
        # answers either list.
        lines.append("")
        lines.append("🥚 <b>Or one thing</b>")
        for j, c in enumerate(components, start=len(dishes) + 1):
            grams = float(c["stated_grams"] or c["median_grams"] or 0)
            lines.append(f"<code>{j}</code> {dish_icon(c['label'])} "
                         f"{_esc(_title(c['label']))} — {grams:.0f} g")
    lines += [
        "",
        "<i>Reply with the number to log it. Add a change if you need one:</i>",
        "<code>4 x1.5</code> · <code>4 250</code> total g · "
        "<code>4 -onion</code> · <code>4 @14:00</code>",
    ]
    return "\n".join(lines)


def _title(name: str) -> str:
    """First letter up, the rest left alone.

    str.title() would turn "Alpro coconut milk" into "Alpro Coconut Milk" and
    "wheat-rye bread" into "Wheat-Rye Bread". Only the first character was ever
    the problem — "pickle juice" sitting in a list of proper names.
    """
    name = (name or "").strip()
    return name[:1].upper() + name[1:] if name else name


# --------------------------------------------------------- notifications


def audit_card(findings: Sequence[Any]) -> str:
    """The daily self-check, grouped by how much it matters.

    Errors first because they mean a number in the log is wrong, not merely
    uncertain — and a wrong number that nobody corrects becomes a median, then
    a trend, then a recommendation.
    """
    if not findings:
        return ("🩺 <b>Match check</b>\n\n"
                "Nothing to flag — every entry's numbers agree with the USDA "
                "rows behind them.\n\n"
                "<i>This checks the database, not your eating. It looks for "
                "components matched to the wrong food, masses that do not fit "
                "their calories, and rows with nutrients missing.</i>")

    icons = {"error": "❌", "warn": "⚠️", "info": "💡"}
    titles = {
        "error": "Wrong, not just uncertain",
        "warn": "Worth a look",
        "info": "Would pay off later",
    }

    # "Daily check" said when it ran and nothing about what it does, which
    # left it reading as a verdict on the eating rather than on the matching.
    # It has no opinion about the food at all.
    lines = ["🩺 <b>Match check</b> — entries whose numbers do not add up",
             "<i>About the food database, not about your eating.</i>"]
    seen: set[tuple[str, str]] = set()
    for severity in ("error", "warn", "info"):
        group = []
        for f in findings:
            if f.severity != severity:
                continue
            # Two entries of the same dish on the same day produce the same
            # sentence twice, and a list that repeats itself reads as two
            # problems. It is one, said twice.
            key = (f.summary, f.detail)
            if key in seen:
                continue
            seen.add(key)
            group.append(f)
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


def supplement_taken_card(rows: Sequence[Any], tz: str = "UTC") -> str:
    """What was taken today and when.

    The time is the point. Magnesium at 22:00 and magnesium at 08:00 are the
    same row and a different intervention, and until now the day's totals
    could not tell them apart.
    """
    import zoneinfo

    if not rows:
        return "💊 <i>Nothing ticked off today yet.</i>"
    zone = zoneinfo.ZoneInfo(tz)
    via = {"from_meal": " (from a meal)", "reminder": " (from a reminder)"}
    lines = ["💊 <b>Taken today</b>", ""]
    for r in sorted(rows, key=lambda x: x["taken_at"]):
        lines.append(f"   • {r['taken_at'].astimezone(zone):%H:%M} "
                     f"{_esc(_title(r['name']))}"
                     f"{via.get(r['logged_via'], '')}")
    return "\n".join(lines)


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
        if s["starts_on"]:
            detail.insert(0, f"from {s['starts_on']:%-d %b}")
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


def supplement_pick_card(stack: Sequence[Any], selected: Sequence[int],
                         reason: str = "schedule") -> str:
    """The question and the count. The buttons below are the list.

    This used to render every supplement as text *and* as a button, so a stack
    of nine appeared twice in one message with the same tick state in both
    places — which reads as a bug even though both halves were correct, and
    buries the buttons below a screen of text you have already read.
    """
    n, total = len(set(selected)), len(stack)
    lines = ["💊 <b>Which did you take?</b>", ""]

    # Why they are ticked, said accurately. This used to assert "pre-ticked by
    # their schedule — the rest are every other day or occasional" in every
    # case, including the one where the ticks came from what was already
    # logged today. With eight of nine on a daily schedule that sentence was
    # simply untrue, and a card that misexplains itself is worse than one that
    # says nothing: it invites you to trust the wrong thing.
    if reason == "logged":
        if n == 0:
            lines.append("<i>Nothing ticked yet today. Tap what you have "
                         "actually taken — a tick is a record, not a plan.</i>")
        elif n == total:
            lines.append("<i>All of them today. Tap any to remove.</i>")
        else:
            lines.append(
                f"<i>{n} of {total} taken so far today. Tap anything else you "
                "have had since, then “log these”.</i>"
            )
    elif n == total:
        lines.append(f"<i>All {total} pre-ticked by their schedule. Tap any to remove.</i>")
    elif n:
        # Names the exceptions rather than describing them as a category, which
        # is checkable against the list right underneath it.
        skipped = [s_["name"] for s_ in stack if s_["id"] not in set(selected)]
        lines.append(
            f"<i>{n} of {total} due today. Not due: {_esc(', '.join(skipped))} — "
            "tap if you took them anyway.</i>"
        )
    else:
        lines.append("<i>Nothing due today. Tap the ones you took, then “log these”.</i>")
    return "\n".join(lines)














# ------------------------------------------------------------- day score


@dataclass(frozen=True)
class DayScore:
    reached: int          # floors fully met
    assessable: int       # floors that can be judged today
    short: list[str]      # names of the ones still under
    breached: list[str]   # ceilings crossed
    nearing: list[str]    # ceilings close to crossing
    unmeasured: int       # floors nothing you ate reports at all
    # Mean of each floor's progress, capped at 1 apiece. "8 of 13" throws away
    # the difference between a day at 95% of every floor and one at 5%, which
    # is most of what you want to know at four in the afternoon.
    covered: float

    # Floors nothing you ate today reports any amount of at all. Separated
    # from "short" because 5% of a floor and 0% of it are different days.
    _untouched: tuple[str, ...] = field(default_factory=tuple)
    # Floors counting for more than one, named so the headline can say the
    # score is not a plain average when it is not.
    weighted_by: tuple[str, ...] = field(default_factory=tuple)

    @property
    def partial(self) -> int:
        """Floors started but not finished."""
        return self.assessable - self.reached - len(self._untouched)


def day_score(
    progress: Sequence[Any], coverage: dict[int, float] | None = None
) -> DayScore:
    """How the day is going against its floors, counted and weighted.

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
    weights_used: set[str] = set()
    reached = assessable = unmeasured = 0
    short: list[str] = []
    weighted = weight_sum = 0.0
    untouched: list[str] = []
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
                breached.append((share, f"{_short(r['nutrient_name'])} {share * 100:.0f}%"))
            elif share >= CEILING_NEAR:
                nearing.append((share, f"{_short(r['nutrient_name'])} {share * 100:.0f}%"))

        if lo is None:
            continue
        if blind:
            unmeasured += 1
            continue
        assessable += 1
        # Weighted, and capped at 1 each before weighting: three times your
        # protein cannot make up for no iron, and a score that let it would
        # reward the easy floor over the one you are actually missing.
        w = float(r["weight"]) if "weight" in r and r["weight"] is not None else 1.0
        weight_sum += w
        if w != 1.0:
            weights_used.add(f"{_short(r['nutrient_name'])} ×{w:g}")
        weighted += w * (min(amount / float(lo), 1.0) if float(lo) > 0 else 0.0)
        if amount >= float(lo):
            reached += 1
        else:
            short.append(_short(r["nutrient_name"]))
            # 0.2 g of protein against a 180 g floor is 0.1%, and calling that
            # "part-way" alongside a headline of 0% reads as a contradiction.
            # Below a twentieth of the target it has not been started.
            if float(lo) <= 0 or amount / float(lo) < BARELY_STARTED:
                untouched.append(_short(r["nutrient_name"]))

    # Worst first. Unsorted, these came out in nutrient-id order, so the
    # morning note named carbs at 103% on a day with cholesterol at 208%.
    breached = [label for _share, label in sorted(breached, reverse=True)]
    nearing = [label for _share, label in sorted(nearing, reverse=True)]

    return DayScore(
        reached=reached, assessable=assessable, short=short, breached=breached,
        nearing=nearing, unmeasured=unmeasured,
        covered=(weighted / weight_sum) if weight_sum else 0.0,
        weighted_by=tuple(sorted(weights_used)),
        _untouched=tuple(untouched),
    )


def score_line(progress: Sequence[Any], coverage: dict[int, float] | None = None) -> str:
    """One bar for the day, counting the thing worth counting.

    Deliberately not a single number in isolation. A score that hides which
    target was missed invites optimising the score, and the number that is
    easiest to move is rarely the one worth moving.
    """
    sc = day_score(progress, coverage)
    reached, assessable = sc.reached, sc.assessable
    short, breached, nearing, unmeasured = sc.short, sc.breached, sc.nearing, sc.unmeasured
    out: list[str] = []

    if assessable:
        pct = reached / assessable * 100
        face = "🟢" if pct >= 80 else "🟡" if pct >= 50 else "🔴"
        # Lead with how much of the day's requirements are actually covered,
        # not how many boxes are ticked. "8 of 13 met" says nothing about
        # whether the other five are at 95% or at nothing, which is most of
        # what you want to know before deciding what to eat next.
        covered = sc.covered * 100
        face = "🟢" if covered >= 80 else "🟡" if covered >= 50 else "🔴"
        # "today's" on a card headed "Mon 17 Aug" is wrong every time you
        # open /yesterday, which is once a day.
        out.append(f"{face} <b>{covered:.0f}% of minimums covered</b>  {bar(covered)}")
        detail = f"{reached} of {assessable} fully met"
        if sc.partial:
            detail += f" · {sc.partial} part-way"
        if sc._untouched:
            detail += f" · {len(sc._untouched)} not started"
        # The weighting is deliberately not repeated here. It is stated when
        # you set it and it is visible in /target; on a card you read six
        # times a day it is a standing footnote about a decision you already
        # made, and it crowds out the part that changes.
        out.append(f"<i>{_esc(detail)}</i>")
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

    from ..config import ENERGY_KCAL

    if not rows:
        return (
            f"📅 <b>{ctx['start']:%-d %b} – {ctx['end']:%-d %b}</b>\n\n"
            "Nothing logged this week."
        )

    _incomplete = set(ctx.get("incomplete") or ())
    by_nutrient: dict[int, list[Any]] = {}
    for r in rows:
        # "Fibre reached on 0 of 6 days" must not count a day whose fibre was
        # simply not recorded. The chart still shows the day; the arithmetic
        # about how often you hit a floor cannot include it.
        if r["day"] in _incomplete:
            continue
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

    all_days = {r["day"] for r in rows}
    n_days = len(all_days)
    n_scored = len(all_days - _incomplete) or n_days
    lines = [
        f"📅 <b>{ctx['start']:%-d %b} – {ctx['end']:%-d %b}</b>",
        f"<i>{n_days} day{'s' if n_days != 1 else ''} logged · "
        f"{ctx.get('meals') or 0} meals</i>",
    ]

    # A shape, before any of the words.
    #
    # The lists below say which nutrients went wrong and how often, which is
    # what you act on — but not whether the week was steady or two good days
    # around five bad ones, and those call for different responses. One row per
    # day, in one <pre> block because per-line <code> spans render
    # proportionally and the columns drift.
    #
    # Energy against its ceiling, floors met as a fraction, ceilings crossed as
    # a count. Three numbers is the most a row can carry and still be read down
    # a column rather than across.
    by_day: dict[Any, list[Any]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)

    # A day the user said was not properly logged is not a day of bad eating,
    # and a chart that shows the two identically invites the wrong conclusion
    # from its own reader. Marked, not hidden: the entries are real, it is only
    # inference that stops.
    incomplete = set(ctx.get("incomplete") or ())
    chart = ["Day     Energy vs cap   Floors  Over"]
    for day in sorted(by_day):
        rs = by_day[day]
        energy = next((r for r in rs if r["nutrient_id"] == ENERGY_KCAL), None)
        cap = float(energy["max_amount"]) if energy and energy["max_amount"] else 0.0
        kcal = float(energy["amount"]) if energy else 0.0
        pct = (kcal / cap * 100) if cap else 0.0
        floors = [r for r in rs
                  if r["min_amount"] is not None and float(r["min_amount"]) > 0]
        met = sum(1 for r in floors if float(r["amount"]) >= float(r["min_amount"]))
        crossed = sum(1 for r in rs
                      if r["max_amount"] is not None and float(r["max_amount"]) > 0
                      and float(r["amount"]) > float(r["max_amount"]))
        chart.append(
            f"{day:%a %-d}".ljust(8)
            + f"{bar(pct, 8)}{pct:4.0f}%"
            + f"{met:>6}/{len(floors)}"
            + f"{crossed if crossed else '-':>5}"
            + ("  (partial)" if day in incomplete else "")
        )
    lines += ["", "<pre>" + "\n".join(chart) + "</pre>"]
    if incomplete & set(by_day):
        n = len(incomplete & set(by_day))
        lines.append(
            f"<i>(partial) — {n} day{'s' if n != 1 else ''} you marked as not "
            "properly logged. Counted in nothing below, and excluded from the "
            "weight trend and /insight.</i>")
    lines += _prior_day_detail(by_day, ctx["end"])

    if over:
        lines += ["", "⚠️ <b>Over the ceiling</b>"]
        for n_over, nid, name, worst in sorted(over, reverse=True)[:4]:
            lines.append(
                f"   • {_emoji(nid)} {_esc(name)} — {n_over} of {n_scored} days, "
                f"worst {worst * 100:.0f}%"
            )

    if under:
        lines += ["", "🎯 <b>Floors you kept missing</b>"]
        for _rate, nid, name, n_met, typical in sorted(under)[:4]:
            lines.append(
                f"   • {_emoji(nid)} {_esc(name)} — reached on {n_met} of {n_scored} days "
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
    span = (ctx["end"] - ctx["start"]).days + 1
    if ctx.get("supp_days") is not None:
        lines.append(f"   • 💊 supplements logged on {ctx['supp_days']} "
                     f"of {span} days")
    if ctx.get("sessions"):
        n = int(ctx["sessions"])
        lines.append(f"   • 🏋 {n} training session{'' if n == 1 else 's'}")

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
        lines.append(f"   • 💸 {fmt_usd(float(ctx['cents']) / 100)}")

    return "\n".join(lines)


def _prior_day_detail(by_day: dict, end: Any) -> list[str]:
    """Yesterday, in more detail than a chart row can hold.

    Yesterday specifically, not the latest day with entries: today is still
    being lived and half its lines are simply not eaten yet, so every floor
    reads as missed. Yesterday is finished, and it is the day whose shape you
    are about to repeat.
    """
    earlier = [d for d in by_day if d < end]
    prior = max(earlier) if earlier else None
    lines: list[str] = []
    if prior is not None:
        rs = by_day[prior]
        misses = sorted(
            ((float(r["amount"]) / float(r["min_amount"]), r) for r in rs
             if r["min_amount"] is not None and float(r["min_amount"]) > 0
             and float(r["amount"]) < float(r["min_amount"])),
            key=lambda t: t[0])[:3]
        overs = sorted(
            ((float(r["amount"]) / float(r["max_amount"]), r) for r in rs
             if r["max_amount"] is not None and float(r["max_amount"]) > 0
             and float(r["amount"]) > float(r["max_amount"])),
            key=lambda t: -t[0])[:3]
        if misses or overs:
            lines += ["", f"🔍 <b>{prior:%A} {prior:%-d %b} in detail</b>"]
            for share, r in overs:
                lines.append(
                    f"   • ⚠️ {_emoji(r['nutrient_id'])} {_esc(_short(r['nutrient_name']))} "
                    f"{fmt_amount(float(r['amount']), r['unit'])} — "
                    f"{share * 100:.0f}% of the ceiling")
            for share, r in misses:
                short = float(r["min_amount"]) - float(r["amount"])
                lines.append(
                    f"   • {_emoji(r['nutrient_id'])} {_esc(_short(r['nutrient_name']))} "
                    f"{share * 100:.0f}% — {fmt_amount(short, r['unit'])} short")
    return lines


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
    ("wake_hour",       "Usually up at",  "7, or blank to learn it"),
    ("fast_break_kcal",      "Fast: kcal",     "50 — any intake over this"),
    ("fast_break_carb_g",    "Fast: carbs",    "5 g"),
    ("fast_break_protein_g", "Fast: protein",  "2 g"),
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
        elif field in ("fast_break_kcal", "fast_break_carb_g", "fast_break_protein_g"):
            shown = f"over {float(v):g}" + (" kcal" if field.endswith("kcal") else " g")
        elif field == "wake_hour":
            shown = f"{int(v):02d}:00 — note arrives {int(v)-1:02d}:30"
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
        # Say which of the two it rests on. "2,236 kcal" from an equation and
        # from your own weight trend are different claims, and only one of them
        # was measured.
        if u["measured_tdee_kcal"]:
            lines.append(
                f"   📐 from your <b>measured</b> maintenance of "
                f"{float(u['measured_tdee_kcal']):,.0f} kcal over "
                f"{u['measured_tdee_days']} days — not the equation"
            )
        conflict = prof.goal_conflict(u["goal"], u["deficit_kcal"])
        if conflict:
            lines.append(f"   ⚠️ {_esc(conflict)}")
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
            "<i>One per line for several.</i>",
        ]
    else:
        lines += [
            "To change something, reply with its number and the new value — "
            "<code>5. 1.4</code>. One per line for several.",
        ]
    return "\n".join(lines)


def profile_recalc_card(working: dict[str, float], applied: int, weight: float,
                        goal: str | None = None, deficit: float | None = None) -> str:
    from . import profile as prof

    conflict = prof.goal_conflict(goal, deficit)
    warn = ([f"⚠️ <b>{_esc(conflict)}</b>",
             "   <i>The button below sets it and redoes this in one tap.</i>", ""]
            if conflict else [])
    # Which of the two the maintenance figure is. An equation's output and a
    # measurement of the same quantity deserve different confidence, and the
    # table is where that distinction has to survive.
    maint_note = "  measured" if working.get("tdee_measured") else ""
    return "\n".join([
        "✅ <b>Targets recalculated</b>",
        "",
        *warn,
        "<pre>"
        f"{'At weight':<12}{weight:g} kg\n"
        f"{'Resting':<12}{working['ree']:,.0f} kcal\n"
        f"{'Maintenance':<12}{working['tdee']:,.0f} kcal{maint_note}\n"
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
        "• <code>/target protein weight 2.5</code> — how much it counts",
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
                bits.append(f"effort {float(r['rpe']):g}/10")
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
        lines.append(f"   • {kcal:,.0f} kcal reported burned")
        lines.append(
            "     <i>Not added to your energy target. Your target is corrected "
            "against three weeks of weight trend, which already contains "
            "whatever you burned — adding a watch's estimate on top would "
            "count the same energy twice.</i>")
    return "\n".join(lines)


def _short_note(note: str) -> str:
    return note if len(note) <= 60 else note[:57] + "…"


SLOT_LABELS: dict[str, tuple[str, str]] = {
    "fasted":    ("🌅", "before food"),
    "breakfast": ("🍳", "after breakfast"),
    "evening":   ("🌆", "evening"),
    "bed":       ("🌙", "before sleeping"),
}


def slot_name(slot: str) -> str:
    emoji, label = SLOT_LABELS.get(slot, ("💊", slot))
    return f"{emoji} {label}"


# The same four, short and without an emoji, for column-aligned tables. An
# emoji is two cells wide in a proportional-ish monospace and "before
# sleeping" is fifteen characters, which together wrapped every row of the
# settings table onto two lines on a phone.
SLOT_SHORT = {"fasted": "fasted", "breakfast": "breakfast",
              "evening": "evening", "bed": "bedtime"}


def supplement_reminder_card(slot: str, rows: Sequence[Any],
                             carried: Sequence[Any] = ()) -> str:
    """The nudge itself. Template and SQL only — invariant 4."""
    outstanding = [r for r in rows if not r["logged"]]
    lines = [f"💊 <b>{slot_name(slot)}</b>", ""]
    for r in outstanding:
        serving = f"{float(r['servings_per_day']):g} × {r['serving_desc']}"
        lines.append(f"   • <b>{_esc(r['name'])}</b> — {_esc(serving)}")
    # Kept visibly apart. A capsule carried from the morning is a different
    # fact from one due now, and merging them loses the only thing that
    # explains why it is on this card at all.
    if carried:
        lines.append("")
        lines.append("<i>Still outstanding from earlier:</i>")
        for r in carried:
            serving = f"{float(r['servings_per_day']):g} × {r['serving_desc']}"
            lines.append(f"   • <b>{_esc(r['name'])}</b> — {_esc(serving)} "
                         f"<i>({slot_name(r['from_slot']).lower()})</i>")
    done = len(rows) - len(outstanding)
    if done:
        lines.append(f"   <i>{done} already logged for today.</i>")
    lines += ["", "<i>Tick only what you actually take. A capsule logged and "
                  "not swallowed puts micronutrients in your totals that never "
                  "reached you.</i>"]
    return "\n".join(lines)


def slot_settings_card(stack: Sequence[Any], times: dict) -> str:
    """Which supplement belongs to which moment, and when each moment is."""
    lines = ["⏰ <b>Supplement times</b>", ""]
    rows = []
    for i, s in enumerate(stack, start=1):
        where = SLOT_SHORT.get(s["slot"], "—") if s["slot"] else "—"
        rows.append((f"{i}. {s['name'][:18]}", where))
    pad = max(len(a) for a, _b in rows) + 2
    lines.append("<pre>" + "\n".join(
        _esc(f"{a:<{pad}}{b}") for a, b in rows) + "</pre>")

    lines.append("<b>When each moment is</b>")
    trows = []
    for slot in ("fasted", "breakfast", "evening", "bed"):
        t = times.get(slot)
        trows.append(f"{SLOT_SHORT[slot]:<11}{t.strftime('%H:%M') if t else '—'}")
    lines.append("<pre>" + "\n".join(_esc(r) for r in trows) + "</pre>")

    # Assigning a supplement to a moment does nothing on its own. Without a
    # time there is no reminder, and a card that lists nine tidy assignments
    # reads as finished when in fact nothing will ever fire.
    assigned = {s["slot"] for s in stack if s["slot"]}
    unscheduled = sorted(assigned - set(times))
    if assigned and not times:
        lines.append("⚠️ <b>No reminders will fire.</b> Nothing is scheduled yet — "
                     "set a time for each moment below.")
    elif unscheduled:
        lines.append("⚠️ No time set for: "
                     + _esc(", ".join(SLOT_SHORT[s_] for s_ in unscheduled))
                     + " — nothing will fire for those.")

    lines += [
        "• <code>3. evening</code> puts line 3 in the evening",
        "• <code>evening 21:00</code> sets when that moment is",
        "• <code>evening off</code> stops that reminder",
        "<i>One per line for several.</i>",
    ]
    return "\n".join(lines)


def suggest_card(suggestions: Sequence[Any], progress: Sequence[Any],
                 kcal_left: float | None) -> str:
    """Why each dish is being suggested, in the same breath as the suggestion.

    A recommender that only names a dish asks to be trusted. Naming the gap it
    closes lets you disagree with it, which is the difference between a tool
    and an oracle.
    """
    names = {r["nutrient_id"]: _short(r["nutrient_name"]) for r in progress}

    gaps = []
    for r in progress:
        if r["min_amount"] is None:
            continue
        target = float(r["min_amount"])
        short = target - float(r["amount"])
        if target > 0 and short > 0.10 * target:
            # Weighted, so protein at x2.5 leads a list it was bottom of.
            w = float(r["weight"]) if "weight" in r and r["weight"] is not None else 1.0
            gaps.append(((short / target) * w, r["nutrient_id"], short, r["unit"]))
    gaps.sort(reverse=True)

    if not suggestions:
        # Saying so beats offering the least-bad rows in a thin list. Three
        # drinks that each close 1% of potassium are not an answer to "what
        # should I eat next", and a tick beside them dresses noise as advice.
        lines = ["🍽 <b>Nothing here would close today's gaps</b>", ""]
        if gaps:
            biggest = gaps[0]
            lines.append(
                f"<i>The gap that matters is "
                f"{_esc(names.get(biggest[1], str(biggest[1])))} — "
                f"{fmt_amount(biggest[2], biggest[3])} to go — and nothing you "
                "have logged before would make a real dent in it.</i>")
        else:
            lines.append("<i>Suggestions come from dishes you have already "
                         "eaten and confirmed. Log a few and they become "
                         "candidates.</i>")
        if kcal_left is not None:
            lines += ["", f"<i>You have {kcal_left:,.0f} kcal left to do it in.</i>"]
        return "\n".join(lines)

    # Name the gaps being ranked against, biggest first. Without this the
    # ranking is an assertion: a suggestion that "closes Calcium 100%" reads
    # as decisive until you know the calcium gap was 8 mg and the protein gap
    # was 118 g.
    lines = ["🍽 <b>What would close today's gaps</b>", ""]

    # When the gaps cannot fit in the energy that is left, say so once rather
    # than repeating "(368 over what is left)" under every row. Protein is
    # 4 kcal a gram whatever it comes in, so a 49 g gap needs at least 196
    # kcal — if the budget is smaller than that, the day is arithmetically
    # closed and no suggestion can change it.
    from ..config import PROTEIN as _PROTEIN

    protein_gap = next((short for _s, nid, short, _u in gaps if nid == _PROTEIN), 0.0)
    if kcal_left is not None and protein_gap > 0:
        floor_kcal = protein_gap * 4
        if floor_kcal > kcal_left:
            lines += [
                f"<i>⚠️ {protein_gap:.0f} g of protein needs at least "
                f"{floor_kcal:,.0f} kcal, and you have {max(kcal_left, 0):,.0f} "
                "left. Both cannot happen today — the suggestions below close "
                "the gaps and go over.</i>",
                "",
            ]
    if gaps:
        shown = ", ".join(
            f"{_esc(names.get(nid, str(nid)))} {fmt_amount(short, unit)}"
            for _share, nid, short, unit in gaps[:4]
        )
        lines += [f"<i>Biggest gaps left: {shown}</i>", ""]
    for i, s in enumerate(suggestions, start=1):
        head = f"<b>{i}. {_esc(s.name)}</b>"
        if s.kcal:
            head += f" — {s.kcal:,.0f} kcal"
            if kcal_left is not None and s.kcal > kcal_left:
                head += f" <i>({s.kcal - kcal_left:,.0f} over what is left)</i>"
        lines.append(head)
        closes = ", ".join(
            f"{_esc(names.get(nid, str(nid)))} {share:.0%}" for nid, share in s.closes[:4]
        )
        lines.append(f"   ✅ closes {closes}")
        if s.breaches:
            over = ", ".join(
                f"{_esc(names.get(nid, str(nid)))} +{share:.0%}" for nid, share in s.breaches[:3]
            )
            lines.append(f"   ⚠️ pushes past {over}")
        lines.append("")

    # The old footer explained the implementation — arithmetic, snapshots, no
    # model — which is a fact about how this was built rather than anything
    # the reader needs. One line about where the list comes from is enough;
    # the rest is on the card already.
    lines.append("<i>From things you have eaten before.</i>")
    return "\n".join(lines).rstrip()


def measured_tdee_offer(flr: Any, current_target: float | None,
                        activity_now: float | None, implied: float | None) -> str:
    """What adopting the measurement would change, before you adopt it."""
    lines = [
        "📐 <b>Your measured maintenance</b>", "",
        f"   • <b>{flr.implied_tdee_kcal:,.0f} kcal</b> from "
        f"{flr.days} days of weigh-ins and what you actually ate",
    ]
    if current_target:
        lines.append(f"   • your target is set from the equation, at "
                     f"<b>{current_target:,.0f} kcal</b>")
    if implied and activity_now:
        lines.append(f"   • that makes your real activity factor "
                     f"<b>{implied:g}</b>, not {float(activity_now):g}")
    elif implied:
        lines.append(f"   • that makes your real activity factor <b>{implied:g}</b>")

    if flr.days < 21:
        lines += ["", f"<i>{flr.days} days is enough to be worth using and not "
                      "enough to be settled — glycogen and water stop dominating "
                      "at about three weeks. It can be re-measured any time.</i>"]
    else:
        lines += ["", "<i>Measured over three weeks or more, so this is a "
                      "better number than any equation can give you.</i>"]
    return "\n".join(lines)


def percent_split(values: Sequence[float]) -> list[int]:
    """Whole percentages that sum to exactly 100.

    Rounding each share independently gave 75 + 18 + 2 + 2 + 2 + 1 + 1 = 101
    on a real cholesterol breakdown. The milligrams were right and the
    percentages were each right to the nearest point, and the column still
    looked broken — which for a card whose whole purpose is "where did this
    come from" is fatal to it.

    Largest remainder: floor everything, then hand the leftover points to
    whichever shares were cut hardest.
    """
    total = sum(values)
    if total <= 0:
        return [0] * len(values)
    exact = [v / total * 100 for v in values]
    out = [int(x) for x in exact]
    leftover = 100 - sum(out)
    order = sorted(range(len(values)), key=lambda i: -(exact[i] - out[i]))
    for i in order[:leftover]:
        out[i] += 1
    return out


def why_card(nutrient_name: str, unit: str, day: dt.date, entries: Sequence[Any],
             supplements: Sequence[Any], target: float | None,
             is_ceiling: bool, tz: str = "UTC") -> str:
    """Where a day's figure for one nutrient actually came from.

    "250% of your cholesterol allowance" is a fact about a number. This is the
    question underneath it — which plate, and which thing on the plate — and
    without an answer the ceiling is something that happens to you rather than
    something you did.
    """
    import zoneinfo

    zone = zoneinfo.ZoneInfo(tz)
    food = sum(float(e["amount"]) for e in entries)
    supp = sum(float(s["amount"]) for s in supplements)
    total = food + supp

    lines = [f"🔎 <b>{_esc(_short(nutrient_name))}</b> — {day:%a %-d %b}", ""]
    if not total:
        return "\n".join(lines + ["<i>Nothing logged today reports it.</i>"])

    head = f"<b>{fmt_amount(total, unit)}</b> so far"
    if target:
        pct = total / target * 100
        head += f" — {pct:.0f}% of your {fmt_amount(target, unit)} " \
                + ("ceiling" if is_ceiling else "target")
    lines += [head, ""]

    # Repeats of the same dish are one row. Three identical espressos listed
    # separately came out 2%, 2%, 1% — largest-remainder has to break the tie
    # somewhere, and identical rows with different percentages read as a bug
    # however correct the arithmetic is. Grouping is more legible anyway.
    grouped: list[dict] = []
    by_name: dict[str, dict] = {}
    for e in entries:
        g = by_name.get(e["name"])
        if g is None:
            g = {"name": e["name"], "amount": 0.0, "n": 0,
                 "first": e["logged_at"], "parts": e["parts"]}
            by_name[e["name"]] = g
            grouped.append(g)
        g["amount"] += float(e["amount"])
        g["n"] += 1
        g["first"] = min(g["first"], e["logged_at"])
    grouped.sort(key=lambda g: -g["amount"])

    # One split across food and supplements together, so the column sums to
    # 100 rather than to each half separately.
    shares = percent_split([g["amount"] for g in grouped]
                           + [float(s_["amount"]) for s_ in supplements])

    rows: list[str] = []
    for i, e in enumerate(grouped):
        amount = e["amount"]
        when = e["first"].astimezone(zone).strftime("%H:%M")
        # Room reserved for the count before the name is cut, or "×3" is what
        # gets truncated away and the row claims to be a single serving.
        suffix = f" ×{e['n']}" if e["n"] > 1 else ""
        name = _short_note(e["name"])[:26 - len(suffix)] + suffix
        rows.append(f"{when} {name:<28}"
                    f"{fmt_amount(amount, unit):>10}  {shares[i]:>3.0f}%")
        # The component behind it, when one clearly dominates. Naming the plate
        # is half an answer: "boiled eggs, avocado and bread" does not tell you
        # it was the eggs.
        for part in e["parts"][:2]:
            scaled = part["amount"] * e["n"]
            if (scaled / amount if amount else 0) < 0.15:
                continue
            rows.append(f"        └ {_short_note(part['label'])[:22]:<24}"
                        f"{fmt_amount(scaled, unit):>10}")
    for j, s_ in enumerate(supplements):
        rows.append(f"  💊  {_short_note(s_['name'])[:26]:<28}"
                    f"{fmt_amount(s_['amount'], unit):>10}  "
                    f"{shares[len(grouped) + j]:>3.0f}%")
    lines.append("<pre>" + "\n".join(_esc(r) for r in rows) + "</pre>")

    lines.append(
        "<i>Each meal shows what was saved when you confirmed it. The lines "
        "underneath show where it came from, ingredient by ingredient — they "
        "always add up to the meal above them.</i>"
    )
    return "\n".join(lines)


def user_food_list_card(foods: Sequence[Any]) -> str:
    if not foods:
        return (
            "🥫 <b>Your own foods</b>\n\n"
            "<i>Nothing yet. Some things you eat are not in a national food "
            "database — home preparations, a local bakery's bun, a brand sold "
            "in one country — and without a row of their own the resolver has "
            "to pick the least-bad wrong answer every time.</i>\n\n"
            "<b>Reply with a name</b> to make one — <code>pickle juice</code>."
        )
    lines = ["🥫 <b>Your own foods</b>", ""]
    rows = []
    for f in foods:
        kcal = f"{float(f['kcal_100g']):,.0f} kcal" if f["kcal_100g"] is not None else "no energy"
        rows.append(f"{_short_note(f['description'])[:22]:<24}{kcal:>12} /100 g")
        rows.append(f"    {f['n_nutrients']} nutrients · used {f['times_used']}×")
    lines.append("<pre>" + "\n".join(_esc(r) for r in rows) + "</pre>")
    lines += ["", "<b>Reply with a name</b> to add another. Your own rows "
                  "outrank USDA's generic one when you log that name."]
    return "\n".join(lines)


def user_food_made_card(name: str, per_100g: dict, parts: Sequence[str],
                        yield_g: float, *, raw_g: float | None = None,
                        pieces: int | None = None,
                        portion_unit: str = "serving") -> str:
    from ..config import CARB, ENERGY_KCAL, FAT, FIBER, PROTEIN, SODIUM

    lines = [f"🥫 <b>{_esc(name)}</b> saved", ""]
    lines.append("<i>Made from:</i>")
    for pline in parts:
        lines.append(f"   • {_esc(pline)}")
    # Which mass the panel was divided by, said out loud. Baking drives off
    # water, so a panel computed against the raw sum understates a baked food
    # by whatever the tin lost, and nothing downstream can detect that from the
    # numbers alone — every figure stays internally consistent while being
    # uniformly too low.
    if raw_g and yield_g < raw_g * 0.995:
        lines += ["", f"<i>{raw_g:,.0f} g in, {yield_g:,.0f} g out — "
                      f"{raw_g - yield_g:,.0f} g lost in cooking. Per 100 g of "
                      f"the finished thing:</i>"]
    else:
        lines += ["", f"<i>Yielding {yield_g:,.0f} g, so per 100 g:</i>"]
    lines.append(
        "<pre>"
        f"{'Energy':<10}{per_100g.get(ENERGY_KCAL, 0):>8,.0f} kcal\n"
        f"{'Protein':<10}{per_100g.get(PROTEIN, 0):>8.1f} g\n"
        f"{'Carbs':<10}{per_100g.get(CARB, 0):>8.1f} g\n"
        f"{'Fat':<10}{per_100g.get(FAT, 0):>8.1f} g\n"
        f"{'Fibre':<10}{per_100g.get(FIBER, 0):>8.1f} g\n"
        f"{'Sodium':<10}{per_100g.get(SODIUM, 0):>8.0f} mg"
        "</pre>"
    )
    if pieces:
        lines.append(
            f"\n🔪 <b>1 {_esc(portion_unit)} = {yield_g / pieces:,.0f} g</b> "
            f"({pieces} per batch). Say <i>one {_esc(portion_unit)} of "
            f"{_esc(name.lower())}</i> and that is the mass it uses — no "
            f"weighing, and no guessing either.")
    elif raw_g is not None and not (raw_g and yield_g < raw_g * 0.995):
        # Only worth raising where it was not already answered. A recipe that
        # stated its finished weight has nothing to warn about.
        lines.append(
            "\n<i>If this is baked or reduced, add <code>makes 850 g, 16 "
            "slices</code> next time — the panel is currently divided by the "
            "raw ingredient mass, which understates anything that loses water "
            "in the oven.</i>")
    lines.append(
        f"\n<i>Every figure is a SQL join against the rows those ingredients "
        f"matched — nothing here was estimated. Log it by name and it will be "
        f"used instead of USDA's nearest guess.</i>"
    )
    return "\n".join(lines)


def plan_card(data: dict, cost_usd: float | None = None) -> str:
    """The weekly review. The one card in this system written by a model.

    It says so, because everything else here is arithmetic and the difference
    matters: a median is a fact and a finding is an argument.
    """
    lines = ["🧠 <b>Weekly review</b>", ""]

    findings = data.get("findings") or []
    if findings:
        lines.append("<b>What the data says</b>")
        for f in findings:
            lines.append(f"   • {_esc(f.get('statement', ''))}  "
                         f"<i>({_esc(str(f.get('confidence', '')))})</i>")
            if f.get("evidence"):
                lines.append(f"     <i>{_esc(f['evidence'])}</i>")
        lines.append("")

    recs = data.get("recommendations") or []
    if recs:
        lines.append("<b>Proposed changes</b>")
        for r in recs:
            lines.append(f"   <b>{r.get('n')}.</b> {_esc(r.get('action', ''))}")
            if r.get("expected_effect"):
                lines.append(f"       → {_esc(r['expected_effect'])}")
            if r.get("risk"):
                lines.append(f"       <i>risk: {_esc(r['risk'])}</i>")
        lines.append("")
    else:
        lines += ["<b>No changes proposed.</b> "
                  "<i>Recommending nothing is a valid outcome and the honest one "
                  "when the data supports no change.</i>", ""]

    gap = data.get("what_the_data_cannot_tell_you")
    if gap:
        lines += [f"<b>What this cannot tell you</b>\n   <i>{_esc(gap)}</i>", ""]

    if recs:
        lines.append("Reply <code>apply 1 3</code> to take some, "
                     "<code>apply all</code>, or ignore this.")
    lines.append(
        "<i>Written by a model from 28 days of medians and target comparisons — "
        "never from your raw log. It is the only card here that is an argument "
        "rather than arithmetic, and nothing changes until you say so.</i>"
    )
    if cost_usd:
        lines.append(f"<i>💸 {fmt_usd(cost_usd)}</i>")
    return "\n".join(lines)


def morning_note(name: str | None, yesterday: Sequence[Any],
                 coverage: dict | None = None) -> str:
    """Good morning, and at most one thing to do about yesterday.

    Template and SQL only — invariant 4. It reads a ceiling that was crossed
    and names the food that crossed it, which is arithmetic on last night's
    log rather than an opinion about it.

    One suggestion, never a list. A morning message that opens with five
    corrections is one you learn to swipe away, and the point of it is to be
    read.
    """
    hi = f"☀️ Good morning{', ' + _esc(_title(name)) if name else ''}."
    if not yesterday:
        return (f"{hi}\n\n<i>Nothing logged yesterday, so nothing to report. "
                "A clean slate either way.</i>")

    sc = day_score(yesterday, coverage or {})
    lines = [hi, ""]

    # The single most useful thing, chosen in a fixed order: a breached ceiling
    # first because it is actionable this morning, then the weightiest floor
    # you missed, then praise, which is what is left when neither applies.
    if sc.breached:
        worst = sc.breached[0]
        # "Cholesterol 250%" carries the percentage; the lever is separate and
        # only offered where there is an honest one-line answer.
        bare = worst.split()[0] if worst else ""
        lever = next((v for k, v in MORNING_LEVERS.items() if k.startswith(bare)), None)
        lines.append(f"Yesterday you went over on <b>{_esc(worst)}</b>."
                     + (f" Today, {lever}." if lever else ""))
    elif sc.short:
        lines.append(f"Yesterday came up short on <b>{_esc(sc.short[0])}</b>.")
    else:
        lines.append("Yesterday hit every floor without crossing a ceiling. "
                     "Hard to improve on.")
    # The coverage figure leads rather than trails: "89% covered" is the
    # summary of a day, and the single excess is the footnote to it. The other
    # way round reads as a scolding with a statistic attached.
    lines.insert(1, f"<b>{sc.covered:.0%} of your minimums covered</b> yesterday.")
    if sc.assessable:
        # Shown even at zero: "0 of 13 fully met" is the most informative
        # version of that line, not the one worth hiding.
        lines.append(f"<i>{sc.reached} of {sc.assessable} floors fully met.</i>")
    return "\n".join(lines)


# Ceilings that have an obvious, single, sayable lever. Deliberately short:
# a suggestion for every nutrient would be a lookup table pretending to be
# advice, and most excesses have no one-line answer.
MORNING_LEVERS: dict[str, str] = {
    "Cholesterol": "fewer egg yolks would be the biggest single change",
    "Sodium": "most of it is usually bread, cheese and anything jarred",
    "Saturated fat": "butter, cheese and fatty cuts are where it concentrates",
    "Total Sugars": "the sweet drinks and snacks first, before the fruit",
    "Alcohol": "a night off is the whole lever",
    "Energy": "the largest single item is usually easier to halve than to drop",
    "Caffeine": "an earlier last coffee matters more than a smaller one",
}


def off_product_card(p: dict, name: str) -> str:
    """An OpenFoodFacts panel, shown before anything is saved.

    Says where the numbers came from. USDA rows are laboratory assays, a
    photographed label is a panel you were holding, and this is a database
    anyone may edit — three different claims, and a card that blurred them
    would be the most quietly wrong thing here.
    """
    from ..config import CARB, ENERGY_KCAL, FAT, FIBER, PROTEIN, SAT_FAT, SODIUM, SUGAR

    panel = p["panel"]
    lines = [f"🌍 <b>{_esc(p['name'] or name)}</b>"]
    bits = [b for b in (p.get("brand"), p.get("quantity")) if b]
    if bits:
        lines.append(f"<i>{_esc(' · '.join(bits))}</i>")
    lines.append("")

    rows = []
    for nid, label, unit in (
        (ENERGY_KCAL, "Energy", "kcal"), (PROTEIN, "Protein", "g"),
        (CARB, "Carbs", "g"), (SUGAR, "of which sugars", "g"),
        (FAT, "Fat", "g"), (SAT_FAT, "of which saturated", "g"),
        (FIBER, "Fibre", "g"), (SODIUM, "Sodium", "mg"),
    ):
        if nid in panel:
            rows.append(f"{label:<20}{panel[nid]:>8,.1f} {unit}")
    lines.append("<pre>" + "\n".join(_esc(r) for r in rows) + "</pre>")
    lines.append("<i>per 100 g</i>")

    if p.get("serving"):
        lines.append(f"<i>label serving: {_esc(p['serving'])}</i>")

    lines += ["", f"<i>From OpenFoodFacts, which anyone can edit — {len(panel)} "
                  f"nutrients populated, and it rates its own entry "
                  f"{p['completeness']:.0%} complete. Check the figures against "
                  "the packet before saving; nothing missing has been filled in "
                  "with a guess.</i>"]
    return "\n".join(lines)


def off_choices_card(results: Sequence[dict], term: str) -> str:
    if not results:
        return (f"🌍 Nothing on OpenFoodFacts for <b>{_esc(term)}</b> with a "
                "usable panel.\n\n<i>A barcode finds it reliably where a name "
                "does not — the long number under the stripes.</i>")
    lines = [f"🌍 <b>Found on OpenFoodFacts</b> for {_esc(term)}", ""]
    for i, p in enumerate(results, 1):
        brand = f" · {_esc(p['brand'])}" if p["brand"] else ""
        kcal = p["panel"].get(1008)
        lines.append(f"<code>{i}</code> {_esc(p['name'])}{brand}"
                     + (f" — {kcal:,.0f} kcal/100 g" if kcal else ""))
        # Whatever tells this entry apart from the one above it.
        detail = []
        if p.get("quantity"):
            detail.append(_esc(p["quantity"]))
        if p.get("completeness"):
            detail.append(f"{float(p['completeness']):.0%} complete")
        if p.get("barcode"):
            detail.append(f"…{_esc(str(p['barcode'])[-4:])}")
        if detail:
            lines.append("      <i>" + " · ".join(detail) + "</i>")

    # Same product, two entries, different numbers. Worth naming: the reader
    # would otherwise take the first and never learn that the site disagrees
    # with itself about this packet.
    seen: dict[str, list[int]] = {}
    for i, p in enumerate(results, 1):
        key = f"{(p.get('name') or '').strip().lower()}|{(p.get('brand') or '').strip().lower()}"
        seen.setdefault(key, []).append(i)
    clashes = []
    for idxs in seen.values():
        if len(idxs) < 2:
            continue
        kcals = [results[i - 1]["panel"].get(1008) for i in idxs]
        kcals = [k for k in kcals if k]
        if len(kcals) >= 2 and max(kcals) - min(kcals) > 0.05 * max(kcals):
            clashes.append(" and ".join(str(i) for i in idxs))
    if clashes:
        lines += ["", "⚠️ <i>" + "; ".join(clashes)
                  + " are the same product with different figures. "
                    "OpenFoodFacts is written by the public and holds "
                    "conflicting entries — the pack size and completeness "
                    "above are the best guide, and the barcode on your packet "
                    "settles it.</i>"]

    lines += ["", "<i>Tap one to see its panel. Nothing is saved until you "
                  "have looked at it.</i>"]
    return "\n".join(lines)


def food_label_card(name: str, panel: dict, data: dict,
                    warnings: Sequence[str] = ()) -> str:
    """A transcribed food panel, verbatim beside the reading.

    The `as printed` column is the point. A transcription is checkable at the
    moment it is made — against the packet in your hand — and only if you can
    see what was read. Without it this is just another number to trust.
    """
    lines = [f"🏷 <b>{_esc(_title(name))}</b>", ""]
    for w in warnings:
        lines.append(f"⚠️ <i>{_esc(w)}</i>")
    if warnings:
        lines.append("")

    if not panel:
        lines.append("<i>Nothing was transcribed from that photo.</i>")
        if data.get("unreadable"):
            lines.append(f"\n<b>What it could not use:</b> "
                         f"{_esc(', '.join(data['unreadable'][:6]))}")
        if data.get("not_tracked"):
            lines.append(f"\n<i>Read, but no nutrient id here: "
                         f"{_esc(', '.join(data['not_tracked'][:6]))}</i>")
        # The two failures that actually happen, and what to do about each.
        lines.append(
            "\n<i>A figure given as a range — <code>128–141 kcal</code> — is "
            "not a number, and picking a point inside it would be an estimate "
            "rather than a transcription. Nor is a search result a panel: it "
            "summarises several products at once, and the one in your hand is "
            "not necessarily any of them.\n\n"
            "Photograph the panel on the packet, send the barcode, or type the "
            "ingredients and I will add them up from USDA.</i>")
        return "\n".join(lines)

    rows = []
    for n in data.get("nutrients") or []:
        nid = int(n.get("nutrient_id", 0))
        if nid not in panel:
            continue
        rows.append(f"{_short_note(str(n.get('as_printed', '')))[:30]:<32}"
                    f"{panel[nid]:>9,.1f}")
    lines.append("<pre>" + "\n".join(_esc(r) for r in rows) + "</pre>")
    lines.append("<i>as printed · per 100 g</i>")

    if data.get("not_tracked"):
        lines.append(f"\n<i>Read but not counted, no nutrient id here: "
                     f"{_esc(', '.join(data['not_tracked'][:6]))}</i>")
    if data.get("unreadable"):
        lines.append(f"\n⚠️ <b>Could not read:</b> "
                     f"{_esc(', '.join(data['unreadable'][:4]))}"
                     "\n<i>Left out rather than guessed. Retake the photo if "
                     "those matter.</i>")

    lines.append("\n<i>Check these against the packet before saving. A wrong "
                 "digit here is wrong in every future serving of this food.</i>")
    return "\n".join(lines)


# Below this, an entry is not a protein serving. A coffee with 3 g in it is
# not a fourth meal and counting it as one makes an uneven day look even.
PROTEIN_SERVING_MIN = 8.0


def protein_spread(entries: Sequence[Any]) -> str | None:
    """How today's protein is distributed, not just how much of it there is.

    There is no absorption ceiling to model — a 100 g bolus is absorbed, and
    Trommelen et al. (2023) found it produced a greater and longer anabolic
    response than 25 g, so discounting protein above some per-meal figure
    would understate what was actually eaten. That is the one direction of
    error this system exists to avoid.

    What the evidence does support is spread: three or four servings of 30-40 g
    beat one of 120 g for total daily synthesis. So this reports the
    distribution and leaves the total alone.
    """
    servings = sorted(
        (float(e["protein"]) for e in entries if float(e["protein"] or 0) >= PROTEIN_SERVING_MIN),
        reverse=True,
    )
    if len(servings) < 2:
        return None
    total = sum(float(e["protein"] or 0) for e in entries)
    shown = " · ".join(f"{g:.0f} g" for g in servings[:5])
    more = f" +{len(servings) - 5}" if len(servings) > 5 else ""
    line = (f"🥩 <b>{total:.0f} g</b> across {len(servings)} servings — "
            f"{shown}{more}")
    # Named only when it is lopsided enough to act on. A gentle skew is
    # normal and flagging it every day would train you to ignore the line.
    if servings[0] > 0.5 * total and total > 40:
        line += "\n<i>Most of it in one meal — spreading it across the day "
        line += "does more for muscle than the same total in one sitting.</i>"
    return line
