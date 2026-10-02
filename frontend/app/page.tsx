import Link from "next/link";

import { StatCard } from "@/app/components/stat-card";
import { ProxyPanel } from "@/app/components/proxy-panel";
import { SystemStatusPanel } from "@/app/components/system-status";
import { API_URL, fetchDashboard, fetchHealth, fetchSearches } from "@/lib/api";
import { formatPercent, formatPrice } from "@/lib/format";

const ALERT_LABELS: Record<string, string> = {
  price_above_market: "Наша цена выше рынка",
};

export default async function Home() {
  const [health, searches, dashboard] = await Promise.all([
    fetchHealth(),
    fetchSearches(),
    fetchDashboard(),
  ]);

  const stats = dashboard ?? {
    searches_total: searches.length,
    searches_active: searches.filter((search) => search.is_active).length,
    listings_active: 0,
    our_listings_active: 0,
    alerts_new: 0,
    latest_alerts: [],
  };

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6 sm:py-12">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            Аналитика рынка Авито
          </h1>
          <span
            className={`rounded-full border px-3 py-1 text-xs ${
              health
                ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300"
                : "border-red-500/30 bg-red-500/10 text-red-300"
            }`}
          >
            {health ? `API ${health.version} · на связи` : "API недоступен"}
          </span>
        </div>
        <p className="max-w-2xl text-sm text-neutral-400">
          Конкуренты, медианы и перцентили, матчинг своих SKU, алерты и рекомендации
          по ценам — всё автоматически по расписанию.
        </p>
      </header>

      <SystemStatusPanel initial={dashboard} />

      <ProxyPanel />

      <section className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard
          label="Поиски"
          value={`${stats.searches_active} / ${stats.searches_total}`}
          hint="активных / всего"
          info="Активные поиски планировщик обходит по расписанию (cron). Второе число — включая поставленные на паузу."
        />
        <StatCard
          label="Лотов на рынке"
          value={String(stats.listings_active)}
          hint="активных в базе"
          info="Уникальные активные объявления во всех поисках (дедупликация по avito_id)."
        />
        <StatCard
          label="Наши SKU"
          value={String(stats.our_listings_active)}
          hint="с матчингом и рекомендациями"
          info="Ваши позиции для сравнения цен с рынком: импорт JSON или перенос из публичного профиля."
        />
        <StatCard
          label="Новые алерты"
          value={String(stats.alerts_new)}
          hint={stats.alerts_new > 0 ? "требуют внимания" : "всё спокойно"}
          accent={stats.alerts_new > 0 ? "warn" : "good"}
          info="Сработавшие правила, которые ещё не подтверждены. Например: наша цена выше медианы рынка больше чем на настроенный процент."
        />
      </section>

      {stats.latest_alerts.length > 0 ? (
        <section className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4 sm:p-5">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-base font-medium text-amber-200 sm:text-lg">
              Последние алерты
            </h2>
            {dashboard ? (
              <span className="text-xs text-amber-300/70">{stats.alerts_new} новых</span>
            ) : null}
          </div>
          <ul className="mt-3 flex flex-col gap-2">
            {stats.latest_alerts.map((alert) => {
              const payload = alert.payload ?? {};
              const deltaPct =
                typeof payload.delta_pct === "number" ? payload.delta_pct / 100 : null;
              const ourPrice =
                typeof payload.our_price === "number" ? payload.our_price : null;
              const marketMedian =
                typeof payload.market_median === "number"
                  ? payload.market_median
                  : null;
              const searchId =
                typeof payload.search_id === "string" ? payload.search_id : null;
              return (
                <li
                  key={alert.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/15 bg-neutral-900/50 px-3 py-2.5 text-sm"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-amber-100">
                      {ALERT_LABELS[alert.type] ?? alert.type}
                    </p>
                    <p className="truncate text-xs text-neutral-400">
                      {String(payload.title ?? payload.sku ?? "")}
                      {ourPrice !== null ? ` · наша ${formatPrice(ourPrice)}` : ""}
                      {marketMedian !== null
                        ? ` · медиана ${formatPrice(marketMedian)}`
                        : ""}
                      {deltaPct !== null ? ` · +${formatPercent(deltaPct)}` : ""}
                    </p>
                  </div>
                  {searchId ? (
                    <Link
                      href={`/searches/${searchId}`}
                      className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
                    >
                      К поиску
                    </Link>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <section className="flex flex-col gap-4">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-lg font-medium">Поиски</h2>
          <span className="text-xs text-neutral-500">{searches.length} шт.</span>
        </div>

        {searches.length === 0 ? (
          <div className="rounded-xl border border-dashed border-neutral-800 p-6 text-sm text-neutral-400 sm:p-8">
            <p className="text-neutral-200">Поисков пока нет.</p>
            <p className="mt-1">
              Массовый импорт: <code>make import-searches file=searches.json</code>{" "}
              или Swagger —{" "}
              <a className="text-emerald-400 underline" href={`${API_URL}/docs`}>
                {API_URL}/docs
              </a>{" "}
              (раздел <code>searches</code>).
            </p>
            <pre className="mt-4 overflow-x-auto rounded-lg bg-neutral-900 p-4 text-xs text-neutral-400">
{`curl -X POST ${API_URL}/api/v1/searches/import \\
  -H 'Content-Type: application/json' \\
  -d '{"items":[{"name":"iPhone 15","url":"https://www.avito.ru/moskva/telefony?q=iphone+15"}]}'`}
            </pre>
          </div>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 sm:gap-4">
            {searches.map((search) => (
              <li key={search.id}>
                <Link
                  href={`/searches/${search.id}`}
                  className="block rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 transition hover:border-neutral-600 sm:p-5"
                >
                  <p className="font-medium">{search.name}</p>
                  <p className="mt-1 truncate text-xs text-neutral-500">{search.url}</p>
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
                    <span>cron: {search.schedule_cron}</span>
                    <span>приоритет: {search.priority}</span>
                    <span
                      className={
                        search.is_active ? "text-emerald-400" : "text-neutral-500"
                      }
                    >
                      {search.is_active ? "активен" : "на паузе"}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
