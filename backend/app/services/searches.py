from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Search

DEFAULT_CRON = "*/30 * * * *"
DEFAULT_PRIORITY = 100


@dataclass(frozen=True, slots=True)
class SearchImportRow:
    name: str
    url: str
    schedule_cron: str = DEFAULT_CRON
    priority: int = DEFAULT_PRIORITY


@dataclass(frozen=True, slots=True)
class SearchImportResult:
    created: int
    updated: int
    skipped: int


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def normalize_search_rows(
    raw_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[SearchImportRow], int]:
    """Валидация поисков: обязательны name и url; cron и приоритет по умолчанию."""
    rows: list[SearchImportRow] = []
    skipped = 0
    for raw in raw_rows:
        name = str(raw.get("name") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not name or not url:
            skipped += 1
            continue
        cron = str(raw.get("schedule_cron") or "").strip() or DEFAULT_CRON
        priority = _as_int(raw.get("priority")) or DEFAULT_PRIORITY
        rows.append(SearchImportRow(name=name, url=url, schedule_cron=cron, priority=priority))
    return rows, skipped


def merge_params(existing: Mapping[str, Any] | None, patch: Mapping[str, Any]) -> dict[str, Any]:
    """Частичное обновление params: None удаляет ключ, остальное перезаписывает."""
    merged: dict[str, Any] = dict(existing or {})
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


async def import_searches(
    session: AsyncSession, rows: Sequence[SearchImportRow]
) -> SearchImportResult:
    """Создаёт поиски; при совпадении URL — обновляет расписание и приоритет."""
    created = 0
    updated = 0
    for row in rows:
        existing = await session.scalar(select(Search).where(Search.url == row.url))
        if existing is None:
            session.add(
                Search(
                    name=row.name,
                    url=row.url,
                    schedule_cron=row.schedule_cron,
                    priority=row.priority,
                    is_active=True,
                )
            )
            created += 1
            continue
        existing.name = row.name
        existing.schedule_cron = row.schedule_cron
        existing.priority = row.priority
        updated += 1
    await session.commit()
    return SearchImportResult(created=created, updated=updated, skipped=0)
