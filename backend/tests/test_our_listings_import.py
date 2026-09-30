from app.services.our_listings import normalize_import_rows, sku_for_item


def test_normalize_valid_rows() -> None:
    rows, skipped = normalize_import_rows(
        [
            {
                "sku": "SKU-1",
                "title": "iPhone 15 128GB",
                "price": "90 000 ₽",
                "cost_price": 60000,
                "category": "Телефоны",
                "avito_item_id": "900001",
                "avito_url": "https://www.avito.ru/item/900001",
                "avito_status": "active",
            },
            {
                "sku": "SKU-2",
                "title": "Samsung Galaxy S23",
                "price": 40000,
            },
        ]
    )
    assert skipped == 0
    assert len(rows) == 2
    first = rows[0]
    assert first.sku == "SKU-1"
    assert first.price == 90000.0
    assert first.cost_price == 60000.0
    assert first.avito_item_id == 900001
    assert first.avito_url == "https://www.avito.ru/item/900001"
    assert rows[1].cost_price is None


def test_normalize_skips_invalid_rows() -> None:
    rows, skipped = normalize_import_rows(
        [
            {"sku": "OK", "title": "Товар", "price": 100},
            {"sku": "", "title": "Без SKU", "price": 100},
            {"sku": "NO-TITLE", "title": "  ", "price": 100},
            {"sku": "NO-PRICE", "title": "Без цены"},
            {"sku": "ZERO", "title": "Ноль", "price": 0},
        ]
    )
    assert skipped == 4
    assert [row.sku for row in rows] == ["OK"]


def test_sku_for_item() -> None:
    assert sku_for_item(123456) == "avito-123456"
