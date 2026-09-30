"""Независимая сверка аналитики: наша IQR-реализация против polars.

Запуск из каталога backend/:

    .venv/bin/python scripts/verify_analytics.py --search-id <uuid>
    .venv/bin/python scripts/verify_analytics.py --file prices.txt

Сравниваются метрики после IQR-отсечения: count, min, max, mean, median, p25, p75.
Код возврата 1 при расхождении выше допуска.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from sqlalchemy import select

from app.services.analytics.iqr import compute_price_stats, filter_outliers

TOLERANCE = 1e-6
METRICS = ("count", "price_min", "price_max", "mean", "median", "p25", "p75")


@dataclass(frozen=True, slots=True)
class MetricComparison:
    metric: str
    ours: float
    reference: float
    diff: float


def cross_check(prices: list[float]) -> list[MetricComparison]:
    ours = compute_price_stats(prices)
    kept = list(filter_outliers(prices).kept)
    series = pl.Series("price", kept)
    reference = {
        "count": float(len(kept)),
        "price_min": float(series.min()),
        "price_max": float(series.max()),
        "mean": float(series.mean()),
        "median": float(series.quantile(0.5, interpolation="linear")),
        "p25": float(series.quantile(0.25, interpolation="linear")),
        "p75": float(series.quantile(0.75, interpolation="linear")),
    }
    comparisons: list[MetricComparison] = []
    for metric in METRICS:
        ours_value = float(getattr(ours, metric))
        reference_value = reference[metric]
        comparisons.append(
            MetricComparison(
                metric=metric,
                ours=ours_value,
                reference=reference_value,
                diff=abs(ours_value - reference_value),
            )
        )
    return comparisons


def all_match(comparisons: list[MetricComparison]) -> bool:
    for comparison in comparisons:
        scale = max(1.0, abs(comparison.reference))
        if comparison.diff > TOLERANCE * scale:
            return False
    return True


async def _fetch_prices(search_id: str) -> list[float]:
    from app.db.models import Listing, SearchListing
    from app.db.session import dispose_engine, get_session_factory

    factory = get_session_factory()
    try:
        async with factory() as session:
            rows = await session.execute(
                select(Listing.current_price)
                .join(SearchListing, SearchListing.listing_id == Listing.id)
                .where(
                    SearchListing.search_id == search_id,
                    Listing.status == "active",
                    Listing.current_price.is_not(None),
                )
            )
            return [float(row[0]) for row in rows.all() if row[0] is not None]
    finally:
        await dispose_engine()


def _load_file(path: str) -> list[float]:
    text = Path(path).read_text(encoding="utf-8")
    prices: list[float] = []
    for chunk in text.replace(",", " ").split():
        try:
            prices.append(float(chunk))
        except ValueError:
            continue
    return prices


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-check analytics against polars")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--search-id", help="UUID поиска в БД")
    source.add_argument("--file", help="файл с ценами (по одной в строке)")
    args = parser.parse_args()

    prices = _load_file(args.file) if args.file else asyncio.run(_fetch_prices(args.search_id))
    if not prices:
        print("FAIL: цены не найдены", file=sys.stderr)
        return 2

    comparisons = cross_check(prices)
    for comparison in comparisons:
        print(
            f"{comparison.metric:10} ours={comparison.ours:>14.2f} "
            f"polars={comparison.reference:>14.2f} diff={comparison.diff:.6f}"
        )
    if not all_match(comparisons):
        print("FAIL: расхождения выше допуска", file=sys.stderr)
        return 1
    print(f"OK: {len(prices)} цен, все метрики совпали с polars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
