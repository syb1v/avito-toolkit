"""Импорт своих объявлений из публичного профиля Авито (без API).

Собирает ваш профиль тем же браузерным транспортом, что и конкурентов,
и переносит объявления в «Наши объявления» (our_listings).

Запуск из каталога backend/:

    .venv/bin/python scripts/import_own_profile.py \
        --url "https://www.avito.ru/user/XXXX/profile?page=1&sort=date"
    # с еженощным обходом профиля:
    .venv/bin/python scripts/import_own_profile.py --url "..." --activate

Дальше: POST /api/v1/our-listings/match-all — сопоставить с рынком и получить
рекомендации по ценам.
"""

import argparse
import asyncio

from redis.asyncio import Redis

from app.collectors.ratelimit import RedisRateLimiter
from app.collectors.transport.browser_patchright import BrowserTransport
from app.config import get_settings
from app.db.models import Search
from app.db.session import dispose_engine, get_session_factory
from app.services.collector import SearchCollector
from app.services.our_listings import import_from_search

PROFILE_CRON = "0 */2 * * *"
PROFILE_PRIORITY = 50


async def _run(url: str, name: str, max_pages: int, activate: bool) -> int:
    factory = get_session_factory()
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    transport = BrowserTransport()
    try:
        async with factory() as session:
            search = Search(
                name=name,
                url=url,
                is_active=activate,
                schedule_cron=PROFILE_CRON,
                priority=PROFILE_PRIORITY,
            )
            session.add(search)
            await session.commit()
            await session.refresh(search)
            search_id = search.id
        print(f"search: {search_id} | активен: {activate}")

        async with factory() as session:
            collector = SearchCollector(
                session, transport, RedisRateLimiter(redis), max_pages=max_pages
            )
            result = await collector.collect(search_id)
        print(f"crawl: {result.to_dict()}")
        if result.listings_seen == 0:
            print("FAIL: профиль не отдал объявлений (проверьте авторизацию/URL)")
            return 1

        async with factory() as session:
            imported = await import_from_search(session, search_id)
        print(
            f"our listings: created={imported.created} updated={imported.updated} "
            f"skipped={imported.skipped}"
        )
        print("дальше: POST /api/v1/our-listings/match-all (панель → Наши объявления)")
        return 0
    finally:
        await transport.close()
        await redis.aclose()
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import own Avito profile listings")
    parser.add_argument("--url", required=True, help="URL вашего публичного профиля")
    parser.add_argument("--name", default="Мой профиль")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--activate", action="store_true", help="обходить профиль по расписанию")
    args = parser.parse_args()
    return asyncio.run(_run(args.url, args.name, args.max_pages, args.activate))


if __name__ == "__main__":
    raise SystemExit(main())
