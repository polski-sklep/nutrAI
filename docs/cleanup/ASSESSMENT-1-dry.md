# Assessment 1 — duplication and consolidation

Scope: `nutrai/` (~13,600 lines). Line references are against the tree **after**
the changes in this commit unless marked "before".

## The short version

This codebase is much drier than its size suggests. There is almost no
copy-pasted *logic* — the near-duplicates I found are overwhelmingly
**presentation boilerplate** (send a card, open a wait, wrap a table in `<pre>`)
and **write-path shapes** (insert the same rows, close the same target row).
Whole categories that usually dominate a DRY pass turned up nothing:

- The USDA/nutrient arithmetic is already single-sourced. `profiles_for` is a
  one-line delegate to `_profiles_con` (`nutrai/db.py:245`), and the canonical-id
  fold is applied in exactly the three documented places.
- The SQL in `nutrai/jobs/audit.py` looks repetitive and is not: each query has
  a different SELECT list and a different predicate, and the shared
  `FROM log_component c JOIN food f … JOIN log_entry e …` prefix is three lines.
  Factoring it into an f-string fragment would make the queries ungreppable and
  less readable to buy nothing.
- The `canonical_id` / Atwater pair is correctly two rules, as documented.

Three things I deliberately did **not** do, and would push back on if asked:
collapse `cb_*` callback handlers behind a decorator, hoist the audit SQL, and
unify the four target-versioning writes. Reasons below.

One class of finding is worth calling out separately, because it is duplication
that has already produced divergence: **two pairs of screens are documented as
being the same command and behave differently** (finding M4). I preserved the
divergence rather than picking a winner — that is a product decision, not a
tidying one.

---

## HIGH confidence — implemented

### H1. `local_date_for(now, u["tz"], u["day_rollover_hour"])` in twelve places

Before: `nutrai/bot.py` ×4, `nutrai/jobs/notify.py` ×5, `nutrai/jobs/report.py`,
`nutrai/http_api.py` ×2. One of them (`cb_slot_log`) had re-inlined the body of
`bot._today()`, which sits eight lines from the top of the same file.

The two columns are never useful apart: a timezone without the rollover hour
dates the 01:09 glass of milk to the wrong day, which is the exact thing
`local_date_for` exists to get right. Added `db.day_for_user(user, when=None)`
(`nutrai/db.py:76`) and used it everywhere. `when` stays an explicit parameter
because the sweeps take one clock reading and reuse it for every user — a job
running across the rollover must not date half its users to one day and half to
the next, and defaulting to `now()` inside the helper would have hidden that.

`db.local_date_for` keeps its raw three-argument form: four callers inside
`db.py` have `tz`/`rollover_hour` as loose parameters, not a user row.

### H2. `INSERT INTO log_component …`, written twice, byte for byte

Before: `db.create_pending_entry` and `db.replace_components` held identical
11-line inserts including the `grams_sources[i] if grams_sources and i < len(…)`
override expression. Extracted to `db._write_components`
(`nutrai/db.py:363`), SQL unchanged.

This is the highest-value of the db extractions because of *what* the duplicated
expression does: `grams_source` is the column invariant 7 turns on. A divergence
between the create path and the `/fix` path would not produce a wrong number
today — it would quietly change what `portion_history` treats as evidence weeks
later.

### H3. `undo_entry` / `undo_last_entry` shared tail

Before: two 12-line blocks doing status flip + `times_logged` decrement +
`last_logged_at` recompute, identical apart from indentation, with the
explanatory comment present on only one of them. Extracted to
`db._discard_confirmed` (`nutrai/db.py:507`); both functions keep their own
distinct SELECT, which is the only thing that genuinely differs.

The invariant-2 and `times_logged` reasoning from both call sites is preserved in
the helper's docstring.

### H4. `_ask` existed and twenty prompts did not use it

`nutrai/bot.py:60` defines `_ask`, and the comment above `PROMPT_CONSUMERS`
(`nutrai/bot.py:36-49`) says in as many words why: opening a prompt and
consuming its reply used to be two edits in two places, and forgetting the
second was silent — six times, each found by a person rather than a test.

`_ask` had four call sites. Twenty other places hand-rolled the same pair
(`msg.answer(..., parse_mode="HTML")` then `db.put_pending(u["id"], kind, …)`).
Converted fifteen: `cb_define_food`, `cb_weight_new`, `cb_rating_note`,
`target_cmd`, `profile_cmd`, `cb_set_time`, `cb_off_rename`, `food_cmd`,
`_consume_food_name`, `/supp add` and `cb_supp_add` directly, plus the four
slot-settings screens via H5.

This is consolidation *onto an abstraction the module already argues for*, not a
new one, and it buys a real guard: `_ask` raises `KeyError` for a kind with no
registered consumer, which the hand-rolled sites bypassed entirely.

Not converted, with reasons:
- `rate` (`nutrai/bot.py:969`) and `cb_rate_kind` (`nutrai/bot.py:992`) open
  `rate_await` beside a keypad, and the second of them uses `edit_text` rather
  than `answer`.
- `report_cmd` (`nutrai/bot.py:2364`) opens `plan_apply` conditionally, after a
  message that was already sent and then edited.
- `_apply_profile_edits` (`nutrai/bot.py:1195`) opens `profile_await` only when
  something actually changed.
- `cb_fix` (`nutrai/bot.py:4212`) has a `log_entry` row, not a user row, so
  `u["id"]` is the wrong id. See L4.

**Ordering note.** `_ask` sends the message and *then* registers the wait; the
hand-rolled sites mostly did it the other way round. Both are one round-trip
apart and the failure modes differ only in which half survives a crash between
them — `_ask`'s order is the safer one (no orphan wait).

I also widened the regex in
`tests/test_commands.py::test_every_prompt_opened_has_something_that_consumes_it`
so it still matches every `_ask` site: it only looked for `_ask(msg, u, …)` and
would have silently stopped covering every prompt a button opens.

### H5. Four screens rendering the supplement slot-times card

Before: `_try_slot_lines`, `supp_schedule_cmd`, `/supp times` and
`cb_supp_times` each built `render.slot_settings_card(stack, await
db.slot_times(...))` and separately called `put_pending("slot_await")`. Now
`bot._send_slot_settings` (`nutrai/bot.py:1706`), which routes through `_ask`.

`stack` stays a parameter — see M4.

### H6. Three screens rendering the supplement stack card

Before: `supp_stack_cmd`, `/supp list` and `cb_supp_manage` each derived
`retired` with the same comprehension over a *second* full read of the stack,
then sent the same card with the same keyboard. Added
`db.retired_supplements` (`nutrai/db.py:1165`) and `bot._send_stack_card`
(`nutrai/bot.py:1688`).

### H7. `<pre>` block construction, thirteen times

`"<pre>" + "\n".join(...) + "</pre>"` appeared thirteen times in
`nutrai/core/render.py`. Replaced with `render._pre` (`nutrai/core/render.py:915`).

It takes *finished* lines rather than escaping them itself, so every call site's
escaping is byte-identical to before — some escape per row as they pad, some
have already escaped inside the row builder, and folding that decision into the
helper would have double-escaped four of them. The docstring is now the one
place the three CLAUDE.md rules about `<pre>` (single block, no nested tags, pad
before escaping) are written down next to the code that has to obey them.

Two sites are left alone (`nutrai/core/render.py:1693`, `2184`): those are a
single aligned literal string rather than a list of rows, and turning them into
lists to fit the helper would be churn.

### H8. Five copies of "send this and swallow the failure" in `notify.py`

Four scheduled jobs each looped over every user with an identical
`try: bot.send_message(..., parse_mode="HTML") except Exception: log.warning(...)`.
Now `notify._deliver` (`nutrai/jobs/notify.py:35`). The reasoning that was
carried by a trailing comment on one of the five ("a blocked bot must not kill
the sweep") is now the helper's docstring, where it applies to all of them.

### H9. The recipe-syntax examples, printed by three different cards

`_RECIPE_EXAMPLES` (`nutrai/bot.py:84`). The `… makes 850 g, 16 slices` line is
documentation of a grammar `_read_makes` actually parses, and it was written out
three times — one copy with mis-matched indentation, which is the copy-paste
fingerprint. An example that drifts from the parser teaches a syntax the bot
then refuses.

`tests/test_commands.py::test_every_recipe_prompt_mentions_the_makes_clause`
counted the literal, and after the change it passed *by coincidence* — a comment
elsewhere in `bot.py` happens to quote the same string. Rewrote it to assert
what now actually has to hold: the constant carries the clause, and every recipe
prompt inlines the constant. Strictly stronger than before.

---

## MEDIUM confidence — documented, not implemented

### M1. Four hand-written target versionings

`nutrai/db.py:1626` (`apply_targets`), `:1667` (`set_manual_target`), `:2118`
(`set_target_weight`), and `nutrai/core/plan.py:222`
(`apply_recommendations`). Each closes the standing row with the same two-line
UPDATE and then inserts a new one.

Invariant 3 ("target rows are versioned, never UPDATEd in place") is currently
enforced by four independent copies of the pattern, which is a good argument for
one named `db.version_target(con, …)`.

I did not do it, for three reasons:

1. The four INSERTs genuinely differ — column lists (`weight`, `period`),
   rationale sources (a literal, a parameter, the previous row's value, a JSON
   blob), and value coercion.
2. `target.weight` is `NOT NULL DEFAULT 1` (`sql/015_target_weight.sql:12`), so a
   unified helper has to decide whether a plain `/target` edit carries the
   existing weight forward or resets it to 1. Today it resets. That is a
   behavioural question, not a refactoring one.
3. `core/plan.py` passes raw floats where every other writer passes `db.num(...)`
   — asyncpg wants `Decimal` for `numeric`. Routing plan through a shared helper
   would fix that, which is a good change and a *behaviour* change in
   deliberately-unwired code that no test exercises.

Recommendation: do it when `core/plan.py` is wired (stage 5), as part of making
that path actually run, with answers to (2) and (3) decided explicitly.

### M2. Two escaping policies for the same job

`render._esc` uses `escape(s, quote=False)` and documents why
(`nutrai/core/render.py:905`). `nutrai/bot.py` calls bare `html.escape` — default
`quote=True` — at eighteen sites (`:791`, `:819`, `:2908`, `:2991`, `:3110`,
`:3124`, `:3127-3128`, `:3145`, `:3147`, `:3165`, `:3167`, `:3318`, `:3322`,
`:3915`, `:4015`, `:4086`, `:4223`).

Not a bug — Telegram decodes `&#x27;` and `&quot;` fine, so nothing renders
wrongly. But it is two functions for one policy, and CLAUDE.md sanctions both
spellings, so it will keep happening. The output difference is invisible; the
source difference is not, which is precisely `_esc`'s stated rationale.

Recommendation: replace `escape(` with `render._esc(` throughout `bot.py` and
drop the `from html import escape` import. Left undone because it changes the
bytes of eighteen live messages for a purely internal gain, and I would rather
that be a deliberate one-line-per-site decision than a side effect of this pass.

### M3. Callback-handler preamble

`u = await db.get_or_create_user(cq.from_user.id)` appears 44 times in
`bot.py`, usually followed by `int(cq.data.split(":", 1)[1])` (30 sites).

A decorator (`@callback("suppoff:")` yielding `(cq, u, arg)`) would remove
~90 lines. I did not do it, and I would argue against it: aiogram's
`dp.callback_query(F.data.startswith(...))` registration is already a decorator,
and stacking a second one that also parses the payload makes the handlers harder
to read in exchange for two lines each. The payload shapes vary (no arg, one int,
two colon-separated fields, an action id that has to be `take_pending`-ed), so
the decorator would need enough configuration to be worse than the repetition.

This is the clearest "two callers that merely look alike" case in the file.

### M4. `/supp list` ≠ `/stack`, and `/supp times` ≠ `/schedule`

`supp_stack_cmd` (`nutrai/bot.py:2675`) documents itself as "`/supp list` under
its own name" and `supp_schedule_cmd` (`:2693`) as "`/supp times` under its own
name". They are not the same:

- `/stack` and `/schedule` read `db.supplement_stack(u["id"])` — everything set up.
- `/supp list` and `/supp times` read the day-filtered stack from
  `nutrai/bot.py:2721` (`on_day=day`), which hides a supplement decided on but
  not yet started.

The comment at `nutrai/bot.py:2718-2720` says explicitly that "/stack and
/schedule show everything, because a supplement decided on but not begun is
exactly what those two screens exist to display" — which reads as an argument
that the subcommand forms are wrong, not that the difference is intended.

H5 and H6 deliberately take `stack` as a parameter so this divergence survives
the refactor untouched. Resolving it is a decision about what the screen means.

Recommendation: decide, then make the four entry points call the same thing with
the same argument.

### M5. The per-user loop preamble in the scheduled jobs

`SELECT id, telegram_id, tz, day_rollover_hour FROM app_user` appears at
`nutrai/jobs/notify.py:161`, `:251`, `:263`, `:276` and
`nutrai/jobs/report.py:32`, each followed by the same `now`/`day` setup.

An `async for u, now, day in _each_user()` generator would remove the preamble
from five jobs. Medium rather than high because two of the five need extra
columns (`display_name`, `wake_hour`, `morning_note`), so the helper needs a
column parameter, and a `SELECT *` version would quietly widen four queries.
Worth doing if a sixth job appears; not yet.

---

## LOW confidence — noted only

### L1. The "recalculate targets" keyboard, twice

`nutrai/bot.py:1228` and `:1526`. Three lines each, one button. A `_kb_recalc()`
helper is harmless and gains almost nothing; two sites is the bare minimum bar
and this is below the line where a name helps.

### L2. `if edit: edit_text(...) else: msg.answer(...)`

`nutrai/bot.py:3921` and `:3988`, both inside `_present`. Two occurrences in one
function; a local closure would be as long as the thing it replaces.

### L3. `except Exception as exc: await _parse_failed(note, exc); return`

Nine sites (`nutrai/bot.py:566`, `:2149`, `:2226`, `:2360`, `:2614`, `:3248`,
`:3255`, `:3348`, `:4045`).
The handler is already the shared part; what is repeated is three tokens of
Python. Leave.

### L4. `cb_fix` cannot use `_ask`

`nutrai/bot.py:4212` opens `fix_entry` with `e["user_id"]` from a `log_entry`
row rather than a user row, so `_ask`'s `u["id"]` would be the entry id. Fixable
by fetching the user, which costs a query on a hot path for tidiness. Left.

### L5. `import datetime as dt` inside the loop body

`nutrai/jobs/report.py:33`. A function-local import inside a `for`. Cosmetic,
unrelated to duplication, and ruff flags it as part of the resting-state noise.

### L6. `by_id = {r["nutrient_id"]: r for r in progress}`

Five sites across `render.py`, `bot.py`, `plan.py`, `notify.py`. A one-line
comprehension over differently-shaped inputs. Extracting it would name a dict
comprehension.

---

## What I checked and found clean

- `nutrai/core/dsl.py` — the three `unparsed.append(tok); i += 1; continue`
  branches are the tail of three structurally different match arms.
- `nutrai/jobs/audit.py` — see the preamble.
- `db.set_supplement_active` / `set_supplement_slot` — same shape, different
  columns, three lines each.
- `db.profiles_for` / `_profiles_con` — already single-sourced.
- `core/plan.py`, `template_by_slug`, `_log_template` — deliberately unwired,
  untouched.

## Verification

`pytest -q -m "not integration"` → **294 passed**, unchanged from before.
Integration tests not run (shared database).

`ruff check nutrai/` → 109 findings, down from 115. No new rule classes
introduced; the drop is removed duplicate lines, not any `--fix` pass.
