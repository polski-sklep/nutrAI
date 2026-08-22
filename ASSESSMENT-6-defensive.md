# Assessment 6 — defensive constructs

Every `try`/`except` and every value-level fallback in `nutrai/`, classified.
Line numbers are as of the commit this file lands in.

The question asked of each one: **when this fires, does a human find out?**
A handler that turns a failure into a sentence on screen or a line in the log
is doing its job. A handler that turns a failure into a plausible number is the
thing this codebase was built to avoid.

Headline: the exception handlers are in unusually good shape — 46 of 48 are at
a genuine trust boundary (model output, Telegram, Anthropic, OpenFoodFacts HTTP,
user-typed text) and nearly all carry a comment explaining the incident that put
them there. The real findings are on the value side: two places convert an
*absent* number into a *fabricated* one, and one of them feeds the only artefact
in the system where a model draws conclusions.

---

## 1. `try` / `except` — full inventory

### JUSTIFIED — untrusted or unavailable input, failure is surfaced

**OpenFoodFacts HTTP** (third-party network, arbitrary JSON)

| site | verdict |
|---|---|
| `nutrai/off.py:71` `except Exception` on the GET | Network, TLS, timeout, malformed JSON. Logs a warning and returns `None`; every caller treats `None` as "not found" and says so on screen. |
| `nutrai/off.py:91` `except (TypeError, ValueError)` | A panel field that is not a number is skipped, and `_panel` *returns the list of absences* rather than swallowing them — the docstring says why. This is the correct shape. |
| `nutrai/off.py:98` `except (TypeError, ValueError): pass` | Same, for the salt→sodium conversion. Falls through to `missing`. |

**HTTP endpoint** (`/activity`, an external client posts to it)

| site | verdict |
|---|---|
| `nutrai/http_api.py:83` `except Exception` on `request.json()` | Body is attacker-controlled. Returns 400 with a reason. |
| `nutrai/http_api.py:97, 127, 140, 151` | `minutes`/`kcal`, `rpe`, `local_date`, `at`. Each returns a 400 naming the field. Nothing is coerced, nothing is defaulted; the comment at 108 explains why `rpe` goes through `Decimal` rather than `float`. Exemplary. |

**Anthropic API** (network, rate limits, billing) — all route to `_parse_failed`

`nutrai/bot.py:554` (backdated text), `2117` (food-as-meal), `2194` (`/food`
ingredients), `2328` (`/improve`), `2582` (food label), `3246` (photo parse),
`3346` (text parse), `4043` (supplement label).

`_parse_failed` (`bot.py:3260`) logs with `log.exception` and edits the
placeholder into a sentence from `_FAILURES` that distinguishes *wait* from
*fix*. Documented as deliberate in the task brief and in the code. **Keep all.**
The reason a broad `except Exception` is right here rather than a narrow one is
in the docstring: an unhandled exception leaves "🍽 digesting…" on screen
forever, which is indistinguishable from a slow model.

**Telegram API**

| site | verdict |
|---|---|
| `nutrai/bot.py:4260` `except TelegramBadRequest` in `resend_unformatted` | Documented in CLAUDE.md as a deliberate, now-unreachable safety net. It re-raises anything that is not a parse-entities failure — note that, it is what makes it safe. **Do not touch.** |
| `nutrai/bot.py:4291` `except Exception` in `sync_command_menu` | Comment: "a stale menu must not stop the bot starting". Logs a warning. Correct trade. |
| `nutrai/jobs/notify.py:187, 236, 251, 270, 289` | Five `bot.send_message` calls inside per-user loops. Comment at 251: "a blocked bot must not kill the sweep". Each logs a warning naming the telegram_id. Correct. |
| `nutrai/jobs/report.py:47, 53` | Same shape, split deliberately so "the model call failed" and "the send failed" are distinguishable in the log. |
| `nutrai/jobs/audit.py:280` | Same shape — **but the logging was broken. See finding 1.** |

**Model output** (the schema is a request, not a guarantee)

| site | verdict |
|---|---|
| `nutrai/llm/parse.py:227, 232` in `count_from_text` | Regex over user text. Returns `None` rather than a guess, and range-checks (`0 < n <= 100`) with the comment "a 'portion' of 400 slices is a misread, not an order". |
| `nutrai/llm/parse.py:733` `except (TypeError, ValueError, KeyError)` in `per_100g` | A transcribed panel line that is not a number is dropped. This is the supplement-label path where CLAUDE.md's amendment applies: transcription, never estimation. Dropping beats approximating. |
| `nutrai/core/supplements.py:96` | Same, and better: every drop appends a `Rejected` with a reason, and the reasons reach the card. This is the model to copy. |

**User-typed text**

| site | verdict |
|---|---|
| `nutrai/bot.py:613, 617` (`/history` arg), `732` (`/incomplete` tokens), `1123` (`_date` format loop), `1607` (`/weight`), `3479`, `3490` (awaited numeric replies) | All parse a human's typing. Each either falls through to the next interpretation or replies with the usage. `1607`'s comment is worth reading: a bare `/weight` from the menu means "what was I last?", so a parse failure is answered rather than scolded. |
| `nutrai/core/dsl.py:490` in `resolve_date` | A malformed `@2026-13-40` falls back to today. Defensible for a DSL where the alternative is refusing a whole repeat command over one token — and `_when_from_ops` shows the resulting date on the card. Marginal; see LOW. |

**Structural**

| site | verdict |
|---|---|
| `nutrai/bot.py:3201` `except asyncio.CancelledError` in `_flush_album` | Not error handling — it *is* the album-buffer mechanism. Each new photo cancels the pending flush. Correct. |

### BORDERLINE — surfaced, but broader than it needs to be

| site | note |
|---|---|
| `nutrai/bot.py:1196` `except Exception: value = None` | Wraps `PROFILE_VALIDATORS[field](raw)`. The user is *told* which line was refused and why ("❌ Height takes cm — got 'tall'"), and the comment explains that refusing beats coercing. Not hiding anything from the user. But `Exception` also catches a bug *inside* a validator and reports it as bad input. Narrowing to `(ValueError, TypeError, KeyError, ArithmeticError)` would keep the behaviour and stop a genuine defect masquerading as a typo — `zoneinfo.ZoneInfoNotFoundError` subclasses `KeyError`, so the timezone validator is covered. MEDIUM. |
| `nutrai/bot.py:1283, 1546` `except (profile_mod.IncompleteProfile, TypeError)` | `IncompleteProfile` is the real signal; `TypeError` is standing in for "one of these `None`s reached arithmetic". `1546` even has to reconstruct which it was (`"some fields"`). Making `derive_targets` raise `IncompleteProfile` for every missing input and dropping `TypeError` would remove the guesswork. MEDIUM. |
| `nutrai/bot.py:3253` `except Exception` around `_present` | Reported to the user as a *parse* failure, but `_present` also resolves, computes and writes a pending entry — a database error here reads as "the model refused that request". It is logged with a stack trace, so nothing is lost, and the alternative (a hung placeholder) is worse. Keep; the imprecision is in the wording, not the handling. LOW. |
| `nutrai/core/render.py:145-150` `except (TypeError, KeyError, IndexError): fdc = None` | Dual-shape duck typing: `getattr(c, "fdc_id", None) or c["fdc_id"]`. Every live caller passes a `ResolvedComponent` or a `dsl.Component`, never a mapping, so the subscript only ever runs when `fdc_id` is legitimately `None` — and then raises `TypeError` and is caught. It works, it only suppresses one informational line, and it is unreadable. `getattr(c, "fdc_id", None)` alone would do. MEDIUM (cosmetic). |

### HIDING AN ERROR

| site | finding |
|---|---|
| `nutrai/jobs/audit.py:277-280` (before this change) | **Finding 1, fixed.** See below. |

---

## 2. Value-level fallbacks

### Finding 1 — the daily audit's failure log could never fire *(HIGH — fixed)*

```python
except Exception as exc:  # a blocked bot must not kill the job
    log_exc = getattr(bot, "_log", None)
    if log_exc:
        log_exc.warning("audit failed for %s: %s", u["telegram_id"], exc)
```

`nutrai/jobs/audit.py` has no module logger, and nothing anywhere in the repo
sets `_log` on a `Bot` — not the aiogram class, not `bot.run()`, not the test
harness. So `log_exc` is always `None` and the warning is *never emitted*: this
is a bare `except: pass` wearing a logging call as a disguise.

What that costs: `audit_and_report` is the daily job whose entire purpose is to
notice the failures that "produced a plausible number and raised nothing". If
its own delivery starts failing, a job that has silently stopped reporting looks
exactly like a job with nothing to report — and the module docstring says the
only reason any of those fifteen bugs surfaced was somebody reading a card.

Every sibling job (`notify.py`, `report.py`) already uses a module-level
`logging.getLogger`. **Fixed:** `audit.py` now does too, with a comment recording
why the line was wrong.

### Finding 2 — the planner's evidence pack fabricates zero medians *(HIGH — fixed)*

`nutrai/core/plan.py:38` (before):

```python
m7 = med7.get(nid, 0.0)
...
elif lo is not None and m7 < lo:
    status = f"under by {lo-m7:.0f}"
```

`db.window_medians` returns a row only for a nutrient that something logged in
the window actually *reports*. A micronutrient that no logged food carries — the
Branded-row case ARCHITECTURE.md §0.3 is entirely about — has no key, becomes
`0.0`, and is handed to Opus as:

```
1103 | Selenium, Se | µg | 0.0 | 0.0 | 55 | - | under by 55
```

That is the phantom-deficiency bug, in the single artefact where a model is
asked to draw conclusions and propose target changes. `PLAN_SYSTEM` explicitly
instructs it to "say so rather than reporting a deficiency that is really a
measurement gap" — and it cannot, because the pack has already erased the
distinction. The pack also carries no per-nutrient coverage column at all, so
there is no second signal to catch it. `med28.get(nid, 0)` had the same defect.

**Fixed:** a pure helper `_median_row()` renders an absent median as `-` and its
status as `no data — nothing logged in this window reports it`. A genuine zero
still reads as a shortfall. `tests/test_nutrition.py::test_an_unmeasured_nutrient_is_not_reported_to_the_planner_as_zero`
asserts all three cases, per the "silent wrong answer" bar in CLAUDE.md.

### Finding 3 — `price()` still guesses at Sonnet pricing *(HIGH value, MEDIUM to implement — reported, not implemented)*

`nutrai/llm/client.py:47`:

```python
p_in, p_out = PRICES.get(model, PRICES["claude-sonnet-5"])
```

The recorded decision in CLAUDE.md § "Decided, not yet done" is unambiguous:
this must return `None`, log a warning, store `llm_call.cost_usd` as NULL, and
have `/spend` print "3 calls, cost unknown". **The silent fallback is still
there.** It is a cost you cannot compute, reported as $0.006.

Not implemented here because it is not a local edit. The full change:

1. `sql/0NN_cost_unknown.sql` — `ALTER TABLE llm_call ALTER COLUMN cost_usd DROP NOT NULL, ALTER COLUMN cost_usd DROP DEFAULT;`
   (`cost_usd numeric NOT NULL DEFAULT 0` is the schema encoding the same
   mistake.) Must be applied by hand to the existing volume — `sql/*.sql` runs
   on first boot only.
2. `client.price()` → `float | None`, with a `log.warning` naming the unpriced
   model. `ToolResult.cost_usd` becomes `float | None`.
3. `nutrai/llm/parse.py:136,146,151` (`spent = res.cost_usd; spent += res2.cost_usd`),
   `:377,460` (`cost = 0.0; cost += res.cost_usd`) — every accumulator must
   propagate `None` rather than treat it as zero, or the honesty is lost one
   line downstream.
4. `nutrai/db.py:970` — `kw.get("cost_usd", 0)` is a second copy of the same
   mistake and must become `kw.get("cost_usd")`.
5. `nutrai/db.py:979` `spend_report` — `sum(cost_usd)` must separate NULL from
   zero: `sum(cost_usd) FILTER (WHERE cost_usd IS NOT NULL)` plus
   `count(*) FILTER (WHERE cost_usd IS NULL)`. Same for `db.py:1427`
   (`round(sum(cost_usd) * 100, 1) AS cents` on the week card).
6. `render.plan_card` / `confirm_card` already type `cost_usd: float | None` and
   guard with `if cost_usd:` — no change needed there.

Worth doing; it needs an integration run against the live database, which this
pass could not take.

### Absent-vs-zero, remaining sites

| site | verdict |
|---|---|
| `nutrai/db.py:1350-1358` `COALESCE(i.kcal, 0) AS kcal_yesterday` etc. in `sleep_predictors` | **MEDIUM.** A day with nothing logged becomes "0 kcal, 0 g alcohol, 0 mg caffeine" and is correlated against that night's sleep rating as if it were a fast. `sleep_predictors` has no production caller today (integration tests only), so nothing acts on it yet — but it also has no `day_quality` filter, which CLAUDE.md § "Days that do not count" requires of anything that draws a conclusion across days. Both should be fixed together, before it is wired. |
| `nutrai/db.py:811` `COALESCE(sum(ln.amount),0)` → `observation.kcal_since_waking` | **MEDIUM.** Same shape, and this one *is* live: a rating typed before the day's first log records "0 kcal since waking" as a covariate. The neighbouring `hours_fasted` handling is the model to follow — it is withheld as NULL when unknown, and `db.observations()` filters on that. `kcal_since_waking` deserves the same treatment; it needs a nullable column check and an `observations()` change, so it is not a one-liner. |
| `nutrai/db.py:579, 599, 448, 461` `COALESCE(k.amount, 0) AS kcal` | **MEDIUM.** An entry whose components all resolved to rows carrying no energy has no `log_nutrient` row for 1008, and `/today`, `/last` and `/history` print "0 kcal" for it. This is precisely the failure `core/nutrition.ENERGY_FALLBACKS` and the audit's `energy_zero` check exist for — the display layer is quietly undoing the honesty. Rendering `—` instead would need a coordinated change across `render.day_card`, `/last` and `/history`; worth scoping as its own change. |
| `nutrai/bot.py:2959-2960` `float(e['kcal'] or 0)` | Same issue, the `/last` card. Listed separately because it is a second `or 0` layered on top of a `COALESCE` that has already done it. |
| `nutrai/db.py:756` `float(r["med"] or 0)` in `window_medians` | **LOW.** `percentile_cont` over a group that exists cannot be NULL, so this is unreachable. It is now the only thing standing between the dict and honest `None`s if finding 2's helper is ever extended. Leave, but do not copy. |
| `nutrai/db.py:400`, `bot.py:3561` `float(r["grams_sigma"] or 0)` | **LOW.** `grams_sigma numeric NOT NULL DEFAULT 0` — cannot be NULL. Redundant, harmless. |
| `nutrai/db.py:572` `float(r["covered_frac"] or 0)` | **LOW.** Coverage NULL → 0 means "0% of the plate measured", which is the *conservative* direction: it warns rather than reassures. |
| `nutrai/db.py:737` `float(val or 0.0)` in `day_energy_sigma` | **LOW.** A day with no confirmed entries returns ±0, and `estimate.fmt_pm` drops the bar entirely when the value is 0 — so nothing false is printed. |
| `nutrai/db.py:785` `current_fast_hours(...) or 0.0` | **LOW.** `/fast` (bot.py:801) checks `h <= 0` and says "Nothing logged yet, so there is no fast to measure." `/rate` (bot.py:1028) does not, and prints "0.0h since you last ate" to a user who has never logged. Cosmetic, first-run only. |
| `nutrai/core/nutrition.py:136-143` `nutrients.get(nid, 0.0)` in `energy_cross_check` | **LOW, deliberate.** A missing macro biases the recomputed Atwater figure *down*, which makes the check fire rather than pass — a false alarm, not a hidden error. And `kcal_db <= 0` returns `ok=False` explicitly rather than pretending. Correct as it stands. |
| `nutrai/jobs/audit.py:184,194` `COALESCE(fb.amount,0)*2` | **LOW.** Same reasoning: absent fibre makes the audit's own cross-check stricter. |
| `nutrai/core/suggest.py:90,112` `nuts.get(nid, 0.0)` | **LOW, arguably correct.** A food whose row does not report selenium scores as contributing none toward a selenium gap — which is the honest answer to "will this close it?". You cannot claim a food helps on the strength of an unmeasured value. |
| `nutrai/core/render.py:127` `float(getattr(c, "sigma", 0) or 0)` | **LOW.** Load-bearing: `dsl.Component` has no `sigma` field, so the repeat and fix cards genuinely cannot show ranges. The provenance mark (`≈`) still appears, so nothing claims to be measured. See finding 4 for the better fix. |
| `nutrai/config.py:109-110` `os.getenv("TELEGRAM_TOKEN", "")` | **LOW, keep.** An empty default lets the 294-test suite import `config` with no environment. A missing Anthropic key surfaces cleanly through `_failure_reason`'s "The Anthropic API key is being rejected" branch. |
| `nutrai/http_api.py:225` `if not TOKEN: log.warning(...); return None` | **JUSTIFIED.** Fails *closed* — the endpoint stays off rather than running unauthenticated — and says so loudly at startup. |

### Finding 4 — the fix-path confirm card is rendered from the wrong list *(MEDIUM — not implemented)*

`nutrai/bot.py:3630-3652`. The entry is stored from `resolved`
(`[... for c in new_comps if c.fdc_id]`, with sigma recomputed from provenance —
the comment above it is explicit about why zeroing sigma would be wrong), but
the card is rendered from `new_comps`. Two consequences:

- Components with no `fdc_id` are **listed on the card and excluded from the
  totals** — exactly the failure `render.confirm_card`'s `unresolved` block was
  written to prevent ("a total computed from part of a plate is not a small
  error, it is a different meal"). The repeat path at `bot.py:3838` already
  handles this correctly, with a `dropped` warning; the fix path was never given
  the same treatment.
- The ranges never show, because `dsl.Component` carries no sigma — even though
  the stored components do.

Passing `resolved` and `unresolved=[c.label for c in new_comps if not c.fdc_id]`
fixes both. Not implemented: it changes what a user sees on a live path, and the
brief asked for conservatism.

Related, and worse in principle: on **both** the fix path (`bot.py:3616-3626`)
and the repeat path (`bot.py:3777-3787`), an added component whose resolver call
returns nothing is appended nowhere and mentioned nowhere. Type `+kiwi`, get a
card with no kiwi and no explanation. `dropped` catches `fdc_id is None`, which
this case never produces. MEDIUM.

---

## 3. Recommendations

**HIGH — implemented in this commit**

1. `jobs/audit.py` — module logger, replacing a warning that could never fire.
2. `core/plan.py` — absent medians render as `-` / "no data", never `0.0` /
   "under by N". With a test.

**HIGH value, deferred for a schema migration**

3. `llm/client.py:price()` → `None`, per the recorded decision. Six-step change
   listed under finding 3, including `ALTER TABLE llm_call`.

**MEDIUM**

4. Render the fix-path confirm card from `resolved`, and surface unresolvable
   additions on both the fix and repeat paths (finding 4).
5. `observation.kcal_since_waking` — withhold as NULL when the day has no log,
   matching `hours_fasted`'s treatment, and filter it in `db.observations()`.
6. `sleep_predictors` — drop the `COALESCE(..., 0)` on intake, and add the
   `day_quality` filter, before anything calls it.
7. Display an absent energy figure as `—` rather than `0 kcal` (`db.py:448,461,
   579,599`, `bot.py:2959`).
8. Narrow `bot.py:1196` to `(ValueError, TypeError, KeyError, ArithmeticError)`.
9. Make `profile.derive_targets` raise `IncompleteProfile` for every missing
   input so `bot.py:1283,1546` can drop `TypeError`.

**LOW**

10. `render.py:145-150` — drop the mapping fallback; `getattr` alone suffices.
11. Give `/rate` the same "nothing logged yet" guard `/fast` has (`bot.py:1028`).
12. Remove the unreachable `or 0` coercions on `NOT NULL` columns
    (`db.py:400`, `bot.py:3561`) — but as churn-neutral drive-bys only.

**Deliberately kept, do not remove**

`bot.resend_unformatted` · `_parse_failed` / `_failure_reason` and all eight
call sites · every `bot.send_message` handler in the scheduled jobs · the
OpenFoodFacts and `/activity` boundaries · every model-output parse in
`llm/parse.py` and `core/supplements.py` · `except asyncio.CancelledError` in
`_flush_album`, which is the album buffer itself · `client.MAX_RETRIES = 4`,
whose comment records the dead-DNS incident that set it.
