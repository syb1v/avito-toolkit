from app.services.accounts import new_profile_dir, slugify


def test_slugify_transliterates_russian() -> None:
    assert slugify("Аккаунт 2") == "akkaunt-2"
    assert slugify("  Мой -- профиль!  ") == "moi-profil"
    assert slugify("Продавец №7 (основной)") == "prodavets-o7-osnovnoi"


def test_slugify_fallback() -> None:
    assert slugify("!!!") == "account"
    assert new_profile_dir("Аккаунт 2") == ".accounts/akkaunt-2"
