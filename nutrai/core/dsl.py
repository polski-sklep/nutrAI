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
                x1.5 | *1.5       scale factor
                half | double     scale 0.5 / 2.0
                -onion | no onion drop a component
                +50 rice | +rice  add a component (grams optional)
                rice 200          set one component to 200 g
                @14:00            override the log time
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

SLOTS = {"breakfast", "lunch", "dinner", "snack", "brunch", "supper", "drink"}

_NUM = r"\d+(?:[.,]\d+)?"
_UNIT = r"(?:g|gram|grams|gr|ml|kg|l)?"

RE_SCALE = re.compile(rf"^[x*×]({_NUM})$", re.I)
RE_QTY = re.compile(rf"^({_NUM}){_UNIT}$", re.I)
RE_ADD_QTY = re.compile(rf"^\+({_NUM}){_UNIT}$", re.I)
RE_ADD_LABEL = re.compile(rf"^\+(.+)$")
RE_DROP = re.compile(rf"^[-–—](.+)$")
RE_TIME = re.compile(r"^@(\d{1,2})[:.h]?(\d{2})?$")
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


Op = Scale | TotalGrams | SetComponent | AddComponent | DropComponent | SetTime | SetSlot


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

        if low in WORD_SCALE:
            ops.append(Scale(WORD_SCALE[low]))
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

        # bare quantity: first one is the whole-dish target weight
        if m := RE_QTY.match(tok):
            if not seen_bare_number:
                ops.append(TotalGrams(_f(m.group(1))))
                seen_bare_number = True
            else:
                unparsed.append(tok)
            i += 1
            continue

        # "rice 200"
        if i + 1 < len(toks) and (m := RE_QTY.match(toks[i + 1])):
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
    grams_source: str = "repeat"


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
