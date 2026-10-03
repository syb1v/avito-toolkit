import Link from "next/link";

import { AccountManager } from "@/app/components/account-manager";
import { ClearAlertsButton } from "@/app/components/clear-alerts-button";
import { ProxyPanel } from "@/app/components/proxy-panel";
import { SearchManager } from "@/app/components/search-manager";
import { StatCard } from "@/app/components/stat-card";
import { SystemStatusPanel } from "@/app/components/system-status";
import {
  fetchAccounts,
  fetchDashboard,
  fetchHealth,
  fetchSearches,
} from "@/lib/api";
import { formatPercent, formatPrice, formatRelativeTime } from "@/lib/format";

const ALERT_LABELS: Record<string, string> = {
  price_above_market: "Наша цена выше рынка",
};

export default async function Home() {
  const [health, searches, accounts, dashboard] = await Promise.all([
    fetchHealth(),
    fetchSearches(),
    fetchAccounts(),
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

      <AccountManager initial={accounts} />

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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-medium text-amber-200 sm:text-lg">
              Последние алерты
            </h2>
            <div className="flex items-center gap-3">
              {dashboard ? (
                <span className="text-xs text-amber-300/70">{stats.alerts_new} новых</span>
              ) : null}
              <ClearAlertsButton
                label="Очистить все"
                className="rounded-lg border border-amber-500/40 px-3 py-1 text-xs text-amber-200 transition hover:bg-amber-500/10"
              />
            </div>
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
                      <span className="ml-2 text-[11px] font-normal text-neutral-500">
                        {formatRelativeTime(alert.created_at)}
                      </span>
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

      <SearchManager initial={searches} accounts={accounts} />
    </main>
  );
}
