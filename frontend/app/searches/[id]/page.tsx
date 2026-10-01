import Link from "next/link";

import { AlertsPanel } from "@/app/components/alerts-panel";
import { DigestPanel } from "@/app/components/digest-panel";
import { PriceChart } from "@/app/components/price-chart";
import { StatCard } from "@/app/components/stat-card";
import { fetchAlerts, fetchHistory, fetchListings, fetchSummary } from "@/lib/api";
import { formatDays, formatPercent, formatPrice } from "@/lib/format";

const LISTINGS_PREVIEW = 50;

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300",
    gone: "border-neutral-700 bg-neutral-800 text-neutral-400",
  };
  const labels: Record<string, string> = {
    active: "активно",
    gone: "снято",
  };
  return (
    <span
      className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-xs ${
        styles[status] ?? "border-neutral-700 bg-neutral-800 text-neutral-400"
      }`}
    >
      {labels[status] ?? status}
    </span>
  );
}

export default async function SearchDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [summary, history, listings, alerts] = await Promise.all([
    fetchSummary(id),
    fetchHistory(id),
    fetchListings(id, 200),
    fetchAlerts(id),
  ]);

  if (summary === null) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <Link href="/" className="text-sm text-neutral-500 hover:text-neutral-300">
          ← Все поиски
        </Link>
        <div className="mt-6 rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 text-sm text-amber-200">
          Поиск не найден или API недоступен. Проверьте, что backend запущен и
          идентификатор поиска существует.
        </div>
      </main>
    );
  }

  const stats = summary.stats;
  const preview = listings.slice(0, LISTINGS_PREVIEW);

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:gap-8 sm:px-6 sm:py-12">
      <header className="flex flex-col gap-2">
        <Link href="/" className="text-sm text-neutral-500 hover:text-neutral-300">
          ← Все поиски
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
            {summary.name}
          </h1>
          <span
            className={`rounded-full border px-3 py-1 text-xs ${
              summary.is_active
                ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300"
                : "border-neutral-700 bg-neutral-800 text-neutral-400"
            }`}
          >
            {summary.is_active ? "активен" : "на паузе"}
          </span>
        </div>
        <a
          href={summary.url}
          target="_blank"
          rel="noreferrer"
          className="truncate text-sm text-neutral-500 underline decoration-neutral-800 underline-offset-4 hover:text-neutral-300"
        >
          {summary.url}
        </a>
      </header>

      <section className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-6">
        <StatCard label="Активных" value={String(summary.active_count)} />
        <StatCard label="Новых сегодня" value={String(summary.new_today_count)} />
        <StatCard label="Снято сегодня" value={String(summary.delisted_today_count)} />
        <StatCard label="Снято за 7 дней" value={String(summary.delisted_7d)} />
        <StatCard
          label="Вымывание"
          value={formatPercent(summary.delisting_velocity)}
          hint="снято/активные за 7д"
        />
        <StatCard
          label="Срок жизни"
          value={formatDays(summary.avg_lifetime_days)}
          hint="средний по снятым"
        />
      </section>

      <AlertsPanel alerts={alerts.filter((alert) => alert.status === "new")} />

      <DigestPanel searchId={id} />

      <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
        <h2 className="text-base font-medium sm:text-lg">Цены рынка</h2>
        {stats === null ? (
          <p className="mt-3 text-sm text-neutral-500">
            Нет активных объявлений с ценой — выполните обход поиска.
          </p>
        ) : (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-6">
            <StatCard label="Медиана" value={formatPrice(stats.median)} accent="info" />
            <StatCard label="Средняя" value={formatPrice(stats.mean)} />
            <StatCard label="P25" value={formatPrice(stats.p25)} />
            <StatCard label="P75" value={formatPrice(stats.p75)} />
            <StatCard label="Минимум" value={formatPrice(stats.price_min)} />
            <StatCard
              label="Максимум"
              value={formatPrice(stats.price_max)}
              hint={`выборка: ${stats.count}`}
            />
          </div>
        )}
      </section>

      <section className="rounded-xl border border-neutral-800 bg-neutral-900/60">
        <h2 className="px-4 pt-4 text-base font-medium sm:px-5 sm:pt-5 sm:text-lg">
          Динамика цен
        </h2>
        <PriceChart data={history} />
      </section>

      <section className="rounded-xl border border-neutral-800">
        <div className="flex items-baseline justify-between gap-3 px-4 py-4 sm:px-5">
          <h2 className="text-base font-medium sm:text-lg">Выдача</h2>
          <span className="text-xs text-neutral-500">
            показано {preview.length} из {listings.length}
          </span>
        </div>

        <div className="hidden overflow-x-auto md:block">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y border-neutral-800 text-left text-xs uppercase tracking-wider text-neutral-500">
                <th className="px-5 py-3 font-medium">#</th>
                <th className="px-5 py-3 font-medium">Объявление</th>
                <th className="px-5 py-3 text-right font-medium">Цена</th>
                <th className="px-5 py-3 font-medium">Статус</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {preview.map((listing) => (
                <tr key={listing.id} className="hover:bg-neutral-900/60">
                  <td className="px-5 py-3 tabular-nums text-neutral-500">
                    {listing.last_position ?? "—"}
                  </td>
                  <td className="max-w-xl px-5 py-3">
                    {listing.url ? (
                      <a
                        href={listing.url}
                        target="_blank"
                        rel="noreferrer"
                        className="line-clamp-1 hover:underline"
                        title={listing.title}
                      >
                        {listing.title}
                      </a>
                    ) : (
                      <span className="line-clamp-1" title={listing.title}>
                        {listing.title}
                      </span>
                    )}
                    <span className="text-xs text-neutral-500">id {listing.id}</span>
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums">
                    {formatPrice(listing.price)}
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge status={listing.status} />
                  </td>
                </tr>
              ))}
              {preview.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-5 py-10 text-center text-neutral-500">
                    Пока пусто — выполните обход поиска.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <ul className="flex flex-col divide-y divide-neutral-800 md:hidden">
          {preview.map((listing) => (
            <li key={listing.id} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-xs tabular-nums text-neutral-500">
                  #{listing.last_position ?? "—"} · id {listing.id}
                </p>
                {listing.url ? (
                  <a
                    href={listing.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-0.5 line-clamp-2 text-sm hover:underline"
                  >
                    {listing.title}
                  </a>
                ) : (
                  <p className="mt-0.5 line-clamp-2 text-sm">{listing.title}</p>
                )}
                <div className="mt-1.5">
                  <StatusBadge status={listing.status} />
                </div>
              </div>
              <p className="whitespace-nowrap text-sm font-medium tabular-nums">
                {formatPrice(listing.price)}
              </p>
            </li>
          ))}
          {preview.length === 0 && (
            <li className="px-4 py-10 text-center text-sm text-neutral-500">
              Пока пусто — выполните обход поиска.
            </li>
          )}
        </ul>
      </section>
    </main>
  );
}
