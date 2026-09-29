from app.collectors.web.parsing import ParsedListing


def dedupe_key(listing: ParsedListing) -> int:
    return listing.listing_id


def dedupe_listings(listings: list[ParsedListing]) -> list[ParsedListing]:
    """Убирает дубли по avito_id, сохраняя первое вхождение (минимальную позицию)."""
    seen: set[int] = set()
    result: list[ParsedListing] = []
    for listing in sorted(listings, key=lambda item: item.position):
        if listing.listing_id in seen:
            continue
        seen.add(listing.listing_id)
        result.append(listing)
    return result


def price_changed(old_price: float | None, new_price: float | None) -> bool:
    if old_price is None or new_price is None:
        return False
    return abs(old_price - new_price) >= 0.01
