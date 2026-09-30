"""Массовый импорт реальных поисков из JSON-файла.

Формат файла:

    [
      {"name": "iPhone 15 Москва",
       "url": "https://www.avito.ru/moskva/telefony?q=iphone+15",
       "schedule_cron": "*/30 * * * *",
       "priority": 100},
      {"name": "Профиль конкурента",
       "url": "https://www.avito.ru/user/xxxxx/profile"}
    ]

Запуск из каталога backend/:

    .venv/bin/python scripts/import_searches.py --file searches.json

Поиски с совпадающим URL обновляются (расписание, приоритет), новые создаются.
После импорта планировщик сам подхватит их в течение ~5 минут.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.db.session import dispose_engine, get_session_factory
from app.services.searches import import_searches, normalize_search_rows


async def _run(file_path: str) -> int:
    raw = json.loads(Path(file_path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("FAIL: ожидается JSON-массив поисков", file=sys.stderr)
        return 2
    rows, invalid = normalize_search_rows(raw)
    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            result = await import_searches(session, rows)
    finally:
        await dispose_engine()
    print(
        f"searches: created={result.created} updated={result.updated} "
        f"skipped={result.skipped + invalid}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk import Avito searches")
    parser.add_argument("--file", required=True, help="путь к JSON с поисками")
    args = parser.parse_args()
    return asyncio.run(_run(args.file))


if __name__ == "__main__":
    raise SystemExit(main())
