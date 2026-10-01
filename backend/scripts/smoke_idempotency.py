"""Идемпотентность обхода: два прогона одного поиска на реальной фикстуре.

Детерминированно (без сети) проверяем, что повторный обход:
- не создаёт новых объявлений и снапшотов;
- не меняет число связей поиска;
- не пишет price_changes.

Используется реальная санитизированная разметка выдачи
(`tests/fixtures/real/search_iphone15.html`), записанная в реальную БД.
После проверки тестовый поиск удаляется из базы (флаг `--keep` оставляет его).

Запуск из каталога backend/ (нужна БД):

    .venv/bin/python scripts/smoke_idempotency.py
    .venv/bin/python scripts/smoke_idempotency.py --fixture tests/fixtures/real/search_iphone15.html

На живом Авито между обходами возможна ротация выдачи (новые/ушедшие лоты) —
это не дубли; детерминированную гарантию даёт этот смоук.
"""

import argparse
import asyncio
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import FetchedPage
from app.db.models import ListingSnapshot, Search, SearchListing
from app.db.session import dispose_engine, get_session_factory
from app.services.collector import CrawlResult, SearchCollector

DEFAULT_FIXTURE = "tests/fixtures/real/search_iphone15.html"
FIXTURE_URL = "https://www.avito.ru/moskva/telefony?q=iphone+15"


class FixtureTransport:
    """Отдаёт реальную страницу выдачи на первой странице, дальше — пусто."""

    name = "fixture"

    def __init__(self, html: str) -> None:
        self._html = html
        self._served = False

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchedPage:
        if not self._served:
            self._served = True
            return FetchedPage(url=url, status_code=200, body=self._html)
        return FetchedPage(url=url, status_code=200, body="")

    async def close(self) -> None:
        return None


async def _counts(session: AsyncSession, search_id: uuid.UUID) -> tuple[int, int]:
    snapshots = await session.scalar(
        select(func.count())
        .select_from(ListingSnapshot)
        .where(ListingSnapshot.search_id == search_id)
    )
    links = await session.scalar(
        select(func.count()).select_from(SearchListing).where(SearchListing.search_id == search_id)
    )
    return int(snapshots or 0), int(links or 0)


async def _collect_once(
    search_id: uuid.UUID, transport: FixtureTransport, max_pages: int
) -> CrawlResult:
    factory = get_session_factory()
    async with factory() as session:
        collector = SearchCollector(
            session,
            transport,
            limiter=None,
            delay_range=(0.0, 0.0),
            max_pages=max_pages,
        )
        return await collector.collect(search_id)


async def _cleanup(search_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(ListingSnapshot).where(ListingSnapshot.search_id == search_id))
        await session.execute(delete(Search).where(Search.id == search_id))
        await session.commit()


async def _run(fixture_path: str, max_pages: int, keep: bool) -> int:
    html = Path(fixture_path).read_text(encoding="utf-8")
    factory = get_session_factory()
    search_id: uuid.UUID | None = None
    try:
        async with factory() as session:
            search = Search(
                name="idempotency fixture",
                url=FIXTURE_URL,
                is_active=False,
                schedule_cron="0 0 1 1 *",
                priority=100,
            )
            session.add(search)
            await session.commit()
            await session.refresh(search)
            search_id = search.id
        print(f"search: {search_id} | fixture: {fixture_path}")

        first = await _collect_once(search_id, FixtureTransport(html), max_pages)
        async with factory() as session:
            first_snapshots, first_links = await _counts(session, search_id)
        print(f"run1: {first.to_dict()}")
        print(f"run1: snapshots={first_snapshots} search_listings={first_links}")

        second = await _collect_once(search_id, FixtureTransport(html), max_pages)
        async with factory() as session:
            second_snapshots, second_links = await _counts(session, search_id)
        print(f"run2: {second.to_dict()}")
        print(f"run2: snapshots={second_snapshots} search_listings={second_links}")

        ok = (
            first.listings_seen == 50
            and second.listings_seen == 50
            and second.new_listings == 0
            and second.price_changes == 0
            and second.gone_listings == 0
            and second_snapshots == first_snapshots
            and second_links == first_links
        )
        print(
            "PASS: повторный обход идемпотентен" if ok else "FAIL: обнаружены дубли/лишние снапшоты"
        )
        return 0 if ok else 1
    finally:
        if search_id is not None and not keep:
            await _cleanup(search_id)
            print("cleanup: тестовый поиск удалён из базы (--keep, чтобы оставить)")
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotency smoke (real fixture, DB)")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument(
        "--keep", action="store_true", help="не удалять тестовый поиск после проверки"
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.fixture, args.max_pages, args.keep))


if __name__ == "__main__":
    raise SystemExit(main())
