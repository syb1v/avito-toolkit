from dataclasses import dataclass, field


@dataclass
class FeedItem:
    avito_id: int | None
    title: str
    description: str
    price: float
    category: str
    params: dict[str, str] = field(default_factory=dict)


class FeedBuilder:
    """Формирование XML-фида Автозагрузки (фаза 6).

    Пайплайн: FeedBuilder → XSD-валидация (lxml) → MinIO/S3 →
    Autoload API trigger → poll /reports → per-item ошибки.
    """

    def __init__(self) -> None:
        self._items: list[FeedItem] = []

    def add_item(self, item: FeedItem) -> None:
        self._items.append(item)

    @property
    def item_count(self) -> int:
        return len(self._items)

    def to_xml(self) -> bytes:
        raise NotImplementedError("генерация фида Автозагрузки — фаза 6")


def validate_feed_xml(xml_bytes: bytes, xsd_path: str) -> list[str]:
    """Валидация фида по официальной XSD-схеме до отправки. Фаза 6."""
    raise NotImplementedError("XSD-валидация — фаза 6")
