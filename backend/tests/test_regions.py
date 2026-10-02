from app.services.regions import (
    matches_region,
    normalize_region,
    region_from_url,
    with_city,
)


def test_region_from_url() -> None:
    assert region_from_url("https://www.avito.ru/moskva/telefony/iphone_123") == "moskva"
    assert region_from_url("https://www.avito.ru/all?q=test") == "all"
    assert region_from_url("https://www.avito.ru/user/123/profile") is None
    assert region_from_url("https://example.com/moskva/item") is None
    assert region_from_url(None) is None


def test_normalize_region() -> None:
    assert normalize_region("  Санкт-Петербург ") == "sankt-peterburg"
    assert normalize_region("Nizhny Novgorod") == "nizhny-novgorod"


def test_matches_region_include_and_exclude() -> None:
    assert matches_region("moskva", ["moskva", "spb"], None) is True
    assert matches_region("kazan", ["moskva"], None) is False
    assert matches_region("kazan", None, ["kazan"]) is False
    assert matches_region("kazan", None, ["moskva"]) is True
    assert matches_region(None, ["moskva"], None) is False
    assert matches_region(None, None, None) is True


def test_with_city_rewrites_search_url_only() -> None:
    assert (
        with_city("https://www.avito.ru/all?q=devialet+dione", "moskva")
        == "https://www.avito.ru/moskva?q=devialet+dione"
    )
    assert (
        with_city("https://www.avito.ru/spb?q=test&p=2", "kazan")
        == "https://www.avito.ru/kazan?q=test&p=2"
    )
    profile = "https://www.avito.ru/user/12345/profile"
    assert with_city(profile, "moskva") == profile
    assert with_city("https://www.avito.ru/all?q=x", None) == "https://www.avito.ru/all?q=x"
