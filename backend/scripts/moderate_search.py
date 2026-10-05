"""Ручной прогон модерации по поиску (с догрузкой описаний кандидатов).

Запуск из каталога backend/:

    .venv/bin/python scripts/moderate_search.py --search-id <uuid>
    .venv/bin/python scripts/moderate_search.py --search-id <uuid> --no-descriptions
    .venv/bin/python scripts/moderate_search.py --search-id <uuid> --no-ai
"""

import argparse
import asyncio
import uuid

from redis.asyncio import Redis

from app.collectors.transport.browser_patchright import BrowserTransport
from app.config import get_settings
from app.db.session import dispose_engine, get_session_factory
from app.services.moderation import moderate_search
from app.services.proxy_pool import build_proxy_pool


async def _run(search_id: str, with_descriptions: bool, with_ai: bool) -> int:
    factory = get_session_factory()
    redis = Redis.from_url(get_settings().redis_url)
    try:
        async with factory() as session:
            pool = await build_proxy_pool(redis, session)
            transport = BrowserTransport(proxy_pool=pool) if with_descriptions else None
            result = await moderate_search(
                session,
                uuid.UUID(search_id),
                ai=with_ai,
                transport=transport,
                with_descriptions=with_descriptions,
            )
            await session.commit()
        print(
            f"total={result.total} flagged={result.flagged} "
            f"descriptions={result.described} ai_scored={result.ai_scored} "
            f"median={result.median} categories={result.categories}"
        )
        return 0
    finally:
        if transport is not None:
            await transport.close()
        await redis.aclose()
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run listing moderation")
    parser.add_argument("--search-id", required=True)
    parser.add_argument("--no-descriptions", action="store_true", help="не догружать описания")
    parser.add_argument("--no-ai", action="store_true", help="без AI-скоринга")
    args = parser.parse_args()
    return asyncio.run(_run(args.search_id, not args.no_descriptions, not args.no_ai))


if __name__ == "__main__":
    raise SystemExit(main())
