"""Официальный API Авито: токены приложений, правка цены, карточка объявления.

Документация: https://developers.avito.ru/api-catalog/item/documentation
Креды: у аккаунта в UI (api_client_id/secret) или общие из env.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from redis.asyncio import Redis

from app.config import Settings

logger = logging.getLogger(__name__)

TOKEN_KEY = "avito:api-token:{client_id}"
TOKEN_TTL_SECONDS = 23 * 3600
API_TIMEOUT_SECONDS = 20.0


class AvitoApiError(Exception):
    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(f"Avito API {code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ApiCredentials:
    client_id: str
    client_secret: str


def env_credentials(settings: Settings) -> ApiCredentials | None:
    if settings.avito_client_id and settings.avito_client_secret:
        return ApiCredentials(settings.avito_client_id, settings.avito_client_secret)
    return None


def account_credentials(account: Any) -> ApiCredentials | None:
    if getattr(account, "api_client_id", None) and getattr(account, "api_client_secret", None):
        return ApiCredentials(account.api_client_id, account.api_client_secret)
    return None


def api_configured(settings: Settings, account: Any | None = None) -> bool:
    return account_credentials(account) is not None or env_credentials(settings) is not None


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


async def get_access_token(redis: Redis, settings: Settings, credentials: ApiCredentials) -> str:
    key = TOKEN_KEY.format(client_id=credentials.client_id)
    cached = await redis.get(key)
    if cached:
        return cached.decode() if isinstance(cached, bytes) else cached
    data = {
        "grant_type": "client_credentials",
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
    }
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{settings.avito_api_base}/token", data=data)
    if response.status_code != 200:
        raise parse_error(response.status_code, response.text)
    token = response.json().get("access_token")
    if not token:
        raise AvitoApiError(response.status_code, "нет access_token в ответе")
    await redis.set(key, token, ex=TOKEN_TTL_SECONDS)
    return token


async def _request(
    redis: Redis,
    settings: Settings,
    credentials: ApiCredentials,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = await get_access_token(redis, settings, credentials)
    url = f"{settings.avito_api_base}{path}"
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
        response = await client.request(
            method,
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    if response.status_code != 200:
        raise parse_error(response.status_code, response.text)
    data = response.json()
    return data if isinstance(data, dict) else {}


async def fetch_self(
    redis: Redis, settings: Settings, credentials: ApiCredentials
) -> dict[str, Any]:
    return await _request(redis, settings, credentials, "GET", "/core/v1/accounts/self")


async def fetch_item_info(
    redis: Redis,
    settings: Settings,
    credentials: ApiCredentials,
    user_id: int,
    item_id: int,
) -> dict[str, Any]:
    return await _request(
        redis,
        settings,
        credentials,
        "GET",
        f"/core/v1/accounts/{user_id}/items/{item_id}/",
    )


async def update_item_price(
    redis: Redis,
    settings: Settings,
    item_id: int,
    price: float,
    credentials: ApiCredentials | None = None,
) -> float:
    """Меняет цену объявления через официальный API. Возвращает записанную цену."""
    creds = credentials or env_credentials(settings)
    if creds is None:
        raise AvitoApiError(None, "не заданы API-ключи")
    body = {"price": int(round(price))}
    data = await _request(
        redis, settings, creds, "POST", f"/core/v1/items/{item_id}/update_price", payload=body
    )
    result = data.get("result")
    if isinstance(result, dict) and result.get("success") is False:
        raise AvitoApiError(200, str(result)[:200])
    logger.info("avito api price updated: item=%s price=%s", item_id, body["price"])
    return float(body["price"])
