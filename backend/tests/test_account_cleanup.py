from app.services.account_cleanup import orphan_account_names


def test_orphan_account_names_are_detected() -> None:
    assert orphan_account_names(["Борис", "Вадим тестовый", None], {"Борис"}) == {"Вадим тестовый"}
