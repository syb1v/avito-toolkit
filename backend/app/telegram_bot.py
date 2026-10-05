"""Telegram-бот: авторизация, уведомления и простое управление тулкитом.

Запуск: ``python -m app.telegram_bot`` (в docker-compose сервис ``telegram``).
Токен и доступы — в переменных TELEGRAM_BOT_TOKEN / TELEGRAM_LOGIN /
TELEGRAM_PASSWORD. Сессия пользователя живёт TELEGRAM_SESSION_DAYS дней.
"""

import asyncio
import logging
import secrets
import uuid
from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis
from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import Alert, Listing, Search
from app.db.session import dispose_engine, get_session_factory
from app.services.queues import system_health

logger = logging.getLogger(__name__)

AUTH_PREFIX = "tg:auth:"
STATE_PREFIX = "tg:state:"
LAST_ALERT_KEY = "tg:last_alert_ts"
STATE_TTL_SECONDS = 600
ALERT_BATCH = 5
HELP_TEXT = (
    "Команды:\n"
    "/status — сводка: поиски, лоты, воркер, очереди\n"
    "/searches — список поисков\n"
    "/crawl <id или часть названия> — запустить обход\n"
    "/alerts — последние уведомления\n"
    "/digest <id или часть названия> — последний AI-дайджест\n"
    "/logout — выйти из аккаунта бота"
)


def _now_ts() -> float:
    return datetime.now(UTC).timestamp()


class TelegramBot:
    def __init__(self) -> None:
        settings = get_settings()
        self._token = (settings.telegram_bot_token or "").strip()
        self._login = settings.telegram_login
        self._password = settings.telegram_password or ""
        self._session_ttl = max(1, settings.telegram_session_days) * 86_400
        self._redis: Redis | None = None
        self._client: httpx.AsyncClient | None = None
        self._offset = 0

    async def start(self) -> None:
        settings = get_settings()
        self._redis = Redis.from_url(settings.redis_url)
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{self._token}",
            timeout=httpx.Timeout(40.0, connect=10.0),
        )
        logger.info("telegram bot started")
        await asyncio.gather(self._poll_loop(), self._notify_loop())

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        if self._redis is not None:
            await self._redis.aclose()

    # --- Telegram API -------------------------------------------------
    async def _send(self, chat_id: int, text: str) -> None:
        assert self._client is not None
        try:
            await self._client.post(
                "/sendMessage",
                json={"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True},
            )
        except Exception as error:  # noqa: BLE001 — сеть до Telegram может отвалиться
            logger.warning("sendMessage failed: %s", error)

    async def _poll_loop(self) -> None:
        assert self._client is not None
        while True:
            try:
                response = await self._client.get(
                    "/getUpdates", params={"offset": self._offset, "timeout": 25}
                )
                payload = response.json()
                for update in payload.get("result", []):
                    self._offset = max(self._offset, int(update["update_id"]) + 1)
                    message = update.get("message") or {}
                    chat_id = (message.get("chat") or {}).get("id")
                    text = (message.get("text") or "").strip()
                    if chat_id is None or not text:
                        continue
                    await self._handle(int(chat_id), text)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001
                logger.warning("telegram poll error: %s", error)
                await asyncio.sleep(3)

    # --- auth ---------------------------------------------------------
    async def _authed(self, chat_id: int) -> bool:
        assert self._redis is not None
        return bool(await self._redis.get(f"{AUTH_PREFIX}{chat_id}"))

    async def _set_state(self, chat_id: int, state: str) -> None:
        assert self._redis is not None
        await self._redis.set(f"{STATE_PREFIX}{chat_id}", state, ex=STATE_TTL_SECONDS)

    async def _get_state(self, chat_id: int) -> str | None:
        assert self._redis is not None
        value = await self._redis.get(f"{STATE_PREFIX}{chat_id}")
        return value.decode() if isinstance(value, bytes) else value

    async def _handle(self, chat_id: int, text: str) -> None:
        assert self._redis is not None
        command = text.split()[0].split("@")[0].lower()
        if command == "/logout":
            await self._redis.delete(f"{AUTH_PREFIX}{chat_id}")
            await self._send(chat_id, "Вы вышли. Для входа отправьте /start")
            return
        if not await self._authed(chat_id):
            await self._login_flow(chat_id, text)
            return
        if command == "/start" or command == "/help":
            await self._send(chat_id, "Бот готов.\n\n" + HELP_TEXT)
        elif command == "/status":
            await self._send(chat_id, await self._status_text())
        elif command == "/searches":
            await self._send(chat_id, await self._searches_text())
        elif command == "/alerts":
            await self._send(chat_id, await self._alerts_text())
        elif command == "/crawl":
            await self._send(chat_id, await self._crawl(text))
        elif command == "/digest":
            await self._send(chat_id, await self._digest(text))
        else:
            await self._send(chat_id, "Не понял команду.\n\n" + HELP_TEXT)

    async def _login_flow(self, chat_id: int, text: str) -> None:
        state = await self._get_state(chat_id)
        if text.strip().lower() in ("/start", "start") or state is None:
            await self._set_state(chat_id, "login")
            await self._send(chat_id, "Введите логин:")
            return
        if state == "login":
            if secrets.compare_digest(text.strip(), self._login):
                await self._set_state(chat_id, "password")
                await self._send(chat_id, "Введите пароль:")
            else:
                await self._send(chat_id, "Неверный логин. Попробуйте ещё раз:")
                await self._set_state(chat_id, "login")
            return
        if state == "password":
            if self._password and secrets.compare_digest(text.strip(), self._password):
                assert self._redis is not None
                await self._redis.set(f"{AUTH_PREFIX}{chat_id}", self._login, ex=self._session_ttl)
                await self._redis.delete(f"{STATE_PREFIX}{chat_id}")
                days = self._session_ttl // 86_400
                await self._send(
                    chat_id, f"Вход выполнен. Сессия активна {days} дн.\n\n" + HELP_TEXT
                )
            else:
                await self._set_state(chat_id, "login")
                await self._send(chat_id, "Неверный пароль. Начнём заново — введите логин:")

    # --- data ---------------------------------------------------------
    async def _status_text(self) -> str:
        settings = get_settings()
        assert self._redis is not None
        health = await system_health(
            redis=self._redis, window_seconds=settings.worker_alive_window_seconds
        )
        factory = get_session_factory()
        try:
            async with factory() as session:
                searches_total = await session.scalar(select(func.count()).select_from(Search))
                searches_active = await session.scalar(
                    select(func.count()).select_from(Search).where(Search.is_active.is_(True))
                )
                listings_active = await session.scalar(
                    select(func.count()).select_from(Listing).where(Listing.status == "active")
                )
                alerts_new = await session.scalar(
                    select(func.count()).select_from(Alert).where(Alert.status == "new")
                )
        finally:
            await dispose_engine()
        worker = "жив" if health["worker_alive"] else "НЕ ОТВЕЧАЕТ"
        return (
            f"Поиски: {searches_active}/{searches_total} активных\n"
            f"Лотов на рынке: {listings_active}\n"
            f"Новых уведомлений: {alerts_new}\n"
            f"Воркер: {worker}\n"
            f"Очереди: обходы {health['crawl_queue']}, аналитика {health['analytics_queue']}"
        )

    async def _find_search(self, query: str) -> Search | None:
        query = query.strip()
        if not query:
            return None
        factory = get_session_factory()
        try:
            async with factory() as session:
                rows = (
                    (await session.execute(select(Search).order_by(Search.priority, Search.name)))
                    .scalars()
                    .all()
                )
        finally:
            await dispose_engine()
        if not rows:
            return None
        try:
            wanted = uuid.UUID(query)
            for row in rows:
                if row.id == wanted:
                    return row
        except ValueError:
            pass
        if query.isdigit():
            index = int(query) - 1
            if 0 <= index < len(rows):
                return rows[index]
        lowered = query.lower()
        for row in rows:
            if lowered in row.name.lower():
                return row
        return None

    async def _searches_text(self) -> str:
        factory = get_session_factory()
        try:
            async with factory() as session:
                rows = (
                    (await session.execute(select(Search).order_by(Search.priority, Search.name)))
                    .scalars()
                    .all()
                )
        finally:
            await dispose_engine()
        if not rows:
            return "Поисков нет."
        lines = ["Поиски (номер. название — обход):"]
        for index, row in enumerate(rows, start=1):
            state = "активен" if row.is_active else "пауза"
            lines.append(f"{index}. {row.name[:60]} [{state}] · id {str(row.id)[:8]}")
        return "\n".join(lines)

    async def _crawl(self, text: str) -> str:
        query = text.partition(" ")[2]
        search = await self._find_search(query)
        if search is None:
            return "Не нашёл поиск. Список: /searches"
        from app.services.progress import CrawlProgress
        from app.workers.tasks import crawl_search

        assert self._redis is not None
        await CrawlProgress(self._redis, search.id).queued(search.name)
        crawl_search.send(str(search.id))
        return f"Обход «{search.name}» поставлен в очередь."

    async def _alerts_text(self) -> str:
        factory = get_session_factory()
        try:
            async with factory() as session:
                rows = (
                    (
                        await session.execute(
                            select(Alert)
                            .where(Alert.status == "new")
                            .order_by(Alert.created_at.desc())
                            .limit(ALERT_BATCH)
                        )
                    )
                    .scalars()
                    .all()
                )
        finally:
            await dispose_engine()
        if not rows:
            return "Новых уведомлений нет."
        lines = ["Последние уведомления:"]
        for alert in rows:
            payload = alert.payload or {}
            title = payload.get("title") or payload.get("kind") or alert.type
            lines.append(f"• {alert.type}: {str(title)[:70]}")
        return "\n".join(lines)

    async def _digest(self, text: str) -> str:
        query = text.partition(" ")[2]
        search = await self._find_search(query)
        if search is None:
            return "Не нашёл поиск. Список: /searches"
        from app.db.models import AiDigest

        factory = get_session_factory()
        try:
            async with factory() as session:
                row = await session.scalar(
                    select(AiDigest)
                    .where(AiDigest.search_id == search.id)
                    .order_by(AiDigest.created_at.desc())
                    .limit(1)
                )
        finally:
            await dispose_engine()
        if row is None:
            return (
                f"Дайджест «{search.name}» ещё не генерировали — "
                "нажмите «Сгенерировать» на странице поиска, он сохранится для всех."
            )
        payload = row.payload or {}
        actions = payload.get("recommended_actions") or []
        lines = [
            f"{search.name}:",
            str(payload.get("headline", "")),
            str(payload.get("price_range_comment", "")),
        ]
        if actions:
            lines.append("Рекомендации:")
            lines.extend(f"• {str(action)[:100]}" for action in actions[:5])
        return "\n".join(lines)

    # --- notifications ------------------------------------------------
    async def _notify_loop(self) -> None:
        assert self._redis is not None
        while True:
            try:
                await asyncio.sleep(60)
                await self._notify_once()
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001
                logger.warning("telegram notify error: %s", error)

    async def _notify_once(self) -> None:
        assert self._redis is not None
        raw_ts = await self._redis.get(LAST_ALERT_KEY)
        last_ts = float(raw_ts) if raw_ts else _now_ts()
        factory = get_session_factory()
        try:
            async with factory() as session:
                rows = (
                    (
                        await session.execute(
                            select(Alert)
                            .where(
                                Alert.status == "new",
                                Alert.created_at > datetime.fromtimestamp(last_ts, tz=UTC),
                            )
                            .order_by(Alert.created_at)
                            .limit(20)
                        )
                    )
                    .scalars()
                    .all()
                )
        finally:
            await dispose_engine()
        if not rows:
            await self._redis.set(LAST_ALERT_KEY, _now_ts())
            return
        chat_ids: list[int] = []
        async for key in self._redis.scan_iter(f"{AUTH_PREFIX}*"):
            name = key.decode() if isinstance(key, bytes) else key
            with_ = name.removeprefix(AUTH_PREFIX)
            if with_.lstrip("-").isdigit():
                chat_ids.append(int(with_))
        for alert in rows:
            payload = alert.payload or {}
            title = payload.get("title") or payload.get("kind") or ""
            text = f"🔔 {alert.type}: {str(title)[:80]}\n"
            if payload.get("delta_pct") is not None:
                text += (
                    f"наша {payload.get('our_price')} ₽ · рынок {payload.get('market_median')} ₽\n"
                )
            if alert.type == "worker_down":
                text += "Воркер не отвечает — проверьте сервер.\n"
            for chat_id in chat_ids:
                await self._send(chat_id, text)
        newest = max(row.created_at for row in rows)
        await self._redis.set(LAST_ALERT_KEY, newest.timestamp())


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан — бот не запущен")
    if not settings.telegram_password:
        raise SystemExit("TELEGRAM_PASSWORD не задан — бот не запущен")
    bot = TelegramBot()
    try:
        await bot.start()
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
