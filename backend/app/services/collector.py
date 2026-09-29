import asyncio
import logging
import random
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BotChallengeError, SourceAdapter
from app.collectors.ratelimit import RedisRateLimiter
from app.collectors.web.parsing import ParsedListing, parse_search_page
from app.config import get_settings
from app.db.models import Listing, ListingSnapshot, Search, SearchListing, Seller
from app.services.normalizer import price_changed

logger = logging.getLogger(__name__)

AVITO_DOMAIN = "avito.ru"
ITEMS_PER_PAGE = 50
RECENT_ACTIVITY_WINDOW = timedelta(hours=24)

REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


@dataclass(slots=True)
class CrawlResult:
    search_id: uuid.UUID
    pages_fetched: int
    pages_failed: int
    listings_seen: int
    new_listings: int
    price_changes: int
    gone_listings: int
    stopped_by_challenge: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["search_id"] = str(self.search_id)
        return payload


class SearchCollector:
    """Обход поиска, дедупликация и запись снапшотов цен."""

    def __init__(
        self,
        session: AsyncSession,
        transport: SourceAdapter,
        limiter: RedisRateLimiter | None = None,
        delay_range: tuple[float, float] | None = None,
        max_pages: int | None = None,
    ) -> None:
        settings = get_settings()
        self._session = session
        self._transport = transport
        self._limiter = limiter
        self._delay_range = delay_range or (
            settings.crawl_delay_min_seconds,
            settings.crawl_delay_max_seconds,
        )
        self._max_pages = max_pages or settings.crawl_max_pages_per_run
        self._rate = settings.crawl_rate_per_minute

    async def collect(self, search_id: uuid.UUID) -> CrawlResult:
        search = await self._session.get(Search, search_id)
        if search is None:
            raise LookupError(f"search {search_id} not found")

        now = datetime.now(UTC)
        unique: dict[int, ParsedListing] = {}
        pages_fetched = 0
        pages_failed = 0
        stopped_by_challenge = False

        for page_number, page_url in enumerate(self._page_urls(search.url), start=1):
            if page_number > self._max_pages:
                break
            if page_number > 1:
                await self._sleep_between_requests()
            if self._limiter is not None:
                await self._limiter.acquire(AVITO_DOMAIN, self._rate)
            try:
                page = await self._transport.fetch(page_url, headers=REQUEST_HEADERS)
            except BotChallengeError:
                logger.warning("bot challenge on page %s of search %s", page_number, search_id)
                stopped_by_challenge = True
                break
            if page.status_code >= 400:
                logger.warning(
                    "page %s of search %s returned %s",
                    page_number,
                    search_id,
                    page.status_code,
                )
                pages_failed += 1
                break
            parsed = parse_search_page(page.body, base_url=page.url)
            if not parsed:
                break
            pages_fetched += 1
            for listing in parsed:
                absolute_position = (page_number - 1) * ITEMS_PER_PAGE + listing.position
                unique.setdefault(listing.listing_id, replace(listing, position=absolute_position))

        result = await self._persist(search, list(unique.values()), now)
        result.pages_fetched = pages_fetched
        result.pages_failed = pages_failed
        result.stopped_by_challenge = stopped_by_challenge
        await self._session.commit()
        return result

    def _page_urls(self, base_url: str) -> Iterator[str]:
        yield base_url
        separator = "&" if "?" in base_url else "?"
        for page in range(2, self._max_pages + 1):
            yield f"{base_url}{separator}p={page}"

    async def _sleep_between_requests(self) -> None:
        low, high = self._delay_range
        if high <= 0:
            return
        await asyncio.sleep(random.uniform(low, max(low, high)))

    async def _persist(
        self, search: Search, listings: list[ParsedListing], now: datetime
    ) -> CrawlResult:
        session = self._session
        listing_ids = [listing.listing_id for listing in listings]

        existing_prices: dict[int, float | None] = {}
        if listing_ids:
            rows = await session.execute(
                select(Listing.id, Listing.current_price).where(Listing.id.in_(listing_ids))
            )
            existing_prices = {
                row[0]: float(row[1]) if row[1] is not None else None for row in rows.all()
            }

        new_ids = [item for item in listing_ids if item not in existing_prices]
        changed_ids = [
            listing.listing_id
            for listing in listings
            if price_changed(existing_prices.get(listing.listing_id), listing.price)
        ]

        seller_rows = {
            listing.seller_id: {
                "id": listing.seller_id,
                "first_seen": now,
                "last_seen": now,
            }
            for listing in listings
            if listing.seller_id is not None
        }
        if seller_rows:
            seller_stmt = pg_insert(Seller).values(list(seller_rows.values()))
            seller_stmt = seller_stmt.on_conflict_do_update(
                index_elements=[Seller.id], set_={"last_seen": now}
            )
            await session.execute(seller_stmt)

        if listings:
            listing_stmt = pg_insert(Listing).values(
                [
                    {
                        "id": listing.listing_id,
                        "title": listing.title,
                        "url": listing.url,
                        "seller_id": listing.seller_id,
                        "current_price": listing.price,
                        "status": "active",
                        "first_seen": now,
                        "last_seen": now,
                    }
                    for listing in listings
                ]
            )
            listing_stmt = listing_stmt.on_conflict_do_update(
                index_elements=[Listing.id],
                set_={
                    "title": listing_stmt.excluded.title,
                    "url": listing_stmt.excluded.url,
                    "seller_id": func.coalesce(listing_stmt.excluded.seller_id, Listing.seller_id),
                    "current_price": func.coalesce(
                        listing_stmt.excluded.current_price, Listing.current_price
                    ),
                    "status": "active",
                    "last_seen": now,
                },
            )
            await session.execute(listing_stmt)

            search_listing_stmt = pg_insert(SearchListing).values(
                [
                    {
                        "search_id": search.id,
                        "listing_id": listing.listing_id,
                        "first_seen": now,
                        "last_seen": now,
                        "last_position": listing.position,
                    }
                    for listing in listings
                ]
            )
            search_listing_stmt = search_listing_stmt.on_conflict_do_update(
                index_elements=[SearchListing.search_id, SearchListing.listing_id],
                set_={
                    "last_seen": now,
                    "last_position": search_listing_stmt.excluded.last_position,
                },
            )
            await session.execute(search_listing_stmt)

        snapshot_ids = set(new_ids) | set(changed_ids)
        snapshot_rows = [
            {
                "search_id": search.id,
                "listing_id": listing.listing_id,
                "recorded_at": now,
                "price": listing.price,
                "position_index": listing.position,
                "is_vip": listing.is_vip,
                "is_highlighted": listing.is_highlighted,
            }
            for listing in listings
            if listing.listing_id in snapshot_ids and listing.price is not None
        ]
        if snapshot_rows:
            await session.execute(insert(ListingSnapshot).values(snapshot_rows))

        gone_ids = await self._gone_ids(search, set(listing_ids), now)
        if gone_ids:
            other_activity = select(SearchListing.listing_id).where(
                SearchListing.last_seen >= now - RECENT_ACTIVITY_WINDOW,
                SearchListing.search_id != search.id,
            )
            gone_stmt = (
                update(Listing)
                .where(Listing.id.in_(gone_ids), ~Listing.id.in_(other_activity))
                .values(status="gone")
            )
            await session.execute(gone_stmt)

        return CrawlResult(
            search_id=search.id,
            pages_fetched=0,
            pages_failed=0,
            listings_seen=len(listings),
            new_listings=len(new_ids),
            price_changes=len(changed_ids),
            gone_listings=len(gone_ids),
        )

    async def _gone_ids(self, search: Search, seen_ids: set[int], now: datetime) -> list[int]:
        rows = await self._session.execute(
            select(SearchListing.listing_id).where(
                SearchListing.search_id == search.id,
                SearchListing.last_seen < now,
            )
        )
        return [row[0] for row in rows.all() if row[0] not in seen_ids]
