"""AI-артефакты: сохранение и чтение ответов AI, фидбек для будущего датасета."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AiArtifact, AiFeedback


async def save_artifact(
    session: AsyncSession,
    *,
    kind: str,
    key: str,
    payload: dict,
    model: str = "",
    cost_usd: float | None = None,
) -> AiArtifact:
    artifact = AiArtifact(
        kind=kind,
        key=key[:128],
        payload=payload,
        model=model[:128],
        cost_usd=cost_usd,
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def latest_artifact(
    session: AsyncSession,
    *,
    kind: str,
    key: str,
    max_age_hours: float | None = None,
) -> AiArtifact | None:
    statement = select(AiArtifact).where(AiArtifact.kind == kind, AiArtifact.key == key[:128])
    if max_age_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        statement = statement.where(AiArtifact.created_at >= cutoff)
    row = await session.execute(statement.order_by(AiArtifact.created_at.desc()).limit(1))
    return row.scalars().first()


async def list_artifacts(
    session: AsyncSession, *, kind: str | None = None, key: str | None = None, limit: int = 20
) -> list[AiArtifact]:
    statement = select(AiArtifact)
    if kind:
        statement = statement.where(AiArtifact.kind == kind)
    if key:
        statement = statement.where(AiArtifact.key == key[:128])
    rows = await session.execute(
        statement.order_by(AiArtifact.created_at.desc()).limit(max(1, min(limit, 100)))
    )
    return list(rows.scalars())


async def save_feedback(
    session: AsyncSession,
    *,
    rating: int,
    comment: str | None = None,
    artifact_id=None,
) -> AiFeedback:
    feedback = AiFeedback(
        artifact_id=artifact_id,
        rating=1 if rating > 0 else -1,
        comment=(comment or "")[:2000] or None,
    )
    session.add(feedback)
    await session.flush()
    return feedback
