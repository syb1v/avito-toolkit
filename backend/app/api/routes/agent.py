"""Агенты рынка: плейбуки, запуск отчётов, экспорт датасета."""

import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import AgentPlaybook, AiArtifact, AiFeedback, ChatMessage
from app.services.agents import run_agent

router = APIRouter(tags=["agents"])


class PlaybookIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=120)
    criteria: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class PlaybookPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    criteria: dict[str, Any] | None = None
    is_active: bool | None = None


class PlaybookOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    criteria: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_headline: str | None = None


async def _load(session: DbSession, playbook_id: uuid.UUID) -> AgentPlaybook:
    row = await session.get(AgentPlaybook, playbook_id)
    if row is None:
        raise HTTPException(status_code=404, detail="плейбук не найден")
    return row


async def _out(session: DbSession, playbook: AgentPlaybook) -> PlaybookOut:
    latest = (
        (
            await session.execute(
                select(AiArtifact)
                .where(AiArtifact.kind == "agent_report", AiArtifact.key == str(playbook.id))
                .order_by(AiArtifact.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    headline = (latest.payload or {}).get("headline") if latest is not None else None
    return PlaybookOut(
        id=playbook.id,
        name=playbook.name,
        category=playbook.category,
        criteria=playbook.criteria or {},
        is_active=playbook.is_active,
        created_at=playbook.created_at,
        updated_at=playbook.updated_at,
        last_headline=headline,
    )


@router.get("/agent/playbooks", response_model=list[PlaybookOut])
async def list_playbooks(session: DbSession) -> list[PlaybookOut]:
    rows = await session.execute(select(AgentPlaybook).order_by(AgentPlaybook.name))
    return [await _out(session, playbook) for playbook in rows.scalars()]


@router.post("/agent/playbooks", response_model=PlaybookOut, status_code=201)
async def create_playbook(payload: PlaybookIn, session: DbSession) -> PlaybookOut:
    playbook = AgentPlaybook(
        name=payload.name.strip(),
        category=payload.category.strip(),
        criteria=payload.criteria,
        is_active=payload.is_active,
    )
    session.add(playbook)
    await session.commit()
    await session.refresh(playbook)
    return await _out(session, playbook)


@router.patch("/agent/playbooks/{playbook_id}", response_model=PlaybookOut)
async def update_playbook(
    playbook_id: uuid.UUID, payload: PlaybookPatch, session: DbSession
) -> PlaybookOut:
    playbook = await _load(session, playbook_id)
    if payload.name is not None:
        playbook.name = payload.name.strip()
    if payload.category is not None:
        playbook.category = payload.category.strip()
    if payload.criteria is not None:
        playbook.criteria = payload.criteria
    if payload.is_active is not None:
        playbook.is_active = payload.is_active
    await session.commit()
    await session.refresh(playbook)
    return await _out(session, playbook)


@router.delete("/agent/playbooks/{playbook_id}", status_code=204)
async def delete_playbook(playbook_id: uuid.UUID, session: DbSession) -> None:
    playbook = await _load(session, playbook_id)
    await session.delete(playbook)
    await session.commit()


@router.post("/agent/playbooks/{playbook_id}/run")
async def run_playbook(playbook_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    playbook = await _load(session, playbook_id)
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        return await run_agent(session, redis, playbook)
    finally:
        await redis.aclose()


@router.get("/agent/playbooks/{playbook_id}/report")
async def latest_report(playbook_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    await _load(session, playbook_id)
    row = (
        (
            await session.execute(
                select(AiArtifact)
                .where(AiArtifact.kind == "agent_report", AiArtifact.key == str(playbook_id))
                .order_by(AiArtifact.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="отчёт ещё не готов")
    return {"created_at": row.created_at.isoformat(), **(row.payload or {})}


@router.get("/ai/dataset/export", response_class=PlainTextResponse)
async def export_dataset(session: DbSession) -> PlainTextResponse:
    """JSONL-датасет для будущего обучения/eval: артефакты, фидбек, чат."""
    lines: list[str] = []
    artifacts = (
        (await session.execute(select(AiArtifact).order_by(AiArtifact.created_at).limit(5000)))
        .scalars()
        .all()
    )
    feedback = {
        str(row.artifact_id): {"rating": row.rating, "comment": row.comment}
        for row in (await session.execute(select(AiFeedback))).scalars()
    }
    for artifact in artifacts:
        lines.append(
            json.dumps(
                {
                    "kind": "artifact",
                    "artifact_kind": artifact.kind,
                    "key": artifact.key,
                    "payload": artifact.payload,
                    "model": artifact.model,
                    "feedback": feedback.get(str(artifact.id)),
                    "created_at": artifact.created_at.isoformat(),
                },
                ensure_ascii=False,
                default=str,
            )
        )
    messages = (
        (
            await session.execute(
                select(ChatMessage).where(ChatMessage.role == "assistant").limit(5000)
            )
        )
        .scalars()
        .all()
    )
    for message in messages:
        lines.append(
            json.dumps(
                {
                    "kind": "chat_answer",
                    "session_id": str(message.session_id),
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                },
                ensure_ascii=False,
            )
        )
    return PlainTextResponse("\\n".join(lines), media_type="application/x-ndjson")
