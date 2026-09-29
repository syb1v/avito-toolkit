"""Локальная проверка сбора: скачать страницу выдачи и распарсить.

Запуск из каталога backend/:

    .venv/bin/python scripts/fetch_page.py --url "https://www.avito.ru/..." --out /tmp/avito.html

Скрипт не пишет в БД и не требует Redis: только сеть, curl_cffi и парсер.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.collectors.transport.http_cffi import HttpCffiTransport
from app.collectors.web.parsing import parse_search_page

REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}
PREVIEW_ITEMS = 5


async def _run(url: str, out: str | None, proxy: str | None, pages: int) -> int:
    transport = HttpCffiTransport(proxy=proxy)
    separator = "&" if "?" in url else "?"
    total = 0
    try:
        for page_number in range(1, pages + 1):
            page_url = url if page_number == 1 else f"{url}{separator}p={page_number}"
            try:
                page = await transport.fetch(page_url, headers=REQUEST_HEADERS)
            except Exception as error:
                print(f"page {page_number}: request failed: {error}", file=sys.stderr)
                return 2
            if out and page_number == 1:
                Path(out).write_text(page.body, encoding="utf-8")
                print(f"saved html: {out}")
            listings = parse_search_page(page.body, base_url=page.url)
            print(f"page {page_number}: {len(listings)} listings")
            for listing in listings[:PREVIEW_ITEMS]:
                print(
                    f"  #{listing.position} {listing.listing_id} | "
                    f"{listing.price} RUB | {listing.title[:60]}"
                )
            total += len(listings)
            if not listings:
                break
    finally:
        await transport.close()
    print(f"total listings parsed: {total}")
    return 0 if total > 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Avito search page fetch & parse")
    parser.add_argument("--url", required=True, help="URL поисковой выдачи Авито")
    parser.add_argument("--out", help="сохранить HTML первой страницы в файл")
    parser.add_argument("--proxy", help="прокси, например http://user:pass@host:port")
    parser.add_argument("--pages", type=int, default=1, help="число страниц (по умолчанию 1)")
    args = parser.parse_args()
    return asyncio.run(_run(args.url, args.out, args.proxy, args.pages))


if __name__ == "__main__":
    raise SystemExit(main())
