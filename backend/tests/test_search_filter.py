from app.services.search_filter import (
    keywords_from_params,
    matches_keyword_groups,
    normalize_text,
    query_from_groups,
)


def test_normalize_text_strips_diacritics_and_case() -> None:
    assert normalize_text("Garmin fēnix 9 Pro") == "garmin fenix 9 pro"
    assert normalize_text("Devialet Phantom Ultimate 108 dB") == "devialet phantom ultimate 108 db"


def test_matches_bang_olufsen_variants() -> None:
    groups = [["b&o", "bang olufsen"], ["beplay", "beoplay"], ["eleven"]]
    assert matches_keyword_groups("B&O Beoplay Eleven", groups) is True
    assert matches_keyword_groups("Bang & Olufsen Beoplay Eleven", groups) is True
    assert matches_keyword_groups("Bang & Olufsen Beoplay A1", groups) is False


def test_matches_garmin_with_diacritics() -> None:
    groups = [["garmin"], ["fenix", "fēnix"], ["9", "9 pro"]]
    assert matches_keyword_groups("Garmin fēnix 9 Pro 47 mm", groups) is True
    assert matches_keyword_groups("Garmin fenix 9X Pro", groups) is False


def test_empty_groups_match_everything() -> None:
    assert matches_keyword_groups("iPhone 15", []) is True
    assert matches_keyword_groups("iPhone 15", None) is True


def test_keywords_from_params() -> None:
    params = {"keyword_groups": [["devialet"], ["mania"], "phantom"]}
    assert keywords_from_params(params) == [["devialet"], ["mania"], ["phantom"]]
    assert keywords_from_params(None) == []
    assert keywords_from_params({"keyword_groups": "broken"}) == []


def test_query_from_groups_prefers_longest_alternative() -> None:
    groups = [["b&o", "bang olufsen"], ["beplay"], ["eleven"]]
    assert query_from_groups(groups) == "bang olufsen beplay eleven"
    assert query_from_groups([["apple watch", "apple"], ["ultra"], ["4"]]) == (
        "apple watch ultra 4"
    )
