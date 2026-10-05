"""Проверки «протухло ли»: аккаунты/cookies, прокси, баланс AI API.

Watchdog вызывает эти функции и заводит алерты в БД; их рассылает Telegram-бот.
"""

import logging
from datetime import UTC, datetime, timedelta

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AvitoAccount
from app.services.proxy_pool import build_proxy_pool

logger = logging.getLogger(__name__)

ACCOUNT_STALE = "account_stale"
PROXY_DEAD = "proxy_dead"
AI_BALANCE_LOW = "ai_balance_low"

DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"
BALANCE_TIMEOUT_SECONDS = 10.0

# Маркеры того, что проблема именно в сессии/входе, а не в лимите IP (429).
STALE_MARKERS = (
    "челлендж",
    "challenge",
    "401",
    "403",
    "авториз",
    "login",
    "войти",
    "доступ ограничен",
)


def stale_account_reason(
    *,
    cookies_at: datetime | None,
    last_check_ok: bool | None,
    last_error: str | None,
    now: datetime,
    max_age_hours: int,
) -> str | None:
    """Причина «аккаунт протух» или None, если всё в порядке."""
    error = (last_error or "").lower()
    if last_check_ok is False and any(marker in error for marker in STALE_MARKERS):
        return f"сессия требует внимания: {(last_error or '')[:140]}"
    if last_check_ok is False and cookies_at is None:
        return "cookies не загружены, проверка не проходит"
    if cookies_at is not None and now - cookies_at > timedelta(hours=max_age_hours):
        days = max(1, int((now - cookies_at).total_seconds() // 86400))
        return f"cookies не обновлялись {days} дн. — обновите вход"
    return None


async def check_accounts(
    session: AsyncSession, settings: Settings, now: datetime | None = None
) -> list[dict[str, str]]:
    """Активные аккаунты, которым нужны свежие cookies/вход."""
    moment = now or datetime.now(UTC)
    rows = (
        await session.execute(select(AvitoAccount).where(AvitoAccount.status == "active"))
    ).scalars()
    stale: list[dict[str, str]] = []
    for account in rows:
        reason = stale_account_reason(
            cookies_at=account.cookies_at,
            last_check_ok=account.last_check_ok,
            last_error=account.last_error,
            now=moment,
            max_age_hours=settings.watchdog_cookies_max_age_hours,
        )
        if reason is not None:
            stale.append({"name": account.name, "reason": reason})
    return stale


async def check_proxies(
    redis: Redis, session: AsyncSession, settings: Settings
) -> dict[str, object] | None:
    """Все включённые прокси мертвы/заблокированы? None — прокси не используются."""
    if not settings.proxy_enabled:
        return None
    pool = await build_proxy_pool(redis, session)
    if pool is None:
        return None
    status = await pool.status()
    if int(status.get("alive") or 0) > 0:
        return None
    entries = list(status.get("entries") or [])
    if not entries:
        return None
    problems = [
        {
            "label": str(entry.get("label") or "?"),
            "failures": int(entry.get("failures") or 0),
            "antibot": bool(entry.get("antibot_blocked")),
            "last_error": str(entry.get("last_error") or "")[:120],
        }
        for entry in entries
    ]
    return {
        "count": len(entries),
        "antibot_blocked": int(status.get("antibot_blocked") or 0),
        "proxies": problems,
    }


def balance_alert(balance_infos: list[dict[str, object]], minimum: float) -> dict | None:
    """Баланс AI API ниже порога или недоступен? None — всё хорошо."""
    if not balance_infos:
        return {"low": False, "balance": None, "currency": None, "reason": "баланс не получен"}
    first = balance_infos[0]
    try:
        total = float(str(first.get("total_balance") or 0))
    except (TypeError, ValueError):
        total = 0.0
    currency = str(first.get("currency") or "")
    if total <= 0:
        return {
            "low": True,
            "balance": total,
            "currency": currency,
            "reason": "баланс AI API исчерпан",
        }
    if total <= minimum:
        return {
            "low": True,
            "balance": total,
            "currency": currency,
            "reason": f"баланс AI API ниже порога {minimum}",
        }
    return {"low": False, "balance": total, "currency": currency, "reason": ""}


async def check_ai_balance(settings: Settings) -> dict | None:
    """Баланс DeepSeek: None — не настроено или сеть недоступна (не алертим)."""
    if not settings.deepseek_api_key or not settings.llm_model.startswith("deepseek/"):
        return None
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=BALANCE_TIMEOUT_SECONDS) as client:
            response = await client.get(DEEPSEEK_BALANCE_URL, headers=headers)
    except Exception as error:  # noqa: BLE001 — сеть не повод для алерта
        logger.info("balance check skipped: %s", error)
        return None
    if response.status_code == 401:
        return {
            "low": True,
            "balance": None,
            "currency": None,
            "reason": "ключ DEEPSEEK_API_KEY недействителен",
        }
    if response.status_code != 200:
        logger.info("balance check HTTP %s", response.status_code)
        return None
    data = response.json()
    infos = data.get("balance_infos")
    if not isinstance(infos, list):
        return None
    alert = balance_alert(
        [item for item in infos if isinstance(item, dict)],
        settings.watchdog_ai_balance_min,
    )
    if alert is not None and not alert["low"] and not data.get("is_available", True):
        alert["low"] = True
        alert["reason"] = "AI API сообщает о недоступности (проверьте баланс)"
    return alert
