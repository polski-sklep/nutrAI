"""Does a USDA row come back when you search for it in your own words?

Self-supervised, so it needs no hand-labelled ground truth and scales to the
whole corpus. For each sampled row the query is built from the row's OWN words:
the head noun plus the one or two rarest words in the description. That is a
fair model of what a person types - "pork jowl", not "Pork, fresh, variety
meats and by-products, jowl, raw" - and the row itself is the correct answer by
construction.

It measures exactly the pathology in docs/resolution/RECONCILED.md section 1:
trigram similarity falls as a description gets longer, and USDA descriptions
get longer as they get more specific, so the rows that describe a food most
precisely are the hardest to reach. Recall@1 by description length is the
number that shows it.

    python scripts/eval_retrieval.py --n 400
    python scripts/eval_retrieval.py --n 400 --json out.json
"""
from __future__ import annotations

import argparse, asyncio, json, re, sys
from collections import Counter
sys.path.insert(0, "/Users/Jacob/Projects/nutrAI")

from nutrai import db

STOP = {"and", "with", "without", "the", "from", "not", "raw", "nfs", "ns",
        "prepared", "commercially", "type", "all", "other", "than", "for"}


def query_for(description: str, df: Counter) -> str | None:
    """The words a person would actually type for this row.

    Head noun, plus the rarest one or two remaining words. The head noun is
    kept because it is how USDA names the food; the rare words are what
    distinguish this row from its siblings, and they are also the words that a
    long description buries.
    """
    segs = [s.strip() for s in description.split(",") if s.strip()]
    if not segs:
        return None
    words = [w for w in re.findall(r"[a-z]+", description.lower())
             if len(w) > 2 and w not in STOP]
    if not words:
        return None
    head = re.findall(r"[a-z]+", segs[0].lower())
    head = [w for w in head if len(w) > 2] or words[:1]
    rest = [w for w in words if w not in head]
    rest.sort(key=lambda w: df[w])          # rarest first
    picked = head[:1] + rest[:2]
    return " ".join(dict.fromkeys(picked))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--json")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    p = await db.pool()
    rows = await p.fetch(
        """SELECT fdc_id, description, data_type FROM food
            WHERE retired_at IS NULL AND owner_user_id IS NULL
            ORDER BY md5(fdc_id::text || $2::text) LIMIT $1""",
        a.n, str(a.seed))

    df: Counter = Counter()
    for r in await p.fetch("SELECT description FROM food"):
        df.update(set(w for w in re.findall(r"[a-z]+", r["description"].lower())
                      if len(w) > 2))

    hit1 = hit5 = miss = skipped = 0
    by_len: dict[str, list[int]] = {}
    misses: list[dict] = []

    for r in rows:
        q = query_for(r["description"], df)
        if not q:
            skipped += 1
            continue
        found = await db.search_foods(q, limit=a.limit, user_id=None)
        ids = [c["fdc_id"] for c in found]
        rank = ids.index(r["fdc_id"]) + 1 if r["fdc_id"] in ids else None
        bucket = ("short (<30)" if len(r["description"]) < 30
                  else "medium (30-59)" if len(r["description"]) < 60
                  else "long (60+)")
        by_len.setdefault(bucket, []).append(1 if rank == 1 else 0)
        if rank == 1:
            hit1 += 1
        elif rank:
            hit5 += 1
        else:
            miss += 1
            if len(misses) < 40:
                misses.append({"query": q, "wanted": r["description"],
                               "got": found[0]["description"] if found else None,
                               "got_sim": round(float(found[0]["sim"] or 0), 3) if found else None})

    n = hit1 + hit5 + miss
    print(f"n={n} (skipped {skipped})")
    print(f"  recall@1  {hit1:4d}  {hit1/n:.1%}")
    print(f"  recall@{a.limit}  {hit1+hit5:4d}  {(hit1+hit5)/n:.1%}")
    print(f"  missed    {miss:4d}  {miss/n:.1%}")
    print("\nrecall@1 by description length — the length effect, if it is there:")
    for k in ("short (<30)", "medium (30-59)", "long (60+)"):
        v = by_len.get(k, [])
        if v:
            print(f"  {k:16} {sum(v)/len(v):6.1%}   (n={len(v)})")
    print("\nnot retrieved at all:")
    for m in misses[:12]:
        print(f"  {m['query'][:28]:28} -> {str(m['got'])[:40]:40} | wanted: {m['wanted'][:44]}")

    if a.json:
        json.dump({"n": n, "recall_at_1": hit1 / n, "recall_at_k": (hit1 + hit5) / n,
                   "by_length": {k: sum(v)/len(v) for k, v in by_len.items()},
                   "misses": misses}, open(a.json, "w"), indent=1)

asyncio.run(main())
