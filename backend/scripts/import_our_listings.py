"""Импорт списка наших SKU из JSON-файла в базу.

Формат (см. skus.example.json):

    [
      {"sku": "IP15-128", "title": "iPhone 15 128GB", "price": "90 000 ₽",
       "cost_price": 60000, "category": "Телефоны",
       "avito_url": "https://www.avito.ru/..."}
    ]

Обязательны: sku, title, price (>0). Строки без них пропускаются.
Повторный импорт обновляет существующие SKU по sku/avito_item_id.

Запуск из каталога backend/:

    .venv/bin/python scripts/import_our_listings.py --file skus.json
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.db.session import dispose_engine, get_session_factory
from app.services.our_listings import normalize_import_rows, upsert_our_listings


async def _run(file_path: str) -> int:
    payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
    rows_raw = payload if isinstance(payload, list) else payload.get("items", [])
    if not isinstance(rows_raw, list):
        print("FAIL: ожидается JSON-массив SKU или объект с items", file=sys.stderr)
        return 2
    rows, invalid = normalize_import_rows(rows_raw)
    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            result = await upsert_our_listings(session, rows)
    finally:
        await dispose_engine()
    print(
        f"our listings: created={result.created} updated={result.updated} "
        f"skipped={result.skipped + invalid}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import our SKUs from JSON")
    parser.add_argument("--file", required=True, help="путь к JSON со списком SKU")
    args = parser.parse_args()
    return asyncio.run(_run(args.file))


if __name__ == "__main__":
    raise SystemExit(main())
