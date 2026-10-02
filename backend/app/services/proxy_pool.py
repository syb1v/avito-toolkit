"""Пул прокси: парсинг списка, ротация, кулдауны и healthcheck."""

import asyncio
import hashlib
import json
import random
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx
from redis.asyncio import Redis

from app.config import get_settings

SUPPORTED_SCHEMES = ("http", "https", "socks5", "socks5h", "socks4")
DEFAULT_SCHEME = "http"
STATE_PREFIX = "proxy:state:"
RR_INDEX_KEY = "proxy:rr_index"
HEALTHCHECK_CONCURRENCY = 5
MASK_VISIBLE = 4
AVITO_PROBE_URL = "https://www.avito.ru/all?q=iphone"
AVITO_PROBE_MARKERS = ("доступ ограничен", "проблема с ip", "hcaptcha", "firewallcaptcha")


class ProxyParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProxyEntry:
    url: str
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @property
    def label(self) -> str:
        auth = f"{self.username}@" if self.username else ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def is_socks(self) -> bool:
        return self.scheme.startswith("socks")

    @property
    def key(self) -> str:
        digest = hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:12]
        return f"{STATE_PREFIX}{digest}"


def _build_url(
    scheme: str,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
) -> str:
    auth = ""
    if username:
        auth = quote(username, safe="")
        if password:
            auth += f":{quote(password, safe='')}"
        auth += "@"
    return f"{scheme}://{auth}{host}:{port}"


def parse_proxy_entry(raw: str) -> ProxyEntry:
    """Поддерживает форматы:

    - ``http://user:pass@host:port`` / ``socks5://host:port``
    - ``host:port:user:pass``
    - ``user:pass@host:port``
    - ``host:port``
    """
    value = raw.strip()
    if not value:
        raise ProxyParseError("пустая строка прокси")

    scheme = DEFAULT_SCHEME
    username: str | None = None
    password: str | None = None

    if "://" in value:
        parsed = urlparse(value)
        scheme = parsed.scheme.lower()
        host = parsed.hostname or ""
        port = parsed.port
        username = unquote(parsed.username) if parsed.username else None
        password = unquote(parsed.password) if parsed.password else None
    elif "@" in value:
        auth_part, _, host_part = value.partition("@")
        username, _, password = auth_part.partition(":")
        host, _, port_raw = host_part.rpartition(":")
        port = int(port_raw) if port_raw.isdigit() else None
    else:
        parts = value.split(":")
        if len(parts) == 2:
            host, port_raw = parts
            port = int(port_raw) if port_raw.isdigit() else None
        elif len(parts) == 4:
            host, port_raw, username, password = parts
            port = int(port_raw) if port_raw.isdigit() else None
        else:
            raise ProxyParseError(f"неизвестный формат прокси: {raw!r}")

    if scheme not in SUPPORTED_SCHEMES:
        raise ProxyParseError(f"неподдерживаемая схема прокси: {scheme}")
    if scheme == "socks5h":
        scheme = "socks5"
    if not host or port is None or not (0 < port < 65536):
        raise ProxyParseError(f"некорректный host:port в прокси: {raw!r}")
    return ProxyEntry(
        url=_build_url(scheme, host, port, username, password),
        scheme=scheme,
        host=host,
        port=port,
        username=username,
        password=password,
    )


def parse_proxy_list(raw: str) -> list[ProxyEntry]:
    entries: list[ProxyEntry] = []
    seen: set[str] = set()
    for chunk in re.split(r"[\n;,]+", raw):
        if not chunk.strip():
            continue
        entry = parse_proxy_entry(chunk)
        if entry.url in seen:
            continue
        seen.add(entry.url)
        entries.append(entry)
    return entries


class ProxyPool:
    """Пул с состоянием в Redis: ротация, кулдаун упавших, счётчики."""

    def __init__(
        self,
        entries: Sequence[ProxyEntry],
        redis: Redis,
        *,
        mode: str = "round_robin",
        cooldown_seconds: int = 300,
        max_failures: int = 3,
        antibot_cooldown_seconds: int = 1800,
    ) -> None:
        if not entries:
            raise ValueError("пустой пул прокси")
        self._entries = list(entries)
        self._redis = redis
        self._mode = mode if mode in ("round_robin", "random") else "round_robin"
        self._cooldown = cooldown_seconds
        self._max_failures = max(1, max_failures)
        self._antibot_cooldown = max(0, antibot_cooldown_seconds)

    @property
    def entries(self) -> list[ProxyEntry]:
        return list(self._entries)

    @property
    def mode(self) -> str:
        return self._mode

    async def _state(self, entry: ProxyEntry) -> dict[str, str]:
        data = await self._redis.hgetall(entry.key)
        return {
            (key.decode() if isinstance(key, bytes) else key): (
                value.decode() if isinstance(value, bytes) else value
            )
            for key, value in data.items()
        }

    async def _healthy(self, entry: ProxyEntry) -> bool:
        state = await self._state(entry)
        now = time.time()
        cooldown_until = float(state.get("cooldown_until") or 0)
        antibot_until = float(state.get("antibot_until") or 0)
        return cooldown_until <= now and antibot_until <= now

    async def next(self) -> ProxyEntry:
        healthy: list[ProxyEntry] = []
        for entry in self._entries:
            if await self._healthy(entry):
                healthy.append(entry)
        candidates = healthy or self._entries  # все в кулдауне — «полуоткрытая» попытка
        if self._mode == "random":
            return random.choice(candidates)
        index = await self._redis.incr(RR_INDEX_KEY)
        return candidates[(index - 1) % len(candidates)]

    async def report_success(
        self,
        entry: ProxyEntry,
        *,
        latency_ms: int | None = None,
        avito: bool = False,
    ) -> None:
        """Успех канала. Метку антибота снимает только успех именно через Авито."""
        mapping: dict[str, Any] = {
            "failures": 0,
            "cooldown_until": 0,
            "last_ok": datetime.now(UTC).isoformat(),
            "last_error": "",
        }
        if avito:
            mapping["antibot_until"] = 0
        if latency_ms is not None:
            mapping["latency_ms"] = latency_ms
        await self._redis.hset(entry.key, mapping=mapping)  # type: ignore[arg-type]

    async def report_failure(self, entry: ProxyEntry, error: str) -> None:
        failures = await self._redis.hincrby(entry.key, "failures", 1)
        mapping: dict[str, Any] = {"last_error": error[:200]}
        if failures >= self._max_failures:
            mapping["cooldown_until"] = int(time.time()) + self._cooldown
        await self._redis.hset(entry.key, mapping=mapping)  # type: ignore[arg-type]

    async def report_antibot(self, entry: ProxyEntry, error: str = "avito challenge") -> None:
        """Антибот-заглушка Авито: прокси живой, но сайт его не пускает.

        Не наращивает failures (канал работает), но помечает маршрут
        ``antibot_until`` — ротация предпочтёт другой прокси, а панель
        покажет реальную причину.
        """
        mapping: dict[str, Any] = {
            "last_error": error[:200],
            "antibot_until": int(time.time()) + self._antibot_cooldown,
        }
        await self._redis.hset(entry.key, mapping=mapping)  # type: ignore[arg-type]

    async def status(self) -> dict[str, Any]:
        now = time.time()
        rows: list[dict[str, Any]] = []
        alive = 0
        cooling = 0
        antibot_blocked = 0
        for entry in self._entries:
            state = await self._state(entry)
            failures = int(state.get("failures") or 0)
            cooldown_until = float(state.get("cooldown_until") or 0)
            antibot_until = float(state.get("antibot_until") or 0)
            in_cooldown = cooldown_until > now
            is_antibot = antibot_until > now
            healthy = not in_cooldown and not is_antibot
            if healthy:
                alive += 1
            if in_cooldown:
                cooling += 1
            if is_antibot:
                antibot_blocked += 1
            rows.append(
                {
                    "label": entry.label,
                    "scheme": entry.scheme,
                    "healthy": healthy,
                    "failures": failures,
                    "cooldown_seconds_left": max(0, int(cooldown_until - now)),
                    "antibot_blocked": is_antibot,
                    "antibot_seconds_left": max(0, int(antibot_until - now)),
                    "last_ok": state.get("last_ok") or None,
                    "last_error": state.get("last_error") or None,
                    "latency_ms": int(state["latency_ms"]) if state.get("latency_ms") else None,
                    "exit_ip": state.get("exit_ip") or None,
                }
            )
        return {
            "enabled": True,
            "mode": self._mode,
            "count": len(rows),
            "alive": alive,
            "in_cooldown": cooling,
            "antibot_blocked": antibot_blocked,
            "entries": rows,
        }

    async def check(
        self,
        entry: ProxyEntry,
        *,
        url: str,
        timeout: float,
        client_factory: Callable[[ProxyEntry], httpx.AsyncClient] | None = None,
    ) -> bool:
        factory = client_factory or self._default_client
        started = time.monotonic()
        try:
            async with factory(entry) as client:
                response = await client.get(url, timeout=timeout)
            latency_ms = int((time.monotonic() - started) * 1000)
            if response.status_code >= 400:
                await self.report_failure(entry, f"HTTP {response.status_code}")
                return False
            exit_ip = _extract_exit_ip(response)
            await self.report_success(entry, latency_ms=latency_ms)
            if exit_ip:
                await self._redis.hset(entry.key, mapping={"exit_ip": exit_ip})
            return True
        except Exception as error:
            await self.report_failure(entry, f"{type(error).__name__}: {error}")
            return False

    @staticmethod
    def _default_client(entry: ProxyEntry) -> httpx.AsyncClient:
        return httpx.AsyncClient(proxy=entry.url, trust_env=False)

    async def check_avito(
        self,
        entry: ProxyEntry,
        *,
        url: str = AVITO_PROBE_URL,
        timeout: float = 20.0,
        client_factory: Callable[[ProxyEntry], httpx.AsyncClient] | None = None,
    ) -> bool:
        """Проверяет, пускает ли Авито трафик через этот прокси."""
        factory = client_factory or self._default_client
        try:
            async with factory(entry) as client:
                response = await client.get(
                    url,
                    timeout=timeout,
                    headers={"Accept-Language": "ru-RU,ru;q=0.9"},
                )
            body = response.text.lower()
            if response.status_code >= 400 or any(m in body for m in AVITO_PROBE_MARKERS):
                await self.report_antibot(entry, f"avito HTTP {response.status_code}")
                return False
            await self.report_success(entry, avito=True)
            return True
        except Exception as error:
            await self.report_failure(entry, f"{type(error).__name__}: {error}")
            return False

    async def check_all(
        self,
        *,
        url: str | None = None,
        timeout: float | None = None,
        client_factory: Callable[[ProxyEntry], httpx.AsyncClient] | None = None,
        avito: bool = False,
    ) -> dict[str, Any]:
        settings = get_settings()
        check_url = url or settings.proxy_healthcheck_url
        check_timeout = timeout or settings.proxy_healthcheck_timeout
        semaphore = asyncio.Semaphore(HEALTHCHECK_CONCURRENCY)

        async def _one(entry: ProxyEntry) -> bool:
            async with semaphore:
                ok = await self.check(
                    entry,
                    url=check_url,
                    timeout=check_timeout,
                    client_factory=client_factory,
                )
                if not avito or not ok:
                    return ok
                return await self.check_avito(
                    entry,
                    timeout=max(check_timeout, 20.0),
                    client_factory=client_factory,
                )

        results = await asyncio.gather(*(_one(entry) for entry in self._entries))
        return {
            "checked": len(results),
            "ok": sum(1 for result in results if result),
            "failed": sum(1 for result in results if not result),
            "avito_checked": avito,
        }


def _extract_exit_ip(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("ip"), str):
            return payload["ip"]
    except (json.JSONDecodeError, ValueError):
        pass
    text = response.text.strip()
    return text if text and len(text) <= 64 else None


def build_proxy_pool(redis: Redis, *, force: bool = False) -> ProxyPool | None:
    """Собирает пул из PROXY_LIST; для совместимости учитывает PROXY_URL.

    ``force=True`` (панель/healthcheck) собирает пул даже при PROXY_ENABLED=false,
    чтобы прокси можно было проверить и включить позже.
    """
    settings = get_settings()
    entries = parse_proxy_list(settings.proxy_list)
    if not entries and settings.proxy_enabled and settings.proxy_url:
        entries = parse_proxy_list(settings.proxy_url)
    if not entries:
        return None
    if not settings.proxy_enabled and not force:
        return None
    return ProxyPool(
        entries,
        redis,
        mode=settings.proxy_rotation,
        cooldown_seconds=settings.proxy_cooldown_seconds,
        max_failures=settings.proxy_max_failures,
        antibot_cooldown_seconds=settings.proxy_antibot_cooldown_seconds,
    )
