import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from html import unescape as html_unescape
from typing import Any
from urllib.parse import unquote, urljoin

from lxml import etree
from lxml import html as lxml_html

AVITO_WEB_BASE = "https://www.avito.ru"

PRICE_PATTERN = re.compile(r"(\d[\d\s\u00a0]*)\s*₽")
DESCRIPTION_JSON_PATTERN = re.compile(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"')
MAX_DESCRIPTION_CHARS = 4000
ITEM_DESCRIPTION_XPATHS = (
    "//*[@data-marker='item-view/itemDescription']",
    "//div[@itemprop='description']",
    "//*[contains(@class,'item-description')]",
)
META_DESCRIPTION_XPATHS = (
    "//meta[@name='description']/@content",
    "//meta[@property='og:description']/@content",
)
LISTING_ID_PATTERNS = (
    re.compile(r"/[^/]*?_(\d{6,})(?:\?|$)"),
    re.compile(r"[?&]id=(\d+)"),
)
INITIAL_DATA_PATTERN = re.compile(
    r"window\.__(?:initialData|initialData2)__\s*=\s*\"([^\"]+)\"", re.DOTALL
)
PROFILE_SNIPPET_MARKER = 'data-marker="item-snippet/'
PROFILE_TITLE_PATTERN = re.compile(
    r'<h4[^>]*>.*?<a[^>]*href="(/[^"]+)"[^>]*>([^<]+)</a>', re.DOTALL
)
PROFILE_PRICE_PATTERN = re.compile(r">([^<>]*₽)<")
SELLER_LINK_PATTERN = re.compile(
    r'href="/user/(?P<hash>[0-9a-f]{6,})/profile[^"]*?iid=(?P<item>\d+)[^"]*"[^>]*>'
    r"(?P<name>[^<]{0,120})<"
)
GENERIC_SELLER_NAMES = {"", "профиль", "все объявления", "перейти в профиль", "в профиль"}


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
    seller_url: str | None = None
    seller_name: str | None = None


def _to_float(value: str) -> float | None:
    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return None
    parsed = float(digits)
    return parsed if parsed > 0 else None


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
    if not listings:
        listings = _parse_dom(html_text, base_url)
    return apply_seller_links(html_text, listings)


def apply_seller_links(html_text: str, listings: list[ParsedListing]) -> list[ParsedListing]:
    """Дополняет объявления продавцом из ссылок карточек `/user/{hash}/profile?iid=ID`."""
    mapping: dict[int, tuple[str, str | None]] = {}
    for match in SELLER_LINK_PATTERN.finditer(html_text):
        name = html_unescape(match.group("name")).strip()
        mapping[int(match.group("item"))] = (
            match.group("hash"),
            None if name.lower() in GENERIC_SELLER_NAMES else name,
        )
    if not mapping:
        return listings
    enriched: list[ParsedListing] = []
    for listing in listings:
        found = mapping.get(listing.listing_id)
        if found is None:
            enriched.append(listing)
            continue
        seller_url = f"{AVITO_WEB_BASE}/user/{found[0]}/profile"
        enriched.append(
            replace(
                listing,
                seller_url=seller_url,
                seller_name=found[1] or listing.seller_name,
            )
        )
    return enriched


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


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def extract_description(html_text: str) -> str | None:
    """Текст описания объявления: JSON-стейт, DOM-селекторы, meta — по убыванию точности."""
    best: str | None = None
    for match in DESCRIPTION_JSON_PATTERN.finditer(html_text):
        try:
            value = json.loads(f'"{match.group(1)}"')
        except (TypeError, ValueError):
            value = match.group(1)
        normalized = _normalize_text(str(value))
        if normalized and (best is None or len(normalized) > len(best)):
            best = normalized
    if best is not None and len(best) > 40:
        return best[:MAX_DESCRIPTION_CHARS]

    try:
        tree = lxml_html.fromstring(html_text)
    except (etree.ParserError, ValueError):
        tree = None
    if tree is not None:
        for xpath in ITEM_DESCRIPTION_XPATHS:
            nodes = tree.xpath(xpath)
            if nodes:
                text = _normalize_text(" ".join(node.text_content() for node in nodes))
                if text:
                    return text[:MAX_DESCRIPTION_CHARS]
        for xpath in META_DESCRIPTION_XPATHS:
            values = tree.xpath(xpath)
            if values:
                text = _normalize_text(str(values[0]))
                if text:
                    return text[:MAX_DESCRIPTION_CHARS]
    return best[:MAX_DESCRIPTION_CHARS] if best else None


def parse_profile_items(html_text: str) -> list[ParsedListing]:
    """Свои объявления со страницы профиля (/profile/items).

    Профиль верстается иначе, чем выдача: сниппеты `data-marker="item-snippet/{id}"`,
    цена в `&nbsp;`. Объявления без цены (резюме, услуги) пропускаются.
    """
    items: list[ParsedListing] = []
    seen: set[int] = set()
    for chunk in html_text.split(PROFILE_SNIPPET_MARKER)[1:]:
        id_match = re.match(r"(\d+)", chunk)
        if id_match is None:
            continue
        listing_id = int(id_match.group(1))
        if listing_id in seen:
            continue
        title_match = PROFILE_TITLE_PATTERN.search(chunk)
        if title_match is None:
            continue
        price: float | None = None
        for raw in reversed(PROFILE_PRICE_PATTERN.findall(chunk)):
            digits = re.sub(r"\D", "", html_unescape(raw))
            if digits:
                price = float(digits)
                break
        if price is None or price <= 0:
            continue
        seen.add(listing_id)
        items.append(
            ParsedListing(
                listing_id=listing_id,
                title=html_unescape(title_match.group(2)).strip(),
                price=price,
                url=urljoin(AVITO_WEB_BASE, title_match.group(1)),
                position=len(items) + 1,
            )
        )
    return items
