"""Seed the global food vocabulary with the mappings verified by hand.

Every row here was probed before and after, and the target checked against
USDA's own figures. This is the seed, not the corpus: the 651 mappings the
audit upheld are loaded separately once extracted from the critique files.

    python scripts/seed_synonyms.py            # report only
    python scripts/seed_synonyms.py --apply
"""
from __future__ import annotations

import asyncio, sys
sys.path.insert(0, "/Users/Jacob/Projects/nutrAI")

from nutrai import db

SRC = "audit-2026-08"

# surface, expands_to, relation, confidence, verified fdc_id, why
SEED: list[tuple[str, str, str, str, int | None, str]] = [
    # --- spellings: the same word, written the way USDA does not ------------
    ("kebab", "kabob", "spelling", "high", 172509,
     "USDA spells it kabob in all 9 rows; kebab returned 0. Breaks Persian, "
     "Turkish, Levantine, Afghan and Uyghur queries with one token."),
    ("kebabs", "kabob", "spelling", "high", 172509, "plural of the above"),
    ("shish kebab", "shish kabob", "spelling", "high", None, "same spelling bridge"),
    ("yoghurt", "yogurt", "spelling", "high", 2705414,
     "Commonwealth spelling reached 4 of 153 yogurt rows."),
    ("lingonberry", "lingenberry", "spelling", "high", 169805,
     "USDA's own spelling is lingenberry; the correct row was unreachable."),
    ("lingonberries", "lingenberry", "spelling", "high", 169805, "plural"),
    ("courgette", "zucchini", "spelling", "high", None, "British name, US row"),
    ("aubergine", "eggplant", "spelling", "high", None, "British name, US row"),
    ("rocket", "arugula", "spelling", "high", None, "British name, US row"),
    ("coriander leaf", "cilantro", "spelling", "high", None,
     "British 'coriander' is the leaf; USDA files leaf under cilantro. The "
     "bare word is left alone deliberately - it is also the seed spice."),
    ("mangetout", "snow peas", "spelling", "high", None, "British name"),
    ("swede", "rutabaga", "spelling", "high", None, "British name"),

    # --- synonyms: a different name for the same food -----------------------
    ("prawn", "shrimp", "synonym", "high", 2706360,
     "Commonwealth word; reached 0 of 69 shrimp rows."),
    ("prawns", "shrimp", "synonym", "high", 2706360, "plural"),
    ("king prawns", "shrimp", "synonym", "high", 2706360, "same"),
    ("porridge", "oatmeal cooked", "synonym", "high", 2708380,
     "Returned nothing, forcing UK users onto 'oatmeal', which auto-matched "
     "Pie/Cookie, oatmeal until the FNDDS head guard landed."),
    ("porridge oats", "oatmeal", "synonym", "high", 2708380, "same"),
    ("guanciale", "cured pork jowl", "synonym", "high", 168269,
     "Cured pork jowl. USDA holds the jowl row; the word reaches nothing. "
     "The case this whole audit started from."),
    ("pancetta", "cured pork belly bacon", "synonym", "high", 167914,
     "Cured pork belly - the same cut as streaky bacon, unsmoked. Kept "
     "separate from guanciale: belly and jowl differ materially in fat."),
    ("rapeseed oil", "canola oil", "synonym", "high", None,
     "Rapeseed IS canola. The bare query took Oil, grapeseed until the "
     "qualifier guard blocked it; canola scored 0.200."),
    ("linseed", "flaxseed", "synonym", "high", None, "Same seed, British name."),
    ("linseeds", "flaxseed", "synonym", "high", None, "plural"),
    ("mince", "ground beef", "synonym", "medium", None,
     "British 'mince' is usually beef but not always - medium, so it only "
     "ever adds a search term."),

    # --- translations: the user's own locale --------------------------------
    ("chleb", "bread", "translation", "high", None, "Polish"),
    ("maslo", "butter", "translation", "high", 2710154, "Polish"),
    ("jajko", "egg", "translation", "high", 2707152, "Polish"),
    ("jajka", "egg", "translation", "high", 2707152, "Polish plural"),
    ("mleko", "milk", "translation", "high", 2705384, "Polish"),
    ("ser", "cheese", "translation", "high", 2705704, "Polish"),
    ("kurczak", "chicken", "translation", "high", None, "Polish"),
    ("wolowina", "beef", "translation", "high", 2705822, "Polish"),
    ("wieprzowina", "pork", "translation", "high", None, "Polish"),
    ("ryz", "rice", "translation", "high", 2708402, "Polish"),
    ("ziemniaki", "potato", "translation", "high", None, "Polish"),
    ("marchewka", "carrot", "translation", "high", None, "Polish"),
    ("cebula", "onion", "translation", "high", None, "Polish"),
    ("twarog", "farmer cheese dry curd cottage cheese", "translation", "medium", None,
     "Polish quark. Nearest USDA is dry-curd cottage cheese; the make differs, "
     "so medium - it adds a search term and never pre-empts."),

    # --- regional: one word, two foods --------------------------------------
    ("jelly", "gelatin dessert", "regional", "medium", 2710310,
     "British 'jelly' is the gelatin dessert (60 kcal); USDA's Jelly is the "
     "fruit spread (266 kcal) and auto-matches at 1.000. Medium and additive "
     "on purpose: for an American user the current behaviour is correct, so "
     "this must widen the candidate list rather than redirect it."),
]


async def main() -> None:
    apply = "--apply" in sys.argv
    p = await db.pool()
    ok = bad = 0
    for surface, expands, rel, conf, fdc, note in SEED:
        folded = db.fold_query(surface.lower())
        # The SAME predicate search_foods retrieves with. Checking trigram
        # alone was wrong and said so loudly: `kabob` scores under pg_trgm's
        # 0.3 threshold against `Lamb, cubed for stew or kabob (leg and
        # shoulder), ...` - the length effect biting the verification of the
        # fix for the length effect - while the full-text arm finds it at once.
        hits = await p.fetchval(
            "SELECT count(*) FROM food WHERE "
            "(to_tsvector('english', description) @@ plainto_tsquery('english', $1) "
            " OR description % $1) "
            "AND owner_user_id IS NULL AND retired_at IS NULL", expands)
        # An expansion that finds nothing is worse than useless: it would add a
        # dead query and hide the fact that the food is genuinely absent.
        flag = "" if hits else "  <-- EXPANSION FINDS NOTHING"
        if not hits:
            bad += 1
        else:
            ok += 1
        print(f"  {folded:22} -> {expands:34} {rel:11} {conf:6} {hits:>4} rows{flag}")
        if apply and hits:
            await p.execute(
                """INSERT INTO food_synonym
                     (surface, expands_to, fdc_id, relation, confidence, source, note)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)
                   ON CONFLICT (surface, expands_to) DO NOTHING""",
                folded, expands, fdc, rel, conf, SRC, note)
    print(f"\n{ok} usable, {bad} expansions find nothing")
    print("applied" if apply else "DRY RUN - pass --apply to write")

if __name__ == "__main__":
    asyncio.run(main())
