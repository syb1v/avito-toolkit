import asyncio
import contextlib
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.collectors.base import (
    BotChallengeError,
    CollectorError,
    FetchedPage,
    RateLimitedError,
)
from app.config import get_settings
from app.services.proxy_pool import ProxyEntry, ProxyPool

logger = logging.getLogger(__name__)

CHALLENGE_MARKERS = (
    "доступ ограничен",
    "проверка безопасности",
    "проблема с ip",
    "firewallcaptcha",
    "hcaptcha",
)
NETWORK_ERROR_MARKERS = (
    "err_proxy_connection_failed",
    "err_tunnel_connection_failed",
    "err_connection",
    "err_timed_out",
    "err_name_not_resolved",
    "this site can’t be reached",
    "нет доступа к сайту",
)
NETWORK_ERROR_STATUS = 599
ITEM_SELECTOR = "div[data-marker='item']"
SELECTOR_TIMEOUT_MS = 15000
CHALLENGE_RETRIES = 3
CHALLENGE_WAIT_SECONDS = 8.0
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
WARMUP_URL = "https://www.avito.ru/"
WARMUP_WAIT_SECONDS = 2.5
RATE_LIMIT_STATUSES = (429, 439)
SINGLETON_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def _clear_singleton_files(user_data_dir: str) -> None:
    """Убирает stale-lock Chromium, оставшийся после падения прошлого запуска."""
    base = Path(user_data_dir)
    if not base.exists():
        return
    for pattern in SINGLETON_FILES:
        for path in base.glob(pattern):
            try:
                if path.is_symlink() or path.is_file():
                    path.unlink()
            except OSError:
                continue


@dataclass(frozen=True, slots=True)
class _PageOutcome:
    page: FetchedPage
    challenge: bool
    rate_limited: bool = False
    network_error: bool = False


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
        block_resources: bool | None = None,
        user_data_dir: str | None = None,
        channel: str | None = None,
        proxy_pool: ProxyPool | None = None,
    ) -> None:
        settings = get_settings()
        self._proxy_pool = proxy_pool
        self._current_entry: ProxyEntry | None = None
        self._proxy = proxy or (settings.proxy_url if settings.proxy_enabled else None)
        self._headless = settings.browser_headless if headless is None else headless
        self._user_data_dir = user_data_dir or settings.browser_user_data_dir or None
        self._channel = channel or settings.browser_channel or None
        self._locale = locale
        self._timeout_ms = timeout_ms
        self._block_resources = (
            settings.browser_block_resources if block_resources is None else block_resources
        )
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._warmed_up = False

    async def _ensure_context(self) -> Any:
        if self._context is not None:
            return self._context
        if self._proxy_pool is not None:
            self._current_entry = await self._proxy_pool.next()
            self._proxy = self._current_entry.url
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
            _clear_singleton_files(self._user_data_dir)
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

    async def fetch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        *,
        expect_items: bool = True,
    ) -> FetchedPage:
        for attempt in range(1, CHALLENGE_RETRIES + 1):
            context = await self._ensure_context()
            page = await context.new_page()
            try:
                if not self._warmed_up:
                    await self._warm_up(page)
                outcome = await self._load_once(page, url, expect_items=expect_items)
            finally:
                with contextlib.suppress(Exception):
                    await page.close()
            if outcome.rate_limited:
                await self._report_antibot("rate limited")
                raise RateLimitedError(f"rate limited at {url} ({outcome.page.status_code})")
            if outcome.network_error:
                await self._report_failure("network error")
                if self._proxy_pool is not None and attempt < CHALLENGE_RETRIES:
                    await self._rotate_proxy()
                    continue
                raise CollectorError(f"network error at {url}")
            if not outcome.challenge:
                await self._report_success()
                return outcome.page
            await self._report_antibot("antibot challenge")
            logger.info(
                "antibot challenge at %s (attempt %s/%s)",
                url,
                attempt,
                CHALLENGE_RETRIES,
            )
            if attempt == CHALLENGE_RETRIES:
                raise BotChallengeError(f"antibot challenge at {url}")
            if self._proxy_pool is not None:
                await self._rotate_proxy()
            else:
                await asyncio.sleep(CHALLENGE_WAIT_SECONDS)
        raise BotChallengeError(f"antibot challenge at {url}")

    async def _load_once(self, page: Any, url: str, *, expect_items: bool = True) -> "_PageOutcome":
        status_code = 200
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            if response is not None:
                status_code = response.status
        except Exception as error:
            logger.warning("navigation issue at %s: %s", url, error)
        if status_code in RATE_LIMIT_STATUSES:
            body = await self._safe_content(page)
            logger.warning("rate limited at %s: HTTP %s", url, status_code)
            return _PageOutcome(
                page=FetchedPage(url=page.url, status_code=status_code, body=body),
                challenge=True,
                rate_limited=True,
            )
        if not expect_items:
            # Страницы объявлений (описания): карточек выдачи тут нет — не ждём их.
            await asyncio.sleep(0.4)
            body = await self._safe_content(page)
            return _PageOutcome(
                page=FetchedPage(url=page.url, status_code=status_code, body=body),
                challenge=self._is_challenge(body),
            )
        try:
            await page.wait_for_selector(ITEM_SELECTOR, timeout=SELECTOR_TIMEOUT_MS)
        except Exception:
            body = await self._safe_content(page)
            if self._is_network_error(body):
                logger.warning("network/proxy error page at %s", url)
                return _PageOutcome(
                    page=FetchedPage(url=page.url, status_code=NETWORK_ERROR_STATUS, body=body),
                    challenge=False,
                    network_error=True,
                )
            return _PageOutcome(
                page=FetchedPage(url=page.url, status_code=status_code, body=body),
                challenge=self._is_challenge(body),
            )
        await asyncio.sleep(0.5)
        if get_settings().browser_humanize:
            await self._humanize(page)
        body = await self._safe_content(page)
        return _PageOutcome(
            page=FetchedPage(url=page.url, status_code=status_code, body=body),
            challenge=self._is_challenge(body),
        )

    @staticmethod
    async def _humanize(page: Any) -> None:
        """Лёгкая имитация человека: движение мыши и прокрутка перед чтением."""
        with contextlib.suppress(Exception):
            await page.mouse.move(
                random.uniform(150, 1200),
                random.uniform(150, 600),
                steps=random.randint(5, 15),
            )
            await page.mouse.wheel(0, random.randint(200, 700))
            await asyncio.sleep(random.uniform(0.4, 1.2))
            await page.mouse.wheel(0, -random.randint(50, 200))

    async def _rotate_proxy(self) -> bool:
        if self._proxy_pool is None:
            return False
        await self._close_context()
        self._warmed_up = False
        self._current_entry = None
        return True

    async def _report_success(self) -> None:
        if self._proxy_pool is not None and self._current_entry is not None:
            await self._proxy_pool.report_success(self._current_entry, avito=True)

    async def _report_failure(self, error: str) -> None:
        if self._proxy_pool is not None and self._current_entry is not None:
            await self._proxy_pool.report_failure(self._current_entry, error)

    async def _report_antibot(self, error: str) -> None:
        """Челлендж Авито — не поломка прокси: не отправляем его в кулдаун."""
        if self._proxy_pool is not None and self._current_entry is not None:
            await self._proxy_pool.report_antibot(self._current_entry, error)

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

    @staticmethod
    def _is_challenge(body: str) -> bool:
        lowered = body.lower()
        return any(marker in lowered for marker in CHALLENGE_MARKERS)

    @staticmethod
    def _is_network_error(body: str) -> bool:
        lowered = body.lower()
        return any(marker in lowered for marker in NETWORK_ERROR_MARKERS)

    async def _close_context(self) -> None:
        if self._context is not None:
            with contextlib.suppress(Exception):
                await self._context.close()
            self._context = None
        if self._browser is not None:
            with contextlib.suppress(Exception):
                await self._browser.close()
            self._browser = None

    async def close(self) -> None:
        await self._close_context()
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
