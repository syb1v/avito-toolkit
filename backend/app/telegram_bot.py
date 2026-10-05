"""Telegram-бот: интерактивное меню на кнопках, уведомления и управление.

Запуск: ``python -m app.telegram_bot`` (сервис ``telegram`` в docker compose).
Пользователь один раз вводит логин/пароль (сессия TELEGRAM_SESSION_DAYS дней),
дальше всё делается кнопками: статус, поиски, обходы, дайджесты, алерты.
"""

import asyncio
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.db.models import AiDigest, Alert, Listing, Search
from app.db.session import dispose_engine, get_session_factory
from app.services.queues import system_health

logger = logging.getLogger(__name__)

AUTH_PREFIX = "tg:auth:"
STATE_PREFIX = "tg:state:"
LAST_ALERT_KEY = "tg:last_alert_ts"
STATE_TTL_SECONDS = 600
ALERT_BATCH = 5


def main_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Статус", "callback_data": "st"},
                {"text": "🔍 Поиски", "callback_data": "se"},
            ],
            [
                {"text": "🔔 Алерты", "callback_data": "al"},
                {"text": "❓ Помощь", "callback_data": "h"},
            ],
        ]
    }


def back_keyboard(target: str = "m") -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "⬅️ Назад", "callback_data": target}]]}


def searches_keyboard(rows: list[tuple[str, str]]) -> dict[str, Any]:
    keyboard = [
        [{"text": f"🔎 {name[:44]}", "callback_data": f"s:{prefix}"}] for prefix, name in rows
    ]
    keyboard.append([{"text": "⬅️ Меню", "callback_data": "m"}])
    return {"inline_keyboard": keyboard}


def search_keyboard(prefix: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🚀 Запустить обход", "callback_data": f"c:{prefix}"}],
            [{"text": "📈 AI-дайджест", "callback_data": f"d:{prefix}"}],
            [{"text": "⬅️ К поискам", "callback_data": "se"}],
        ]
    }


def alerts_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Обновить", "callback_data": "al"},
                {"text": "🧹 Очистить новые", "callback_data": "acl"},
            ],
            [{"text": "⬅️ Меню", "callback_data": "m"}],
        ]
    }


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
        logger.info("telegram bot started (inline menu)")
        await asyncio.gather(self._poll_loop(), self._notify_loop())

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        if self._redis is not None:
            await self._redis.aclose()

    # --- Telegram API -------------------------------------------------
    async def _api(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert self._client is not None
        try:
            response = await self._client.post(f"/{method}", json=payload)
            return response.json()
        except Exception as error:  # noqa: BLE001 — сеть до Telegram может отвалиться
            logger.warning("%s failed: %s", method, error)
            return {}

    async def _send(self, chat_id: int, text: str, keyboard: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:3900],
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            payload["reply_markup"] = keyboard
        await self._api("sendMessage", payload)

    async def _edit(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        keyboard: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:3900],
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            payload["reply_markup"] = keyboard
        result = await self._api("editMessageText", payload)
        if not result.get("ok"):
            await self._send(chat_id, text, keyboard)

    async def _answer(self, callback_id: str, text: str | None = None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text[:200]
        await self._api("answerCallbackQuery", payload)

    # --- polling ------------------------------------------------------
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
                    callback = update.get("callback_query")
                    if callback:
                        await self._handle_callback(callback)
                        continue
                    message = update.get("message") or {}
                    chat_id = (message.get("chat") or {}).get("id")
                    text = (message.get("text") or "").strip()
                    if chat_id is None or not text:
                        continue
                    await self._handle_message(int(chat_id), text)
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

    async def _handle_message(self, chat_id: int, text: str) -> None:
        assert self._redis is not None
        command = text.split()[0].split("@")[0].lower()
        if command == "/logout":
            await self._redis.delete(f"{AUTH_PREFIX}{chat_id}")
            await self._send(chat_id, "Вы вышли. Для входа отправьте /start")
            return
        if not await self._authed(chat_id):
            await self._login_flow(chat_id, text)
            return
        if command in ("/start", "/menu"):
            await self._send(chat_id, self._menu_text(), main_keyboard())
        elif command == "/status":
            await self._send(chat_id, await self._status_text(), back_keyboard())
        elif command == "/searches":
            await self._send(chat_id, "Выберите поиск:", await self._searches_keyboard())
        elif command == "/alerts":
            await self._send(chat_id, await self._alerts_text(), alerts_keyboard())
        elif command == "/help":
            await self._send(chat_id, self._help_text(), main_keyboard())
        else:
            # неизвестная команда — показываем меню (минимум инструкций)
            await self._send(chat_id, self._menu_text(), main_keyboard())

    async def _login_flow(self, chat_id: int, text: str) -> None:
        state = await self._get_state(chat_id)
        if text.strip().lower() in ("/start", "start") or state is None:
            await self._set_state(chat_id, "login")
            await self._send(chat_id, "🔐 Введите логин:")
            return
        if state == "login":
            if secrets.compare_digest(text.strip(), self._login):
                await self._set_state(chat_id, "password")
                await self._send(chat_id, "🔑 Введите пароль:")
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
                    chat_id,
                    f"✅ Вход выполнен, сессия {days} дн.\n\n" + self._menu_text(),
                    main_keyboard(),
                )
            else:
                await self._set_state(chat_id, "login")
                await self._send(chat_id, "Неверный пароль. Начнём заново — введите логин:")

    # --- callbacks ----------------------------------------------------
    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        callback_id = str(callback.get("id") or "")
        message = callback.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        message_id = message.get("message_id")
        data = str(callback.get("data") or "")
        if chat_id is None or message_id is None:
            await self._answer(callback_id)
            return
        chat_id = int(chat_id)
        message_id = int(message_id)
        if not await self._authed(chat_id):
            await self._answer(callback_id, "Сначала войдите: /start")
            return

        if data == "m":
            await self._edit(chat_id, message_id, self._menu_text(), main_keyboard())
            await self._answer(callback_id)
        elif data == "st":
            await self._edit(chat_id, message_id, await self._status_text(), back_keyboard())
            await self._answer(callback_id)
        elif data == "se":
            await self._edit(
                chat_id, message_id, "Выберите поиск:", await self._searches_keyboard()
            )
            await self._answer(callback_id)
        elif data.startswith("s:"):
            await self._show_search(chat_id, message_id, data[2:], callback_id)
        elif data.startswith("c:"):
            await self._crawl(chat_id, message_id, data[2:], callback_id)
        elif data.startswith("d:"):
            await self._show_digest(chat_id, message_id, data[2:], callback_id)
        elif data == "al":
            await self._edit(chat_id, message_id, await self._alerts_text(), alerts_keyboard())
            await self._answer(callback_id)
        elif data == "acl":
            count = await self._count_new_alerts()
            if count == 0:
                await self._answer(callback_id, "Новых алертов нет")
                return
            await self._edit(
                chat_id,
                message_id,
                f"Очистить {count} новых алертов? Это необратимо.",
                {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Да, очистить", "callback_data": "acly"},
                            {"text": "Отмена", "callback_data": "al"},
                        ]
                    ]
                },
            )
            await self._answer(callback_id)
        elif data == "acly":
            deleted = await self._clear_new_alerts()
            await self._edit(
                chat_id,
                message_id,
                f"🧹 Очищено алертов: {deleted}",
                back_keyboard("al"),
            )
            await self._answer(callback_id, f"Очищено: {deleted}")
        elif data == "h":
            await self._edit(chat_id, message_id, self._help_text(), back_keyboard())
            await self._answer(callback_id)
        else:
            await self._answer(callback_id)

    # --- data ---------------------------------------------------------
    @staticmethod
    def _menu_text() -> str:
        return "🤖 *Авито-тулкит*\n\nВсё управление — кнопками ниже. Команды не нужны."

    @staticmethod
    def _help_text() -> str:
        return (
            "Как пользоваться:\n"
            "• 📊 Статус — поиски, лоты, воркер, очереди\n"
            "• 🔍 Поиски — список; откройте поиск, чтобы запустить обход или "
            "посмотреть дайджест\n"
            "• 🔔 Алерты — последние события и очистка\n\n"
            "Команды на всякий случай: /menu, /logout."
        )

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
        worker = "✅ жив" if health["worker_alive"] else "❌ НЕ ОТВЕЧАЕТ"
        return (
            f"📊 *Статус*\n\n"
            f"Поиски: {searches_active}/{searches_total} активных\n"
            f"Лотов на рынке: {listings_active}\n"
            f"Новых алертов: {alerts_new}\n"
            f"Воркер: {worker}\n"
            f"Очереди: обходы {health['crawl_queue']}, аналитика {health['analytics_queue']}"
        )

    async def _search_rows(self) -> list[Search]:
        factory = get_session_factory()
        try:
            async with factory() as session:
                return list(
                    (await session.execute(select(Search).order_by(Search.priority, Search.name)))
                    .scalars()
                    .all()
                )
        finally:
            await dispose_engine()

    async def _searches_keyboard(self) -> dict[str, Any]:
        rows = await self._search_rows()
        if not rows:
            return back_keyboard()
        return searches_keyboard([(str(row.id)[:8], row.name) for row in rows])

    async def _find_search(self, prefix: str) -> Search | None:
        prefix = prefix.strip().lower()
        if not prefix:
            return None
        rows = await self._search_rows()
        for row in rows:
            if str(row.id).lower().startswith(prefix):
                return row
        for row in rows:
            if prefix in row.name.lower():
                return row
        return None

    async def _show_search(
        self, chat_id: int, message_id: int, prefix: str, callback_id: str
    ) -> None:
        search = await self._find_search(prefix)
        if search is None:
            await self._answer(callback_id, "Поиск не найден")
            return
        state = "активен" if search.is_active else "на паузе"
        short = str(search.id)[:8]
        text = (
            f"🔍 *{search.name[:60]}*\n\n"
            f"Статус: {state}\n"
            f"Расписание: `{search.schedule_cron}`\n"
            f"Ссылка: {search.url}"
        )
        await self._edit(chat_id, message_id, text, search_keyboard(short))
        await self._answer(callback_id)

    async def _crawl(self, chat_id: int, message_id: int, prefix: str, callback_id: str) -> None:
        search = await self._find_search(prefix)
        if search is None:
            await self._answer(callback_id, "Поиск не найден")
            return
        from app.services.progress import CrawlProgress
        from app.workers.tasks import crawl_search

        assert self._redis is not None
        await CrawlProgress(self._redis, search.id).queued(search.name)
        crawl_search.send(str(search.id))
        await self._answer(callback_id, "🚀 Обход поставлен в очередь")
        state = "активен" if search.is_active else "на паузе"
        text = (
            f"🔍 *{search.name[:60]}*\n\n"
            f"Статус: {state}\n"
            f"🚀 Обход поставлен в очередь — прогресс смотрите в панели."
        )
        await self._edit(chat_id, message_id, text, search_keyboard(str(search.id)[:8]))

    async def _show_digest(
        self, chat_id: int, message_id: int, prefix: str, callback_id: str
    ) -> None:
        search = await self._find_search(prefix)
        if search is None:
            await self._answer(callback_id, "Поиск не найден")
            return
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
            text = (
                f"📈 *{search.name[:60]}*\n\n"
                "Дайджест ещё не готов. Сгенерируйте его на странице поиска в панели — "
                "после этого он появится здесь."
            )
        else:
            payload = row.payload or {}
            actions = payload.get("recommended_actions") or []
            lines = [
                f"📈 *{search.name[:60]}*",
                "",
                str(payload.get("headline", "")),
                str(payload.get("price_range_comment", "")),
            ]
            if actions:
                lines.append("")
                lines.append("Рекомендации:")
                lines.extend(f"• {str(action)[:120]}" for action in actions[:5])
            text = "\n".join(lines)
        await self._edit(chat_id, message_id, text, search_keyboard(str(search.id)[:8]))
        await self._answer(callback_id)

    async def _alerts_text(self) -> str:
        factory = get_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Alert)
                    .where(Alert.status == "new")
                    .order_by(Alert.created_at.desc())
                    .limit(ALERT_BATCH)
                )
                rows = result.scalars().all()
        finally:
            await dispose_engine()
        if not rows:
            return "🔔 *Алерты*\n\nНовых уведомлений нет."
        lines = ["🔔 *Последние алерты*", ""]
        for alert in rows:
            payload = alert.payload or {}
            title = payload.get("title") or payload.get("kind") or alert.type
            lines.append(f"• {alert.type}: {str(title)[:80]}")
        return "\n".join(lines)

    async def _count_new_alerts(self) -> int:
        factory = get_session_factory()
        try:
            async with factory() as session:
                return int(
                    await session.scalar(
                        select(func.count()).select_from(Alert).where(Alert.status == "new")
                    )
                    or 0
                )
        finally:
            await dispose_engine()

    async def _clear_new_alerts(self) -> int:
        factory = get_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(delete(Alert).where(Alert.status == "new"))
                await session.commit()
                return int(getattr(result, "rowcount", 0) or 0)
        finally:
            await dispose_engine()

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
        last_ts = float(raw_ts) if raw_ts else datetime.now(UTC).timestamp()
        factory = get_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Alert)
                    .where(
                        Alert.status == "new",
                        Alert.created_at > datetime.fromtimestamp(last_ts, tz=UTC),
                    )
                    .order_by(Alert.created_at)
                    .limit(20)
                )
                rows = result.scalars().all()
        finally:
            await dispose_engine()
        if not rows:
            await self._redis.set(LAST_ALERT_KEY, datetime.now(UTC).timestamp())
            return
        chat_ids: list[int] = []
        async for key in self._redis.scan_iter(f"{AUTH_PREFIX}*"):
            name = key.decode() if isinstance(key, bytes) else key
            suffix = name.removeprefix(AUTH_PREFIX)
            if suffix.lstrip("-").isdigit():
                chat_ids.append(int(suffix))
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
                await self._send(chat_id, text, alerts_keyboard())
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
