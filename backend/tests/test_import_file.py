import io

import pytest
from openpyxl import Workbook

from app.services.import_file import (
    fallback_query,
    load_staging,
    parse_xlsx,
    save_staging,
    search_params,
    search_url,
)


def _xlsx(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_xlsx_reads_avito_export() -> None:
    data = _xlsx(
        [
            ["Id", "AvitoId", "AvitoStatus", "Title", "Price", "Category"],
            [7896993287, 7896993287, "Активно", "Плавающий трипод", 2437, "Фототехника"],
            [8185320402, 8185320402, "Истёк", "B&O Beoplay A9", "480 957", "Аудио"],
            [None, None, None, None, None, None],
        ]
    )
    rows = parse_xlsx(data)
    assert len(rows) == 2
    assert rows[0].avito_id == 7896993287
    assert rows[0].title == "Плавающий трипод"
    assert rows[0].price == 2437.0
    assert rows[1].status == "Истёк"
    assert rows[1].price == 480957.0


def test_parse_xlsx_without_title_column() -> None:
    assert parse_xlsx(_xlsx([["Id", "Price"], [1, 100]])) == []


def test_fallback_query_strips_colors_and_noise() -> None:
    query = fallback_query("Продам Bang & Olufsen Beoplay Eleven Natural Aluminium")
    assert "Natural" not in query
    assert "Aluminium" not in query
    assert "Продам" not in query
    assert "Beoplay" in query
    assert len(query.split()) <= 5


def test_search_url_and_params() -> None:
    url = search_url("beoplay eleven")
    assert url.startswith("https://www.avito.ru/all?q=")
    assert "beoplay%20eleven" in url
    params = search_params(query="beoplay eleven", keyword_groups=None, exclude_keywords=None)
    assert params["keyword_groups"] == [["beoplay eleven"]]
    assert params["exclude_keywords"] == []


async def test_staging_roundtrip() -> None:
    fakeredis = pytest.importorskip("fakeredis.aioredis")
    redis = fakeredis.FakeRedis()
    try:
        data = _xlsx([["Id", "Title", "Price"], [111, "Товар", "1000"]])
        rows = parse_xlsx(data)
        token = await save_staging(redis, rows)
        loaded = await load_staging(redis, token)
        assert loaded is not None
        assert loaded[0]["avito_id"] == 111
        assert await load_staging(redis, "нет-такого") is None
    finally:
        await redis.aclose()
