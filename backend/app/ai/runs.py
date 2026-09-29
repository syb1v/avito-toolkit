from typing import Any

from app.ai.client import LlmResult
from app.db.models import LlmRun


async def record_llm_run(
    session: Any,
    *,
    task: str,
    result: LlmResult[Any],
    prompt_version: str = "v1",
) -> LlmRun:
    run = LlmRun(
        task=task,
        model=result.model,
        prompt_version=prompt_version,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
    )
    session.add(run)
    await session.flush()
    return run
