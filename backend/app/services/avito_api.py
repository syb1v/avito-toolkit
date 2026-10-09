"""Официальный API Авито: токен приложения и правка цены объявления.

Документация: https://developers.avito.ru/api-catalog/item/documentation
Авторизация приложения: POST /token (client_credentials), кэш токена в Redis.
"""

import json
import logging

import httpx
from redis.asyncio import Redis

from app.config import Settings

logger = logging.getLogger(__name__)

TOKEN_KEY = "avito:api-token"
TOKEN_TTL_SECONDS = 23 * 3600
API_TIMEOUT_SECONDS = 20.0


class AvitoApiError(Exception):
    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(f"Avito API {code}: {message}")
        self.code = code
        self.message = message


def api_configured(settings: Settings) -> bool:
    return bool(settings.avito_client_id and settings.avito_client_secret)


async def get_access_token(redis: Redis, settings: Settings) -> str:
    cached = await redis.get(TOKEN_KEY)
    if cached:
        return cached.decode() if isinstance(cached, bytes) else cached
    url = f"{settings.avito_api_base}/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.avito_client_id,
        "client_secret": settings.avito_client_secret,
    }
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
        response = await client.post(url, data=data)
    if response.status_code != 200:
        raise AvitoApiError(response.status_code, response.text[:200])
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise AvitoApiError(response.status_code, "нет access_token в ответе")
    await redis.set(TOKEN_KEY, token, ex=TOKEN_TTL_SECONDS)
    return token


def parse_error(status: int, body: str) -> AvitoApiError:
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return AvitoApiError(status, body[:200])
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return AvitoApiError(int(error.get("code") or status), str(error.get("message") or body))
    message = data.get("message") if isinstance(data, dict) else None
    return AvitoApiError(status, str(message or body)[:200])


async def update_item_price(redis: Redis, settings: Settings, item_id: int, price: float) -> float:
    """Меняет цену объявления через официальный API. Возвращает записанную цену."""
    token = await get_access_token(redis, settings)
    url = f"{settings.avito_api_base}/core/v1/items/{item_id}/update_price"
    body = {"price": int(round(price))}
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    if response.status_code != 200:
        raise parse_error(response.status_code, response.text)
    data = response.json()
    result = data.get("result") if isinstance(data, dict) else None
    if isinstance(result, dict) and result.get("success") is False:
        raise AvitoApiError(response.status_code, str(result)[:200])
    logger.info("avito api price updated: item=%s price=%s", item_id, body["price"])
    return float(body["price"])
