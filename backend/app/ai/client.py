from pydantic import BaseModel

from app.config import get_settings


class LlmNotConfiguredError(RuntimeError):
    pass


async def complete_structured[T: BaseModel](
    schema: type[T],
    *,
    system_prompt: str,
    user_prompt: str,
    task: str = "generic",
    prompt_version: str = "v1",
) -> T:
    """Structured output через litellm: ответ валидируется Pydantic-схемой."""
    settings = get_settings()
    if settings.llm_model.startswith("deepseek/") and not settings.deepseek_api_key:
        raise LlmNotConfiguredError("DEEPSEEK_API_KEY не задан")

    import litellm

    response = await litellm.acompletion(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        response_format=schema,
    )
    content = response.choices[0].message.content
    if content is None:
        raise LlmNotConfiguredError("LLM вернул пустой ответ")
    return schema.model_validate_json(content)
