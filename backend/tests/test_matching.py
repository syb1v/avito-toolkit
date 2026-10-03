import pytest

from app.services.matching import (
    MatchCandidate,
    compute_market_position,
    rank_candidates,
)

CANDIDATES = [
    MatchCandidate(1, "iPhone 15 128 GB", 75000.0),
    MatchCandidate(2, "iPhone 14 Pro 256 GB", 62500.0),
    MatchCandidate(3, "Samsung Galaxy S23", 45990.0),
    MatchCandidate(4, "iPhone 15 256 GB запечатанный", 82000.0),
]


def test_rank_candidates_finds_similar_titles() -> None:
    ranked = rank_candidates("iPhone 15 128 ГБ", CANDIDATES, min_score=60, limit=3)
    ids = [item.candidate.listing_id for item in ranked]
    assert ids[0] == 1
    assert 3 not in ids
    assert ranked[0].score > ranked[-1].score if len(ranked) > 1 else True


def test_rank_candidates_respects_threshold() -> None:
    ranked = rank_candidates("Samsung Galaxy S23", CANDIDATES, min_score=90, limit=5)
    assert [item.candidate.listing_id for item in ranked] == [3]


def test_rank_candidates_empty() -> None:
    assert rank_candidates("iPhone", [], min_score=60) == []


def test_rank_candidates_rejects_model_and_capacity_variants() -> None:
    problem = [
        MatchCandidate(10, "iPhone 15 Pro, 256 ГБ", 49000.0),
        MatchCandidate(11, "iPhone 15 Plus, 256 ГБ", 41000.0),
        MatchCandidate(12, "iPhone 15, 512 ГБ", 47000.0),
        MatchCandidate(13, "iPhone 15, 256 ГБ", 38000.0),
        MatchCandidate(14, "iPhone 15 Pro Max, 256 ГБ", 57000.0),
    ]
    ranked = rank_candidates("iPhone 15 256 ГБ", problem, min_score=60, limit=10)
    assert [item.candidate.listing_id for item in ranked] == [13]


def test_rank_candidates_rejects_other_series() -> None:
    candidates = [
        MatchCandidate(20, "Apple Watch Ultra 2 49mm", 50000.0),
        MatchCandidate(21, "Apple Watch Ultra 4 49mm", 70000.0),
    ]
    ranked = rank_candidates("Apple Watch Ultra 4", candidates, min_score=60, limit=10)
    assert [item.candidate.listing_id for item in ranked] == [21]


def test_market_position_with_outlier() -> None:
    position = compute_market_position(70000.0, [50000, 60000, 65000, 70000, 1000000])
    assert position.stats is not None
    assert position.matched_count == 5
    assert position.stats.count == 4
    assert position.stats.median == pytest.approx(62500.0)
    assert position.cheaper_share == pytest.approx(3 / 5)
    assert position.delta_to_median_pct == pytest.approx(70000 / 62500 * 100 - 100)


def test_market_position_without_prices() -> None:
    position = compute_market_position(1000.0, [])
    assert position.matched_count == 0
    assert position.stats is None
    assert position.delta_to_median_pct is None
