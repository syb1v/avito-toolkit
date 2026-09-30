from pathlib import Path

from app.collectors.web.parsing import parse_search_page

FIXTURE = Path(__file__).parent / "fixtures" / "real" / "search_iphone15.html"
EXPECTED_COUNT = 50


def _listings():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_search_page(html, base_url="https://www.avito.ru")


def test_real_search_fixture_extracts_all_items() -> None:
    listings = _listings()
    assert len(listings) == EXPECTED_COUNT
    assert [item.position for item in listings] == list(range(1, EXPECTED_COUNT + 1))
    assert len({item.listing_id for item in listings}) == EXPECTED_COUNT
    assert all(item.title for item in listings)
    assert all(item.price is not None and item.price > 0 for item in listings)
    assert all(item.url.startswith("https://www.avito.ru/") for item in listings)
    assert all(item.url.endswith(str(item.listing_id)) for item in listings)


def test_real_search_fixture_spot_check_first_item() -> None:
    first = _listings()[0]
    assert first.listing_id == 7924579043
    assert first.price == 43490.0
    assert first.title.startswith("iPhone 15")
    assert first.url.endswith("_7924579043")


def test_real_search_fixture_uses_dom_markup_not_initial_data() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    assert html.count('data-marker="item"') == EXPECTED_COUNT
    assert 'itemprop="price"' in html
    assert "__initialData__" not in html
