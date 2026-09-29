from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from statistics import fmean

IQR_MULTIPLIER = 1.5


def percentile(values: Sequence[float], q: float) -> float:
    """Перцентиль с линейной интерполяцией (метод numpy 'linear')."""
    if not 0 <= q <= 100:
        raise ValueError("q must be between 0 and 100")
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q / 100
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] * (1 - fraction) + ordered[upper_index] * fraction


@dataclass(frozen=True, slots=True)
class PriceStats:
    count: int
    price_min: float
    price_max: float
    mean: float
    median: float
    p25: float
    p75: float


@dataclass(frozen=True, slots=True)
class OutlierFilterResult:
    kept: tuple[float, ...]
    dropped: tuple[float, ...]
    lower_bound: float
    upper_bound: float


def filter_outliers(
    prices: Iterable[float], multiplier: float = IQR_MULTIPLIER
) -> OutlierFilterResult:
    """IQR-отсечение выбросов: [max(0, Q1 - k*IQR), Q3 + k*IQR]."""
    data = [float(price) for price in prices]
    if not data:
        return OutlierFilterResult((), (), 0.0, 0.0)
    q1 = percentile(data, 25)
    q3 = percentile(data, 75)
    iqr = q3 - q1
    lower_bound = max(0.0, q1 - multiplier * iqr)
    upper_bound = q3 + multiplier * iqr
    kept = tuple(price for price in data if lower_bound <= price <= upper_bound)
    dropped = tuple(price for price in data if not lower_bound <= price <= upper_bound)
    return OutlierFilterResult(kept, dropped, lower_bound, upper_bound)


def compute_price_stats(prices: Iterable[float], use_iqr: bool = True) -> PriceStats:
    data = [float(price) for price in prices]
    if use_iqr:
        filtered = filter_outliers(data)
        if filtered.kept:
            data = list(filtered.kept)
    if not data:
        raise ValueError("no prices to analyze")
    return PriceStats(
        count=len(data),
        price_min=min(data),
        price_max=max(data),
        mean=fmean(data),
        median=percentile(data, 50),
        p25=percentile(data, 25),
        p75=percentile(data, 75),
    )
