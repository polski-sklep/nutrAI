"""OpenFoodFacts mapping. No network: the fixtures are real API shapes.

A third source with a third level of authority. USDA rows are laboratory
assays, a photographed label is a panel you were holding, and this is a
database anyone may edit — three different claims, and code that blurred them
would be the most quietly wrong thing here.
"""

from __future__ import annotations

from nutrai import off

OLIMP = {
    "code": "5901330082801",
    "product_name": "Whey Protein Complex White Chocolate and Raspberry",
    "brands": "Olimp Sport Nutrition, Olimp",
    "quantity": "700 g",
    "serving_size": "35 g",
    "completeness": 0.475,
    "nutriments": {
        "energy-kcal_100g": 382.857, "proteins_100g": 74.2857,
        "fat_100g": 4.28571, "carbohydrates_100g": 11.1428,
        "sugars_100g": 4.0, "saturated-fat_100g": 0.571428,
        "salt_100g": 0.842857,
    },
}


def test_units_are_converted_to_what_usda_stores():
    p = off.summarise(OLIMP)
    assert round(p["panel"][1008]) == 383          # kcal
    assert round(p["panel"][1003], 1) == 74.3      # g protein
    # Salt, not sodium: 2.5 g salt is 1 g sodium, and the result is mg.
    assert round(p["panel"][1093]) == 337


def test_a_missing_nutrient_is_absent_not_zero():
    """A panel with no fibre figure and a product with no fibre look identical
    in a stored row and mean completely different things."""
    p = off.summarise(OLIMP)
    assert 1079 not in p["panel"]
    assert "fiber" in p["missing"]
    assert all(v is not None for v in p["panel"].values())


def test_brands_parse_from_either_api_shape():
    """The product endpoint returns a comma-joined string; search returns a
    list. Both are real and both arrive here."""
    assert off.summarise(OLIMP)["brand"] == "Olimp Sport Nutrition"
    assert off.summarise({**OLIMP, "brands": ["Olimp", "Olimp Sport"]})["brand"] == "Olimp"
    assert off.summarise({**OLIMP, "brands": None})["brand"] == ""


def test_minerals_scale_from_grams():
    p = off.summarise({**OLIMP, "nutriments": {
        **OLIMP["nutriments"], "calcium_100g": 0.12, "vitamin-b12_100g": 0.0000012}})
    assert round(p["panel"][1087]) == 120        # 0.12 g -> 120 mg
    assert round(p["panel"][1178], 1) == 1.2     # 0.0000012 g -> 1.2 µg


def test_the_search_endpoint_is_the_current_one():
    """/cgi/search.pl answers 503 under any load; it is kept alive for
    compatibility rather than for use."""
    import inspect

    # The code, not the prose. The docstring names the old endpoint precisely
    # so nobody reinstates it, and a naive substring check flagged that.
    body = [ln for ln in inspect.getsource(off.search).splitlines()
            if "_get(" in ln]
    assert body and "SEARCH" in body[0], body
    assert off.SEARCH == "https://search.openfoodfacts.org"


# --------------------------------------------------- transcribed food panels


def test_a_per_serving_panel_is_scaled_and_says_so():
    from nutrai.llm.parse import per_100g

    panel, warns = per_100g({
        "basis": "per_serving", "serving_grams": 30,
        "nutrients": [{"nutrient_id": 1008, "amount": 111.6, "unit": "kcal",
                       "as_printed": "Calories 111.6"}],
    })
    assert round(panel[1008]) == 372
    assert any("30 g" in w for w in warns)


def test_a_per_serving_panel_with_no_serving_weight_reads_nothing():
    """Dividing by a number nobody supplied is how a made-up composition gets
    stored and then trusted for every future portion."""
    from nutrai.llm.parse import per_100g

    panel, warns = per_100g({
        "basis": "per_serving", "serving_grams": None,
        "nutrients": [{"nutrient_id": 1008, "amount": 172, "unit": "kcal",
                       "as_printed": "Calories 172"}],
    })
    assert panel == {}
    assert warns and "cannot" in warns[0]


def test_a_serving_column_that_includes_milk_is_flagged():
    """Nesquik prints 'per serving: 30 g plus 125 ml semi-skimmed milk'. That
    column describes a bowl of cereal and milk, not the cereal."""
    from nutrai.llm.parse import per_100g

    _panel, warns = per_100g({
        "basis": "per_100g", "serving_includes_additions": True,
        "nutrients": [{"nutrient_id": 1008, "amount": 372, "unit": "kcal",
                       "as_printed": "Calories 372"}],
    })
    assert any("milk" in w for w in warns)


def test_folic_acid_also_counts_as_total_folate():
    """The target sits on total folate. Under 1186 alone it would count toward
    nothing; under 1177 alone it would claim to be food folate, which it is
    not."""
    from nutrai.llm.parse import per_100g

    panel, _w = per_100g({
        "basis": "per_100g",
        "nutrients": [{"nutrient_id": 1186, "amount": 185, "unit": "ug",
                       "as_printed": "Folic Acid (ug) 185"}],
    })
    assert panel[1186] == 185 and panel[1177] == 185


def test_the_card_shows_each_line_as_printed():
    """A transcription is checkable at the moment it is made, and only if you
    can see what was read."""
    from nutrai.core.render import food_label_card

    data = {"nutrients": [
        {"nutrient_id": 1089, "amount": 10.4, "unit": "mg", "as_printed": "Iron(mg) 10.4"},
    ], "unreadable": ["Trans fat (g)"]}
    out = food_label_card("nesquik cereal", {1089: 10.4}, data)
    assert "Iron(mg) 10.4" in out
    assert "Could not read" in out and "Trans fat" in out
    assert "Nesquik cereal" in out       # capitalised for display
