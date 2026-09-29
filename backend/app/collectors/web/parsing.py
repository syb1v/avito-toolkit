import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urljoin

from lxml import etree
from lxml import html as lxml_html

AVITO_WEB_BASE = "https://www.avito.ru"

PRICE_PATTERN = re.compile(r"(\d[\d\s\u00a0]*)\s*₽")
LISTING_ID_PATTERNS = (
    re.compile(r"/[^/]*?_(\d{6,})(?:\?|$)"),
    re.compile(r"[?&]id=(\d+)"),
)
INITIAL_DATA_PATTERN = re.compile(
    r"window\.__(?:initialData|initialData2)__\s*=\s*\"([^\"]+)\"", re.DOTALL
)


@dataclass(frozen=True, slots=True)
class ParsedListing:
    listing_id: int
    title: str
    price: float | None
    url: str
    position: int
    seller_id: int | None = None
    is_vip: bool = False
    is_highlighted: bool = False


def _to_float(value: str) -> float | None:
    digits = re.sub(r"[^\d]", "", value)
    return float(digits) if digits else None


def extract_price(text: str) -> float | None:
    match = PRICE_PATTERN.search(text)
    if match is None:
        return None
    return _to_float(match.group(1))


def extract_listing_id(url: str) -> int | None:
    for pattern in LISTING_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return int(match.group(1))
    return None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        return int(digits) if digits else None
    return None


def parse_search_page(html_text: str, base_url: str = "") -> list[ParsedListing]:
    """Разбор страницы выдачи: сначала встроенный JSON, затем DOM-селекторы."""
    listings = _parse_initial_data(html_text, base_url)
    if listings:
        return listings
    return _parse_dom(html_text, base_url)


def _parse_initial_data(html_text: str, base_url: str) -> list[ParsedListing]:
    match = INITIAL_DATA_PATTERN.search(html_text)
    if match is None:
        return []
    try:
        payload = json.loads(unquote(match.group(1)))
    except (TypeError, ValueError):
        return []
    listings: list[ParsedListing] = []
    for position, item in enumerate(_iter_item_dicts(payload), start=1):
        parsed = _item_from_json(item, position, base_url)
        if parsed is not None:
            listings.append(parsed)
    return listings


def _iter_item_dicts(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if _looks_like_item(node):
            yield node
        for value in node.values():
            yield from _iter_item_dicts(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_item_dicts(value)


def _looks_like_item(node: dict[str, Any]) -> bool:
    if "title" not in node or "id" not in node:
        return False
    return "priceDetailed" in node or "price" in node


def _item_from_json(item: dict[str, Any], position: int, base_url: str) -> ParsedListing | None:
    listing_id = _coerce_int(item.get("id"))
    title = str(item.get("title") or "").strip()
    if listing_id is None or not title:
        return None
    url_path = item.get("uri") or item.get("urlPath") or item.get("url") or ""
    seller = item.get("seller")
    seller_id = _coerce_int(
        item.get("sellerId") or (seller.get("id") if isinstance(seller, dict) else None)
    )
    return ParsedListing(
        listing_id=listing_id,
        title=title,
        price=_price_from_json(item),
        url=urljoin(base_url or AVITO_WEB_BASE, str(url_path)),
        position=position,
        seller_id=seller_id,
        is_vip=bool(item.get("isVip") or item.get("vip") or item.get("isPromo")),
        is_highlighted=bool(item.get("isHighlighted") or item.get("highlighted")),
    )


def _price_from_json(item: dict[str, Any]) -> float | None:
    for key in ("priceDetailed", "price"):
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("value")
            if isinstance(value, dict):
                value = value.get("value")
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            parsed = extract_price(value)
            if parsed is not None:
                return parsed
            return _to_float(value)
    return None


def _parse_dom(html_text: str, base_url: str) -> list[ParsedListing]:
    if not html_text.strip():
        return []
    try:
        tree = lxml_html.fromstring(html_text)
    except (etree.ParserError, ValueError):
        return []
    listings: list[ParsedListing] = []
    for position, node in enumerate(tree.xpath("//div[@data-marker='item']"), start=1):
        parsed = _item_from_dom(node, position, base_url)
        if parsed is not None:
            listings.append(parsed)
    return listings


def _item_from_dom(node: Any, position: int, base_url: str) -> ParsedListing | None:
    anchor = _first_node(
        node,
        (
            ".//a[@data-marker='item-title']",
            ".//h3[@itemprop='name']/ancestor::a[1]",
            ".//a[@itemprop='url']",
        ),
    )
    href = anchor.get("href") if anchor is not None else None
    listing_id = _coerce_int(node.get("data-item-id"))
    if listing_id is None and href is not None:
        listing_id = extract_listing_id(href)
    if listing_id is None:
        return None
    title = " ".join(anchor.text_content().split()) if anchor is not None else ""
    return ParsedListing(
        listing_id=listing_id,
        title=title,
        price=_price_from_dom(node),
        url=urljoin(base_url or AVITO_WEB_BASE, href) if href else "",
        position=position,
        seller_id=_seller_from_dom(node),
        is_vip=bool(node.xpath(".//*[contains(@class, 'vip')]")),
        is_highlighted=bool(
            node.xpath(".//*[contains(@class, 'highlight')] | .//*[@data-marker='item-highlight']")
        ),
    )


def _price_from_dom(node: Any) -> float | None:
    meta = node.xpath(".//meta[@itemprop='price']/@content")
    if meta:
        value = _to_float(str(meta[0]))
        if value is not None:
            return value
    text_nodes = node.xpath(
        ".//*[@data-marker='item-price']//text() | .//*[contains(@class, 'price')]//text()"
    )
    if text_nodes:
        return extract_price(" ".join(str(item) for item in text_nodes))
    return None


def _seller_from_dom(node: Any) -> int | None:
    values = node.xpath(
        ".//a[contains(@data-marker, 'seller')]/@data-user-id"
        " | .//a[contains(@data-marker, 'seller')]/@data-seller-id"
    )
    for value in values:
        seller_id = _coerce_int(str(value))
        if seller_id is not None:
            return seller_id
    return None


def _first_node(node: Any, xpaths: tuple[str, ...]) -> Any | None:
    for xpath in xpaths:
        found = node.xpath(xpath)
        if found:
            return found[0]
    return None
