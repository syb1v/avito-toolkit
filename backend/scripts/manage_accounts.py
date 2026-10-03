"""Управление аккаунтами Авито (профили + cookies).

Примеры:

    .venv/bin/python scripts/manage_accounts.py list
    .venv/bin/python scripts/manage_accounts.py add --name "Аккаунт 2"
    .venv/bin/python scripts/manage_accounts.py cookies --name "Аккаунт 2" \\
        --from-browser brave --fresh
    .venv/bin/python scripts/manage_accounts.py cookies --name "Аккаунт 2" --file ~/cookies.json
    .venv/bin/python scripts/manage_accounts.py check --name "Аккаунт 2"
    .venv/bin/python scripts/manage_accounts.py remove --name "Аккаунт 2"

Свой основной профиль (BROWSER_USER_DATA_DIR) заводится миграцией как аккаунт
«Основной» и удалению не подлежит — им можно продолжать пользоваться как раньше.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.transport.browser_patchright import BrowserTransport
from app.collectors.web.parsing import parse_search_page
from app.config import get_settings
from app.db.models import AvitoAccount, Search
from app.db.session import dispose_engine, get_session_factory
from app.services.accounts import (
    proxy_label_for,
    resolve_profile_path,
    resolve_proxy_label,
    unique_profile_dir,
)
from app.services.cookies import (
    BROWSER_LOADERS,
    apply_cookies_to_profile,
    cookies_from_browser,
    parse_cookie_input,
)

CHECK_URL = "https://www.avito.ru/all?q=iphone"


async def _find(session: AsyncSession, name: str) -> AvitoAccount:
    account = await session.scalar(select(AvitoAccount).where(AvitoAccount.name == name))
    if account is None:
        raise SystemExit(f"Аккаунт {name!r} не найден. Список: manage_accounts.py list")
    return account


async def cmd_list() -> int:
    factory = get_session_factory()
    try:
        async with factory() as session:
            rows = await session.execute(
                select(AvitoAccount, func.count(Search.id))
                .outerjoin(Search, Search.account_id == AvitoAccount.id)
                .group_by(AvitoAccount.id)
                .order_by(AvitoAccount.is_default.desc(), AvitoAccount.name)
            )
            print(
                f"{'имя':<24} {'роль':<10} {'статус':<8} {'поисков':<8} "
                f"{'прокси':<28} cookies_at           профиль"
            )
            for account, count in rows.all():
                cookies = (
                    account.cookies_at.strftime("%Y-%m-%d %H:%M") if account.cookies_at else "—"
                )
                marker = " (основной)" if account.is_default else ""
                proxy = proxy_label_for(account.proxy_url) or "личный IP"
                print(
                    f"{account.name + marker:<24} {account.role:<10} {account.status:<8} "
                    f"{count:<8} {proxy:<28} {cookies:<20} {account.profile_dir}"
                )
            return 0
    finally:
        await dispose_engine()


async def cmd_add(
    name: str,
    notes: str | None,
    profile_dir: str | None,
    role: str,
    proxy_label: str | None,
) -> int:
    factory = get_session_factory()
    try:
        async with factory() as session:
            exists = await session.scalar(select(AvitoAccount.id).where(AvitoAccount.name == name))
            if exists is not None:
                raise SystemExit(f"Аккаунт {name!r} уже есть")
            profile = profile_dir or await unique_profile_dir(session, name)
            try:
                proxy_url = resolve_proxy_label(proxy_label)
            except ValueError as error:
                raise SystemExit(str(error)) from error
            account = AvitoAccount(
                name=name,
                profile_dir=profile,
                notes=notes,
                role=role,
                proxy_url=proxy_url,
                status="active",
            )
            session.add(account)
            await session.commit()
            await session.refresh(account)
            path = resolve_profile_path(account.profile_dir)
            print(f"Создан аккаунт {account.name!r}: {account.profile_dir} -> {path}")
            print(
                "Загрузите cookies: manage_accounts.py cookies "
                f"--name {account.name!r} --from-browser brave --fresh"
            )
            return 0
    finally:
        await dispose_engine()


def _load_input(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.from_browser:
        return cookies_from_browser(args.from_browser)
    if args.file:
        raw = Path(args.file).expanduser().read_text(encoding="utf-8")
    else:
        raw = args.cookie or ""
    return parse_cookie_input(raw)


async def cmd_cookies(args: argparse.Namespace) -> int:
    cookies = _load_input(args)
    if not cookies:
        raise SystemExit("cookies не найдены (нужны домены avito.ru)")
    factory = get_session_factory()
    try:
        async with factory() as session:
            account = await _find(session, args.name)
            profile = str(resolve_profile_path(account.profile_dir))
            print(f"Аккаунт {account.name!r}, cookies: {len(cookies)}")
            check = await apply_cookies_to_profile(cookies, profile, args.url, fresh=args.fresh)
            account.cookies_at = datetime.now(UTC)
            account.last_check_at = account.cookies_at
            account.last_check_ok = check.ok
            account.last_error = None if check.ok else f"проверка: объявлений={check.items}"
            if check.ok and account.status == "paused":
                account.status = "active"
            await session.commit()
            if not check.ok:
                print("FAIL: cookies не дали доступ — профиль сохранён, но проверку не прошёл.")
                return 1
            print("OK: cookies загружены, аккаунт готов к обходам.")
            return 0
    finally:
        await dispose_engine()


async def cmd_check(name: str, force: bool = False) -> int:
    factory = get_session_factory()
    transport: BrowserTransport | None = None
    try:
        async with factory() as session:
            account = await _find(session, name)
            settings = get_settings()
            cooldown = settings.account_check_cooldown_minutes * 60
            if (
                not force
                and cooldown > 0
                and account.last_check_at is not None
                and (datetime.now(UTC) - account.last_check_at).total_seconds() < cooldown
            ):
                print("Проверка недавно была — пропускаю (--force чтобы проверить всё равно).")
                return 0
            transport = BrowserTransport(
                user_data_dir=str(resolve_profile_path(account.profile_dir))
            )
            checked_at = datetime.now(UTC)
            try:
                page = await transport.fetch(CHECK_URL)
                items = len(parse_search_page(page.body, base_url=page.url))
                ok = page.status_code < 400 and items > 0
                account.last_error = None if ok else f"HTTP {page.status_code}, items={items}"
                print(f"Проверка {name!r}: HTTP {page.status_code}, объявлений={items}")
            except Exception as error:  # noqa: BLE001 — фиксируем статус
                ok = False
                account.last_error = f"{type(error).__name__}: {error}"
                print(f"Проверка {name!r}: ошибка {account.last_error}")
            account.last_check_at = checked_at
            account.last_check_ok = ok
            await session.commit()
            return 0 if ok else 1
    finally:
        if transport is not None:
            await transport.close()
        await dispose_engine()


async def cmd_remove(name: str) -> int:
    factory = get_session_factory()
    try:
        async with factory() as session:
            account = await _find(session, name)
            if account.is_default:
                raise SystemExit("Основной аккаунт удалить нельзя")
            await session.delete(account)
            await session.commit()
            print(f"Аккаунт {name!r} удалён; поиски переведены на основной профиль.")
            return 0
    finally:
        await dispose_engine()


async def cmd_proxy(name: str, label: str | None) -> int:
    factory = get_session_factory()
    try:
        async with factory() as session:
            account = await _find(session, name)
            try:
                account.proxy_url = resolve_proxy_label(label)
            except ValueError as error:
                raise SystemExit(str(error)) from error
            await session.commit()
            print(f"{name!r}: прокси → {proxy_label_for(account.proxy_url) or 'личный IP'}")
            return 0
    finally:
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="Avito account profiles & cookies")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="список аккаунтов")

    add = sub.add_parser("add", help="создать аккаунт")
    add.add_argument("--name", required=True)
    add.add_argument("--notes")
    add.add_argument("--profile-dir")
    add.add_argument(
        "--role",
        choices=("searcher", "seller"),
        default="searcher",
        help="searcher — обход поиска (по умолчанию), seller — управление объявлениями",
    )
    add.add_argument(
        "--proxy",
        help="метка прокси из PROXY_LIST для sticky-привязки (см. make accounts)",
    )

    cookies = sub.add_parser("cookies", help="загрузить cookies в аккаунт")
    cookies.add_argument("--name", required=True)
    source = cookies.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="JSON Cookie-Editor или текст")
    source.add_argument("--cookie", help="строка Cookie из DevTools")
    source.add_argument("--from-browser", choices=BROWSER_LOADERS)
    cookies.add_argument("--url", default=CHECK_URL)
    cookies.add_argument("--fresh", action="store_true")

    proxy = sub.add_parser("proxy", help="привязать/снять sticky-прокси аккаунта")
    proxy.add_argument("--name", required=True)
    proxy.add_argument("--label", help="метка прокси из PROXY_LIST; без неё — снять")
    proxy.add_argument("--clear", action="store_true", help="ходить с личного IP")

    check = sub.add_parser("check", help="проверить доступ аккаунта")
    check.add_argument("--name", required=True)
    check.add_argument("--force", action="store_true", help="игнорировать кулдаун проверки")

    remove = sub.add_parser("remove", help="удалить аккаунт")
    remove.add_argument("--name", required=True)

    args = parser.parse_args()
    settings = get_settings()
    if settings.browser_headless:
        print(
            "Внимание: BROWSER_HEADLESS=true — Авито отдаёт выдачу только видимому "
            "браузеру, проверка может вернуть 0 объявлений.",
            file=sys.stderr,
        )
    if args.command == "list":
        return asyncio.run(cmd_list())
    if args.command == "add":
        return asyncio.run(cmd_add(args.name, args.notes, args.profile_dir, args.role, args.proxy))
    if args.command == "cookies":
        return asyncio.run(cmd_cookies(args))
    if args.command == "check":
        return asyncio.run(cmd_check(args.name, args.force))
    if args.command == "proxy":
        return asyncio.run(cmd_proxy(args.name, None if args.clear else args.label))
    return asyncio.run(cmd_remove(args.name))


if __name__ == "__main__":
    raise SystemExit(main())
