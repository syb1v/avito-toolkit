import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import AvitoAccount, Search
from app.services.account_care import account_care_state, clear_rest, set_rest
from app.services.accounts import (
    account_overview,
    proxy_label_for,
    resolve_profile_path,
    resolve_proxy_label,
    unique_profile_dir,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])

VALID_STATUSES = ("active", "paused")
VALID_ROLES = ("searcher", "seller")


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = None
    role: str = "searcher"
    proxy_label: str | None = None
    api_client_id: str | None = Field(default=None, max_length=128)
    api_client_secret: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = None
    status: str | None = None
    role: str | None = None
    proxy_label: str | None = None
    api_client_id: str | None = None
    api_client_secret: str | None = None


class AccountCookiesIn(BaseModel):
    cookies: str = Field(min_length=1, max_length=200_000)
    fresh: bool = True


class AccountOut(BaseModel):
    id: uuid.UUID
    name: str
    profile_dir: str
    role: str
    proxy_label: str | None = None
    status: str
    notes: str | None
    cookies_at: datetime | None
    last_check_at: datetime | None
    last_check_ok: bool | None
    last_error: str | None
    api_configured: bool = False
    api_user_id: int | None = None
    searches_count: int
    profile_exists: bool
    pages_today: int = 0
    daily_limit: int = 0
    last_activity: datetime | None = None
    warmup_last: datetime | None = None
    rest_until: datetime | None = None
    rest_reason: str | None = None


def _care_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _account_out(
    account: AvitoAccount, searches_count: int, care: dict[str, Any] | None = None
) -> AccountOut:
    care = care or {}
    return AccountOut(
        id=account.id,
        name=account.name,
        profile_dir=account.profile_dir,
        role=account.role,
        proxy_label=proxy_label_for(account.proxy_url),
        status=account.status,
        notes=account.notes,
        cookies_at=account.cookies_at,
        last_check_at=account.last_check_at,
        last_check_ok=account.last_check_ok,
        last_error=account.last_error,
        api_configured=bool(account.api_client_id and account.api_client_secret),
        api_user_id=account.api_user_id,
        searches_count=searches_count,
        profile_exists=resolve_profile_path(account.profile_dir).exists(),
        pages_today=int(care.get("pages_today") or 0),
        daily_limit=int(care.get("daily_limit") or 0),
        last_activity=_care_dt(care.get("last_activity")),
        warmup_last=_care_dt(care.get("warmup_last")),
        rest_until=_care_dt(care.get("rest_until")),
        rest_reason=care.get("rest_reason"),
    )


async def validate_api_credentials(client_id: str, client_secret: str) -> int:
    """Проверяет API-ключи через /accounts/self, возвращает user_id."""
    from app.services.avito_api import ApiCredentials, AvitoApiError, fetch_self

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        me = await fetch_self(
            redis, settings, ApiCredentials(client_id=client_id, client_secret=client_secret)
        )
    except AvitoApiError as error:
        raise HTTPException(
            status_code=422, detail=f"API-ключи не приняты: {error.message}"
        ) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"API недоступен: {error}") from error
    finally:
        await redis.aclose()
    user_id = me.get("id")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=422, detail="в ответе API нет user id")
    return user_id


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
    settings = get_settings()
    rows = await account_overview(session)
    redis = Redis.from_url(settings.redis_url)
    try:
        result: list[AccountOut] = []
        for row in rows:
            care = await account_care_state(
                redis, str(row["id"]), daily_limit=settings.account_daily_page_limit
            )
            result.append(
                AccountOut(
                    **row,
                    **{
                        "pages_today": care["pages_today"],
                        "daily_limit": care["daily_limit"],
                        "last_activity": _care_dt(care.get("last_activity")),
                        "warmup_last": _care_dt(care.get("warmup_last")),
                        "rest_until": _care_dt(care.get("rest_until")),
                        "rest_reason": care.get("rest_reason"),
                    },
                )
            )
        return result
    finally:
        await redis.aclose()


@router.post("", response_model=AccountOut, status_code=201)
async def create_account(payload: AccountCreate, session: DbSession) -> AccountOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    exists = await session.scalar(select(AvitoAccount.id).where(AvitoAccount.name == name))
    if exists is not None:
        raise HTTPException(status_code=409, detail="account with this name already exists")
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be {VALID_ROLES}")
    try:
        proxy_url = resolve_proxy_label(payload.proxy_label)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    api_user_id: int | None = None
    if payload.api_client_id and payload.api_client_secret:
        api_user_id = await validate_api_credentials(
            payload.api_client_id, payload.api_client_secret
        )
    account = AvitoAccount(
        name=name,
        profile_dir=await unique_profile_dir(session, name),
        role=payload.role,
        proxy_url=proxy_url,
        status="active",
        notes=payload.notes,
        api_client_id=payload.api_client_id,
        api_client_secret=payload.api_client_secret,
        api_user_id=api_user_id,
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
    if payload.role is not None:
        if payload.role not in VALID_ROLES:
            raise HTTPException(status_code=422, detail=f"role must be {VALID_ROLES}")
        account.role = payload.role
    if "proxy_label" in payload.model_fields_set:
        try:
            account.proxy_url = resolve_proxy_label(payload.proxy_label)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if (
        "api_client_id" in payload.model_fields_set
        or "api_client_secret" in payload.model_fields_set
    ):
        account.api_client_id = payload.api_client_id
        account.api_client_secret = payload.api_client_secret
        if payload.api_client_id and payload.api_client_secret:
            account.api_user_id = await validate_api_credentials(
                payload.api_client_id, payload.api_client_secret
            )
        else:
            account.api_user_id = None
    await session.commit()
    await session.refresh(account)
    return _account_out(account, await _searches_count(session, account.id))


@router.delete("/{account_id}", status_code=204)
async def delete_account(account_id: uuid.UUID, session: DbSession) -> None:
    account = await _load(session, account_id)
    await session.delete(account)
    await session.commit()


@router.post("/{account_id}/sync-api", status_code=202)
async def start_sync_api(account_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    """Ставит синхронизацию наших SKU аккаунта через официальный API."""
    account = await _load(session, account_id)
    if not (account.api_client_id and account.api_client_secret):
        raise HTTPException(status_code=422, detail="у аккаунта нет API-ключей")
    from app.workers.tasks import sync_account_items as sync_task

    sync_task.send(str(account.id))
    return {"status": "started", "account_id": str(account.id)}


@router.get("/{account_id}/sync-api")
async def get_sync_api(account_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    """Статус синхронизации по API (Redis, TTL 1 час)."""
    await _load(session, account_id)
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        raw = await redis.get(f"account-sync:{account_id}")
    finally:
        await redis.aclose()
    if raw is None:
        return {"status": "idle"}
    return json.loads(raw)


@router.post("/{account_id}/warmup", status_code=202)
async def warmup_account_now(account_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    """Мягкий прогрев аккаунта прямо сейчас (главная + одна выдача, паузы)."""
    await _load(session, account_id)
    from app.workers.tasks import warmup_account

    message = warmup_account.send(str(account_id))
    return {"status": "queued", "message_id": message.message_id}


class RestIn(BaseModel):
    minutes: int | None = Field(default=None, ge=1, le=24 * 60)


@router.post("/{account_id}/rest", status_code=202)
async def rest_account(
    account_id: uuid.UUID, payload: RestIn, session: DbSession
) -> dict[str, Any]:
    """Отправить аккаунт в «отдых» вручную (например, перед сменой IP)."""
    account = await _load(session, account_id)
    settings = get_settings()
    minutes = payload.minutes or settings.account_rest_minutes
    until = await set_rest(Redis.from_url(settings.redis_url), str(account.id), minutes, "вручную")
    return {"status": "resting", "until": until, "minutes": minutes}


@router.post("/{account_id}/resume", status_code=202)
async def resume_account(account_id: uuid.UUID, session: DbSession) -> dict[str, Any]:
    """Разбудить аккаунт: снять «отдых» досрочно."""
    account = await _load(session, account_id)
    settings = get_settings()
    await clear_rest(Redis.from_url(settings.redis_url), str(account.id))
    return {"status": "active"}


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
    account = await _load(session, account_id)
    settings = get_settings()
    cooldown = settings.account_check_cooldown_minutes * 60
    if (
        cooldown > 0
        and account.last_check_at is not None
        and (datetime.now(UTC) - account.last_check_at).total_seconds() < cooldown
    ):
        left = int(cooldown - (datetime.now(UTC) - account.last_check_at).total_seconds())
        return {"status": "cooldown", "seconds_left": left}
    from app.workers.tasks import check_account as check_account_task

    message = check_account_task.send(str(account_id))
    return {"status": "queued", "message_id": message.message_id}
