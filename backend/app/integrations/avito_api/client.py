import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

DEFAULT_BASE_URL = "https://api.avito.ru"
TOKEN_PATH = "/token"
DEFAULT_TOKEN_TTL_SECONDS = 3600
TOKEN_REFRESH_MARGIN_SECONDS = 60


class AvitoApiError(RuntimeError):
    pass


class AvitoApiNotConfiguredError(AvitoApiError):
    pass


class AvitoAuthError(AvitoApiError):
    pass


@dataclass(frozen=True, slots=True)
class AvitoCredentials:
    client_id: str
    client_secret: str
    user_id: int | None = None


@dataclass(frozen=True, slots=True)
class AvitoItem:
    item_id: int
    title: str
    price: float | None
    status: str | None
    url: str | None
    category: str | None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        return int(digits) if digits else None
    return None


def parse_price(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        digits = re.sub(r"[^\d.]", "", value.replace(",", "."))
        return float(digits) if digits else None
    if isinstance(value, Mapping):
        for key in ("value", "price", "amount"):
            if key in value:
                parsed = parse_price(value[key])
                if parsed is not None:
                    return parsed
    return None


def parse_item(payload: Mapping[str, Any]) -> AvitoItem | None:
    item_id = _as_int(payload.get("id"))
    title = str(payload.get("title") or "").strip()
    if item_id is None or not title:
        return None
    category = payload.get("category")
    if isinstance(category, Mapping):
        category = category.get("name")
    url = payload.get("url") or payload.get("urlPath")
    status = payload.get("status")
    return AvitoItem(
        item_id=item_id,
        title=title,
        price=parse_price(payload.get("price")),
        status=str(status) if status is not None else None,
        url=str(url) if url else None,
        category=str(category) if category else None,
    )


def parse_items_response(payload: Mapping[str, Any]) -> list[AvitoItem]:
    raw: Any = payload.get("resources")
    if raw is None:
        raw = payload.get("items")
    if isinstance(raw, Mapping):
        raw = raw.get("items")
    if not isinstance(raw, list):
        return []
    items: list[AvitoItem] = []
    for entry in raw:
        if isinstance(entry, Mapping):
            parsed = parse_item(entry)
            if parsed is not None:
                items.append(parsed)
    return items


class AvitoApiClient:
    """Клиент официального Avito Business API (OAuth2 client_credentials).

    Реализует только чтение своих объявлений; операции записи появятся
    в фазе массового репрайсинга с отдельным safety-гейтом.
    """

    def __init__(
        self,
        credentials: AvitoCredentials,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        settings = get_settings()
        self._credentials = credentials
        self._base_url = (base_url or settings.avito_base_url or DEFAULT_BASE_URL).rstrip("/")
        self._client = http_client
        self._owns_client = http_client is None
        if http_client is not None and not str(http_client.base_url):
            http_client.base_url = httpx.URL(self._base_url)
        self._timeout = timeout
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._user_id = credentials.user_id

    @classmethod
    def from_settings(cls) -> "AvitoApiClient":
        settings = get_settings()
        if not settings.avito_client_id or not settings.avito_client_secret:
            raise AvitoApiNotConfiguredError(
                "AVITO_CLIENT_ID/AVITO_CLIENT_SECRET не заданы. "
                "Получить доступ: avito.ru/professionals/api"
            )
        return cls(
            AvitoCredentials(
                client_id=settings.avito_client_id,
                client_secret=settings.avito_client_secret,
                user_id=settings.avito_user_id,
            )
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        return self._client

    async def get_access_token(self) -> str:
        if self._token is not None and time.monotonic() < self._token_expires_at:
            return self._token
        client = await self._get_client()
        response = await client.post(
            TOKEN_PATH,
            data={
                "grant_type": "client_credentials",
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
            },
        )
        if response.status_code >= 400:
            raise AvitoAuthError(f"token request failed: {response.status_code}")
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise AvitoAuthError("token response has no access_token")
        expires_in = _as_int(payload.get("expires_in")) or DEFAULT_TOKEN_TTL_SECONDS
        self._token = str(token)
        self._token_expires_at = time.monotonic() + max(
            expires_in - TOKEN_REFRESH_MARGIN_SECONDS, 30
        )
        return self._token

    async def _authorized_get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        token = await self.get_access_token()
        client = await self._get_client()
        response = await client.get(
            path,
            params=dict(params or {}),
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code in (401, 403):
            self._token = None
            raise AvitoAuthError(f"GET {path} unauthorized: {response.status_code}")
        if response.status_code >= 400:
            raise AvitoApiError(f"GET {path} failed: {response.status_code}")
        return response.json()

    async def get_self(self) -> dict[str, Any]:
        payload = await self._authorized_get("/core/v1/accounts/self")
        if not isinstance(payload, Mapping):
            raise AvitoApiError("unexpected self payload")
        return dict(payload)

    async def resolve_user_id(self) -> int:
        if self._user_id is not None:
            return self._user_id
        payload = await self.get_self()
        user_id = _as_int(payload.get("id"))
        account = payload.get("account")
        if user_id is None and isinstance(account, Mapping):
            user_id = _as_int(account.get("id"))
        if user_id is None:
            raise AvitoApiError("cannot resolve user_id (set AVITO_USER_ID)")
        self._user_id = user_id
        return user_id

    async def list_items(
        self,
        page: int = 1,
        per_page: int = 100,
        status: str = "active",
        user_id: int | None = None,
    ) -> list[AvitoItem]:
        resolved_user_id = user_id or await self.resolve_user_id()
        payload = await self._authorized_get(
            f"/core/v1/accounts/{resolved_user_id}/items/",
            params={"page": page, "per_page": per_page, "status": status},
        )
        if not isinstance(payload, Mapping):
            raise AvitoApiError("unexpected items payload")
        return parse_items_response(payload)

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
