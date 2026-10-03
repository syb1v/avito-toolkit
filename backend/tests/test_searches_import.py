from app.services.searches import (
    DEFAULT_CRON,
    DEFAULT_PRIORITY,
    merge_params,
    normalize_search_rows,
)


def test_normalize_applies_defaults() -> None:
    rows, skipped = normalize_search_rows(
        [
            {"name": "iPhone 15 Москва", "url": "https://www.avito.ru/moskva?q=iphone+15"},
            {
                "name": "Профиль конкурента",
                "url": "https://www.avito.ru/user/123/profile",
                "schedule_cron": "0 * * * *",
                "priority": "5",
            },
        ]
    )
    assert skipped == 0
    assert rows[0].schedule_cron == DEFAULT_CRON
    assert rows[0].priority == DEFAULT_PRIORITY
    assert rows[1].schedule_cron == "0 * * * *"
    assert rows[1].priority == 5


def test_normalize_skips_rows_without_name_or_url() -> None:
    rows, skipped = normalize_search_rows(
        [
            {"name": "", "url": "https://a"},
            {"name": "Без URL", "url": "   "},
            {"name": "Ок", "url": "https://ok"},
        ]
    )
    assert skipped == 2
    assert [row.name for row in rows] == ["Ок"]


def test_merge_params_keeps_untouched_keys() -> None:
    existing = {"keyword_groups": [["devialet"]], "max_pages": 5}
    merged = merge_params(existing, {"max_age_days": 7, "max_pages": 3})
    assert merged == {"keyword_groups": [["devialet"]], "max_pages": 3, "max_age_days": 7}
    assert merge_params(existing, {"keyword_groups": None}) == {"max_pages": 5}
    assert merge_params(None, {"a": 1}) == {"a": 1}
