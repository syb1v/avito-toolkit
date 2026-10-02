"""Заводит список товаров как поиски Авито и (опционально) собирает рынок.

Одна строка = один товар. Для каждого создаётся поиск по стране
(`https://www.avito.ru/all?q=<товар>`) с расписанием; с флагом --crawl сразу
выполняется обход и печатается медиана рынка.

Запуск из каталога backend/:

    .venv/bin/python scripts/import_products.py --file products.txt --crawl
    .venv/bin/python scripts/import_products.py --file products.txt --crawl --max-pages 1
"""

import argparse
import asyncio
import random
import uuid
from pathlib import Path
from urllib.parse import quote

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.ratelimit import RedisRateLimiter
from app.collectors.transport.browser_patchright import BrowserTransport
from app.config import get_settings
from app.db.models import Listing, Search, SearchListing
from app.db.session import dispose_engine, get_session_factory
from app.services.analytics.iqr import compute_price_stats
from app.services.collector import SearchCollector

DEFAULT_CRON = "0 */6 * * *"
PAUSE_BETWEEN_PRODUCTS_SECONDS = 8.0


def search_url(product: str) -> str:
    return f"https://www.avito.ru/all?q={quote(product)}"


def read_products(path: str) -> list[str]:
    products: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        products.append(value)
    return products


async def upsert_search(
    session: AsyncSession, name: str, url: str, cron: str, priority: int
) -> tuple[Search, bool]:
    existing = await session.scalar(select(Search).where(Search.url == url))
    if existing is not None:
        existing.name = name
        existing.schedule_cron = cron
        existing.priority = priority
        await session.commit()
        return existing, False
    search = Search(
        name=name,
        url=url,
        schedule_cron=cron,
        priority=priority,
        is_active=True,
    )
    session.add(search)
    await session.commit()
    await session.refresh(search)
    return search, True


async def market_median(session: AsyncSession, search_id: uuid.UUID) -> float | None:
    rows = await session.execute(
        select(Listing.current_price)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(
            SearchListing.search_id == search_id,
            Listing.status == "active",
            Listing.is_flagged.is_(False),
            Listing.current_price.is_not(None),
        )
    )
    prices = [float(row[0]) for row in rows.all() if row[0] is not None]
    if not prices:
        return None
    return float(compute_price_stats(prices).median)


async def _run(file_path: str, crawl: bool, max_pages: int, cron: str) -> int:
    products = read_products(file_path)
    if not products:
        print("FAIL: список товаров пуст")
        return 2

    factory = get_session_factory()
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    transport = BrowserTransport() if crawl else None
    try:
        created = 0
        for index, product in enumerate(products):
            url = search_url(product)
            async with factory() as session:
                search, is_new = await upsert_search(session, product, url, cron, 50)
                created += 1 if is_new else 0
                search_id = search.id
            line = f"[{'new' if is_new else 'upd'}] {product}"
            if crawl and transport is not None:
                async with factory() as session:
                    collector = SearchCollector(
                        session,
                        transport,
                        RedisRateLimiter(redis),
                        max_pages=max_pages,
                    )
                    result = await collector.collect(search_id)
                async with factory() as session:
                    median = await market_median(session, search_id)
                line += (
                    f" | лотов: {result.listings_seen}, новых: {result.new_listings}"
                    f", медиана: {median if median is None else round(median)} ₽"
                )
                if index < len(products) - 1:
                    await asyncio.sleep(
                        random.uniform(
                            PAUSE_BETWEEN_PRODUCTS_SECONDS, PAUSE_BETWEEN_PRODUCTS_SECONDS * 2
                        )
                    )
            print(line)
        print(f"итого: товаров {len(products)}, новых поисков {created}")
        return 0
    finally:
        if transport is not None:
            await transport.close()
        await redis.aclose()
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import products as Avito searches")
    parser.add_argument("--file", required=True, help="файл со списком товаров")
    parser.add_argument("--crawl", action="store_true", help="сразу обойти рынок")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--cron", default=DEFAULT_CRON)
    args = parser.parse_args()
    return asyncio.run(_run(args.file, args.crawl, args.max_pages, args.cron))


if __name__ == "__main__":
    raise SystemExit(main())
