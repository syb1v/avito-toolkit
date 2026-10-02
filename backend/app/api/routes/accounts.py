import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.db.models import AvitoAccount, Search
from app.services.accounts import account_overview, resolve_profile_path, unique_profile_dir

router = APIRouter(prefix="/accounts", tags=["accounts"])

VALID_STATUSES = ("active", "paused")


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = None
    status: str | None = None


class AccountCookiesIn(BaseModel):
    cookies: str = Field(min_length=1, max_length=200_000)
    fresh: bool = True


class AccountOut(BaseModel):
    id: uuid.UUID
    name: str
    profile_dir: str
    status: str
    notes: str | None
    is_default: bool
    cookies_at: datetime | None
    last_check_at: datetime | None
    last_check_ok: bool | None
    last_error: str | None
    searches_count: int
    profile_exists: bool


def _account_out(account: AvitoAccount, searches_count: int) -> AccountOut:
    return AccountOut(
        id=account.id,
        name=account.name,
        profile_dir=account.profile_dir,
        status=account.status,
        notes=account.notes,
        is_default=account.is_default,
        cookies_at=account.cookies_at,
        last_check_at=account.last_check_at,
        last_check_ok=account.last_check_ok,
        last_error=account.last_error,
        searches_count=searches_count,
        profile_exists=resolve_profile_path(account.profile_dir).exists(),
    )


async def _load(session: DbSession, account_id: uuid.UUID) -> AvitoAccount:
    account = await session.get(AvitoAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return account


async def _searches_count(session: DbSession, account_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Search).where(Search.account_id == account_id)
    )
    return int(count or 0)


@router.get("", response_model=list[AccountOut])
async def list_accounts(session: DbSession) -> list[AccountOut]:
    rows = await account_overview(session)
    return [AccountOut(**row) for row in rows]


@router.post("", response_model=AccountOut, status_code=201)
async def create_account(payload: AccountCreate, session: DbSession) -> AccountOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    exists = await session.scalar(select(AvitoAccount.id).where(AvitoAccount.name == name))
    if exists is not None:
        raise HTTPException(status_code=409, detail="account with this name already exists")
    account = AvitoAccount(
        name=name,
        profile_dir=await unique_profile_dir(session, name),
        status="active",
        notes=payload.notes,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return _account_out(account, 0)


@router.patch("/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: uuid.UUID, payload: AccountUpdate, session: DbSession
) -> AccountOut:
    account = await _load(session, account_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")
        account.name = name
    if payload.notes is not None:
        account.notes = payload.notes
    if payload.status is not None:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be {VALID_STATUSES}")
        account.status = payload.status
    await session.commit()
    await session.refresh(account)
    return _account_out(account, await _searches_count(session, account.id))


@router.delete("/{account_id}", status_code=204)
async def delete_account(account_id: uuid.UUID, session: DbSession) -> None:
    account = await _load(session, account_id)
    if account.is_default:
        raise HTTPException(status_code=409, detail="default account cannot be deleted")
    await session.delete(account)
    await session.commit()


@router.post("/{account_id}/cookies", status_code=202)
async def upload_cookies(
    account_id: uuid.UUID, payload: AccountCookiesIn, session: DbSession
) -> dict[str, Any]:
    """Загрузка cookies из UI: воркер пишет их в профиль и проверяет выдачу."""
    await _load(session, account_id)
    from app.workers.tasks import apply_account_cookies

    message = apply_account_cookies.send(str(account_id), payload.cookies, payload.fresh)
    return {"status": "queued", "message_id": message.message_id}


@router.post("/{account_id}/check", status_code=202)
async def check_account(account_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    await _load(session, account_id)
    from app.workers.tasks import check_account as check_account_task

    message = check_account_task.send(str(account_id))
    return {"status": "queued", "message_id": message.message_id}
