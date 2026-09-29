from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OurListing
from app.integrations.avito_api.client import AvitoApiClient, AvitoItem

DEFAULT_MAX_PAGES = 10
DEFAULT_PER_PAGE = 100


@dataclass(frozen=True, slots=True)
class SyncResult:
    created: int
    updated: int
    skipped: int
    pages_fetched: int


def sku_for_item(item_id: int) -> str:
    return f"avito-{item_id}"


async def _upsert_item(session: AsyncSession, item: AvitoItem, now: datetime) -> str:
    existing = await session.scalar(
        select(OurListing).where(OurListing.avito_item_id == item.item_id)
    )
    if existing is None:
        existing = await session.get(OurListing, sku_for_item(item.item_id))
    if existing is None:
        session.add(
            OurListing(
                sku=sku_for_item(item.item_id),
                title=item.title,
                price=item.price if item.price is not None else 0.0,
                category=item.category,
                avito_item_id=item.item_id,
                avito_status=item.status,
                avito_url=item.url,
                last_synced_at=now,
            )
        )
        return "created"
    existing.title = item.title
    if item.price is not None:
        existing.price = item.price
    if item.category:
        existing.category = item.category
    existing.avito_item_id = item.item_id
    existing.avito_status = item.status
    existing.avito_url = item.url
    existing.last_synced_at = now
    return "updated"


async def sync_our_listings(
    session: AsyncSession,
    client: AvitoApiClient,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    per_page: int = DEFAULT_PER_PAGE,
    status: str = "active",
) -> SyncResult:
    """Выгружает свои объявления через официальный API и обновляет our_listings."""
    created = 0
    updated = 0
    skipped = 0
    pages_fetched = 0
    now = datetime.now(UTC)

    for page in range(1, max_pages + 1):
        items = await client.list_items(page=page, per_page=per_page, status=status)
        if not items:
            break
        pages_fetched += 1
        for item in items:
            if item.price is None:
                skipped += 1
                continue
            action = await _upsert_item(session, item, now)
            if action == "created":
                created += 1
            else:
                updated += 1
        await session.flush()
        if len(items) < per_page:
            break

    await session.commit()
    return SyncResult(
        created=created,
        updated=updated,
        skipped=skipped,
        pages_fetched=pages_fetched,
    )
