import json
import sys
import types

from scripts.import_cookies import cookies_from_browser, parse_cookie_input


class _FakeCookie:
    def __init__(self, domain: str, name: str, value: str, expires: int | None = None) -> None:
        self.domain = domain
        self.name = name
        self.value = value
        self.path = "/"
        self.secure = True
        self.expires = expires

    def has_nonstandard_attr(self, name: str) -> bool:
        return name == "httponly"


def test_cookies_from_browser(monkeypatch) -> None:
    fake = types.SimpleNamespace(
        brave=lambda domain_name: [
            _FakeCookie(".avito.ru", "sessid", "secret", 1890000000),
            _FakeCookie("example.com", "other", "x"),
            _FakeCookie(".avito.ru", "u", "42"),
        ]
    )
    monkeypatch.setitem(sys.modules, "browser_cookie3", fake)
    cookies = cookies_from_browser("brave")
    assert [cookie["name"] for cookie in cookies] == ["sessid", "u"]
    assert cookies[0]["expires"] == 1890000000.0
    assert "expires" not in cookies[1]
    assert cookies[0]["sameSite"] == "Lax"


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
