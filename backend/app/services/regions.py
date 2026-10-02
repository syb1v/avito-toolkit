"""Города/регионы Авито: извлечение из URL, нормализация фильтров, подмена города."""

import re
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from app.services.accounts import transliterate

NON_REGION_SEGMENTS = {"user", "brands", "catalog", "web", "profile"}


def normalize_region(value: str) -> str:
    """Slug региона: «Санкт-Петербург» → sankt-peterburg, как в URL Авито."""
    return transliterate(value)


def region_from_url(url: str | None) -> str | None:
    """Первый сегмент пути объявления Авито: /moskva/... → moskva."""
    if not url:
        return None
    parts = urlsplit(url)
    if "avito" not in parts.netloc:
        return None
    for segment in parts.path.split("/"):
        slug = normalize_region(segment)
        if not slug:
            continue
        if slug in NON_REGION_SEGMENTS:
            return None
        return slug
    return None


def regions_from_params(params: Mapping[str, object] | None) -> list[str]:
    return _list_from_params(params, "regions")


def exclude_regions_from_params(params: Mapping[str, object] | None) -> list[str]:
    return _list_from_params(params, "exclude_regions")


def _list_from_params(params: Mapping[str, object] | None, key: str) -> list[str]:
    if not isinstance(params, Mapping):
        return []
    raw = params.get(key)
    if isinstance(raw, str):
        raw = re.split(r"[,\n;]+", raw)
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for value in raw:
        slug = normalize_region(str(value))
        if slug and slug not in result:
            result.append(slug)
    return result


def matches_region(
    region: str | None,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
) -> bool:
    """True, если регион объявления проходит include- и exclude-фильтры."""
    normalized = normalize_region(region or "")
    include_set = {normalize_region(value) for value in (include or []) if value}
    exclude_set = {normalize_region(value) for value in (exclude or []) if value}
    if include_set and normalized not in include_set:
        return False
    return not (exclude_set and normalized in exclude_set)


def with_city(url: str, city: str | None) -> str:
    """Подменяет регион в поисковом URL Авито (…/all?q=… → …/moskva?q=…).

    Профили/бренды не трогаем: подмена только у URL с поисковым запросом ``q``.
    """
    slug = normalize_region(city or "")
    if not slug:
        return url
    parts = urlsplit(url)
    if "avito" not in parts.netloc:
        return url
    query = parse_qs(parts.query, keep_blank_values=True)
    if "q" not in query:
        return url
    segments = [segment for segment in parts.path.split("/") if segment]
    if segments and normalize_region(segments[0]) not in NON_REGION_SEGMENTS:
        segments[0] = slug
    else:
        segments.insert(0, slug)
    path = "/" + "/".join(segments)
    return urlunsplit(
        (parts.scheme, parts.netloc, path, urlencode(query, doseq=True), parts.fragment)
    )
