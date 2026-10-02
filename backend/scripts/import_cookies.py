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
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from app.config import get_settings

DEFAULT_PROFILE_DIR = ".browser-profile"
VERIFY_URL = "https://www.avito.ru/moskva/telefony?q=iphone+15"
COOKIE_DOMAIN = ".avito.ru"
DOMAIN_FILTER = "avito"
SAMESITE_MAP = {
    "no_restriction": "None",
    "unspecified": "Lax",
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
}
BROWSER_LOADERS = (
    "brave",
    "chrome",
    "chromium",
    "edge",
    "firefox",
    "librewolf",
    "opera",
    "vivaldi",
)
ITEM_SELECTOR = "div[data-marker='item']"


def _cookie_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = str(raw.get("name") or "").strip()
    value = raw.get("value")
    if not name or value is None:
        return None
    domain = str(raw.get("domain") or COOKIE_DOMAIN)
    if DOMAIN_FILTER not in domain:
        return None
    entry: dict[str, Any] = {
        "name": name,
        "value": str(value),
        "domain": domain,
        "path": str(raw.get("path") or "/"),
        "expires": float(raw.get("expirationDate") or raw.get("expires") or -1),
        "httpOnly": bool(raw.get("httpOnly", False)),
        "secure": bool(raw.get("secure", True)),
    }
    same_site = raw.get("sameSite")
    if isinstance(same_site, str):
        mapped = SAMESITE_MAP.get(same_site.lower())
        if mapped:
            entry["sameSite"] = mapped
    return entry


def cookies_from_browser(browser: str) -> list[dict[str, Any]]:
    """Читает cookies avito.ru из установленного браузера через browser_cookie3."""
    try:
        import browser_cookie3
    except ImportError as error:
        raise RuntimeError(
            "нужен пакет browser-cookie3: .venv/bin/pip install browser-cookie3"
        ) from error
    loader = getattr(browser_cookie3, browser, None)
    if loader is None:
        raise RuntimeError(f"browser_cookie3 не умеет читать {browser!r}")
    try:
        jar = loader(domain_name=DOMAIN_FILTER)
    except Exception as error:  # noqa: BLE001 — у браузеров разные причины отказа
        raise RuntimeError(f"не удалось прочитать cookies из {browser}: {error}") from error
    entries: list[dict[str, Any]] = []
    for cookie in jar:
        domain = str(cookie.domain or "")
        if DOMAIN_FILTER not in domain:
            continue
        entry: dict[str, Any] = {
            "name": cookie.name,
            "value": cookie.value,
            "domain": domain,
            "path": cookie.path or "/",
            "secure": bool(cookie.secure),
            "httpOnly": bool(cookie.has_nonstandard_attr("httponly")),
            "sameSite": "Lax",
        }
        if cookie.expires:
            entry["expires"] = float(cookie.expires)
        entries.append(entry)
    return entries


def parse_cookie_input(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if text.startswith("[") or text.startswith("{"):
        payload = json.loads(text)
        rows = payload if isinstance(payload, list) else payload.get("cookies", [])
        entries = [_cookie_entry(row) for row in rows if isinstance(row, dict)]
        return [entry for entry in entries if entry is not None]
    cookies: list[dict[str, Any]] = []
    for pair in re.split(r"[;\n]+", text):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        cookies.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": COOKIE_DOMAIN,
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
            }
        )
    return cookies


async def _run(
    cookies: list[dict[str, Any]],
    profile_dir: str,
    verify_url: str,
    *,
    fresh: bool = False,
) -> int:
    from patchright.async_api import async_playwright

    settings = get_settings()
    channel = settings.browser_channel or "chromium"
    profile_path = Path(profile_dir)
    if fresh and profile_path.exists():
        print(f"Сброс профиля: {profile_path.resolve()}")
        shutil.rmtree(profile_path, ignore_errors=True)
    profile_path.mkdir(parents=True, exist_ok=True)
    print(f"Профиль: {profile_path.resolve()}")
    print(f"Cookies к импорту: {len(cookies)}")

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            profile_dir,
            headless=False,
            channel=channel,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
        )
        await context.add_cookies(cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(verify_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        html = await page.content()
        challenge = "доступ ограничен" in html.lower() or "hcaptcha" in html.lower()
        items = html.count('data-marker="item"')
        print(f"Проверка: челлендж={'да' if challenge else 'нет'}, объявлений={items}")
        await context.close()

    if challenge or items == 0:
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
