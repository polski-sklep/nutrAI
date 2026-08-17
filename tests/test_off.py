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
