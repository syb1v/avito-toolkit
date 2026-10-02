from app.collectors.web.parsing import extract_description


def test_extract_description_from_json_state() -> None:
    html = (
        '<html><body><script>window.state = {"item": {"description": '
        '"Продаю iPhone 15, проблема с чипами WiFi, ТОРГ. Пишите в WhatsApp."}}'
        "</script></body></html>"
    )
    description = extract_description(html)
    assert description is not None
    assert "проблема с чипами" in description
    assert "WhatsApp" in description


def test_extract_description_prefers_longest_json() -> None:
    html = (
        '<html><script>{"description": "коротко"}</script>'
        '<script>{"description": "Очень длинное описание товара с деталями состояния, '
        'торгом и прочими условиями продажи, которого хватит для анализа."}</script></html>'
    )
    description = extract_description(html)
    assert description is not None
    assert description.startswith("Очень длинное")


def test_extract_description_from_meta_fallback() -> None:
    html = (
        '<html><head><meta name="description" content="iPhone 15, реплика 1:1, '
        'люкс качество, цена ниже рынка"/></head><body></body></html>'
    )
    description = extract_description(html)
    assert description == "iPhone 15, реплика 1:1, люкс качество, цена ниже рынка"


def test_extract_description_from_dom_node() -> None:
    html = (
        '<html><body><div data-marker="item-view/itemDescription">'
        "  Полное   описание\nтовара  </div></body></html>"
    )
    assert extract_description(html) == "Полное описание товара"


def test_extract_description_empty() -> None:
    assert extract_description("<html><body>нет описания</body></html>") is None
