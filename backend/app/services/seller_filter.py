"""Целевые и исключаемые продавцы в параметрах поиска (ссылки или имена)."""

import re
from collections.abc import Mapping, Sequence

TARGET_KEY = "target_sellers"
EXCLUDE_KEY = "exclude_sellers"
MAX_REFS = 200


def seller_refs_from_params(params: Mapping[str, object] | None, key: str) -> list[str]:
    if not isinstance(params, Mapping):
        return []
    raw = params.get(key)
    if not isinstance(raw, list):
        return []
    refs = [str(value).strip() for value in raw if str(value).strip()]
    return refs[:MAX_REFS]


def is_url_ref(ref: str) -> bool:
    value = ref.strip().lower()
    return "://" in value or value.startswith("avito.ru") or "/user/" in value


def ref_matches_seller(
    ref: str, *, name: str | None, url: str | None, seller_id: int | None = None
) -> bool:
    """Совпадение ссылки/имени/ID из настроек поиска с продавцом объявления."""
    value = ref.strip().lower()
    if not value:
        return False
    if value.isdigit() and seller_id is not None and int(value) == seller_id:
        return True
    normalized_name = (name or "").lower().replace("ё", "е")
    if is_url_ref(value):
        link = value if "://" in value else f"https://{value}"
        link = link.split("?")[0].rstrip("/")
        if url:
            listing_url = url.lower().split("?")[0].rstrip("/")
            if listing_url == link:
                return True
            if "/user/" in link:
                tail = link.split("/user/", 1)[1].split("/", 1)[0]
            elif "/brands/" in link:
                tail = link.split("/brands/", 1)[1].split("/", 1)[0]
            else:
                tail = link.rstrip("/").rsplit("/", 1)[-1]
            if tail and len(tail) >= 6 and tail in listing_url:
                return True
        return False
    if re.fullmatch(r"[0-9a-f]{8,}", value) and url and value in url.lower():
        return True
    if not normalized_name:
        return False
    ref_name = value.replace("ё", "е")
    return ref_name in normalized_name or normalized_name in ref_name


def seller_filter_reason(
    *,
    name: str | None,
    url: str | None,
    target_refs: Sequence[str],
    exclude_refs: Sequence[str],
    seller_id: int | None = None,
) -> str | None:
    """None — продавец проходит; иначе 'excluded' или 'not_target'."""
    if exclude_refs and any(
        ref_matches_seller(ref, name=name, url=url, seller_id=seller_id)
        for ref in exclude_refs
    ):
        return "excluded"
    if target_refs and not any(
        ref_matches_seller(ref, name=name, url=url, seller_id=seller_id)
        for ref in target_refs
    ):
        return "not_target"
    return None
