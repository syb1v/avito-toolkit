from app.services.accounts import slugify


def test_slugify_transliterates_russian() -> None:
    assert slugify("Аккаунт 2") == "akkaunt-2"
    assert slugify("  Мой -- профиль!  ") == "moi-profil"
    assert slugify("Продавец №7 (основной)") == "prodavets-o7-osnovnoi"


def test_slugify_fallback() -> None:
    assert slugify("!!!") == "account"
