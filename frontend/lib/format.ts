const priceFormatter = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 0,
});

const compactFormatter = new Intl.NumberFormat("ru-RU", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${priceFormatter.format(value)} ₽`;
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return compactFormatter.format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function formatDays(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${value.toFixed(1)} дн.`;
}
