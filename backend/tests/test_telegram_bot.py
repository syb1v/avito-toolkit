from app.telegram_bot import (
    alerts_keyboard,
    back_keyboard,
    main_keyboard,
    search_keyboard,
    searches_keyboard,
    subs_keyboard,
)


def _callbacks(keyboard: dict) -> list[str]:
    return [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]


def test_main_keyboard_has_all_sections() -> None:
    callbacks = _callbacks(main_keyboard())
    assert callbacks == ["st", "se", "al", "h", "subs"]


def test_searches_keyboard_prefixes_and_menu() -> None:
    keyboard = searches_keyboard([("abcd1234", "iPhone 15"), ("ef567890", "Devialet")])
    callbacks = _callbacks(keyboard)
    assert callbacks == ["s:abcd1234", "s:ef567890", "m"]
    assert "iPhone 15" in keyboard["inline_keyboard"][0][0]["text"]


def test_search_keyboard_actions() -> None:
    callbacks = _callbacks(search_keyboard("abcd1234"))
    assert callbacks == ["c:abcd1234", "d:abcd1234", "se"]


def test_alerts_keyboard_has_refresh_and_clear() -> None:
    assert "al" in _callbacks(alerts_keyboard())
    assert "acl" in _callbacks(alerts_keyboard())


def test_back_keyboard_target() -> None:
    assert _callbacks(back_keyboard()) == ["m"]
    assert _callbacks(back_keyboard("al")) == ["al"]


def test_subs_keyboard_toggles() -> None:
    keyboard = subs_keyboard({"ai_balance_low"})
    callbacks = _callbacks(keyboard)
    assert "sub:ai_balance_low" in callbacks
    assert callbacks[-1] == "m"
    first = keyboard["inline_keyboard"][0][0]["text"]
    assert "✅" in first or "⬜" in first
