from app.services.search_filter import (
    exclude_keywords_from_params,
    first_matching_exclude,
    first_missing_group,
    keywords_from_params,
    matches_exclude_keywords,
    matches_keyword_groups,
    matches_search,
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


def test_exclude_keywords_filters_titles() -> None:
    groups = [["devialet"], ["dione"]]
    excludes = exclude_keywords_from_params({"exclude_keywords": ["чехол", "ремонт"]})
    assert excludes == ["чехол", "ремонт"]
    assert matches_search("Devialet Dione саундбар", groups, excludes) is True
    assert matches_search("Devialet Dione чехол для саундбара", groups, excludes) is False
    assert matches_exclude_keywords("Саундбар Devialet Dione, ремонт", excludes) is True
    assert matches_search("Samsung q990", groups, excludes) is False


def test_exclude_keywords_string_and_case() -> None:
    excludes = exclude_keywords_from_params({"exclude_keywords": "Копия, реплика; 1:1"})
    assert excludes == ["Копия", "реплика", "1:1"]
    assert matches_exclude_keywords("Копия Devialet Dione", excludes) is True
    assert matches_exclude_keywords("Devialet Dione", excludes) is False
    assert exclude_keywords_from_params(None) == []


def test_query_from_groups_prefers_longest_alternative() -> None:
    groups = [["b&o", "bang olufsen"], ["beplay"], ["eleven"]]
    assert query_from_groups(groups) == "bang olufsen beplay eleven"
    assert query_from_groups([["apple watch", "apple"], ["ultra"], ["4"]]) == (
        "apple watch ultra 4"
    )


def test_first_matching_exclude_and_missing_group() -> None:
    text = "Bang & Olufsen Beoplay Eleven Copper Tone"
    assert first_matching_exclude(text, ["б/у", "copper"]) == "copper"
    assert first_matching_exclude(text, ["б/у"]) is None
    groups = [["b&o", "bang olufsen"], ["beoplay"], ["natural aluminium"]]
    assert first_missing_group(text, groups) == ["natural aluminium"]
    assert first_missing_group("B&O Beoplay Eleven Natural Aluminium", groups) is None
