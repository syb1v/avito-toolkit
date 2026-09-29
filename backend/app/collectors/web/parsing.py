import re
from dataclasses import dataclass

PRICE_PATTERN = re.compile(r"(\d[\d\s\u00a0]*)\s*₽")


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


def extract_price(text: str) -> float | None:
    match = PRICE_PATTERN.search(text)
    if match is None:
        return None
    digits = re.sub(r"[^\d]", "", match.group(1))
    return float(digits) if digits else None


def parse_search_page(html: str, base_url: str = "") -> list[ParsedListing]:
    """Разбор страницы выдачи. Реализация — фаза 1."""
    raise NotImplementedError("parse_search_page будет реализован в фазе 1")
