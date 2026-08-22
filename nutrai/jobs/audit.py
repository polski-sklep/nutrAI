"""A daily check that the log means what it says.

Every check here exists because the failure it looks for actually happened, was
invisible at the time, and was found by hand afterwards. That is the problem
this module solves: each of these bugs produced a plausible number and no error,
and the only reason any of them surfaced was somebody reading a card closely and
thinking "that can't be right".

The common shape is worth naming. A wrong USDA row is internally consistent —
the Atwater cross-check passes, the macros look sane, nothing raises — so the
only evidence is a nutrient that does not belong: 17 g of fibre on a plate of
fried chicken, because the match was "Chicken, meatless". A component that
resolved to a row carrying no energy contributes zero calories and the guard
that would catch it skips rows whose energy is zero. Neither is detectable from
one number; both are obvious from the right query.

No model is called. SQL and arithmetic, per invariant 4 — an auditor that
depended on a model would share the failure modes of the thing it audits.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .. import db
from ..config import CARB, ENERGY_KCAL, FIBER
from ..core.nutrition import ENERGY_FALLBACKS
from ..llm.parse import INVERTING_TERMS

if TYPE_CHECKING:                      # annotation only, as in jobs/notify.py
    from aiogram import Bot

log = logging.getLogger("nutrai.audit")

# Fibre is carbohydrate-by-difference minus the digestible part, so a food whose
# fibre exceeds this share of its carbohydrate is either a bran product or the
# wrong row. On the plate that prompted this module it was 50%.
FIBRE_SHARE_OF_CARB = 0.40
# Below this fraction of a day's mass weighed or stated, the day's totals are an
# opinion. docs/ARCHITECTURE.md §4.5 puts the same number on the day card.
MASS_CONFIDENCE_FLOOR = 50.0
# An alias this well used has earned forty seconds of human attention.
PIN_SUGGEST_HITS = 5

# Words that pick out one member of a family of very similar foods. Within a
# set they are mutually exclusive: a thing is a white or a yolk or a whole egg,
# and never two of them.
#
# 99 g of "egg whites, fried" was matched to "Egg, whole, cooked, fried" and
# carried 397 mg of cholesterol that egg white does not contain — the day read
# 249% of its ceiling and the advice was to eat fewer yolks, on a day with one
# yolk in it. Trigram similarity cannot see this: the two names share every
# token that matters and differ by one word which is, precisely, the word that
# decides what the food is.
#
# Only families where the members differ enough for the mismatch to move a
# number. "Diced" versus "sliced" belongs nowhere near this list.
QUALIFIER_SETS: tuple[frozenset[str], ...] = (
    frozenset({"white", "yolk", "whole"}),        # egg
    frozenset({"skimmed", "skim", "whole"}),      # milk
    frozenset({"raw", "cooked", "dried"}),
    frozenset({"decaffeinated", "caffeinated"}),
    frozenset({"unsweetened", "sweetened"}),
)


def _qualifiers(text: str, family: frozenset[str]) -> set[str]:
    """Which of a family appear as whole words.

    Substrings will not do: "whole" is inside "wholemeal" and "white" is inside
    "whitefish". Nor will exact tokens — the label said "whites" and the row
    said "whole", so a trailing plural has to come off before comparing.
    """
    words = {w[:-1] if len(w) > 4 and w.endswith("s") else w
             for w in re.findall(r"[a-z]+", text.lower())}
    return words & family


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # error | warn | info
    summary: str
    detail: str
    entry_id: int | None = None


async def audit_user(user_id: int, days: int = 1) -> list[Finding]:
    """Every check, against the last `days` days of confirmed entries."""
    p = await db.pool()
    since = dt.date.today() - dt.timedelta(days=days)
    found: list[Finding] = []

    # --- a match that negates the food -------------------------------------
    # "Chicken, meatless, breaded, fried" scored high enough to auto-match a
    # real breaded chicken. Macros close enough to pass every guard; the only
    # tell was the fibre.
    terms = list(INVERTING_TERMS)
    for r in await p.fetch(
        """SELECT c.entry_id, c.label, f.description, e.name
             FROM log_component c
             JOIN food f ON f.fdc_id = c.fdc_id
             JOIN log_entry e ON e.id = c.entry_id
            WHERE e.user_id = $1 AND e.status = 'confirmed' AND e.local_date >= $2
              AND EXISTS (SELECT 1 FROM unnest($3::text[]) t
                           WHERE f.description ILIKE '%' || t || '%'
                             AND c.label NOT ILIKE '%' || t || '%')""",
        user_id, since, terms,
    ):
        found.append(Finding(
            "inverted_match", "error",
            f"{r['label']} is matched to a meat substitute",
            f"“{r['description']}” — if that is not what you ate, the whole entry "
            f"is wrong, not just this line.",
            r["entry_id"],
        ))

    # --- the qualifier that decides which food this is ---------------------
    for r in await p.fetch(
        """SELECT c.entry_id, c.label, f.description, round(c.grams) AS grams
             FROM log_component c
             JOIN food f ON f.fdc_id = c.fdc_id
             JOIN log_entry e ON e.id = c.entry_id
            WHERE e.user_id = $1 AND e.status = 'confirmed' AND e.local_date >= $2""",
        user_id, since,
    ):
        for family in QUALIFIER_SETS:
            in_label = _qualifiers(str(r["label"]), family)
            in_desc = _qualifiers(str(r["description"]), family)
            if in_label and in_desc and not (in_label & in_desc):
                found.append(Finding(
                    "qualifier_mismatch", "error",
                    f"{r['label']} is matched to a {sorted(in_desc)[0]} row",
                    f"“{r['description']}” — you said "
                    f"{sorted(in_label)[0]} and the row says {sorted(in_desc)[0]}, "
                    f"which for {r['grams']:.0f} g is usually a different food "
                    f"rather than a different wording.",
                    r["entry_id"],
                ))
                break

    # --- a component contributing no energy at all -------------------------
    for r in await p.fetch(
        """SELECT c.entry_id, c.label, f.description, round(c.grams) AS grams
             FROM log_component c
             JOIN food f ON f.fdc_id = c.fdc_id
             JOIN log_entry e ON e.id = c.entry_id
            WHERE e.user_id = $1 AND e.status = 'confirmed' AND e.local_date >= $2
              AND NOT EXISTS (SELECT 1 FROM food_nutrient fn
                               WHERE fn.fdc_id = c.fdc_id
                                 AND fn.nutrient_id = ANY($3::int[]))""",
        user_id, since, [ENERGY_KCAL, *ENERGY_FALLBACKS],
    ):
        found.append(Finding(
            "no_energy_row", "error",
            f"{r['label']} added 0 kcal",
            f"“{r['description']}” reports no energy in USDA, so its "
            f"{r['grams']:.0f} g are missing from the day's total.",
            r["entry_id"],
        ))

    # --- fibre out of proportion to carbohydrate ---------------------------
    for r in await p.fetch(
        """SELECT e.id, e.name, round(fib.amount) AS fibre, round(carb.amount) AS carb
             FROM log_entry e
             JOIN log_nutrient fib  ON fib.entry_id = e.id AND fib.nutrient_id = $3
             JOIN log_nutrient carb ON carb.entry_id = e.id AND carb.nutrient_id = $4
            WHERE e.user_id = $1 AND e.status = 'confirmed' AND e.local_date >= $2
              AND carb.amount > 0 AND fib.amount > carb.amount * $5""",
        user_id, since, FIBER, CARB, FIBRE_SHARE_OF_CARB,
    ):
        found.append(Finding(
            "fibre_implausible", "warn",
            f"{r['name']}: {r['fibre']:.0f} g fibre against {r['carb']:.0f} g carbs",
            "Fibre is part of carbohydrate, so this ratio usually means a "
            "component matched the wrong row rather than that the meal was "
            "unusually high in fibre.",
            r["id"],
        ))

    # --- macros that do not explain the energy -----------------------------
    # The Atwater cross-check runs before you confirm; this catches the entries
    # where it fired and was confirmed anyway.
    for r in await p.fetch(
        """SELECT e.id, e.name,
                  round(k.amount) AS kcal,
                  round(pr.amount*4 + cb.amount*4 + ft.amount*9 - COALESCE(fb.amount,0)*2) AS atwater
             FROM log_entry e
             JOIN log_nutrient k  ON k.entry_id = e.id AND k.nutrient_id = 1008
             JOIN log_nutrient pr ON pr.entry_id = e.id AND pr.nutrient_id = 1003
             JOIN log_nutrient cb ON cb.entry_id = e.id AND cb.nutrient_id = 1005
             JOIN log_nutrient ft ON ft.entry_id = e.id AND ft.nutrient_id = 1004
             LEFT JOIN log_nutrient fb ON fb.entry_id = e.id AND fb.nutrient_id = 1079
            WHERE e.user_id = $1 AND e.status = 'confirmed' AND e.local_date >= $2
              AND k.amount > 0
              AND abs(pr.amount*4 + cb.amount*4 + ft.amount*9
                      - COALESCE(fb.amount,0)*2 - k.amount) > k.amount * 0.12""",
        user_id, since,
    ):
        found.append(Finding(
            "atwater_mismatch", "warn",
            f"{r['name']}: macros imply {r['atwater']:.0f} kcal, stored {r['kcal']:.0f}",
            "A component is probably matched to the wrong food, or its mass is wrong.",
            r["id"],
        ))

    # --- a day built mostly on guesses -------------------------------------
    for r in await p.fetch(
        """SELECT local_date, pct_measured FROM v_day_mass_confidence
            WHERE user_id = $1 AND local_date >= $2 AND pct_measured < $3""",
        user_id, since, MASS_CONFIDENCE_FLOOR,
    ):
        found.append(Finding(
            "low_mass_confidence", "warn",
            f"{r['local_date']:%a %-d %b}: only {r['pct_measured']:.0f}% of the mass was weighed",
            "Every trend under this is noise. Weighing one dense item — oil, "
            "cheese, nuts — moves it more than weighing three light ones.",
        ))

    # --- an alias pointing at a row that negates the food -------------------
    # This is the one that makes the bug recur. A bad tier-2 match writes an
    # alias, and from then on the same food resolves to the same wrong row for
    # free, forever, without even a model call to reconsider it. The component
    # check above finds the meal; this finds the cause.
    for r in await p.fetch(
        """SELECT a.alias, a.hits, f.description
             FROM food_alias a JOIN food f ON f.fdc_id = a.fdc_id
            WHERE a.user_id = $1
              AND EXISTS (SELECT 1 FROM unnest($2::text[]) t
                           WHERE f.description ILIKE '%' || t || '%'
                             AND a.alias NOT ILIKE '%' || t || '%')""",
        user_id, terms,
    ):
        found.append(Finding(
            "inverted_alias", "error",
            f"“{r['alias']}” is permanently pointed at a meat substitute",
            f"It resolves to “{r['description']}” with no model call, so every "
            f"future log of it repeats the same error silently. Used {r['hits']} "
            f"time(s) so far.",
        ))

    # --- aliases carrying real weight that nobody has checked --------------
    for r in await p.fetch(
        """SELECT a.alias, a.hits, f.description
             FROM food_alias a JOIN food f ON f.fdc_id = a.fdc_id
            WHERE a.user_id = $1 AND NOT a.pinned AND a.hits >= $2
         ORDER BY a.hits DESC LIMIT 5""",
        user_id, PIN_SUGGEST_HITS,
    ):
        found.append(Finding(
            "unpinned_alias", "info",
            f"“{r['alias']}” has resolved {r['hits']} times, unverified",
            f"It points at “{r['description']}”. If that is right, pin it and it "
            f"can never be re-pointed by a later parse.",
        ))

    return found


def summarise(findings: list[Finding]) -> dict[str, int]:
    out = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        out[f.severity] = out.get(f.severity, 0) + 1
    return out


async def audit_and_report(bot: Bot) -> None:
    """Daily job. Silent when there is nothing to say."""
    p = await db.pool()
    for u in await p.fetch("SELECT id, telegram_id FROM app_user"):
        findings = await audit_user(u["id"], days=1)
        if not any(f.severity in ("error", "warn") for f in findings):
            continue
        from ..core import render

        try:
            await bot.send_message(
                u["telegram_id"], render.audit_card(findings), parse_mode="HTML"
            )
        except Exception as exc:  # a blocked bot must not kill the job
            # A module logger, like every other job here. This used to look for
            # a `_log` attribute on the bot, which nothing sets — so the one
            # signal that the daily audit could not be delivered was itself
            # swallowed, and a job that silently stopped reporting looked
            # exactly like a job with nothing to report.
            log.warning("audit failed for %s: %s", u["telegram_id"], exc)
