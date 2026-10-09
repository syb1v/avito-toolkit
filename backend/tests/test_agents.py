from app.ai.client import resolve_model
from app.ai.prompts import build_agent_prompt
from app.config import Settings


def test_resolve_model_cloud_and_local() -> None:
    cloud = Settings(llm_model="deepseek/deepseek-chat")
    assert resolve_model(cloud) == ("deepseek/deepseek-chat", {})

    local = Settings(llm_local_base_url="http://localhost:11434/v1", llm_local_model="qwen3:30b")
    model, extra = resolve_model(local)
    assert model == "openai/qwen3:30b"
    assert extra == {"api_base": "http://localhost:11434/v1", "api_key": "local"}

    prefixed = Settings(llm_local_base_url="http://x", llm_local_model="openai/qwen")
    assert resolve_model(prefixed)[0] == "openai/qwen"


def test_build_agent_prompt_contains_criteria() -> None:
    prompt = build_agent_prompt(
        name="Devialet агент",
        category="Devialet",
        criteria="- целевая цена: 120000",
        data='{"markets": []}',
    )
    assert "Devialet агент" in prompt
    assert "целевая цена" in prompt
    assert "price_actions" in prompt
