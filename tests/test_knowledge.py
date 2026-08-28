"""Regression tests for the food knowledge layer, generated rather than listed.

The audit that produced this layer probed 6,000+ terms across fifteen cuisines
and found the failures by *enumeration* — which is exactly what a hand-written
test set cannot reproduce, because it only ever knows the foods someone thought
of. So these tests generate their cases from the database and from the
vocabulary table itself: adding a synonym adds a test, and adding a USDA row
with an FNDDS dish head adds a test.

They are integration tests. `pytest -q` stays DB-free; these run under
`pytest -q -m integration`.
"""
from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nutrai:nutrai@localhost:5432/nutrai")


def _db_ready() -> tuple[bool, str]:
    try:
        import asyncpg
    except ImportError:  # pragma: no cover
        return False, "asyncpg not installed"

    async def check() -> tuple[bool, str]:
        try:
            con = await asyncio.wait_for(asyncpg.connect(DATABASE_URL), timeout=5)
        except Exception as exc:
            return False, f"no database at {DATABASE_URL}: {exc}"
        try:
            if not await con.fetchval("SELECT count(*) FROM food"):
                return False, "no USDA data loaded — run scripts/load_usda.py"
            return True, ""
        finally:
            await con.close()

    try:
        return asyncio.run(check())
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


_READY, _WHY = _db_ready()
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _READY, reason=_WHY)]


def run(coro):
    """One event loop per test, and the connection pool dies inside it.

    db.pool() memoises a pool bound to whatever loop created it. Closing it
    from a later asyncio.run() raises 'Event loop is closed' from deep inside
    asyncpg, which reads like a driver bug and is not one. Same helper as
    tests/test_integration.py, for the same reason.
    """

    async def wrapper():
        from nutrai import db

        try:
            return await coro
        finally:
            await db.close()

    return asyncio.run(wrapper())


# --------------------------------------------------------------- vocabulary


def test_every_synonym_reaches_at_least_one_row():
    """A synonym that retrieves nothing is worse than no synonym.

    It adds a dead query, costs a round trip, and — the part that matters —
    hides the fact that the food is genuinely absent, which is the one honest
    thing the resolver can say when USDA does not carry something.

    Generated from the table, so this fails the moment somebody adds a mapping
    without checking it, and it fails against the SAME retrieval predicate
    `search_foods` uses. Checking with trigram alone is not equivalent: `kabob`
    scores under pg_trgm's 0.3 threshold against `Lamb, cubed for stew or
    kabob (leg and shoulder), ...`, so a trigram-only check called five good
    expansions dead while the full-text arm found all of them.
    """
    from nutrai import db

    async def check() -> None:
        p = await db.pool()
        rows = await p.fetch(
            "SELECT surface, expands_to, confidence FROM food_synonym "
            "WHERE retired_at IS NULL")
        assert rows, "no vocabulary loaded — run scripts/seed_synonyms.py --apply"
        dead = []
        for r in rows:
            n = await p.fetchval(
                "SELECT count(*) FROM food WHERE "
                "(to_tsvector('english', description) @@ plainto_tsquery('english', $1)"
                " OR description % $1) "
                "AND owner_user_id IS NULL AND retired_at IS NULL",
                r["expands_to"])
            if not n:
                dead.append(f"{r['surface']!r} -> {r['expands_to']!r}")
        assert not dead, f"synonyms whose expansion retrieves nothing: {dead}"

    run(check())


def test_a_seeded_surface_reaches_a_candidate_through_the_resolver():
    """The vocabulary has to work where the resolver looks, not just in SQL.

    Every one of these returned NOTHING before the layer existed — not a weak
    match, nothing — and only a `none` verdict genuinely starves the model
    tier, because a weak match still escalates with its candidate list intact.

    Driven through `_candidates`, which is what `resolve_items` actually calls,
    because the probe script measuring `search_foods` directly is precisely the
    error that let an audit report guanciale as unreachable after it was
    reachable.
    """
    from nutrai import db
    from nutrai.llm.parse import _candidates

    async def check() -> None:
        p = await db.pool()
        surfaces = [r["surface"] for r in await p.fetch(
            "SELECT surface FROM food_synonym "
            "WHERE retired_at IS NULL AND confidence = 'high'")]
        assert surfaces, "no high-confidence vocabulary loaded"
        empty = []
        for s in surfaces:
            cands = await _candidates({"search_terms": "", "state": "unknown"}, s, None)
            if not cands:
                empty.append(s)
        assert not empty, f"high-confidence surfaces still reaching nothing: {empty}"

    run(check())


# ------------------------------------------------------- the FNDDS dish head


def test_no_fndds_dish_head_auto_matches_the_ingredient_it_names():
    """Generated over the corpus, not over the four examples that were found.

    FNDDS inverts USDA's usual shape: the head is what the thing IS and the
    food you asked for is the qualifier. `Pie, oatmeal` is a pie. The head then
    shares no word with a bare-ingredient query, so the first-segment branch of
    `unrequested_qualifier` finds nothing to narrow and the row walks past the
    guard written to catch it.

    Every `<dish>, <food>` row in the database is a case here, so a new USDA
    release adding one is covered without anybody noticing it needs to be.
    """
    from nutrai import db
    from nutrai.llm.parse import _DISH_HEAD_WORDS, unrequested_qualifier

    async def check() -> None:
        p = await db.pool()
        rows = await p.fetch(
            """SELECT description FROM food
                WHERE description LIKE '%, %' AND retired_at IS NULL
                  AND lower(split_part(description, ',', 1)) = ANY($1::text[])
                LIMIT 400""",
            sorted(_DISH_HEAD_WORDS))
        assert rows, "no dish-headed rows found — has the corpus changed?"

        leaked = []
        for r in rows:
            desc = r["description"]
            # The bare ingredient a person would type: the second segment.
            head = desc.split(",")[0].strip().lower()
            ingredient = desc.split(",")[1].strip().lower()
            if not ingredient or len(ingredient) < 3:
                continue
            # Not the inverted shape at all when the ingredient segment repeats
            # the head word — `Butter, Clarified butter (ghee)` and
            # `Sauce, cheese sauce mix, dry`. Someone typing "clarified butter
            # (ghee)" is asking for that exact row, so the guard is right to
            # let it through and this is not a case.
            if set(head.split()) & set(ingredient.split()):
                continue
            # The guard must refuse to let the dish stand in for the ingredient.
            if unrequested_qualifier(ingredient, desc) is None:
                leaked.append(f"{ingredient!r} -> {desc!r}")
        assert not leaked, (
            f"{len(leaked)} dish-headed rows would auto-match a bare "
            f"ingredient; first few: {leaked[:5]}")

    run(check())


def test_a_dish_head_the_query_asked_for_is_not_blocked():
    """The guard must not fire when the person asked for the dish.

    `avocado oil` wants `Oil, avocado`; `rice pudding` wants `Pudding, rice`.
    Blocking those would trade one silent wrong answer for another, which is
    how the first attempt at this guard promoted `Spaghetti squash, cooked`
    over `Spaghetti, spinach, cooked`.
    """
    from nutrai.llm.parse import unrequested_qualifier as uq

    for query, desc in [
        ("avocado oil", "Oil, avocado"),
        ("rice pudding", "Pudding, rice"),
        ("apple pie", "Pie, apple"),
        ("oatmeal cookie", "Cookie, oatmeal"),
        ("chicken soup", "Soup, chicken"),
    ]:
        assert uq(query, desc) is None, f"{query!r} vs {desc!r} was blocked"


def test_a_category_head_is_not_treated_as_a_dish():
    """`Cheese, brie` has the identical shape to `Pie, oatmeal` and is right.

    Cheese is what brie IS; a pie is not what oatmeal is. The distinction is
    semantic, which is why dish heads are a named list rather than a structural
    rule — Agent 2 of the resolution audit measured a head-noun rule wrongly
    rejecting 30 of 132 live aliases, `black pepper` -> `Spices, pepper, black`
    among them.
    """
    from nutrai.llm.parse import unrequested_qualifier as uq

    for query, desc in [
        ("brie", "Cheese, brie"),
        ("black pepper", "Spices, pepper, black"),
        ("salmon", "Fish, salmon, NFS"),
        ("cheddar", "Cheese, cheddar"),
        ("sirloin", "Beef, sirloin"),
    ]:
        assert uq(query, desc) is None, f"{query!r} vs {desc!r} was blocked"


# --------------------------------------------------------------- orthography


def test_folding_never_changes_an_ascii_query():
    """Generated over the corpus: the descriptions are the queries people type.

    Folding is applied to every search, so a fold that altered ordinary ASCII
    would silently change every lookup in the system.
    """
    from nutrai import db

    async def check() -> None:
        p = await db.pool()
        rows = await p.fetch(
            "SELECT description FROM food WHERE retired_at IS NULL "
            "ORDER BY md5(fdc_id::text) LIMIT 800")
        changed = [r["description"] for r in rows
                   if r["description"].isascii()
                   and db.fold_query(r["description"]) != r["description"]]
        assert not changed, f"ASCII text altered by folding: {changed[:5]}"

    run(check())


def test_folding_is_idempotent_and_leaves_no_diacritics():
    """Folding twice must equal folding once, and the result must be ASCII.

    Accented spellings returned ZERO candidates before this existed while
    their ASCII forms reached a list — a word the database holds, made
    unreachable by spelling it properly.
    """
    from nutrai.db import fold_query as f

    for s in ["rāmen", "shōyu", "jalapeño", "açaí", "crème fraîche", "gulyás",
              "bánh mì", "masło", "żurek", "smørrebrød", "döner", "Æbleskiver",
              "kaše", "ćevapi", "Ł", "plain ascii"]:
        once = f(s)
        assert f(once) == once, f"{s!r} folds unstably"
        assert once.isascii(), f"{s!r} folded to {once!r}, still non-ASCII"
