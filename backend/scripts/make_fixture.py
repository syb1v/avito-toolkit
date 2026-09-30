"""Санитайз реального HTML выдачи Авито в тестовую фикстуру.

Убирает скрипты/стили/картинки/инлайн-стили, узлы продавца и query-параметры
ссылок, оставляя реальную разметку карточек (`data-marker`, `itemprop`, пути URL)
для регрессионных тестов парсера.

Запуск из каталога backend/:

    .venv/bin/python scripts/make_fixture.py \
        --in /tmp/avito_raw.html --out tests/fixtures/real/search_iphone15.html
"""

import argparse
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from lxml import html as lxml_html

DROP_TAGS = ("script", "style", "noscript", "iframe", "img", "svg", "link", "source")
DROP_XPATHS = (
    ".//*[contains(@data-marker, 'seller')]",
    ".//*[contains(@class, 'seller')]",
    ".//*[contains(@data-marker, 'location')]",
    ".//*[contains(@class, 'geo')]",
)
KEEP_ATTRS = {
    "data-marker",
    "data-item-id",
    "itemprop",
    "content",
    "href",
    "class",
    "title",
    "alt",
}
ITEM_MARKER = 'data-marker="item"'


def sanitize(raw_html: str) -> str:
    tree = lxml_html.fromstring(raw_html)
    containers = tree.xpath("//div[@data-marker='catalog-serp']")
    if not containers:
        raise SystemExit("catalog-serp не найден — разметка выдачи изменилась?")
    node = containers[0]

    for tag in DROP_TAGS:
        for element in node.xpath(f".//{tag}"):
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
    for xpath in DROP_XPATHS:
        for element in node.xpath(xpath):
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)

    for element in node.iter():
        if not isinstance(element.tag, str):
            continue
        for attr in list(element.attrib):
            if attr not in KEEP_ATTRS:
                del element.attrib[attr]
        href = element.get("href")
        if href:
            split = urlsplit(href)
            if href.startswith("/") or "avito.ru" in split.netloc:
                element.set("href", urlunsplit((split.scheme, split.netloc, split.path, "", "")))

    body = lxml_html.tostring(node, encoding="unicode", method="html")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ru"><head><meta charset="utf-8">'
        "<title>Avito fixture</title></head><body>"
        f"{body}</body></html>\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize Avito page into a test fixture")
    parser.add_argument("--in", dest="input", required=True, help="сырой HTML-файл")
    parser.add_argument("--out", dest="output", required=True, help="куда сохранить фикстуру")
    parser.add_argument("--min-items", type=int, default=50, help="минимум карточек (иначе ошибка)")
    args = parser.parse_args()

    raw = Path(args.input).read_text(encoding="utf-8", errors="ignore")
    sanitized = sanitize(raw)
    items = sanitized.count(ITEM_MARKER)
    if items < args.min_items:
        raise SystemExit(f"после санитайза карточек {items} < {args.min_items}")
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sanitized, encoding="utf-8")
    print(f"saved: {out_path} | items: {items} | size: {len(sanitized)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
