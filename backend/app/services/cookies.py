"""Cookies аккаунтов: парсинг, чтение из браузера, запись в профиль и проверка."""

import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from app.config import get_settings

logger = logging.getLogger(__name__)

COOKIE_DOMAIN = ".avito.ru"
DOMAIN_FILTER = "avito"
VERIFY_URL = "https://www.avito.ru/moskva/telefony?q=iphone+15"
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


@dataclass(frozen=True, slots=True)
class CookieCheck:
    ok: bool
    items: int
    challenge: bool


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


def parse_cookie_input(text: str) -> list[dict[str, Any]]:
    """Разбирает JSON Cookie-Editor или строку Cookie/DevTools."""
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


async def apply_cookies_to_profile(
    cookies: list[dict[str, Any]],
    profile_dir: str,
    verify_url: str = VERIFY_URL,
    *,
    fresh: bool = False,
    proxy_url: str | None = None,
) -> CookieCheck:
    """Пишет cookies в профиль, открывает видимый Chromium и проверяет выдачу.

    Проверка идёт через тот же прокси, что закреплён за аккаунтом: иначе
    датацентр-IP Авито отдаёт заглушку и cookies ошибочно считаются плохими.
    """
    from patchright.async_api import async_playwright

    from app.collectors.transport.browser_patchright import proxy_settings

    settings = get_settings()
    channel = settings.browser_channel or "chromium"
    profile_path = Path(profile_dir)
    if fresh and profile_path.exists():
        logger.info("reset profile %s", profile_path.resolve())
        shutil.rmtree(profile_path, ignore_errors=True)
    profile_path.mkdir(parents=True, exist_ok=True)
    proxy = cast(Any, proxy_settings(proxy_url)) if proxy_url else None

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(profile_path),
            headless=False,
            channel=channel,
            proxy=proxy,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
        )
        await context.add_cookies(cast(Any, cookies))
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(verify_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        html = await page.content()
        challenge = "доступ ограничен" in html.lower() or "hcaptcha" in html.lower()
        items = html.count('data-marker="item"')
        await context.close()
    return CookieCheck(ok=not challenge and items > 0, items=items, challenge=challenge)
