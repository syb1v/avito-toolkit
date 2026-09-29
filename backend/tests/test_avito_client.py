import httpx
import pytest

from app.integrations.avito_api.client import (
    AvitoApiClient,
    AvitoAuthError,
    AvitoCredentials,
    parse_item,
    parse_items_response,
    parse_price,
)

TOKEN_RESPONSE = {
    "access_token": "test-token",
    "expires_in": 3600,
    "token_type": "Bearer",
}
ITEMS_PAYLOAD = {
    "resources": [
        {
            "id": 101,
            "title": "iPhone 15 128 GB",
            "price": {"value": 75000},
            "status": "active",
            "url": "https://www.avito.ru/item/101",
            "category": {"name": "Телефоны"},
        },
        {
            "id": "202",
            "title": "Samsung Galaxy S23",
            "price": "45 990",
            "status": "active",
        },
    ]
}


def _make_client(handler) -> AvitoApiClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="https://api.avito.ru")
    return AvitoApiClient(
        AvitoCredentials("client-id", "secret", user_id=42), http_client=http_client
    )


async def test_list_items_uses_cached_token() -> None:
    calls = {"token": 0, "items": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            calls["token"] += 1
            assert "grant_type=client_credentials" in request.content.decode()
            return httpx.Response(200, json=TOKEN_RESPONSE)
        if request.url.path == "/core/v1/accounts/42/items/":
            calls["items"] += 1
            assert request.headers["authorization"] == "Bearer test-token"
            params = dict(request.url.params)
            assert params["per_page"] == "100"
            return httpx.Response(200, json=ITEMS_PAYLOAD)
        return httpx.Response(404)

    client = _make_client(handler)
    try:
        items = await client.list_items()
        assert [item.item_id for item in items] == [101, 202]
        assert items[0].price == 75000.0
        assert items[0].category == "Телефоны"
        assert items[1].price == 45990.0
        await client.list_items(page=2)
        assert calls["token"] == 1
        assert calls["items"] == 2
    finally:
        await client.close()


async def test_token_failure_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    client = _make_client(handler)
    try:
        with pytest.raises(AvitoAuthError):
            await client.get_access_token()
    finally:
        await client.close()


async def test_unauthorized_clears_token_and_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(403, json={})

    client = _make_client(handler)
    try:
        with pytest.raises(AvitoAuthError):
            await client.list_items()
        assert client._token is None
    finally:
        await client.close()


def test_parse_price_variants() -> None:
    assert parse_price(1000) == 1000.0
    assert parse_price("12 000 ₽") == 12000.0
    assert parse_price({"value": 999}) == 999.0
    assert parse_price({"price": {"value": "1 500"}}) == 1500.0
    assert parse_price(None) is None
    assert parse_price(True) is None


def test_parse_item_requires_id_and_title() -> None:
    item = parse_item(
        {
            "id": "123",
            "title": "iPhone 15",
            "price": {"value": "75 000"},
            "status": "active",
            "category": "Телефоны",
        }
    )
    assert item is not None
    assert item.item_id == 123
    assert item.price == 75000.0
    assert parse_item({"title": "без id"}) is None
    assert parse_item({"id": 1}) is None


def test_parse_items_response_variants() -> None:
    assert len(parse_items_response({"resources": [{"id": 1, "title": "A", "price": 1}]})) == 1
    assert len(parse_items_response({"items": [{"id": 2, "title": "B", "price": 2}]})) == 1
    assert parse_items_response({}) == []
    assert parse_items_response({"resources": "broken"}) == []
