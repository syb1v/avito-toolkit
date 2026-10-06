"""Агрегаты расходов на AI: дневной ряд, средние и прогноз."""

import math
from datetime import date, timedelta

DAILY_WINDOW_DAYS = 30


def daily_series(
    totals: dict[date, float], *, end: date, days: int = DAILY_WINDOW_DAYS
) -> list[tuple[date, float]]:
    """Непрерывный дневной ряд расходов (нули для дней без вызовов)."""
    start = end - timedelta(days=days - 1)
    series: list[tuple[date, float]] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        series.append((day, round(float(totals.get(day, 0.0)), 6)))
    return series


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def runway_days(balance: float | None, avg_day_usd: float) -> int | None:
    """На сколько дней хватит баланса при текущем среднем расходе."""
    if balance is None or balance < 0 or avg_day_usd <= 0:
        return None
    return max(0, math.floor(balance / avg_day_usd + 1e-9))


def forecast_month_usd(avg_day_usd: float, days: int = 30) -> float:
    return round(avg_day_usd * days, 6)
