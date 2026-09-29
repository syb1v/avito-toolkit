import json
from pathlib import Path
from urllib.parse import quote

from app.collectors.web.parsing import (
    ParsedListing,
    extract_listing_id,
    extract_price,
    parse_search_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _dom_fixture() -> str:
    return (FIXTURES / "min_search.html").read_text(encoding="utf-8")


def _initial_data_html(payload: dict) -> str:
    encoded = quote(json.dumps(payload, ensure_ascii=False))
    return f'<html><body><script>window.__initialData__ = "{encoded}";</script></body></html>'


def test_extract_listing_id_from_listing_url() -> None:
    url = "https://www.avito.ru/moskva/telefony/iphone_15_128gb_4123456789?slocation=621540"
    assert extract_listing_id(url) == 4123456789


def test_extract_listing_id_from_query() -> None:
    assert extract_listing_id("https://www.avito.ru/brands?bt=1&id=99887766") == 99887766


def test_extract_listing_id_returns_none_for_plain_url() -> None:
    assert extract_listing_id("https://www.avito.ru/moskva/telefony") is None


def test_extract_price_formats() -> None:
    assert extract_price("75 000 ₽") == 75000
    assert extract_price("62\u00a0500 ₽") == 62500
    assert extract_price("без цены") is None


def test_parse_dom_fixture() -> None:
    listings = parse_search_page(_dom_fixture(), base_url="https://www.avito.ru")
    assert len(listings) == 3
    first, second, third = listings
    assert first.listing_id == 111111111
    assert first.title == "iPhone 15 128 GB"
    assert first.price == 75000
    assert first.url == "https://www.avito.ru/moskva/telefony/iphone_15_128gb_111111111"
    assert first.position == 1
    assert second.listing_id == 2222222222
    assert second.price == 62500
    assert second.url.startswith("https://www.avito.ru/moskva/telefony/iphone_14_pro_2222222222")
    assert third.listing_id == 3333333333
    assert third.price == 45990
    assert third.seller_id == 777777


def test_parse_initial_data_preferred_over_dom() -> None:
    payload = {
        "data": {
            "catalog": {
                "items": [
                    {
                        "id": 444444444,
                        "title": "MacBook Air M2",
                        "priceDetailed": {"value": 89990},
                        "uri": "/moskva/noutbuki/macbook_air_m2_444444444",
                        "sellerId": 555,
                    },
                    {
                        "id": "666666666",
                        "title": "Dell XPS 13",
                        "price": {"value": "54 990"},
                        "url": "/moskva/noutbuki/dell_xps_13_666666666",
                    },
                ]
            }
        }
    }
    listings = parse_search_page(_initial_data_html(payload), base_url="https://www.avito.ru")
    assert [listing.listing_id for listing in listings] == [444444444, 666666666]
    assert listings[0].price == 89990
    assert listings[0].title == "MacBook Air M2"
    assert listings[0].seller_id == 555
    assert listings[1].price == 54990
    assert listings[1].url == "https://www.avito.ru/moskva/noutbuki/dell_xps_13_666666666"


def test_malformed_initial_data_falls_back_to_dom() -> None:
    html = (
        '<html><body><script>window.__initialData__ = "%%%not-json%%%";</script>'
        + _dom_fixture()
        + "</body></html>"
    )
    listings = parse_search_page(html, base_url="https://www.avito.ru")
    assert len(listings) == 3
    assert isinstance(listings[0], ParsedListing)


def test_empty_html_returns_empty_list() -> None:
    assert parse_search_page("") == []
