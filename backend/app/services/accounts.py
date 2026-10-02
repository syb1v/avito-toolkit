"""Аккаунты Авито: профили с доверенными cookies и их привязка к поискам."""

import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AvitoAccount, Search

DEFAULT_PROFILE_DIR = ".browser-profile"
ACCOUNTS_SUBDIR = ".accounts"
CLEAN_SLUG = re.compile(r"[^a-z0-9]+")
TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate(value: str) -> str:
    """Кириллица/диакритика → латинский slug (может быть пустым)."""
    lowered = unicodedata.normalize("NFKD", value.lower().replace("ё", "е"))
    transliterated = "".join(TRANSLIT.get(char, char) for char in lowered)
    ascii_only = transliterated.encode("ascii", "ignore").decode("ascii")
    return CLEAN_SLUG.sub("-", ascii_only).strip("-")


def slugify(value: str) -> str:
    return transliterate(value) or "account"


def accounts_base_dir() -> Path:
    base = Path(get_settings().browser_user_data_dir or DEFAULT_PROFILE_DIR)
    return base.parent / ACCOUNTS_SUBDIR


def default_profile_dir() -> str:
    return get_settings().browser_user_data_dir or DEFAULT_PROFILE_DIR


def resolve_profile_path(profile_dir: str | None) -> Path:
    """Каталог профиля: абсолютный → как есть; основной → BROWSER_USER_DATA_DIR.

    Относительные каталоги аккаунтов (``.accounts/<slug>``) считаются от родителя
    основного профиля — так и dev-стек, и прод-том ``/data`` видят одни и те же пути.
    """
    base = Path(get_settings().browser_user_data_dir or DEFAULT_PROFILE_DIR)
    value = profile_dir or str(base)
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    if value == str(base) or value == DEFAULT_PROFILE_DIR:
        return base
    return base.parent / path


def new_profile_dir(name: str) -> str:
    return f"{ACCOUNTS_SUBDIR}/{slugify(name)}"


async def unique_profile_dir(session: AsyncSession, name: str) -> str:
    """Подбирает свободный каталог .accounts/<slug>(-2, -3, ...)."""
    base = slugify(name)
    candidate = base
    index = 1
    while True:
        profile = f"{ACCOUNTS_SUBDIR}/{candidate}"
        exists = await session.scalar(
            select(func.count())
            .select_from(AvitoAccount)
            .where(AvitoAccount.profile_dir == profile)
        )
        if not exists:
            return profile
        index += 1
        candidate = f"{base}-{index}"


async def get_account(session: AsyncSession, account_id: uuid.UUID) -> AvitoAccount | None:
    return await session.get(AvitoAccount, account_id)


async def account_for_search(session: AsyncSession, search: Search) -> AvitoAccount | None:
    if search.account_id is None:
        return None
    return await session.get(AvitoAccount, search.account_id)


async def search_profile_path(session: AsyncSession, search: Search) -> Path:
    account = await account_for_search(session, search)
    return resolve_profile_path(account.profile_dir if account is not None else None)


async def account_overview(session: AsyncSession) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(AvitoAccount, func.count(Search.id))
        .outerjoin(Search, Search.account_id == AvitoAccount.id)
        .group_by(AvitoAccount.id)
        .order_by(AvitoAccount.is_default.desc(), AvitoAccount.name)
    )
    overview: list[dict[str, Any]] = []
    for account, searches_count in rows.all():
        overview.append(
            {
                "id": account.id,
                "name": account.name,
                "profile_dir": account.profile_dir,
                "status": account.status,
                "notes": account.notes,
                "is_default": account.is_default,
                "cookies_at": account.cookies_at,
                "last_check_at": account.last_check_at,
                "last_check_ok": account.last_check_ok,
                "last_error": account.last_error,
                "searches_count": int(searches_count or 0),
                "profile_exists": resolve_profile_path(account.profile_dir).exists(),
            }
        )
    return overview
