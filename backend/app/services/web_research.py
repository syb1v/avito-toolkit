"""Source-backed product research.

This service intentionally does not turn an LLM answer into evidence. A claim
is verifiable only when a provider returns a URL and source metadata.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import quote

import httpx


@dataclass(frozen=True, slots=True)
class ResearchSource:
    url: str
    title: str
    retrieved_at: datetime
    claims: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearchResult:
    query: str
    sources: tuple[ResearchSource, ...]
    status: str


class _ResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("class") == "result__a":
            self._href = values.get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            title = " ".join("".join(self._text).split())
            if self._href and title:
                self.results.append((self._href, title))
            self._href = None
            self._text = []


def validate_source(url: str, title: str, claims: list[str]) -> ResearchSource:
    if not url.startswith(("https://", "http://")):
        raise ValueError("source URL must be absolute")
    if not title.strip():
        raise ValueError("source title is required")
    if not claims:
        raise ValueError("source must support at least one claim")
    return ResearchSource(url, title.strip(), datetime.now(UTC), tuple(claims))


async def research_product_identity(query: str) -> ResearchResult:
    """Fetch a small source set from the configured provider.

    The current low-dependency provider uses DuckDuckGo HTML search and keeps
    result snippets as leads only. No snippet is promoted to a verified claim;
    callers must pass claims through an explicit source/LLM verification step.
    """
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "avito-toolkit-research/1.0"})
            response.raise_for_status()
    except httpx.HTTPError:
        return ResearchResult(query, (), "needs_review")
    parser = _ResultParser()
    parser.feed(response.text)
    sources = tuple(
        validate_source(url, title, ["search result requires verification"])
        for url, title in parser.results[:5]
        if url.startswith(("https://", "http://"))
    )
    if not sources:
        return ResearchResult(query, (), "needs_review")
    return ResearchResult(query, sources, "sources_found")
