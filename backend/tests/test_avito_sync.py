from app.services.avito_sync import sku_for_item


def test_sku_for_item() -> None:
    assert sku_for_item(123) == "avito-123"
    assert sku_for_item(987654321) == "avito-987654321"
