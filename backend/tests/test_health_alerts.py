from datetime import UTC, datetime, timedelta

import pytest

from app.services.health_alerts import balance_alert, stale_account_reason

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def test_stale_account_challenge_needs_cookies() -> None:
    reason = stale_account_reason(
        cookies_at=NOW - timedelta(hours=1),
        last_check_ok=False,
        last_error="челлендж Авито — нужны свежие cookies",
        now=NOW,
        max_age_hours=72,
    )
    assert reason is not None
    assert "сессия" in reason


def test_stale_account_rate_limit_is_not_stale() -> None:
    assert (
        stale_account_reason(
            cookies_at=NOW - timedelta(hours=1),
            last_check_ok=False,
            last_error="429: Авито лимитирует запросы (похоже на лимит IP)",
            now=NOW,
            max_age_hours=72,
        )
        is None
    )


def test_stale_account_old_cookies() -> None:
    reason = stale_account_reason(
        cookies_at=NOW - timedelta(hours=100),
        last_check_ok=True,
        last_error=None,
        now=NOW,
        max_age_hours=72,
    )
    assert reason is not None
    assert "не обновлялись" in reason


def test_stale_account_ok() -> None:
    assert (
        stale_account_reason(
            cookies_at=NOW - timedelta(hours=2),
            last_check_ok=True,
            last_error=None,
            now=NOW,
            max_age_hours=72,
        )
        is None
    )


def test_stale_account_without_cookies() -> None:
    reason = stale_account_reason(
        cookies_at=None,
        last_check_ok=False,
        last_error=None,
        now=NOW,
        max_age_hours=72,
    )
    assert reason is not None
    assert "cookies не загружены" in reason


def test_balance_alert_thresholds() -> None:
    empty = balance_alert([], 1.0)
    assert empty is not None
    assert empty["low"] is False

    zero = balance_alert([{"currency": "CNY", "total_balance": "0.00"}], 1.0)
    assert zero is not None
    assert zero["low"] is True
    assert zero["currency"] == "CNY"

    low = balance_alert([{"currency": "CNY", "total_balance": "0.50"}], 1.0)
    assert low is not None
    assert low["low"] is True
    assert "порога" in low["reason"]

    ok = balance_alert([{"currency": "CNY", "total_balance": "12.30"}], 1.0)
    assert ok is not None
    assert ok["low"] is False


def test_ai_spend_daily_series_and_averages() -> None:
    from datetime import date

    from app.services.ai_spend import average, daily_series, forecast_month_usd, runway_days

    totals = {date(2026, 10, 4): 0.004, date(2026, 10, 5): 0.006}
    series = daily_series(totals, end=date(2026, 10, 5), days=3)
    assert series == [
        (date(2026, 10, 3), 0.0),
        (date(2026, 10, 4), 0.004),
        (date(2026, 10, 5), 0.006),
    ]
    assert average([cost for _day, cost in series]) == pytest.approx(0.003333)
    assert average([]) == 0.0
    assert runway_days(2.3, 0.01) == 230
    assert runway_days(None, 0.01) is None
    assert runway_days(2.3, 0.0) is None
    assert forecast_month_usd(0.02) == 0.6
