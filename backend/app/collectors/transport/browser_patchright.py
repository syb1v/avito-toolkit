import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from app.collectors.base import FetchedPage
from app.config import get_settings

logger = logging.getLogger(__name__)

CHALLENGE_MARKERS = (
    "доступ ограничен",
    "проверка безопасности",
    "проблема с ip",
)
ITEM_SELECTOR = "div[data-marker='item']"
SELECTOR_TIMEOUT_MS = 15000
CHALLENGE_RETRIES = 3
CHALLENGE_WAIT_SECONDS = 8.0
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
WARMUP_URL = "https://www.avito.ru/"
WARMUP_WAIT_SECONDS = 1.5


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

    Отличия от «чистого» Playwright, критичные для Авито:
    - полный Chromium (channel=chromium), а не headless-shell;
    - постоянный профиль (BROWSER_USER_DATA_DIR) с живыми cookies;
    - прогрев сессии заходом на главную;
    - никакой подмены User-Agent — соответствует реальному фингерпринту;
    - ожидание JS-челленджа с повторами и перезагрузкой.
    """

    name = "browser-patchright"

    def __init__(
        self,
        proxy: str | None = None,
        headless: bool | None = None,
        locale: str = "ru-RU",
        timeout_ms: int = 45000,
        block_resources: bool = True,
        user_data_dir: str | None = None,
        channel: str | None = None,
    ) -> None:
        settings = get_settings()
        self._proxy = proxy or (settings.proxy_url if settings.proxy_enabled else None)
        self._headless = settings.browser_headless if headless is None else headless
        self._user_data_dir = user_data_dir or settings.browser_user_data_dir or None
        self._channel = channel or settings.browser_channel or None
        self._locale = locale
        self._timeout_ms = timeout_ms
        self._block_resources = block_resources
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._warmed_up = False

    async def _ensure_context(self) -> Any:
        if self._context is not None:
            return self._context
        from patchright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launch_args = ["--disable-blink-features=AutomationControlled"]
        if get_settings().browser_no_sandbox:
            launch_args.append("--no-sandbox")

        launch_options: dict[str, Any] = {
            "headless": self._headless,
            "args": launch_args,
        }
        if self._channel:
            launch_options["channel"] = self._channel
        if self._proxy:
            launch_options["proxy"] = proxy_settings(self._proxy)

        context_options: dict[str, Any] = {
            "locale": self._locale,
            "timezone_id": "Europe/Moscow",
            "viewport": {"width": 1440, "height": 900},
        }
        if self._user_data_dir:
            self._context = await self._playwright.chromium.launch_persistent_context(
                self._user_data_dir,
                **launch_options,
                **context_options,
            )
        else:
            self._browser = await self._playwright.chromium.launch(**launch_options)
            self._context = await self._browser.new_context(**context_options)

        if self._block_resources:
            await self._context.route("**/*", self._block_route)
        return self._context

    @staticmethod
    async def _block_route(route: Any) -> None:
        if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    async def _warm_up(self, page: Any) -> None:
        try:
            await page.goto(WARMUP_URL, wait_until="domcontentloaded", timeout=self._timeout_ms)
            await asyncio.sleep(WARMUP_WAIT_SECONDS)
        except Exception as error:
            logger.debug("warmup failed: %s", error)
        self._warmed_up = True

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchedPage:
        context = await self._ensure_context()
        page = await context.new_page()
        try:
            if not self._warmed_up:
                await self._warm_up(page)
            return await self._load_with_retries(page, url)
        finally:
            await page.close()

    async def _safe_content(self, page: Any) -> str:
        for _ in range(2):
            try:
                return await page.content()
            except Exception:
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    await asyncio.sleep(1.0)
        try:
            return await page.content()
        except Exception as error:
            logger.warning("cannot read page content: %s", error)
            return ""

    async def _load_with_retries(self, page: Any, url: str) -> FetchedPage:
        for attempt in range(1, CHALLENGE_RETRIES + 1):
            status_code = 200
            try:
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=self._timeout_ms
                )
                if response is not None:
                    status_code = response.status
            except Exception as error:
                logger.warning(
                    "navigation issue at %s (attempt %s/%s): %s",
                    url,
                    attempt,
                    CHALLENGE_RETRIES,
                    error,
                )
            try:
                await page.wait_for_selector(ITEM_SELECTOR, timeout=SELECTOR_TIMEOUT_MS)
            except Exception:
                body = await self._safe_content(page)
                if not self._is_challenge(body) or attempt == CHALLENGE_RETRIES:
                    return FetchedPage(url=page.url, status_code=status_code, body=body)
                logger.info(
                    "antibot challenge at %s (attempt %s/%s), wait %.0fs",
                    url,
                    attempt,
                    CHALLENGE_RETRIES,
                    CHALLENGE_WAIT_SECONDS,
                )
                await asyncio.sleep(CHALLENGE_WAIT_SECONDS)
                continue
            await asyncio.sleep(0.5)
            body = await self._safe_content(page)
            return FetchedPage(url=page.url, status_code=status_code, body=body)
        body = await self._safe_content(page)
        return FetchedPage(url=page.url, status_code=200, body=body)

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
