import uuid
from dataclasses import dataclass


@dataclass
class FakeSearch:
    id: uuid.UUID
    name: str


def test_find_search_by_name_and_id() -> None:
    from app.services.chat import _find_search

    first = FakeSearch(uuid.uuid4(), "Bang & Olufsen Eleven")
    second = FakeSearch(uuid.uuid4(), "Devialet Dione")
    searches = [first, second]
    assert _find_search(searches, "devialet") is second
    assert _find_search(searches, "Bang & Olufsen Eleven") is first
    assert _find_search(searches, str(second.id)) is second
    assert _find_search(searches, "нет такого") is None
    assert _find_search(searches, None) is first
    assert _find_search([], "что угодно") is None
