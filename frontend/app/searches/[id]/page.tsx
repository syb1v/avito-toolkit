import Link from "next/link";

import { AlertsPanel } from "@/app/components/alerts-panel";
import { DigestPanel } from "@/app/components/digest-panel";
import { PriceChart } from "@/app/components/price-chart";
import { fetchAlerts, fetchHistory, fetchListings, fetchSummary } from "@/lib/api";
import { formatDays, formatPercent, formatPrice } from "@/lib/format";

const LISTINGS_PREVIEW = 50;

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4">
      <p className="text-xs uppercase tracking-wider text-neutral-500">{label}</p>
      <p className="mt-2 text-xl font-medium tabular-nums">{value}</p>
      {hint ? <p className="mt-1 text-xs text-neutral-500">{hint}</p> : null}
    </div>
  );
}

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
      className={`rounded-full border px-2 py-0.5 text-xs ${
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
      <main className="mx-auto max-w-3xl px-6 py-16">
        <Link href="/" className="text-sm text-neutral-500 hover:text-neutral-300">
          ← Все поиски
        </Link>
        <div className="mt-8 rounded-xl border border-amber-500/30 bg-amber-500/10 p-6 text-sm text-amber-200">
          Поиск не найден или API недоступен. Проверьте, что backend запущен и
          идентификатор поиска существует.
        </div>
      </main>
    );
  }

  const stats = summary.stats;

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-3">
        <Link href="/" className="text-sm text-neutral-500 hover:text-neutral-300">
          ← Все поиски
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{summary.name}</h1>
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
          className="truncate text-sm text-neutral-500 underline hover:text-neutral-300"
        >
          {summary.url}
        </a>
      </header>

      <section className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
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

      <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5">
        <h2 className="text-lg font-medium">Цены рынка</h2>
        {stats === null ? (
          <p className="mt-3 text-sm text-neutral-500">
            Нет активных объявлений с ценой — выполните обход поиска.
          </p>
        ) : (
          <div className="mt-4 grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <StatCard label="Медиана" value={formatPrice(stats.median)} />
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
        <h2 className="px-5 pt-5 text-lg font-medium">Динамика цен</h2>
        <PriceChart data={history} />
      </section>

      <section className="rounded-xl border border-neutral-800">
        <div className="flex items-baseline justify-between px-5 py-4">
          <h2 className="text-lg font-medium">Выдача</h2>
          <span className="text-xs text-neutral-500">
            показано {Math.min(listings.length, LISTINGS_PREVIEW)} из {listings.length}
          </span>
        </div>
        <div className="overflow-x-auto">
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
              {listings.slice(0, LISTINGS_PREVIEW).map((listing) => (
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
              {listings.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-5 py-10 text-center text-neutral-500">
                    Пока пусто — выполните обход поиска (POST /api/v1/searches/
                    {"{id}"}/crawl).
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
