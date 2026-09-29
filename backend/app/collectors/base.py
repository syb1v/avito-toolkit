from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class CollectorError(RuntimeError):
    pass


class BotChallengeError(CollectorError):
    """Источник вернул антибот-челлендж (Qrator, GeeTest, 403)."""


class RateLimitedError(CollectorError):
    """Источник ограничил частоту запросов (429)."""


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    status_code: int
    body: str


@runtime_checkable
class SourceAdapter(Protocol):
    """Единый интерфейс источника данных.

    Реализации: HTTP с TLS-эмуляцией (Level 1), браузерные (Level 2),
    официальный Avito API (контур A).
    """

    name: str

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchedPage: ...

    async def close(self) -> None: ...
