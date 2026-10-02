import itertools
from typing import Any

from app.services.collector import SearchCollector

BASE = "https://www.avito.ru/all?q=test"


def _collector(max_pages: int | None) -> SearchCollector:
    return SearchCollector(None, None, max_pages=max_pages)  # type: ignore[arg-type]


def test_unlimited_pages_yield_forever() -> None:
    urls = list(itertools.islice(_collector(0)._page_urls(BASE), 4))
    assert urls[0] == BASE
    assert urls[1] == f"{BASE}&p=2"
    assert urls[2] == f"{BASE}&p=3"
    assert urls[3] == f"{BASE}&p=4"


def test_limited_pages_stop_at_max() -> None:
    urls = list(_collector(3)._page_urls(BASE))
    assert urls == [BASE, f"{BASE}&p=2", f"{BASE}&p=3"]


def test_separator_picks_question_mark_when_missing() -> None:
    collector: Any = _collector(2)
    urls = list(collector._page_urls("https://www.avito.ru/all"))
    assert urls == ["https://www.avito.ru/all", "https://www.avito.ru/all?p=2"]
