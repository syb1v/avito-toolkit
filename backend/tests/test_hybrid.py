from pathlib import Path

from app.collectors.base import BotChallengeError, FetchedPage, RateLimitedError
from app.collectors.transport.hybrid import HybridTransport

FIXTURE = (Path(__file__).parent / "fixtures" / "min_search.html").read_text(encoding="utf-8")
EMPTY_SHELL = "<html><body><div id='root'>shell</div></body></html>"


class FakeTransport:
    name = "fake"

    def __init__(self, pages: list[str | Exception]) -> None:
        self._pages = list(pages)
        self.calls = 0

    async def fetch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        *,
        expect_items: bool = True,
    ) -> FetchedPage:
        self.calls += 1
        item = self._pages.pop(0) if self._pages else ""
        if isinstance(item, Exception):
            raise item
        return FetchedPage(url=url, status_code=200, body=item)

    async def close(self) -> None:
        return None


async def test_fallback_on_empty_primary() -> None:
    primary = FakeTransport([EMPTY_SHELL])
    fallback = FakeTransport([FIXTURE])
    transport = HybridTransport(primary, fallback)
    page = await transport.fetch("https://www.avito.ru/moskva?q=test")
    assert "iPhone" in page.body
    assert fallback.calls == 1


async def test_primary_used_when_items_present() -> None:
    primary = FakeTransport([FIXTURE])
    fallback = FakeTransport([FIXTURE])
    transport = HybridTransport(primary, fallback)
    page = await transport.fetch("https://www.avito.ru/moskva?q=test")
    assert "iPhone" in page.body
    assert fallback.calls == 0


async def test_fallback_on_bot_challenge() -> None:
    primary = FakeTransport([BotChallengeError("403")])
    fallback = FakeTransport([FIXTURE])
    transport = HybridTransport(primary, fallback)
    page = await transport.fetch("https://www.avito.ru/moskva?q=test")
    assert "iPhone" in page.body
    assert fallback.calls == 1


async def test_fallback_on_rate_limited() -> None:
    primary = FakeTransport([RateLimitedError("429")])
    fallback = FakeTransport([FIXTURE])
    transport = HybridTransport(primary, fallback)
    page = await transport.fetch("https://www.avito.ru/moskva?q=test")
    assert "iPhone" in page.body
    assert fallback.calls == 1


async def test_confirmed_primary_empty_page_stops_without_fallback() -> None:
    primary = FakeTransport([FIXTURE, EMPTY_SHELL])
    fallback = FakeTransport([FIXTURE])
    transport = HybridTransport(primary, fallback)
    await transport.fetch("https://www.avito.ru/moskva?q=test")
    page = await transport.fetch("https://www.avito.ru/moskva?q=test&p=2")
    assert "shell" in page.body
    assert fallback.calls == 0


async def test_reset_re_enables_fallback() -> None:
    primary = FakeTransport([FIXTURE, EMPTY_SHELL])
    fallback = FakeTransport([FIXTURE])
    transport = HybridTransport(primary, fallback)
    await transport.fetch("https://www.avito.ru/moskva?q=test")
    transport.reset()
    page = await transport.fetch("https://www.avito.ru/moskva?q=test")
    assert "iPhone" in page.body
    assert fallback.calls == 1
