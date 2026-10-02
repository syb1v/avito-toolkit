"""Фильтрация выдачи по ключевым словам товара (точность метрик).

Группы ключей: все группы должны совпасть (AND), внутри группы достаточно
одного варианта (OR). Нормализация: регистр, ё→е, диакритика (fēnix→fenix),
амперсанд (&), пробелы.
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence

TOKEN_CLEAN = re.compile(r"[^0-9a-zа-яё&+]+")

KeywordGroups = Sequence[Sequence[str]]


def normalize_text(value: str) -> str:
    lowered = value.lower().replace("ё", "е")
    decomposed = unicodedata.normalize("NFKD", lowered)
    without_diacritics = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = TOKEN_CLEAN.sub(" ", without_diacritics)
    return " ".join(cleaned.split())


def text_variants(value: str) -> set[str]:
    base = normalize_text(value)
    variants = {base}
    if "&" in base:
        variants.add(" ".join(base.replace("&", " ").split()))
    return {variant for variant in variants if variant}


def _token_sequence_contains(title_tokens: Sequence[str], alt_tokens: Sequence[str]) -> bool:
    if not alt_tokens or len(alt_tokens) > len(title_tokens):
        return False
    for index in range(len(title_tokens) - len(alt_tokens) + 1):
        if list(title_tokens[index : index + len(alt_tokens)]) == list(alt_tokens):
            return True
    return False


def _contains_any(title: str, alternatives: Sequence[str]) -> bool:
    title_token_variants = [tuple(variant.split()) for variant in text_variants(title)]
    for alternative in alternatives:
        alternative_variants = [tuple(variant.split()) for variant in text_variants(alternative)]
        if any(
            _token_sequence_contains(title_tokens, alt_tokens)
            for alt_tokens in alternative_variants
            for title_tokens in title_token_variants
        ):
            return True
    return False


def matches_keyword_groups(title: str, groups: KeywordGroups | None) -> bool:
    if not groups:
        return True
    return all(_contains_any(title, group) for group in groups)


def matches_exclude_keywords(title: str, excludes: Sequence[str] | None) -> bool:
    """True, если заголовок попал под стоп-слово (объявление исключается)."""
    if not excludes:
        return False
    return _contains_any(title, excludes)


def matches_search(
    title: str,
    groups: KeywordGroups | None,
    excludes: Sequence[str] | None = None,
) -> bool:
    """Итоговый фильтр поиска: include-группы (AND) и стоп-слова (NOT)."""
    if not matches_keyword_groups(title, groups):
        return False
    return not matches_exclude_keywords(title, excludes)


def keywords_from_params(params: Mapping[str, object] | None) -> list[list[str]]:
    if not isinstance(params, Mapping):
        return []
    raw_groups = params.get("keyword_groups")
    if not isinstance(raw_groups, list):
        return []
    groups: list[list[str]] = []
    for group in raw_groups:
        if isinstance(group, str):
            groups.append([group])
        elif isinstance(group, list):
            alternatives = [str(value) for value in group if str(value).strip()]
            if alternatives:
                groups.append(alternatives)
    return groups


def exclude_keywords_from_params(params: Mapping[str, object] | None) -> list[str]:
    if not isinstance(params, Mapping):
        return []
    raw = params.get("exclude_keywords")
    if isinstance(raw, str):
        raw = [chunk for chunk in re.split(r"[,\n;]+", raw)]
    if not isinstance(raw, list):
        return []
    return [str(value).strip() for value in raw if str(value).strip()]


def query_from_groups(groups: KeywordGroups, max_words: int = 4) -> str:
    words: list[str] = []
    for group in groups:
        if not group:
            continue
        best = max(group, key=len)
        words.extend(best.split()[: max(1, max_words - len(words))])
        if len(words) >= max_words:
            break
    return " ".join(words[:max_words])
