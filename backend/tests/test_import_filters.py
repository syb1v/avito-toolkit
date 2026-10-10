from app.services.import_file import validate_generated_filter


def test_filter_validator_rejects_neighbor_model_and_include_exclude_conflict() -> None:
    assert not validate_generated_filter(
        title="Devialet Gemini 2 Opera de Paris",
        query="Devialet Mania Opera",
        keyword_groups=[["Devialet"], ["Mania"]],
        exclude_keywords=[],
    )
    assert not validate_generated_filter(
        title="B&O Eleven",
        query="B&O Eleven",
        keyword_groups=[["B&O"], ["Eleven"]],
        exclude_keywords=["Eleven"],
    )


def test_filter_validator_accepts_title_anchored_filter() -> None:
    assert validate_generated_filter(
        title="B&O Beoplay Eleven",
        query="B&O Eleven",
        keyword_groups=[["B&O", "Bang Olufsen"], ["Eleven"]],
        exclude_keywords=["копия", "ремонт"],
    )
