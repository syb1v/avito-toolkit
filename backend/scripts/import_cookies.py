"""Перенос доверенных cookies из обычного браузера в профиль автоматизации.

Зачем: антибот-фаервол Авито доверяет вашему обычному браузеру (там всё работает),
но не «чистой» автоматизированной сессии. Импорт cookies переносит эту доверенность
в профиль, который использует воркер (BROWSER_USER_DATA_DIR).

Способы:
- автоматически из установленного браузера (Brave/Chrome/Chromium/Firefox/...):
    .venv/bin/python scripts/import_cookies.py --from-browser brave --fresh
- расширение Cookie-Editor: открыть avito.ru → Export → JSON, затем:
    .venv/bin/python scripts/import_cookies.py --file ~/cookies.json
- DevTools → Application → Cookies → скопировать строкой:
    .venv/bin/python scripts/import_cookies.py --cookie "v=...; u=...; ft=..."

Скрипт открывает браузер, добавляет cookies, проверяет страницу поиска и закрывается.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.services.cookies import (
    BROWSER_LOADERS,
    VERIFY_URL,
    apply_cookies_to_profile,
    cookies_from_browser,
    parse_cookie_input,
)

DEFAULT_PROFILE_DIR = ".browser-profile"


async def _stamp_default_account(ok: bool, items: int) -> None:
    """Отмечает в БД, что cookies аккаунта обновлены и проверены."""
    from app.db.models import AvitoAccount
    from app.db.session import dispose_engine, get_session_factory

    factory = get_session_factory()
    try:
        async with factory() as session:
            account = await session.scalar(
                select(AvitoAccount).order_by(AvitoAccount.name).limit(1)
            )
            if account is None:
                return
            now = datetime.now(UTC)
            account.last_check_at = now
            account.last_check_ok = ok
            if ok:
                account.cookies_at = now
                account.last_error = None
            else:
                account.last_error = f"cookies не дали доступ (объявлений: {items})"
            await session.commit()
    except Exception as error:  # noqa: BLE001 — не роняем импорт из-за БД
        print(f"WARN: не удалось обновить статус аккаунта в БД: {error}")
    finally:
        await dispose_engine()


async def default_account_proxy() -> str | None:
    """Прокси, закреплённый за аккаунтом (если есть в БД)."""
    from app.db.models import AvitoAccount
    from app.db.session import dispose_engine, get_session_factory

    factory = get_session_factory()
    try:
        async with factory() as session:
            account = await session.scalar(
                select(AvitoAccount).order_by(AvitoAccount.name).limit(1)
            )
            return account.proxy_url if account is not None else None
    except Exception:  # noqa: BLE001 — импорт cookies важнее статуса
        return None
    finally:
        await dispose_engine()


async def _run(
    cookies: list[dict[str, Any]],
    profile_dir: str,
    verify_url: str,
    *,
    fresh: bool = False,
) -> int:
    print(f"Профиль: {Path(profile_dir).resolve()}")
    print(f"Cookies к импорту: {len(cookies)}")
    proxy_url = await default_account_proxy()
    if proxy_url:
        print("Проверка через закреплённый прокси аккаунта")
    check = await apply_cookies_to_profile(
        cookies, profile_dir, verify_url, fresh=fresh, proxy_url=proxy_url
    )
    print(f"Проверка: челлендж={'да' if check.challenge else 'нет'}, объявлений={check.items}")
    await _stamp_default_account(check.ok, check.items)
    if not check.ok:
        print("FAIL: cookies не дали доступ. Обновите их (страница должна работать в браузере).")
        return 1
    print("OK: доступ есть, профиль сохранён. Воркер будет использовать его автоматически.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import browser cookies into automation profile")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="JSON-файл выгрузки Cookie-Editor или текстовый")
    source.add_argument("--cookie", help="строка Cookie из DevTools")
    source.add_argument(
        "--from-browser",
        choices=BROWSER_LOADERS,
        help="прочитать cookies avito.ru прямо из установленного браузера",
    )
    parser.add_argument("--profile", default=None, help="каталог профиля")
    parser.add_argument("--url", default=VERIFY_URL, help="URL для проверки доступа")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="сбросить профиль перед импортом (лечит сожжённые cookies)",
    )
    args = parser.parse_args()

    if args.from_browser:
        try:
            cookies = cookies_from_browser(args.from_browser)
        except RuntimeError as error:
            print(f"FAIL: {error}", file=sys.stderr)
            return 2
    else:
        if args.file:
            raw_text = Path(args.file).expanduser().read_text(encoding="utf-8")
        else:
            raw_text = args.cookie or ""
        try:
            cookies = parse_cookie_input(raw_text)
        except (ValueError, TypeError) as error:
            print(f"FAIL: не удалось разобрать cookies: {error}", file=sys.stderr)
            return 2
    if not cookies:
        print("FAIL: cookies не найдены (нужны домены avito.ru)", file=sys.stderr)
        return 2

    settings = get_settings()
    profile_dir = args.profile or settings.browser_user_data_dir or DEFAULT_PROFILE_DIR
    return asyncio.run(_run(cookies, profile_dir, args.url, fresh=args.fresh))


if __name__ == "__main__":
    raise SystemExit(main())
