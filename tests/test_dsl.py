from nutrai.core import dsl


def ops(text):
    c = dsl.parse(text)
    assert c is not None
    return c


def test_bare_index():
    c = ops("3")
    assert (c.selector, c.selector_kind, c.ops, c.needs_model) == ("3", "index", [], False)


def test_total_grams():
    c = ops("3 250")
    assert c.ops == [dsl.TotalGrams(250.0)] and not c.needs_model


def test_grams_with_unit():
    assert ops("3 250g").ops == [dsl.TotalGrams(250.0)]
    assert ops("3 1,5").ops == [dsl.TotalGrams(1.5)]


def test_scale():
    assert ops("3 x1.5").ops == [dsl.Scale(1.5)]
    assert ops("3 *2").ops == [dsl.Scale(2.0)]
    assert ops("3 half").ops == [dsl.Scale(0.5)]
    assert ops("3 double").ops == [dsl.Scale(2.0)]


def test_drop_forms():
    for t in ("3 -onion", "3 - onion", "3 no onion", "3 without onion"):
        assert ops(t).ops == [dsl.DropComponent("onion")], t


def test_add_forms():
    assert ops("3 +50 rice").ops == [dsl.AddComponent("rice", 50.0)]
    assert ops("3 +50g rice").ops == [dsl.AddComponent("rice", 50.0)]
    assert ops("3 + 50 rice").ops == [dsl.AddComponent("rice", 50.0)]
    assert ops("3 +rice").ops == [dsl.AddComponent("rice", None)]


def test_set_component():
    assert ops("3 rice 200").ops == [dsl.SetComponent("rice", 200.0)]


def test_time_and_slot():
    assert ops("3 @14:00").ops == [dsl.SetTime(14, 0)]
    assert ops("3 @0830").ops == [dsl.SetTime(8, 30)]
    assert ops("3 #lunch").ops == [dsl.SetSlot("lunch")]
    assert ops("3 @99:99").needs_model


def test_compound():
    c = ops("3 x1.5 -onion +50 rice #dinner @19:30")
    assert c.ops == [
        dsl.Scale(1.5),
        dsl.DropComponent("onion"),
        dsl.AddComponent("rice", 50.0),
        dsl.SetSlot("dinner"),
        dsl.SetTime(19, 30),
    ]
    assert not c.needs_model


def test_slug_selector():
    c = ops("b -egg")
    assert (c.selector, c.selector_kind) == ("b", "slug")
    assert c.ops == [dsl.DropComponent("egg")]


def test_escalates_only_on_genuine_miss():
    c = ops("3 but the sauce was thinner today")
    assert c.needs_model
    assert "sauce" in " ".join(c.unparsed) or c.unparsed


def test_not_a_repeat_at_all():
    assert dsl.parse("250 g of chicken thigh and a fistful of rice") is None
    assert dsl.parse("") is None


# ------------------------------------------------------------------- apply


def comps():
    return [
        dsl.Component("mince", 1, 200.0),
        dsl.Component("onion", 2, 60.0),
        dsl.Component("rice", 3, 150.0),
    ]


def test_apply_scale():
    out, un = dsl.apply(comps(), [dsl.Scale(1.5)])
    assert [c.grams for c in out] == [300.0, 90.0, 225.0]
    assert un == []


def test_apply_total_grams_is_proportional():
    out, _ = dsl.apply(comps(), [dsl.TotalGrams(205.0)])
    assert round(sum(c.grams for c in out), 6) == 205.0
    assert round(out[0].grams / out[2].grams, 4) == round(200 / 150, 4)


def test_apply_drop_then_scale_order_matters():
    out, _ = dsl.apply(comps(), [dsl.DropComponent("onion"), dsl.Scale(2.0)])
    assert [c.label for c in out] == ["mince", "rice"]
    assert [c.grams for c in out] == [400.0, 300.0]


def test_apply_set_marks_source():
    out, _ = dsl.apply(comps(), [dsl.SetComponent("rice", 200.0)])
    rice = next(c for c in out if c.label == "rice")
    assert rice.grams == 200.0 and rice.grams_source == "stated"


def test_apply_add_unknown_is_unresolved():
    out, un = dsl.apply(comps(), [dsl.AddComponent("kimchi", 80.0)])
    assert len(out) == 3 and un == [dsl.AddComponent("kimchi", 80.0)]


def test_apply_add_known_accumulates():
    out, un = dsl.apply(comps(), [dsl.AddComponent("rice", 50.0)])
    assert next(c for c in out if c.label == "rice").grams == 200.0
    assert un == []


def test_apply_never_mutates_input():
    original = comps()
    dsl.apply(original, [dsl.Scale(10.0)])
    assert [c.grams for c in original] == [200.0, 60.0, 150.0]


def test_a_number_before_words_names_what_it_measures():
    """"40g chicken breast" meant forty grams of chicken breast and was read
    as "shrink the whole plate to forty grams": a 633 kcal dinner became 91,
    every component scaled by a fifteenth, and the leftover words went to the
    model as a new ingredient."""
    from nutrai.core.dsl import SetComponent, TotalGrams, parse_ops

    ops, rest = parse_ops("40g chicken breast".split())
    assert ops == [SetComponent("chicken breast", 40.0)]
    assert rest == []

    ops, _ = parse_ops("40g chicken breast 40g pork chop".split())
    assert ops == [SetComponent("chicken breast", 40.0),
                   SetComponent("pork chop", 40.0)]

    # A bare number with nothing after it still sets the plate total.
    assert parse_ops(["250"])[0] == [TotalGrams(250.0)]
    assert parse_ops("250 x1.5".split())[0][0] == TotalGrams(250.0)


def test_the_existing_forms_are_unchanged():
    from nutrai.core.dsl import AddComponent, DropComponent, SetComponent, parse_ops

    assert parse_ops("rice 200".split())[0] == [SetComponent("rice", 200.0)]
    assert parse_ops("+50 rice".split())[0] == [AddComponent("rice", 50.0)]
    assert parse_ops(["-onion"])[0] == [DropComponent("onion")]


def test_spaced_scale_is_a_scale_not_a_component():
    """`1 x 3` meant three coffees and set a component called "x" to 3 g.

    The card advertises `x1.5`, so a space is the obvious typo, and the token
    fell through every rule to the "rice 200" form. That invented a component,
    resolved the single letter "x" against USDA — which always finds
    something — and put three grams of it into an espresso. The number on the
    card was wrong by a plausible amount, which is the only kind of wrong that
    matters here.
    """
    for text, factor in (("1 x 3", 3.0), ("1 * 3", 3.0), ("1 × 2", 2.0),
                         ("1 x 1.5", 1.5), ("1 x3", 3.0)):
        cmd = dsl.parse(text)
        assert cmd is not None and cmd.ops == [dsl.Scale(factor)], text
        assert not cmd.unparsed, text


def test_one_letter_label_is_never_a_food():
    """The general form of the same bug: nothing edible has a one-letter name.

    Left unparsed the user is told it could not be read. Treated as a label it
    becomes a database search, and a database search always succeeds.
    """
    for text in ("1 q 40", "1 40g z"):
        cmd = dsl.parse(text)
        assert cmd is not None
        assert not [o for o in cmd.ops if isinstance(o, dsl.SetComponent)], text
        assert cmd.unparsed, text
    # "1 x" now leaves the repeat grammar entirely — a bare index and a bare
    # token with no operator and no connective is a food description, and "x"
    # simply is not a food. It fails at the resolver instead, which says so.
    assert dsl.parse("1 x") is None


def test_a_number_and_a_food_is_food_not_a_modified_repeat():
    """"1 pickle" put 100 g of pickle into a protein shake and logged it.

    The bare noun matched no operator, went to `unparsed`, and `needs_model`
    paid a model to read it as a modification — which it did, because that is
    what it was asked. "2 eggs", "1 banana" and "3 slices salami" are the same
    shape and all of them are food.

    Returning None is the whole fix: the handler then treats the message as a
    novel food description, which is what it is.
    """
    for text in ("1 pickle", "2 eggs", "1 banana", "3 slices salami",
                 "2 chicken breasts", "1 apple"):
        assert dsl.parse(text) is None, text


def test_a_real_modification_still_reaches_the_repeat_path():
    """A change to a dish says so — with an operator or a connective."""
    for text in ("1 -onion", "1 +pickle", "1 x1.5", "1 250", "1 @14:00",
                 "1 with pickle", "1 without onion", "1 extra rice",
                 "3 with vitamin d3/k2", "1"):
        assert dsl.parse(text) is not None, text


def test_the_modifier_words_contain_no_foods():
    """The test is whether a phrase is *about* a dish. Any ingredient name in
    this set makes that ingredient's own dish unloggable — "1 rice" would stop
    meaning a portion of rice."""
    for food in ("rice", "pickle", "onion", "egg", "eggs", "banana", "chicken",
                 "salami", "apple", "milk", "oil"):
        assert food not in dsl.MODIFIER_WORDS, food


def test_a_mistyped_operator_stays_a_mistyped_operator():
    """"@99:99" is a time typed wrong, not a food called "@99:99".

    The rule that sends "1 pickle" to the meal parser must not also send a
    failed operator there — answering a mistyped time with a database search
    helps nobody, and the repeat path is where it gets told it was unreadable.
    """
    for text in ("3 @99:99", "1 x1.5.2", "1 -", "1 +"):
        assert dsl.parse(text) is not None, text


def test_a_correction_finds_the_component_it_names():
    """"80g turkey breast" appended a second turkey instead of fixing the first.

    `_label_match` looked for a single word among the component's words and
    compared a phrase by prefix, so "turkey breast" missed "baked turkey
    breast" on every branch. `apply` turns a SetComponent it cannot place into
    an AddComponent, so the entry logged 907 kcal of a bird eaten once — and
    both components resolved to the same USDA row.
    """
    assert dsl._label_match("baked turkey breast", "turkey breast")
    assert dsl._label_match("baked turkey breast", "turkey breast.")   # typing
    assert dsl._label_match("Baked Turkey Breast", "turkey breast")    # casing
    # Still loose in the documented direction.
    assert dsl._label_match("red onion", "onion")
    assert dsl._label_match("olive oil", "oil")
    # And still not loose enough to hit a different food.
    assert not dsl._label_match("chicken breast", "turkey breast")
    assert not dsl._label_match("rice", "chicken")


def test_a_correction_sets_rather_than_adds():
    """The whole point: one turkey, at the corrected mass."""
    comps = [dsl.Component("baked turkey breast", 100, 400.0, "as_logged", 1.0, "estimate")]
    ops, _unparsed = dsl.parse_ops("80g turkey breast.".split())
    out, unresolved = dsl.apply(comps, ops)
    assert len(out) == 1, [c.label for c in out]
    assert out[0].grams == 80.0
    assert not unresolved


def test_a_glass_of_water_is_not_breakfast():
    """A 12 kcal lemon water logged at 08:33 was filed as "breakfast".

    The slot came from the clock alone, so a day looked like it began with a
    meal it did not — on the screen and in every slot-shaped question asked of
    it afterwards.
    """
    assert dsl.slot_for_hour(8, kcal=12) == "drink"
    assert dsl.slot_for_hour(8, None, kcal=2) == "drink"      # black coffee
    # A small solid thing is still a snack, not a meal-sized claim.
    assert dsl.slot_for_hour(15, kcal=41) == "snack"
    # And a real breakfast is still breakfast.
    assert dsl.slot_for_hour(8, kcal=400) == "breakfast"
    # The model's own "drink" still wins outright, whatever the energy.
    assert dsl.slot_for_hour(13, "drink", kcal=400) == "drink"
    # Unknown energy changes nothing — the clock decides, as before.
    assert dsl.slot_for_hour(8) == "breakfast"
