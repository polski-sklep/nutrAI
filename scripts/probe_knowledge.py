"""Ask the live resolver what it would do with a food name, without logging anything.

Every agent in the knowledge audit uses this one probe so the findings are
comparable. It deliberately does NOT consult food_alias: an alias is a cache of
a past resolution for one user, and measuring it would measure the cache rather
than the knowledge. Same reasoning as scripts/golden.py.

    python scripts/probe_knowledge.py guanciale halloumi "pork jowl"
    python scripts/probe_knowledge.py --file terms.txt --json
"""
from __future__ import annotations

import argparse, asyncio, json, sys
sys.path.insert(0, "/Users/Jacob/Projects/nutrAI")

from nutrai import db
from nutrai.config import AUTO_MATCH_SIMILARITY, WEAK_MATCH_SIMILARITY

# What the resolver would conclude, named so a report can group by it.
#   none  - every query returned nothing at all. USDA has no word for it.
#   weak  - a best candidate exists but scores below the weak floor: the right
#           answer was probably never on the list.
#   ask   - between the floors. The model tier would be asked, which is the
#           system working, not failing.
#   auto  - would be taken with no model consulted. The dangerous one when
#           wrong, because it also writes an alias that is never re-checked.
def verdict(sim: float | None) -> str:
    if sim is None:
        return "none"
    if sim >= AUTO_MATCH_SIMILARITY:
        return "auto"
    if sim < WEAK_MATCH_SIMILARITY:
        return "weak"
    return "ask"


async def probe(term: str, limit: int = 5) -> dict:
    # The global vocabulary is part of retrieval, so the probe must consult it
    # or it measures a resolver that no longer exists. Mirrors `_queries`:
    # a synonym adds a phrase to search on and never decides the match.
    rows = list(await db.search_foods(term, limit=limit, user_id=None))
    seen = {r["fdc_id"] for r in rows}
    for syn in await db.synonyms_for(term):
        for r in await db.search_foods(syn["expands_to"], limit=limit, user_id=None):
            if r["fdc_id"] not in seen:
                seen.add(r["fdc_id"])
                rows.append(r)
    rows.sort(key=lambda r: -float(r["sim"] or 0))
    rows = rows[:limit]
    cands = [
        {"fdc_id": r["fdc_id"], "description": r["description"],
         "data_type": r["data_type"], "sim": round(float(r["sim"] or 0), 3)}
        for r in rows
    ]
    top = cands[0] if cands else None
    return {
        "term": term,
        "verdict": verdict(top["sim"] if top else None),
        "top": top,
        "candidates": cands,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="*")
    ap.add_argument("--file", help="one term per line")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=5)
    a = ap.parse_args()

    terms = list(a.terms)
    if a.file:
        terms += [ln.strip() for ln in open(a.file) if ln.strip()
                  and not ln.startswith("#")]
    if not terms:
        ap.error("give some terms, or --file")

    out = [await probe(t, a.limit) for t in terms]
    if a.json:
        print(json.dumps(out, ensure_ascii=False))
        return
    counts: dict[str, int] = {}
    for r in out:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        top = r["top"]
        shown = f"{top['sim']:.3f}  {top['description']}" if top else "-      (nothing)"
        print(f"{r['verdict']:5} {r['term'][:34]:34} {shown}")
    total = len(out)
    print("\n" + "  ".join(f"{k}={v} ({v/total:.0%})" for k, v in sorted(counts.items())))

asyncio.run(main())
