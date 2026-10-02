from app.ai.prompts import build_moderation_prompt
from app.services.moderation import (
    CATEGORY_COPY,
    CATEGORY_FAKE_BAIT,
    CATEGORY_IRRELEVANT,
    detect_clusters,
    evaluate_listing,
    normalize_title,
)


def test_normalize_title() -> None:
    assert normalize_title("iPhone 15, 128 ГБ!") == "iphone 15 128 гб"
    assert normalize_title("  КОПИЯ   iPhone_15 ") == "копия iphone 15"


def test_copy_word_flagged() -> None:
    verdict = evaluate_listing("iPhone 15 копия 1:1", None, 40000, 80000, 0)
    assert verdict.flagged is True
    assert verdict.category == CATEGORY_COPY
    assert any("копия" in reason for reason in verdict.reasons)


def test_description_copy_detected() -> None:
    verdict = evaluate_listing(
        "iPhone 15 256",
        "Продаю реплику, качество люкс, полный аналог оригинала",
        40000,
        80000,
        0,
    )
    assert verdict.flagged is True
    assert verdict.category == CATEGORY_COPY


def test_junk_word_flagged_as_irrelevant() -> None:
    verdict = evaluate_listing("iPhone 15 на запчасти", None, 40000, 80000, 0)
    assert verdict.flagged is True
    assert verdict.category == CATEGORY_IRRELEVANT
    assert any("запчаст" in reason for reason in verdict.reasons)


def test_description_defect_detected() -> None:
    verdict = evaluate_listing(
        "iPhone 15 256",
        "Проблема с чипами WiFi, не работает Face ID",
        45000,
        80000,
        0,
    )
    assert verdict.flagged is True
    assert verdict.category == CATEGORY_IRRELEVANT


def test_low_price_flagged_as_bait() -> None:
    verdict = evaluate_listing("iPhone 15 128", None, 20000, 80000, 0)
    assert verdict.flagged is True
    assert verdict.category == CATEGORY_FAKE_BAIT
    assert any("ниже 35% медианы" in reason for reason in verdict.reasons)


def test_bait_phrase_flagged() -> None:
    verdict = evaluate_listing(
        "iPhone 15 256", "ТОРГ!! ПРЕДЛОГАТЬ ЦЕНУ ЦЕНА НЕ 6 ТЫСЯЧ", 45000, 80000, 0
    )
    assert verdict.flagged is True
    assert verdict.category == CATEGORY_FAKE_BAIT


def test_soft_words_alone_not_flagged() -> None:
    verdict = evaluate_listing("iPhone 15, торг, срочно", None, 75000, 80000, 0)
    assert verdict.flagged is False
    assert verdict.category is None
    assert any("маркетинг" in reason for reason in verdict.reasons)


def test_cluster_requires_same_price_and_sellers() -> None:
    rows = [
        (1, "iPhone 15 128", 40000.0, 10),
        (2, "iphone 15, 128", 40000.0, 11),
        (3, "IPHONE 15 128!", 40000.0, 12),
        (4, "iPhone 15 256", 50000.0, 13),
        (5, "iPhone 15 128", 41000.0, 10),
    ]
    clusters = detect_clusters(rows)
    assert clusters == {1: 3, 2: 3, 3: 3}

    verdict = evaluate_listing("iPhone 15 128", None, 40000, 40000, 3, duplicate_min_cluster=3)
    assert verdict.flagged is True
    assert verdict.category == "duplicate"
    assert any("дубли" in reason for reason in verdict.reasons)


def test_moderation_prompt_lists_items_with_descriptions() -> None:
    prompt = build_moderation_prompt(
        query="iPhone 15 Москва",
        median=35000.0,
        items=[
            (111, "iPhone 15 копия", 15000.0, "полный аналог"),
            (222, "iPhone 15 128", 40000.0, None),
        ],
    )
    assert "iPhone 15 Москва" in prompt
    assert "111" in prompt and "222" in prompt
    assert "полный аналог" in prompt
    assert "35000" in prompt
