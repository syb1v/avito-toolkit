import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from app.collectors.base import FetchedPage
from app.config import get_settings

logger = logging.getLogger(__name__)

CHALLENGE_MARKERS = ("доступ ограничен", "проверка безопасности")
ITEM_SELECTOR = "div[data-marker='item']"
CHALLENGE_RETRIES = 2
CHALLENGE_WAIT_SECONDS = 6.0
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


def proxy_settings(proxy_url: str) -> dict[str, str]:
    parsed = urlparse(proxy_url)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server = f"{server}:{parsed.port}"
    settings = {"server": server}
    if parsed.username:
        settings["username"] = parsed.username
    if parsed.password:
        settings["password"] = parsed.password
    return settings


class BrowserTransport:
    """Level 2: рендер через Patchright (undetected Chromium).

    Используется как fallback, когда HTTP-выдача пуста или встречает
    JS-челлендж. Реализация patchright импортируется лениво, чтобы пакет
    не был обязательным для базового HTTP-сбора.
    """

    name = "browser-patchright"

    def __init__(
        self,
        proxy: str | None = None,
        headless: bool = True,
        locale: str = "ru-RU",
        timeout_ms: int = 45000,
        block_resources: bool = True,
    ) -> None:
        settings = get_settings()
        self._proxy = proxy or (settings.proxy_url if settings.proxy_enabled else None)
        self._headless = headless
        self._locale = locale
        self._timeout_ms = timeout_ms
        self._block_resources = block_resources
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None

    async def _ensure_context(self) -> Any:
        if self._context is not None:
            return self._context
        from patchright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launch_options: dict[str, Any] = {
            "headless": self._headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if self._proxy:
            launch_options["proxy"] = proxy_settings(self._proxy)
        self._browser = await self._playwright.chromium.launch(**launch_options)
        self._context = await self._browser.new_context(
            locale=self._locale,
            timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
            ),
        )
        if self._block_resources:
            await self._context.route("**/*", self._block_route)
        return self._context

    @staticmethod
    async def _block_route(route: Any) -> None:
        if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchedPage:
        context = await self._ensure_context()
        page = await context.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            status_code = response.status if response is not None else 200
            for attempt in range(CHALLENGE_RETRIES + 1):
                try:
                    await page.wait_for_selector(ITEM_SELECTOR, timeout=self._timeout_ms)
                    break
                except Exception:
                    body = await page.content()
                    if not self._is_challenge(body) or attempt == CHALLENGE_RETRIES:
                        break
                    logger.info("browser challenge detected, waiting %.0fs", CHALLENGE_WAIT_SECONDS)
                    await asyncio.sleep(CHALLENGE_WAIT_SECONDS)
            body = await page.content()
            return FetchedPage(url=page.url, status_code=status_code, body=body)
        finally:
            await page.close()

    @staticmethod
    def _is_challenge(body: str) -> bool:
        lowered = body.lower()
        return any(marker in lowered for marker in CHALLENGE_MARKERS)

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
