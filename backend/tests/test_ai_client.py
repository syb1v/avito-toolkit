from app.ai.client import prepare_response_format
from app.ai.schemas import MarketDigest, PriceActionRecommendation


def test_deepseek_uses_json_object_mode_with_schema_text() -> None:
    response_format, instruction = prepare_response_format("deepseek/deepseek-chat", MarketDigest)
    assert response_format == {"type": "json_object"}
    assert "headline" in instruction
    assert "json" in instruction.lower()


def test_other_models_use_pydantic_schema() -> None:
    response_format, instruction = prepare_response_format(
        "openai/gpt-4o-mini", PriceActionRecommendation
    )
    assert response_format is PriceActionRecommendation
    assert instruction == ""
