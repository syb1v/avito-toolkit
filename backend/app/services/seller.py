"""Фаза 6: правки своих объявлений через кабинет продавца (браузерная сессия).

Авито API для этого не подходит (нет управления чужими/своими объявлениями в
нужном объёме и требуется одобрение приложения), поэтому действуем в браузерном
профиле продавца: открываем страницу редактирования, меняем цену, сохраняем,
проверяем результат и делаем скриншот для аудита.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from app.config import get_settings

logger = logging.getLogger(__name__)

ITEM_ID_RE = re.compile(r"_(\d{6,})(?:\?|$)")
PRICE_SELECTORS = (
    "input[data-marker='price/input']",
    "input[name='price']",
    "input[inputmode='numeric']",
)
SAVE_SELECTORS = (
    "button[data-marker='submit-button']",
    "button:has-text('Сохранить')",
    "button:has-text('Применить')",
)
CHALLENGE_MARKERS = ("доступ ограничен", "проблема с ip", "hcaptcha", "войдите", "вход")


@dataclass(frozen=True, slots=True)
class EditOutcome:
    ok: bool
    mode: str
    message: str
    screenshot_path: str | None = None


def item_id_from_url(url: str | None) -> int | None:
    if not url:
        return None
    match = ITEM_ID_RE.search(url)
    if match:
        return int(match.group(1))
    tail = url.rstrip("/").split("/")[-1].split("?")[0]
    if tail.isdigit():
        return int(tail)
    return None


def build_edit_url(item_id: int) -> str:
    return get_settings().avito_edit_url_template.format(item_id=item_id)


async def _first_locator(page: Any, selectors: tuple[str, ...]) -> Any | None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() > 0:
                return locator
        except Exception:  # noqa: BLE001 — селектор может быть невалидным
            continue
    return None


def _is_challenge(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in CHALLENGE_MARKERS)


async def apply_price_edit(
    *,
    profile_dir: str,
    proxy_url: str | None,
    page_url: str,
    new_price: float,
    screenshot_dir: str,
    edit_id: str,
) -> EditOutcome:
    """Меняет цену объявления в кабинете продавца. Возвращает исход и скриншот."""
    from patchright.async_api import async_playwright

    from app.collectors.transport.browser_patchright import proxy_settings

    settings = get_settings()
    channel = settings.browser_channel or "chromium"
    Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    screenshot = str(Path(screenshot_dir) / f"{edit_id}.png")
    proxy = cast(Any, proxy_settings(proxy_url)) if proxy_url else None
    target_text = str(int(round(new_price)))

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            profile_dir,
            headless=settings.browser_headless,
            channel=channel,
            proxy=proxy,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2500)
            html = await page.content()
            if _is_challenge(html):
                await page.screenshot(path=screenshot, full_page=True)
                return EditOutcome(
                    ok=False,
                    mode="live",
                    message="Авито не пустил в кабинет (проверка/вход) — обновите cookies продавца",
                    screenshot_path=screenshot,
                )
            price_input = await _first_locator(page, PRICE_SELECTORS)
            if price_input is None:
                await page.screenshot(path=screenshot, full_page=True)
                return EditOutcome(
                    ok=False,
                    mode="live",
                    message="не нашёл поле цены (нужна актуализация селекторов)",
                    screenshot_path=screenshot,
                )
            await price_input.fill(target_text)
            await page.wait_for_timeout(500)
            save = await _first_locator(page, SAVE_SELECTORS)
            if save is None:
                await page.screenshot(path=screenshot, full_page=True)
                return EditOutcome(
                    ok=False,
                    mode="live",
                    message="не нашёл кнопку сохранения (нужна актуализация селекторов)",
                    screenshot_path=screenshot,
                )
            await save.click()
            await page.wait_for_timeout(4000)
            # проверяем результат: перезагружаем и сверяем значение поля
            await page.reload(wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            check_input = await _first_locator(page, PRICE_SELECTORS)
            actual = ""
            if check_input is not None:
                try:
                    actual = (await check_input.input_value()).strip()
                except Exception:  # noqa: BLE001
                    actual = ""
            await page.screenshot(path=screenshot, full_page=True)
            if actual and actual.replace(" ", "") != target_text:
                return EditOutcome(
                    ok=False,
                    mode="live",
                    message=f"после сохранения цена «{actual}», ожидали «{target_text}»",
                    screenshot_path=screenshot,
                )
            return EditOutcome(
                ok=True,
                mode="live",
                message=f"цена обновлена на {target_text} ₽",
                screenshot_path=screenshot,
            )
        finally:
            await context.close()
