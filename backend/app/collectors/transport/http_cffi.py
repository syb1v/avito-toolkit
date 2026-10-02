from typing import Any

from app.collectors.base import (
    BotChallengeError,
    FetchedPage,
    RateLimitedError,
)
from app.config import get_settings
from app.services.proxy_pool import ProxyEntry, ProxyPool

DEFAULT_TIMEOUT_SECONDS = 30


class HttpCffiTransport:
    """Level 1: быстрый HTTP-транспорт с TLS/JA3/JA4-эмуляцией (curl_cffi).

    Поддерживает пул прокси: перед запросом берёт следующий прокси по ротации;
    при смене прокси сессия пересоздаётся. Ошибки/челленджи помечают прокси
    в пуле, чтобы он ушёл в кулдаун.
    """

    name = "http-cffi"

    def __init__(
        self,
        impersonate: str = "chrome",
        proxy: str | None = None,
        proxy_pool: ProxyPool | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        settings = get_settings()
        self._impersonate = impersonate
        self._proxy_pool = proxy_pool
        self._proxy = proxy or (settings.proxy_url if settings.proxy_enabled else None)
        self._timeout = timeout
        self._session: Any | None = None
        self._last_entry: ProxyEntry | None = None

    async def _get_session(self) -> Any:
        if self._proxy_pool is not None:
            entry = await self._proxy_pool.next()
            self._last_entry = entry
            if entry.url != self._proxy:
                await self._drop_session()
                self._proxy = entry.url
        if self._session is None:
            from curl_cffi.requests import AsyncSession

            self._session = AsyncSession(
                impersonate=self._impersonate,
                proxy=self._proxy,
                timeout=self._timeout,
            )
        return self._session

    async def _drop_session(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchedPage:
        try:
            session = await self._get_session()
            response = await session.get(url, headers=headers)
        except Exception as error:
            if self._proxy_pool is not None and self._last_entry is not None:
                await self._proxy_pool.report_failure(
                    self._last_entry, f"{type(error).__name__}: {error}"
                )
            raise
        if response.status_code in (401, 403):
            await self._report_failure(f"HTTP {response.status_code}")
            raise BotChallengeError(f"anti-bot challenge at {url}: {response.status_code}")
        if response.status_code == 429:
            await self._report_failure("HTTP 429")
            raise RateLimitedError(f"rate limited at {url}")
        if self._proxy_pool is not None and self._last_entry is not None:
            await self._proxy_pool.report_success(self._last_entry)
        return FetchedPage(
            url=str(response.url),
            status_code=response.status_code,
            body=response.text,
        )

    async def _report_failure(self, error: str) -> None:
        if self._proxy_pool is not None and self._last_entry is not None:
            await self._proxy_pool.report_failure(self._last_entry, error)

    async def close(self) -> None:
        await self._drop_session()
