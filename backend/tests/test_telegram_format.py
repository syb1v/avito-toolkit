from app.telegram_bot import alert_panel_path, format_alert_text


def test_format_alert_text_price_with_link() -> None:
    text = format_alert_text(
        "price_above_market",
        {
            "title": "B&O <Eleven>",
            "our_price": 42000,
            "market_median": 45000,
            "delta_pct": 7.1,
            "search_id": "abc",
        },
        panel_url="http://panel.local",
    )
    assert "<b>Наша цена выше рынка</b>" in text
    assert "B&amp;O &lt;Eleven&gt;" in text
    assert "http://panel.local/searches/abc" in text


def test_format_alert_text_auto_reprice_and_paths() -> None:
    text = format_alert_text(
        "auto_reprice",
        {"headline": "Подняли цены", "applied": 3, "drafts": 1, "failed": 0, "mode": "live"},
        panel_url="http://panel.local",
    )
    assert "Подняли цены" in text
    assert "применено 3 правок" in text
    assert "http://panel.local/our-listings" in text

    assert alert_panel_path("account_stale", {}) == "/#accounts"
    assert alert_panel_path("proxy_dead", {}) == "/#proxies"
    assert alert_panel_path("ai_balance_low", {}) == "/#ai"
    assert alert_panel_path("worker_down", {}) == "/#alerts"
    assert alert_panel_path("price_above_market", {}) == "/our-listings"


def test_format_alert_text_without_panel() -> None:
    text = format_alert_text("worker_down", {}, panel_url="")
    assert "Воркер не отвечает" in text
    assert "href" not in text
