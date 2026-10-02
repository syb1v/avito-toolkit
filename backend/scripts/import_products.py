"""Заводит список товаров как поиски Авито и (опционально) собирает рынок.

Формат строки:

    <Название товара> [| <группа1: alt1, alt2>; <группа2: alt1>; ...]

Группы ключей — фильтр точности: все группы должны встретиться в названии
объявления (AND), внутри группы достаточно одного варианта (OR). Если фильтр
не задан, он выводится автоматически из названия (бренд + модель без цветов
и комплектаций).

Запуск из каталога backend/:

    .venv/bin/python scripts/import_products.py --file products.txt --crawl
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
from app.services.proxy_pool import build_proxy_pool
from app.services.search_filter import normalize_text, query_from_groups

DEFAULT_CRON = "0 */6 * * *"
PAUSE_BETWEEN_PRODUCTS_SECONDS = 8.0
AUTO_KEYWORDS_LIMIT = 4

STOPWORDS = {
    "and",
    "the",
    "with",
    "case",
    "band",
    "one",
    "size",
    "gps",
    "cellular",
    "wi-fi",
    "wifi",
    "natural",
    "aluminium",
    "aluminum",
    "matte",
    "black",
    "white",
    "silver",
    "gold",
    "gray",
    "grey",
    "titanium",
    "translucent",
    "ocean",
    "rose",
    "bloom",
    "cocoon",
    "exclusive",
    "edition",
    "deep",
    "forest",
    "mm",
    "db",
    "new",
    "original",
}


def parse_product_line(line: str) -> tuple[str, list[list[str]]]:
    name, _, filter_part = line.partition("|")
    name = name.strip()
    groups: list[list[str]] = []
    for group in filter_part.split(";"):
        alternatives = [value.strip() for value in group.split(",") if value.strip()]
        if alternatives:
            groups.append(alternatives)
    if not groups:
        tokens = [token for token in normalize_text(name).split() if token not in STOPWORDS][
            :AUTO_KEYWORDS_LIMIT
        ]
        groups = [[token] for token in tokens]
    return name, groups


def read_products(path: str) -> list[tuple[str, list[list[str]]]]:
    products: list[tuple[str, list[list[str]]]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        products.append(parse_product_line(value))
    return products


def search_url(query: str) -> str:
    return f"https://www.avito.ru/all?q={quote(query)}"


async def upsert_search(
    session: AsyncSession,
    name: str,
    query: str,
    groups: list[list[str]],
    cron: str,
    priority: int,
    max_pages: int = 1,
) -> tuple[Search, bool]:
    url = search_url(query)
    params = {
        "product": name,
        "query": query,
        "keyword_groups": groups,
        "max_pages": max_pages,
    }
    existing = await session.scalar(select(Search).where(Search.url == url))
    if existing is not None:
        existing.name = name
        existing.schedule_cron = cron
        existing.priority = priority
        existing.params = params
        await session.commit()
        return existing, False
    search = Search(
        name=name,
        url=url,
        params=params,
        schedule_cron=cron,
        priority=priority,
        is_active=True,
    )
    session.add(search)
    await session.commit()
    await session.refresh(search)
    return search, True


async def market_median(session: AsyncSession, search_id: uuid.UUID) -> tuple[float | None, int]:
    from app.services.search_filter import keywords_from_params, matches_keyword_groups

    search = await session.get(Search, search_id)
    groups = keywords_from_params(search.params if search is not None else None)
    rows = await session.execute(
        select(Listing.title, Listing.current_price)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(
            SearchListing.search_id == search_id,
            Listing.status == "active",
            Listing.is_flagged.is_(False),
            Listing.current_price.is_not(None),
        )
    )
    prices: list[float] = []
    excluded = 0
    for title, price in rows.all():
        if price is None:
            continue
        if groups and not matches_keyword_groups(title or "", groups):
            excluded += 1
            continue
        prices.append(float(price))
    if not prices:
        return None, excluded
    return float(compute_price_stats(prices).median), excluded


async def _run(file_path: str, crawl: bool, max_pages: int, cron: str) -> int:
    products = read_products(file_path)
    if not products:
        print("FAIL: список товаров пуст")
        return 2

    factory = get_session_factory()
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    transport = BrowserTransport(proxy_pool=build_proxy_pool(redis)) if crawl else None
    try:
        created = 0
        for index, (name, groups) in enumerate(products):
            query = query_from_groups(groups)
            async with factory() as session:
                search, is_new = await upsert_search(session, name, query, groups, cron, 50)
                created += 1 if is_new else 0
                search_id = search.id
            line = f"[{'new' if is_new else 'upd'}] {name[:60]} | query: {query}"
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
                    median, excluded = await market_median(session, search_id)
                line += (
                    f" | лотов: {result.listings_seen}, новых: {result.new_listings}"
                    f", медиана: {median if median is None else round(median)} ₽"
                    f", не по теме: {excluded}"
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
