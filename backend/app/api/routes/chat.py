"""Чат-ассистент и AI-артефакты: сессии, сообщения, действия с подтверждением."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import delete, select

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import Alert, ChatMessage, ChatSession, Search
from app.services.ai_center import list_artifacts, save_feedback
from app.services.chat import ACTION_LABELS, answer_message, plan_message, run_tools

router = APIRouter(tags=["chat"])

HISTORY_LIMIT = 12
MAX_MESSAGE_CHARS = 4000


class SessionOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    tool_name: str | None = None
    tool_payload: dict | None = None
    created_at: datetime


class ChatReplyOut(BaseModel):
    message: MessageOut
    tool_trace: list[dict[str, Any]] = []
    pending_action: dict[str, Any] | None = None


class SendMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class RunActionIn(BaseModel):
    session_id: uuid.UUID
    action_type: Literal["crawl", "digest", "clear_alerts", "manual_edit"]
    search: str | None = None
    sku: str | None = None
    price: float | None = None


class ArtifactOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    kind: str
    key: str
    payload: dict
    model: str
    cost_usd: float | None
    created_at: datetime


class FeedbackIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    artifact_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=2000)


async def _get_session(session: DbSession, session_id: uuid.UUID) -> ChatSession:
    row = await session.get(ChatSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="диалог не найден")
    return row


def _message_out(message: ChatMessage) -> MessageOut:
    return MessageOut(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        tool_name=message.tool_name,
        tool_payload=message.tool_payload,
        created_at=message.created_at,
    )


@router.get("/chat/sessions", response_model=list[SessionOut])
async def list_sessions(session: DbSession) -> list[ChatSession]:
    rows = await session.execute(select(ChatSession).order_by(ChatSession.updated_at.desc()))
    return list(rows.scalars())


@router.post("/chat/sessions", response_model=SessionOut, status_code=201)
async def create_session(session: DbSession) -> ChatSession:
    row = ChatSession(title="Новый диалог")
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/chat/sessions/{session_id}", status_code=204)
async def delete_session(session_id: uuid.UUID, session: DbSession) -> None:
    row = await _get_session(session, session_id)
    await session.delete(row)
    await session.commit()


@router.post("/chat/sessions/{session_id}/clear", response_model=SessionOut)
async def clear_session(session_id: uuid.UUID, session: DbSession) -> ChatSession:
    row = await _get_session(session, session_id)
    await session.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    row.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/chat/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(session_id: uuid.UUID, session: DbSession) -> list[MessageOut]:
    await _get_session(session, session_id)
    rows = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .limit(200)
    )
    return [_message_out(message) for message in rows.scalars()]


@router.post("/chat/sessions/{session_id}/messages", response_model=ChatReplyOut)
async def send_message(
    session_id: uuid.UUID, payload: SendMessageIn, session: DbSession
) -> ChatReplyOut:
    chat = await _get_session(session, session_id)
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        rows = await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id, ChatMessage.role.in_(("user", "assistant"))
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(HISTORY_LIMIT)
        )
        history = [(m.role, m.content) for m in reversed(rows.scalars().all())]

        user_message = ChatMessage(session_id=session_id, role="user", content=payload.text)
        session.add(user_message)
        await session.flush()

        plan = await plan_message(session, text=payload.text, history=history)
        trace, tool_data = await run_tools(
            plan.content.tools, session=session, redis=redis, search=plan.content.search
        )
        answer = await answer_message(
            session, text=payload.text, history=history, tool_data=tool_data
        )

        pending_action: dict[str, Any] | None = None
        plan_content = plan.content
        if plan_content.action_type in ACTION_LABELS:
            pending_action = cast(
                dict[str, Any],
                {
                    "type": plan_content.action_type,
                    "label": ACTION_LABELS[plan_content.action_type],
                    "search": plan_content.action_search,
                    "sku": plan_content.action_sku,
                    "price": plan_content.action_price,
                },
            )

        tool_payload: dict[str, Any] = {"calls": trace}
        if pending_action:
            tool_payload["pending_action"] = pending_action
        if trace:
            session.add(
                ChatMessage(
                    session_id=session_id,
                    role="tool",
                    content="; ".join(call["name"] for call in trace),
                    tool_payload=tool_payload,
                )
            )
        assistant_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=answer.content.answer,
            tool_payload=tool_payload if pending_action else None,
        )
        session.add(assistant_message)
        if chat.title == "Новый диалог":
            chat.title = payload.text[:80]
        chat.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(assistant_message)
        return ChatReplyOut(
            message=_message_out(assistant_message),
            tool_trace=trace,
            pending_action=pending_action,
        )
    finally:
        await redis.aclose()


@router.post("/chat/actions", response_model=MessageOut)
async def run_action(payload: RunActionIn, session: DbSession) -> MessageOut:
    """Выполняет действие, подтверждённое человеком."""
    chat = await _get_session(session, payload.session_id)
    result_text = ""
    if payload.action_type == "clear_alerts":
        from sqlalchemy import update

        await session.execute(update(Alert).where(Alert.status == "new").values(status="acked"))
        result_text = "Отметил все алерты прочитанными."
    elif payload.action_type in ("crawl", "digest"):
        from app.services.chat import _find_search  # локальный импорт: приватный хелпер

        searches = list((await session.execute(select(Search))).scalars())
        found = _find_search(searches, payload.search)
        if found is None:
            raise HTTPException(status_code=404, detail="поиск не найден")
        if payload.action_type == "crawl":
            from app.workers.tasks import crawl_search

            crawl_search.send(str(found.id))
            result_text = f"Обход «{found.name}» поставлен в очередь."
        else:
            from app.api.routes.ai import create_digest

            await create_digest(found.id, session)
            result_text = f"Дайджест по «{found.name}» обновлён."
    elif payload.action_type == "manual_edit":
        if not payload.sku or payload.price is None or payload.price <= 0:
            raise HTTPException(status_code=422, detail="нужны sku и цена")
        from app.api.routes.seller import ManualEditIn, create_manual_edit

        outcome = await create_manual_edit(
            ManualEditIn(sku=payload.sku, price=payload.price), session
        )
        result_text = f"Своя цена для {payload.sku}: {payload.price:.0f} ₽ — " + (
            "применяется." if outcome.applied else "сохранена черновиком (нужно подтверждение)."
        )
    message = ChatMessage(session_id=payload.session_id, role="assistant", content=result_text)
    session.add(message)
    chat.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(message)
    return _message_out(message)


@router.get("/ai/artifacts", response_model=list[ArtifactOut])
async def get_artifacts(
    session: DbSession, kind: str | None = None, key: str | None = None, limit: int = 20
) -> list[ArtifactOut]:
    rows = await list_artifacts(session, kind=kind, key=key, limit=limit)
    return [
        ArtifactOut(
            id=row.id,
            kind=row.kind,
            key=row.key,
            payload=row.payload,
            model=row.model,
            cost_usd=float(row.cost_usd) if row.cost_usd is not None else None,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/ai/feedback", status_code=201)
async def post_feedback(payload: FeedbackIn, session: DbSession) -> dict[str, Any]:
    await save_feedback(
        session,
        rating=payload.rating,
        comment=payload.comment,
        artifact_id=payload.artifact_id,
    )
    await session.commit()
    return {"status": "ok"}
