import pytest

from app.services.web_research import validate_source


def test_source_requires_absolute_url_and_claim() -> None:
    source = validate_source("https://devialet.com/gemini", "Devialet Gemini", ["model family"])
    assert source.url.startswith("https://")
    assert source.claims == ("model family",)


def test_source_without_url_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_source("Gemini search result", "", [])
