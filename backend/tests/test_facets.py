from app.services.facets import brand_from_dictionary, listing_brand, title_hash


def test_brand_from_dictionary() -> None:
    assert brand_from_dictionary("B&O Beoplay Eleven Natural") == "Bang & Olufsen"
    assert brand_from_dictionary("Bang & Olufsen Beosound A9") == "Bang & Olufsen"
    assert brand_from_dictionary("Devialet Phantom Ultimate") == "Devialet"
    assert brand_from_dictionary("Insta360 X4 Air") == "Insta360"
    assert brand_from_dictionary("Наушники без бренда") is None


def test_listing_brand_prefers_ai_tags_with_hash() -> None:
    title = "Beoplay Eleven"
    params = {
        "ai_tags": {
            "brand": "B&O",
            "model": "Eleven",
            "color": "Natural",
            "title_hash": title_hash(title),
        }
    }
    assert listing_brand(title, params) == "B&O"
    # заголовок изменился — кэш невалиден, работает словарь
    assert listing_brand("Beoplay Eleven 2", params) == "Bang & Olufsen"
    # «Другое» не считаем брендом — падаем в словарь
    params_other = {"ai_tags": {"brand": "Другое", "title_hash": title_hash(title)}}
    assert listing_brand(title, params_other) == "Bang & Olufsen"
    assert listing_brand(title, None) == "Bang & Olufsen"
