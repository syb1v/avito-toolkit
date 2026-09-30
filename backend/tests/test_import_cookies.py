import json

from scripts.import_cookies import parse_cookie_input


def test_parse_cookie_editor_json() -> None:
    payload = json.dumps(
        [
            {
                "name": "v",
                "value": "abc",
                "domain": ".avito.ru",
                "path": "/",
                "expirationDate": 1790000000.5,
                "httpOnly": True,
                "secure": True,
                "sameSite": "no_restriction",
            },
            {
                "name": "other",
                "value": "x",
                "domain": ".example.com",
            },
        ]
    )
    cookies = parse_cookie_input(payload)
    assert len(cookies) == 1
    cookie = cookies[0]
    assert cookie["name"] == "v"
    assert cookie["domain"] == ".avito.ru"
    assert cookie["sameSite"] == "None"
    assert cookie["expires"] == 1790000000.5


def test_parse_raw_cookie_header() -> None:
    cookies = parse_cookie_input("v=abc; u=def=ghi; ft=1")
    assert [cookie["name"] for cookie in cookies] == ["v", "u", "ft"]
    assert cookies[1]["value"] == "def=ghi"
    assert all(cookie["domain"] == ".avito.ru" for cookie in cookies)


def test_parse_empty_input() -> None:
    assert parse_cookie_input("") == []
    assert parse_cookie_input("   ") == []


def test_json_without_avito_cookies_returns_empty() -> None:
    payload = json.dumps([{"name": "a", "value": "b", "domain": ".example.com"}])
    assert parse_cookie_input(payload) == []
