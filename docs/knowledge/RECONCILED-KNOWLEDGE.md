# Reconciliation — food knowledge and matching

28 Aug 2026. Inputs: fifteen domain audits (13,364 lines + a 1,867-line re-run)
and fifteen independent critiques (6,624 lines), over **6,000+ probed terms**,
plus direct verification of every claim this document acts on.

Supersedes the audits and critiques where they conflict. Nothing here is
encoded yet; §6 is the decision this document exists to put.

---

## 1. What the critics changed

**882 proposals reviewed · 651 upheld · 125 downgraded · 101 overturned.**

| domain | rev | upheld | down | overturned | guards caught | survived |
|---|---:|---:|---:|---:|---:|---:|
| southeast-asian | 121 | 108 | 8 | 5 | 7 | 17 |
| british-german-nordic | 82 | 59 | 14 | 9 | 4 | 6 |
| african | 74 | 60 | 8 | 6 | 0 | 10 |
| eastern-europe-balkan | 69 | 46 | 9 | 14 | 1 | 6 |
| greek-turkish-levantine | 65 | 52 | 6 | 7 | 6 | 8 |
| south-america | 64 | 47 | 12 | 5 | 2 | 2 |
| italian-french | 58 | 45 | 8 | 5 | 6 | 2 |
| japanese-korean | 58 | 43 | 8 | 7 | 10 | 34 |
| mexico-central-caribbean | 48 | 33 | 9 | 6 | 7 | 16 |
| taxonomy-fallback | 48 | 33 | 9 | 6 | 0 | 12 |
| chinese | 46 | 31 | 7 | 8 | 5 | 15 |
| iberian-lusophone | 46 | 30 | 8 | 8 | 1 | 10 |
| south-asian | 42 | 31 | 4 | 7 | 3 | 8 |
| middle-east-central-asia | 39 | 23 | 12 | 4 | 2 | 2 |
| normalization-orthography | 22 | 10 | 3 | 4 | 10 | 7 |
| **total** | **882** | **651** | **125** | **101** | **64** | **155** |

Two method errors ran through every audit, and through the reports built on
them. Both are verified.

### 1.1 The probe measures the bare label; the resolver does not

`scripts/probe_knowledge.py` queries `db.search_foods` with one string.
`parse.resolve_items` pools the user's label **and** the model's `search_terms`.
Measured with realistic search terms:

    ghee            0.227 "unreachable"  ->  AUTO 1.000 Butter, Clarified butter (ghee)
    brown bread     "274 kcal error"     ->  Bread, whole wheat leads at 0.762
    streaky bacon   "most valuable find" ->  AUTO 0.917 Pork, cured, bacon, cooked
    rapeseed oil    "auto to grapeseed"  ->  BLOCKED by unrequested_qualifier
    jam sandwich    "auto to Spam"       ->  BLOCKED

Any future audit of this system must probe the pooled query, not the label.

### 1.2 A `weak` verdict is not a failure

`resolve_items` appends to `need_model` unconditionally, so a weak match still
reaches the model tier **with its top-5 candidate list**. Only `none` — zero
candidates — starves that tier. The audits filed reachability gaps as their most
valuable class; most of that class is the system working as designed, and
CLAUDE.md already records escalation as a win rather than a regression.

**The failure classes that survive contact with the real resolver are two:**
`none`, and an `auto` that no guard blocks.

---

## 2. Three structural defects, all confirmed live

### 2.1 `unrequested_qualifier` is blind to FNDDS's inverted head

The guard assumes the first comma segment is the food's *name*. True of SR
Legacy — `Spaghetti, spinach, cooked` — and inverted in FNDDS, where the head is
the **dish type** and the queried food is the qualifier:

    unrequested_qualifier("oatmeal",      "Pie, oatmeal")       -> ALLOWED
    unrequested_qualifier("sweet potato", "Pie, sweet potato")  -> ALLOWED
    unrequested_qualifier("seaweed",      "Soup, seaweed")      -> ALLOWED

The head shares no word with the query, so the `i == 0` branch requires
`(words & q) and extra`, finds no overlap, and falls through to `continue`.

Confirmed auto-matching in production, past all three guards:

    sweet potato -> Pie, sweet potato    0.812   over Sweet potato, NFS  0.765
    oatmeal      -> Cookie, oatmeal      0.667   three-way tie, cookie at the head
    millet       -> Millet (FNDDS)       1.000   118 kcal cooked vs 378 raw
    jelly        -> Jelly (fruit spread) 1.000   266 kcal vs Gelatin dessert 60

This one mechanism explains the majority of the 155 surviving auto-matches. It
is a guard fix, not a data problem, and it is the highest-value change here.

`jelly` and `millet` were found by critics, not by the audits that owned those
domains — which is the argument for the critic pass having been worth its cost.

### 2.2 Exact similarity ties are common, and precedence breaks them wrongly

CLAUDE.md states that precedence "only breaks an exact tie in a float, which
does not occur". **Measured: it occurs on 6 of 10 common single-word queries.**
Short queries produce small rational similarities that collide.

    Oil, avocado    sr_legacy  precedence 2   0.6666667   <- taken
    Avocado, raw    fndds      precedence 3   0.6666667

So precedence *is* load-bearing, and it is ranking a derived product above the
food itself. Agent 1 of the resolution audit separately established that
precedence ranks Foundation first while Foundation is the thinnest dataset
loaded. Both claims in CLAUDE.md need correcting.

### 2.3 Terms that return nothing at all

Only `none` genuinely starves the model tier, and it is common. Confirmed:

- **Polish, the user's own locale** — `chleb`, `masło`, `jajko`, `mleko`,
  `ser`, `kurczak`, `wołowina`, `ryż`: bread, butter, egg, milk, cheese,
  chicken, beef, rice. All nothing.
- **One word breaking a cuisine group** — `kebab` returns 0 rows; USDA spells it
  `kabob` in all nine. That single token breaks Persian, Turkish, Levantine,
  Afghan and Uyghur queries at once.
- **British/Commonwealth vocabulary** — `prawn` reaches 0 of 69 shrimp rows;
  `yoghurt` reaches 4 of 153 yogurt rows; `porridge` returns nothing.
- **Non-ASCII forms** — macron spellings (`rāmen`, `shōyu`) return zero
  candidates while their ASCII forms work. No Unicode folding anywhere.
- **USDA's own misspelling** — `lingonberry` returns nothing; the row is
  `Cranberry, low bush or lingenberry, raw`.

---

## 3. What the knowledge layer must be

### 3.1 A global synonym table, separate from `food_alias`

`food_alias.user_id` is `NOT NULL` — it is a per-user cache of past
resolutions, correctly so. General knowledge ("guanciale is cured pork jowl")
has nowhere to live. It needs its own table, and it must not be conflated with
the cache: an alias records what *this user* did, a synonym records what is
*true*.

```sql
CREATE TABLE food_synonym (
    id           bigserial PRIMARY KEY,
    surface      text NOT NULL,          -- what a person types, lowercased
    fdc_id       integer NOT NULL REFERENCES food(fdc_id),
    relation     text NOT NULL,          -- 'synonym' | 'spelling' | 'regional'
    confidence   text NOT NULL,          -- 'high' | 'medium'
    source       text NOT NULL,          -- 'audit-2026-08' | 'user' | ...
    note         text,                   -- why, in one line
    retired_at   timestamptz,            -- corrected, kept as history
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (surface, fdc_id)
);
```

**It expands the query; it does not decide the match.** A surface hit adds its
row's description as an extra search term, and the existing ranking and the
three guards then run unchanged. That keeps one resolution path rather than
two, and means a wrong synonym degrades to a bad candidate rather than a silent
auto-match.

**`confidence = 'high'` only may pre-empt.** `medium` contributes a search term
and never an auto-match.

### 3.2 Normalisation, applied at query time only

Unicode/diacritic folding (`rāmen` → `ramen`, `masło` → `maslo`) is safe
mechanically and is applied to the query before search. Two refusals:

- **`chilli` / `chili` / `chile` must not be collapsed.** `chili` is also a
  dish. Folding them merges a spice with a stew.
- **Nothing is folded in the stored descriptions.** `food` is a faithful copy
  of a public dataset and the loader would undo any edit — the same reasoning
  that keeps `food_nutrient` unrewritten.

### 3.3 No automatic nutritional fallback — and this contradicts the brief

The brief asked that an unknown food fall back to "a nutritionally useful"
neighbour rather than nothing. **The evidence says refuse this for most cases**,
and the critics said so repeatedly and independently.

Gochujang is the clean example: nothing in USDA is close. Sriracha is 93 kcal,
2,124 mg sodium, 15 g sugar; gochujang is a 230–250 kcal fermented rice-soy
paste. A fallback here does not produce a slightly wrong number, it produces a
confident wrong number where the system currently produces an honest question.

The system already behaves correctly when it does not know: it escalates to the
model tier, and failing that asks the user to define the food. That is better
than a plausible neighbour, and it is the same argument invariant 6 makes about
missing nutrients — a skip is honest, a zero is not.

**What is built instead**: synonyms so the *right* row is reachable, and the
existing `/food` path for genuinely absent foods. A `nutritional_fallback`
relation is therefore **not** in the schema above. If you want it, say so and it
goes in as `medium`-only, never pre-empting, always labelled on the card.

---

## 4. What is deliberately not being built

- **Ranking changes.** Measured at ~1 point over six formulas; `COVERS_BOOST`
  stays at 1.35 with the window recorded in `db.py`.
- **pgvector / embeddings.** The failures are cases where the wrong row is
  *lexically nearer* and one word decides. An embedding smooths exactly the
  distinction that must be sharpened.
- **A dish → ingredient knowledge table.** The model already decomposes dishes
  well; carbonara *did* yield guanciale as an item. The failure was downstream,
  at resolution. Building a recipe table would be a second version of something
  that works.
- **The 101 overturned and 125 downgraded mappings.** Kept in the critique
  files as the record of what was refused and why. `bovril → yeast extract` is
  the specimen: Bovril is beef extract, and has been again since 2006.

---

## 5. Order of work

1. **The three code fixes** — FNDDS-inverted head in `unrequested_qualifier`;
   an exact-tie break that prefers the food over a derived product; Unicode
   folding on the query. All three are guarded by the golden set and by
   `scripts/eval_retrieval.py` before and after.
2. **`food_synonym` + query expansion**, then load the 651 upheld mappings with
   their confidence and source.
3. **The regression suite** — generated and invariant-style, not a handful of
   hand-written foods. It must fail if `guanciale` stops reaching cured pork, if
   an FNDDS dish-head auto-matches a bare ingredient, or if a `high` synonym
   stops resolving. Cases are generated from `food_synonym` itself, so adding
   knowledge adds tests.
4. **Re-measure** `eval_retrieval.py` and `golden.py` for the after numbers.

## 6. How future food knowledge is added

One route, so it cannot drift:

1. Probe the term with `scripts/probe_knowledge.py`. A verdict of `ask` or a
   correct `auto` needs no knowledge — leave it alone.
2. For `none`, or an `auto` on a wrong row, propose `surface -> fdc_id` with a
   confidence and a one-line reason.
3. **Verify the target's nutrients with a SELECT and quote them.** A mapping
   that is culturally right and nutritionally 3× off is a bad mapping.
4. Someone other than the proposer checks it. That is not ceremony: this pass
   overturned 101 of 882 proposals, including one outright factual error.
5. `high` is encoded; `medium` is encoded as a non-pre-empting search term;
   `low` is recorded as refused, with the reason, and not encoded.
