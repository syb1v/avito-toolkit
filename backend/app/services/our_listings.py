import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, OurListing, SearchListing

NON_NUMERIC = re.compile(r"[^0-9.,-]")


@dataclass(frozen=True, slots=True)
class ImportRow:
    sku: str
    title: str
    price: float
    cost_price: float | None = None
    category: str | None = None
    account: str | None = None
    avito_item_id: int | None = None
    avito_url: str | None = None
    avito_status: str | None = None


@dataclass(frozen=True, slots=True)
class ImportResult:
    created: int
    updated: int
    skipped: int


def sku_for_item(item_id: int) -> str:
    return f"avito-{item_id}"


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = NON_NUMERIC.sub("", value).replace(",", ".")
        if not cleaned or cleaned.count(".") > 1:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = "".join(char for char in value if char.isdigit())
        return int(digits) if digits else None
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_import_rows(
    raw_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[ImportRow], int]:
    """Валидация строк импорта: без sku/title/положительной цены строки отбрасываются."""
    rows: list[ImportRow] = []
    skipped = 0
    for raw in raw_rows:
        sku = _as_str(raw.get("sku"))
        title = _as_str(raw.get("title"))
        price = _as_float(raw.get("price"))
        if not sku or not title or price is None or price <= 0:
            skipped += 1
            continue
        rows.append(
            ImportRow(
                sku=sku,
                title=title,
                price=price,
                cost_price=_as_float(raw.get("cost_price")),
                category=_as_str(raw.get("category")),
                account=_as_str(raw.get("account")),
                avito_item_id=_as_int(raw.get("avito_item_id")),
                avito_url=_as_str(raw.get("avito_url")),
                avito_status=_as_str(raw.get("avito_status")),
            )
        )
    return rows, skipped


async def upsert_our_listings(session: AsyncSession, rows: Sequence[ImportRow]) -> ImportResult:
    created = 0
    updated = 0
    for row in rows:
        existing = await session.get(OurListing, row.sku)
        if existing is None and row.avito_item_id is not None:
            existing = await session.scalar(
                select(OurListing).where(OurListing.avito_item_id == row.avito_item_id)
            )
        if existing is None:
            session.add(
                OurListing(
                    sku=row.sku,
                    title=row.title,
                    price=row.price,
                    cost_price=row.cost_price,
                    category=row.category,
                    account=row.account,
                    avito_item_id=row.avito_item_id,
                    avito_url=row.avito_url,
                    avito_status=row.avito_status,
                )
            )
            created += 1
            continue
        existing.title = row.title
        existing.price = row.price
        if row.cost_price is not None:
            existing.cost_price = row.cost_price
        if row.category:
            existing.category = row.category
        if row.account:
            existing.account = row.account
        if row.avito_item_id is not None:
            existing.avito_item_id = row.avito_item_id
        if row.avito_url:
            existing.avito_url = row.avito_url
        if row.avito_status:
            existing.avito_status = row.avito_status
        updated += 1
    await session.commit()
    return ImportResult(created=created, updated=updated, skipped=0)


async def import_from_search(
    session: AsyncSession, search_id: Any, account: str | None = None
) -> ImportResult:
    """Переносит объявления спарсенного поиска (например, своего профиля) в наши SKU."""
    rows = await session.execute(
        select(
            Listing.id,
            Listing.title,
            Listing.current_price,
            Listing.url,
            Listing.status,
        )
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(SearchListing.search_id == search_id)
    )
    import_rows: list[ImportRow] = []
    skipped = 0
    for listing_id, title, price, url, status in rows.all():
        if price is None:
            skipped += 1
            continue
        import_rows.append(
            ImportRow(
                sku=sku_for_item(listing_id),
                title=title,
                price=float(price),
                account=account,
                avito_item_id=listing_id,
                avito_url=url,
                avito_status=status,
            )
        )
    result = await upsert_our_listings(session, import_rows)
    return ImportResult(created=result.created, updated=result.updated, skipped=skipped)
