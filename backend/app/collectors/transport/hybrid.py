from app.collectors.base import (
    BotChallengeError,
    FetchedPage,
    RateLimitedError,
    SourceAdapter,
)
from app.collectors.web.parsing import parse_search_page


class HybridTransport:
    """Level 1 (HTTP) с автоматическим фолбэком на Level 2 (браузер).

    Браузер подключается, если HTTP-транспорт получил антибот-челлендж
    либо вернул страницу без объявлений (SSR-оболочка) настолько, насколько
    HTTP ещё не подтвердил работоспособность в рамках текущего обхода.
    """

    name = "hybrid"

    def __init__(self, primary: SourceAdapter, fallback: SourceAdapter) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_confirmed = False

    def reset(self) -> None:
        """Сброс состояния перед новым обходом."""
        self._primary_confirmed = False

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchedPage:
        page: FetchedPage | None = None
        try:
            page = await self._primary.fetch(url, headers=headers)
        except (BotChallengeError, RateLimitedError):
            page = None
        if page is not None:
            if _has_items(page):
                self._primary_confirmed = True
                return page
            if self._primary_confirmed:
                return page
        return await self._fallback.fetch(url)

    async def close(self) -> None:
        await self._primary.close()
        await self._fallback.close()


def _has_items(page: FetchedPage) -> bool:
    return bool(parse_search_page(page.body, base_url=page.url))
