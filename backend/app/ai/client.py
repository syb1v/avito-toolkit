import json
from dataclasses import dataclass

from pydantic import BaseModel

from app.config import get_settings


class LlmNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LlmResult[T: BaseModel]:
    content: T
    model: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None


def prepare_response_format(model: str, schema: type[BaseModel]) -> tuple[object, str]:
    """Возвращает (response_format, доп. инструкция для system-промпта).

    DeepSeek поддерживает только JSON-режим (`json_object`), поэтому схема
    передаётся текстом. Остальные провайдеры (OpenAI-совместимые с json_schema)
    получают Pydantic-схему напрямую.
    """
    if model.startswith("deepseek/"):
        instruction = "\n\nВерни ответ строго в формате JSON по схеме:\n" + json.dumps(
            schema.model_json_schema(), ensure_ascii=False
        )
        return {"type": "json_object"}, instruction
    return schema, ""


async def complete_structured[T: BaseModel](
    schema: type[T],
    *,
    system_prompt: str,
    user_prompt: str,
    task: str = "generic",
    prompt_version: str = "v1",
    max_tokens: int | None = None,
) -> LlmResult[T]:
    """Structured output через litellm: ответ валидируется Pydantic-схемой."""
    settings = get_settings()
    if settings.llm_model.startswith("deepseek/") and not settings.deepseek_api_key:
        raise LlmNotConfiguredError("DEEPSEEK_API_KEY не задан")

    import litellm

    response_format, schema_instruction = prepare_response_format(settings.llm_model, schema)
    response = await litellm.acompletion(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": f"{system_prompt}{schema_instruction}"},
            {"role": "user", "content": user_prompt},
        ],
        temperature=settings.llm_temperature,
        max_tokens=max(settings.llm_max_tokens, max_tokens or 0),
        response_format=response_format,
    )
    content = response.choices[0].message.content
    if content is None:
        raise LlmNotConfiguredError("LLM вернул пустой ответ")

    usage = getattr(response, "usage", None)
    cost_usd: float | None = None
    try:
        cost_usd = float(litellm.completion_cost(completion_response=response))
    except Exception:
        cost_usd = None
    return LlmResult(
        content=schema.model_validate_json(content),
        model=settings.llm_model,
        tokens_in=getattr(usage, "prompt_tokens", None),
        tokens_out=getattr(usage, "completion_tokens", None),
        cost_usd=cost_usd,
    )
