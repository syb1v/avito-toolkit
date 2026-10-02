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

export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) {
    return "только что";
  }
  if (minutes < 60) {
    return `${minutes} мин назад`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours} ч назад`;
  }
  return `${Math.round(hours / 24)} дн назад`;
}
