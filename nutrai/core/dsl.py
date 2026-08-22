"""The zero-token repeat path.

Most of what you eat, you have eaten before. Sending that fact to a language
model is waste: it is slower, it is non-deterministic, and it can be wrong
about something the database already knows exactly. So the common cases are a
regular grammar parsed locally, and only a genuine miss falls through to a
model — and then only with the dish's own component list as context, never a
photo and never the food database.

Grammar
-------
    <selector> [<op> ...]

    selector    1..9              index into the last /r menu
                <slug>            a dish or meal-template slug ("b", "stirfry")

    op          250 | 250g        total grams for the whole dish (proportional)
                x1.5 | *1.5       scale factor (a space is fine: x 1.5)
                half | double     scale 0.5 / 2.0
                -onion | no onion drop a component
                +50 rice | +rice  add a component (grams optional)
                rice 200          set one component to 200 g
                @14:00            override the log time
                @yesterday | @sat | @2026-08-14 | @-2
                                  file it on an earlier day, never a later one
                #dinner           override the meal slot

Examples
--------
    3                     repeat dish 3 exactly
    3 x1.5                repeat 50% larger
    3 -onion #lunch       repeat without onion, filed as lunch
    3 rice 200 +50 oil    repeat, rice set to 200 g, 50 g oil added
    b @08:30              log the whole 'b' breakfast template at 08:30
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

_NUM = r"\d+(?:[.,]\d+)?"
_UNIT = r"(?:g|gram|grams|gr|ml|kg|l)?"

RE_SCALE = re.compile(rf"^[x*×]({_NUM})$", re.I)
RE_QTY = re.compile(rf"^({_NUM}){_UNIT}$", re.I)
RE_ADD_QTY = re.compile(rf"^\+({_NUM}){_UNIT}$", re.I)
RE_ADD_LABEL = re.compile(rf"^\+(.+)$")
RE_DROP = re.compile(rf"^[-–—](.+)$")
RE_TIME = re.compile(r"^@(\d{1,2})[:.h]?(\d{2})?$")
# @yesterday, @yday, @sat, @2026-08-14, @-1 (one day back).
#
# Food gets remembered late. Without this the only options are to log it on the
# wrong day — which silently corrupts the day it lands on *and* the day it came
# from — or not to log it at all, which corrupts a third day by omission. A
# tracker that can only describe the present tense is one you stop trusting the
# moment you eat something away from your phone.
RE_DATE_ISO = re.compile(r"^@(\d{4})-(\d{2})-(\d{2})$")
RE_DATE_BACK = re.compile(r"^@-(\d{1,2})$")
WORD_DAYS = {"yesterday": 1, "yday": 1, "today": 0, "tonight": 0}
WEEKDAYS = {
    "mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2, "weds": 2,
    "wednesday": 2, "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "fri": 4,
    "friday": 4, "sat": 5, "saturday": 5, "sun": 6, "sunday": 6,
}
RE_SLOT = re.compile(r"^#(\w+)$")
RE_INDEX = re.compile(r"^\d{1,2}$")
RE_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,31}$", re.I)

WORD_SCALE = {"half": 0.5, "double": 2.0, "triple": 3.0, "twice": 2.0}


@dataclass(frozen=True)
class Scale:
    factor: float


@dataclass(frozen=True)
class TotalGrams:
    grams: float


@dataclass(frozen=True)
class SetComponent:
    label: str
    grams: float


@dataclass(frozen=True)
class AddComponent:
    label: str
    grams: float | None


@dataclass(frozen=True)
class DropComponent:
    label: str


@dataclass(frozen=True)
class SetTime:
    hour: int
    minute: int


@dataclass(frozen=True)
class SetSlot:
    slot: str


@dataclass(frozen=True)
class SetDate:
    """Days back from today, or an explicit date. Never forward.

    Relative rather than absolute where possible, because it is resolved against
    the user's own day-rollover hour at apply time — a meal at 01:00 belongs to
    the day that has not ended yet, and "yesterday" has to mean the same thing
    to this op as it does to everything else.
    """
    days_back: int | None = None
    iso: str | None = None
    weekday: int | None = None  # 0=Monday, the most recent one that has passed


Op = Scale | TotalGrams | SetComponent | AddComponent | DropComponent | SetTime | SetSlot | SetDate


@dataclass
class RepeatCommand:
    selector: str
    selector_kind: Literal["index", "slug"]
    ops: list[Op] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)

    @property
    def needs_model(self) -> bool:
        """True only when the local grammar could not account for every token.

        This is the metric to watch. If it climbs above a few percent of
        messages, the grammar is missing a shorthand you actually use — extend
        the grammar rather than paying a model to guess."""
        return bool(self.unparsed)


def _f(tok: str) -> float:
    return float(tok.replace(",", "."))


# "x1.5" mistyped as "x1.5.2" is still an attempt at a scale factor.
SIGIL_NUM = re.compile(r"^[x*×]\d", re.I)

# Words that say "this is a change to that dish" rather than "this is a food".
#
# Deliberately only connectives and comparatives. A food word must never appear
# here: the test is whether the phrase is *about* an existing dish, and any
# ingredient name added to this set would make its own dish unloggable.
MODIFIER_WORDS = frozenset({
    "with", "without", "no", "not", "minus", "plus", "extra", "more", "less",
    "instead", "swap", "sub", "skip", "hold", "add", "and", "but", "only",
    "half", "double", "light", "heavy", "big", "small", "large",
})


def parse(text: str) -> RepeatCommand | None:
    """Parse a repeat command, or return None if this is not one at all.

    Returning None (rather than raising) is deliberate: the handler then treats
    the message as a novel food description and routes it to the parser.
    """
    toks = text.strip().split()
    if not toks:
        return None

    head = toks[0]
    if RE_INDEX.match(head):
        cmd = RepeatCommand(selector=head, selector_kind="index")
    elif RE_SLUG.match(head):
        cmd = RepeatCommand(selector=head.lower(), selector_kind="slug")
    else:
        return None

    cmd.ops, cmd.unparsed = parse_ops(toks[1:])

    # "1 pickle" is one pickle, not dish 1 with a pickle in it.
    #
    # A bare index followed by a bare noun matched no operator, went to
    # `unparsed`, and `needs_model` then paid a model to read it as a
    # modification — which it duly did, adding 100 g of pickle to a protein
    # shake and logging it. "2 eggs", "1 banana" and "3 slices salami" are all
    # the same shape, and all of them are food.
    #
    # A real modification says so. Every one carries either an operator token
    # (-onion, +50 rice, x1.5, @14:00) or a connective, because that is how the
    # sentence works: you are describing a change *to* something. A noun on its
    # own describes a thing, not a change to one.
    #
    # Index selectors only. A slug that does not exist already falls through to
    # the parser in `_try_repeat`, so a bare digit is the one head that cannot
    # correct itself — and bare digits are exactly what quantities look like.
    if (cmd.selector_kind == "index" and not cmd.ops and cmd.unparsed
            and not any(t.lower() in MODIFIER_WORDS for t in cmd.unparsed)
            # A token wearing an operator's sigil is a failed operator, not a
            # food. "@99:99" is a time typed wrong, and answering it with a
            # search for something called "@99:99" helps nobody — the repeat
            # path is where it gets told it could not be read.
            and not any(t[:1] in "@#+-*×" or SIGIL_NUM.match(t) for t in cmd.unparsed)):
        return None
    return cmd


def parse_ops(toks: list[str]) -> tuple[list[Op], list[str]]:
    """The operator grammar on its own, with no selector in front of it.

    `parse` is "which dish, then what changed". A correction to a card already
    on screen is only the second half — the dish is already known — and
    `rice 200` would otherwise parse as dish "rice" scaled to a 200 g total,
    which is a different and silently wrong instruction.

    Shared rather than reimplemented so the two can never drift: there is one
    grammar, and `3 -onion +50 rice` and `-onion +50 rice` mean the same thing
    by construction.
    """
    ops: list[Op] = []
    unparsed: list[str] = []

    i = 0
    seen_bare_number = False
    while i < len(toks):
        tok = toks[i]
        low = tok.lower()

        if m := RE_SCALE.match(tok):
            ops.append(Scale(_f(m.group(1))))
            i += 1
            continue

        # "x 3" with a space. The card documents `x1.5`, so a space is the
        # natural typo, and without this rule it fell all the way through to
        # the "rice 200" form: `1 x 3` set a component named "x" to 3 g, which
        # then resolved against USDA and put three grams of something into a
        # coffee. Silent, plausible, and wrong — the failure mode this grammar
        # exists to avoid. A lone x/*/× is never a food.
        if low in ("x", "*", "×") and i + 1 < len(toks) and (m := RE_QTY.match(toks[i + 1])):
            ops.append(Scale(_f(m.group(1))))
            i += 2
            continue

        if low in WORD_SCALE:
            ops.append(Scale(WORD_SCALE[low]))
            i += 1
            continue

        if m := RE_DATE_ISO.match(tok):
            ops.append(SetDate(iso=f"{m.group(1)}-{m.group(2)}-{m.group(3)}"))
            i += 1
            continue

        if m := RE_DATE_BACK.match(tok):
            ops.append(SetDate(days_back=int(m.group(1))))
            i += 1
            continue

        if low.startswith("@") and low[1:] in WORD_DAYS:
            ops.append(SetDate(days_back=WORD_DAYS[low[1:]]))
            i += 1
            continue

        if low.startswith("@") and low[1:] in WEEKDAYS:
            ops.append(SetDate(weekday=WEEKDAYS[low[1:]]))
            i += 1
            continue

        if m := RE_TIME.match(tok):
            hh = int(m.group(1))
            mm = int(m.group(2) or 0)
            if 0 <= hh < 24 and 0 <= mm < 60:
                ops.append(SetTime(hh, mm))
            else:
                unparsed.append(tok)
            i += 1
            continue

        if m := RE_SLOT.match(tok):
            ops.append(SetSlot(m.group(1).lower()))
            i += 1
            continue

        # "no onion" / "without onion"
        if low in ("no", "without", "minus", "skip") and i + 1 < len(toks):
            ops.append(DropComponent(toks[i + 1].lower()))
            i += 2
            continue

        # "-onion"
        if m := RE_DROP.match(tok):
            ops.append(DropComponent(m.group(1).lower()))
            i += 1
            continue

        # "-" "onion"
        if tok in ("-", "–", "—") and i + 1 < len(toks):
            ops.append(DropComponent(toks[i + 1].lower()))
            i += 2
            continue

        # "+50 rice" / "+50g rice"
        if m := RE_ADD_QTY.match(tok):
            grams = _f(m.group(1))
            if i + 1 < len(toks) and not _is_op_token(toks[i + 1]):
                ops.append(AddComponent(toks[i + 1].lower(), grams))
                i += 2
            else:
                unparsed.append(tok)
                i += 1
            continue

        # "+rice"
        if tok.startswith("+") and len(tok) > 1:
            m2 = RE_ADD_LABEL.match(tok)
            assert m2
            ops.append(AddComponent(m2.group(1).lower(), None))
            i += 1
            continue

        # "+" "50" "rice"  or  "+" "rice"
        if tok == "+" and i + 1 < len(toks):
            if RE_QTY.match(toks[i + 1]) and i + 2 < len(toks):
                ops.append(
                    AddComponent(toks[i + 2].lower(), _f(RE_QTY.match(toks[i + 1]).group(1)))
                )
                i += 3
            else:
                ops.append(AddComponent(toks[i + 1].lower(), None))
                i += 2
            continue

        # bare quantity
        if m := RE_QTY.match(tok):
            grams = _f(m.group(1))
            # "40g chicken breast" is forty grams of chicken breast, not an
            # instruction to shrink the whole plate to forty grams. It was the
            # second: a 633 kcal dinner became 91 kcal, every component scaled
            # by 1/15, and the leftover words went to the model as a new
            # ingredient. A number followed by words names the thing it
            # measures — the mirror of "rice 200", which already worked.
            words = []
            j = i + 1
            while j < len(toks) and not _is_op_token(toks[j]) and not RE_QTY.match(toks[j]):
                words.append(toks[j].lower())
                j += 1
            if words and len(" ".join(words)) >= 2:
                ops.append(SetComponent(" ".join(words), grams))
                i = j
                continue
            if not seen_bare_number:
                ops.append(TotalGrams(grams))
                seen_bare_number = True
            else:
                unparsed.append(tok)
            i += 1
            continue

        # "rice 200"
        if i + 1 < len(toks) and (m := RE_QTY.match(toks[i + 1])):
            if len(low) < 2:
                # Nothing edible has a one-letter name. Left unparsed, the user
                # is told it could not be read; treated as a label it becomes a
                # database search that always finds *something*.
                unparsed.append(tok)
                i += 1
                continue
            ops.append(SetComponent(low, _f(m.group(1))))
            i += 2
            continue

        unparsed.append(tok)
        i += 1

    return ops, unparsed


def _is_op_token(tok: str) -> bool:
    return bool(
        RE_SCALE.match(tok)
        or RE_TIME.match(tok)
        or RE_DATE_ISO.match(tok)
        or RE_DATE_BACK.match(tok)
        or (tok.lower().startswith("@") and tok.lower()[1:] in WORD_DAYS)
        or (tok.lower().startswith("@") and tok.lower()[1:] in WEEKDAYS)
        or RE_SLOT.match(tok)
        or RE_DROP.match(tok)
        or tok.startswith("+")
        or tok.lower() in WORD_SCALE
    )


# --------------------------------------------------------------------------
# Applying a parsed command to a dish's component list.


@dataclass
class Component:
    label: str
    fdc_id: int | None
    grams: float
    state: str = "as_logged"
    yield_factor: float = 1.0
    # Defaults to an estimate rather than to "repeat". "repeat" is a fact
    # about how the entry was made, which log_entry.source already records;
    # this column answers how the mass was arrived at. Conflating them made
    # every repeated portion read as a guess.
    grams_source: str = "estimate"


def apply(components: list[Component], ops: list[Op]) -> tuple[list[Component], list[AddComponent]]:
    """Apply ops to a copy of `components`.

    Returns (new_components, unresolved_additions). An addition whose label is
    not already an alias cannot be resolved here — it needs the food resolver,
    and possibly one cheap model call. Everything else is arithmetic.
    """
    # Provenance is carried through, not overwritten.
    #
    # This used to hardcode "repeat" for every component. On the repeat path
    # that is honest — dish_component stores no provenance, so there is none to
    # keep — but the fix path feeds in rows from log_component, which do have
    # it. Correcting the rice in "400 g rice and 100 g chicken" silently
    # downgraded the untouched chicken from `stated` to `repeat`: it rendered
    # as a guess, and portion_history() stopped counting it, because that reads
    # only scale/stated/package rows. A mass you stated does not stop being
    # stated because you corrected something next to it.
    out = [
        Component(c.label, c.fdc_id, float(c.grams), c.state, c.yield_factor, c.grams_source)
        for c in components
    ]
    unresolved: list[AddComponent] = []

    for op in ops:
        if isinstance(op, Scale):
            for c in out:
                c.grams *= op.factor
        elif isinstance(op, TotalGrams):
            total = sum(c.grams for c in out)
            if total > 0:
                k = op.grams / total
                for c in out:
                    c.grams *= k
        elif isinstance(op, DropComponent):
            out = [c for c in out if not _label_match(c.label, op.label)]
        elif isinstance(op, SetComponent):
            hit = next((c for c in out if _label_match(c.label, op.label)), None)
            if hit is not None:
                hit.grams = op.grams
                hit.grams_source = "stated"
            else:
                unresolved.append(AddComponent(op.label, op.grams))
        elif isinstance(op, AddComponent):
            hit = next((c for c in out if _label_match(c.label, op.label)), None)
            if hit is not None and op.grams is not None:
                hit.grams += op.grams
            else:
                unresolved.append(op)

    return [c for c in out if c.grams > 0], unresolved


def _label_match(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    return a == b or b in a.split() or a.startswith(b) or b.startswith(a)


def resolve_date(op: SetDate, today: "dt.date") -> "dt.date":
    """A SetDate against the user's own today. Always backwards.

    A named weekday means the most recent one that has already happened, never
    the coming one: you are recording a meal you ate, and there is no such thing
    as remembering next Saturday. Same for an explicit date — a future one is
    clamped to today rather than accepted, because it is far more likely to be a
    typo than an intention, and a meal filed in the future is invisible in every
    summary until it silently arrives.
    """
    import datetime as _dt

    if op.iso:
        try:
            d = _dt.date.fromisoformat(op.iso)
        except ValueError:
            return today
        return min(d, today)
    if op.weekday is not None:
        # Naming today's own weekday means today, not a week ago. `@-7` is how
        # you say last Saturday on a Saturday, and it is unambiguous.
        days_back = (today.weekday() - op.weekday) % 7
        return today - _dt.timedelta(days=days_back)
    if op.days_back:
        return today - _dt.timedelta(days=max(0, op.days_back))
    return today


# Meal slots, from the clock rather than from the model.
#
# The tool schema offered breakfast/lunch/dinner/snack/drink with no
# description and no time of day, so the model classified by dish *type*: a
# chia seed pudding eaten at 16:11 came back "breakfast", because a chia
# pudding is a breakfast food. Most entries came back with nothing at all.
#
# When you ate is something this system knows exactly and the model cannot
# know, so it is not a question worth asking. "drink" is kept from the model,
# because that is a fact about the thing rather than about the hour.
SLOT_BOUNDARIES = ((11, "breakfast"), (15, "lunch"), (17, "snack"), (22, "dinner"))


def slot_for_hour(hour: int, model_slot: str | None = None) -> str:
    if model_slot == "drink":
        return "drink"
    for cutoff, name in SLOT_BOUNDARIES:
        if hour < cutoff:
            return name
    return "snack"
