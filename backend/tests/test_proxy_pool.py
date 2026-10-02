import fakeredis.aioredis
import httpx
import pytest

from app.services.proxy_pool import (
    ProxyEntry,
    ProxyParseError,
    ProxyPool,
    parse_proxy_entry,
    parse_proxy_list,
)


def test_parse_url_forms() -> None:
    entry = parse_proxy_entry("http://user:p%40ss@1.2.3.4:8080")
    assert entry.scheme == "http"
    assert entry.host == "1.2.3.4"
    assert entry.port == 8080
    assert entry.username == "user"
    assert entry.password == "p@ss"
    assert entry.url == "http://user:p%40ss@1.2.3.4:8080"

    socks = parse_proxy_entry("socks5://5.6.7.8:1080")
    assert socks.is_socks is True
    assert socks.url == "socks5://5.6.7.8:1080"

    socksh = parse_proxy_entry("socks5h://5.6.7.8:1080")
    assert socksh.scheme == "socks5"


def test_parse_colon_and_at_forms() -> None:
    colon = parse_proxy_entry("1.2.3.4:8080:user:pass")
    assert colon.url == "http://user:pass@1.2.3.4:8080"
    at_form = parse_proxy_entry("user:pass@1.2.3.4:8080")
    assert at_form.url == "http://user:pass@1.2.3.4:8080"
    plain = parse_proxy_entry("1.2.3.4:8080")
    assert plain.url == "http://1.2.3.4:8080"
    assert plain.username is None


def test_parse_errors() -> None:
    with pytest.raises(ProxyParseError):
        parse_proxy_entry("ftp://1.2.3.4:21")
    with pytest.raises(ProxyParseError):
        parse_proxy_entry("1.2.3.4")
    with pytest.raises(ProxyParseError):
        parse_proxy_entry("")


def test_parse_list_dedup_and_separators() -> None:
    entries = parse_proxy_list("1.2.3.4:8080, 5.6.7.8:1080\n1.2.3.4:8080;")
    assert [entry.host for entry in entries] == ["1.2.3.4", "5.6.7.8"]


@pytest.fixture()
async def redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


async def _entries() -> list[ProxyEntry]:
    return [parse_proxy_entry(f"http://10.0.0.{index}:8080") for index in range(1, 4)]


async def test_pool_round_robin_and_cooldown(redis) -> None:
    pool = ProxyPool(
        await _entries(), redis, mode="round_robin", cooldown_seconds=60, max_failures=2
    )
    picks = [(await pool.next()).host for _ in range(4)]
    assert picks[:3] == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
    assert picks[3] == "10.0.0.1"

    first = pool.entries[0]
    await pool.report_failure(first, "timeout")
    await pool.report_failure(first, "timeout")
    status = await pool.status()
    assert status["in_cooldown"] == 1
    assert status["entries"][0]["healthy"] is False

    picks2 = [(await pool.next()).host for _ in range(3)]
    assert "10.0.0.1" not in picks2

    await pool.report_success(first, latency_ms=120)
    status = await pool.status()
    assert status["alive"] == 3
    assert status["entries"][0]["latency_ms"] == 120


async def test_antibot_does_not_kill_proxy(redis) -> None:
    pool = ProxyPool(await _entries(), redis, max_failures=2, antibot_cooldown_seconds=600)
    first = pool.entries[0]
    await pool.report_antibot(first, "avito challenge")
    status = await pool.status()
    assert status["entries"][0]["failures"] == 0
    assert status["entries"][0]["antibot_blocked"] is True
    assert status["entries"][0]["healthy"] is False
    assert status["antibot_blocked"] == 1

    picks = [(await pool.next()).host for _ in range(2)]
    assert "10.0.0.1" not in picks

    await pool.report_success(first)
    status = await pool.status()
    assert status["entries"][0]["antibot_blocked"] is True  # generic-успех метку не снимает

    await pool.report_success(first, avito=True)
    status = await pool.status()
    assert status["entries"][0]["antibot_blocked"] is False
    assert status["entries"][0]["healthy"] is True


async def test_pool_random_mode(redis) -> None:
    pool = ProxyPool(await _entries(), redis, mode="random")
    picks = {(await pool.next()).host for _ in range(20)}
    assert picks.issubset({"10.0.0.1", "10.0.0.2", "10.0.0.3"})


async def test_check_all_with_fake_http(redis) -> None:
    pool = ProxyPool(await _entries(), redis)

    def handler(request: httpx.Request) -> httpx.Response:
        if "10.0.0.1" in str(request.url) or request.url.host == "check.test":
            return httpx.Response(200, json={"ip": "9.9.9.9"})
        return httpx.Response(500)

    def factory(entry: ProxyEntry) -> httpx.AsyncClient:
        if entry.host == "10.0.0.2":
            return httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(500))
            )
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await pool.check_all(url="https://check.test/ip", client_factory=factory)
    assert result == {"checked": 3, "ok": 2, "failed": 1, "avito_checked": False}

    status = await pool.status()
    assert status["entries"][1]["healthy"] is True  # одна ошибка — кулдауна ещё нет
    assert status["entries"][1]["last_error"] is not None
    assert status["entries"][0]["exit_ip"] == "9.9.9.9"
