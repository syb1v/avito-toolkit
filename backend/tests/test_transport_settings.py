from app.collectors.transport.browser_patchright import (
    BrowserTransport,
    proxy_settings,
)


def test_proxy_settings_with_credentials() -> None:
    settings = proxy_settings("http://user:secret@proxy.example.com:8080")
    assert settings == {
        "server": "http://proxy.example.com:8080",
        "username": "user",
        "password": "secret",
    }


def test_proxy_settings_without_credentials() -> None:
    settings = proxy_settings("socks5://10.0.0.1:1080")
    assert settings == {"server": "socks5://10.0.0.1:1080"}


def test_is_challenge_detects_antibot_pages() -> None:
    assert BrowserTransport._is_challenge(
        "<html><title>Доступ ограничен: проблема с IP</title></html>"
    )
    assert BrowserTransport._is_challenge("<html>firewallCaptcha challenge</html>")
    assert BrowserTransport._is_challenge("<html>Проверка безопасности</html>")
    assert not BrowserTransport._is_challenge("<html>обычная страница выдачи</html>")
