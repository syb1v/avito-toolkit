import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models import Search

router = APIRouter(prefix="/searches", tags=["searches"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class SearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
    schedule_cron: str = "*/30 * * * *"
    priority: int = 100


class SearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    params: dict | None
    schedule_cron: str
    priority: int
    is_active: bool


@router.get("", response_model=list[SearchRead])
async def list_searches(session: DbSession) -> list[Search]:
    result = await session.execute(select(Search).order_by(Search.priority, Search.name))
    return list(result.scalars().all())


@router.post("", response_model=SearchRead, status_code=201)
async def create_search(payload: SearchCreate, session: DbSession) -> Search:
    search = Search(**payload.model_dump())
    session.add(search)
    await session.commit()
    await session.refresh(search)
    return search
