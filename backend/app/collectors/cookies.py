import json

from redis.asyncio import Redis

DEFAULT_TTL_SECONDS = 12 * 60 * 60


class CookieStore:
    """Cookie-сессии в Redis, привязанные к выходному IP прокси.

    Level 2 (браузер) получает cookies после прохождения JS-челленджа и
    складывает их сюда; Level 1 переиспользует их для HTTP-запросов.
    """

    def __init__(self, redis: Redis, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(domain: str, ip: str | None) -> str:
        return f"cookies:{domain}:{ip or 'local'}"

    async def get(self, domain: str, ip: str | None = None) -> dict[str, str] | None:
        raw = await self._redis.get(self._key(domain, ip))
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, domain: str, cookies: dict[str, str], ip: str | None = None) -> None:
        await self._redis.set(self._key(domain, ip), json.dumps(cookies), ex=self._ttl)

    async def delete(self, domain: str, ip: str | None = None) -> None:
        await self._redis.delete(self._key(domain, ip))
