import Link from "next/link";

import { AiSpendPanel } from "@/app/components/ai-spend-panel";
import { ClearAlertsButton } from "@/app/components/clear-alerts-button";
import { StatCard } from "@/app/components/stat-card";
import { SystemStatusPanel } from "@/app/components/system-status";
import { fetchDashboard, fetchHealth, fetchSearches } from "@/lib/api";
import { formatPercent, formatPrice, formatRelativeTime } from "@/lib/format";
import { ALERT_TYPE_LABELS } from "@/lib/terms";

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
          <div>
            <p className="mb-2 text-xs uppercase tracking-[0.18em] text-sky-300/70">Обзор</p>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Состояние toolkit</h1>
          </div>
          <span className={`rounded-full border px-3 py-1 text-xs ${health ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300" : "border-red-500/30 bg-red-500/10 text-red-300"}`}>
            {health ? `API ${health.version} · на связи` : "API недоступен"}
          </span>
        </div>
        <p className="max-w-2xl text-sm text-neutral-400">
          Краткая сводка обходов, рынка, объявлений и событий. Подробная работа находится в отдельных разделах слева.
        </p>
      </header>

      <SystemStatusPanel initial={dashboard} />

      <section className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4" aria-label="Ключевые показатели">
        <StatCard label="Поиски" value={`${stats.searches_active} / ${stats.searches_total}`} hint="активных / всего" info="Активный поиск включён для обходов. Текущий статус обхода смотрите на странице Поиски." />
        <StatCard label="Лоты на рынке" value={String(stats.listings_active)} hint="активных в базе" info="Уникальные активные объявления во всех поисках." />
        <StatCard label="Наши SKU" value={String(stats.our_listings_active)} hint="активных объявлений" info="Позиции выбранного продавца доступны в разделе Мои объявления." />
        <StatCard label="Новые алерты" value={String(stats.alerts_new)} hint={stats.alerts_new > 0 ? "требуют внимания" : "всё спокойно"} accent={stats.alerts_new > 0 ? "warn" : "good"} info="События, которые ещё не подтверждены." />
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-medium sm:text-lg">Быстрый доступ</h2>
              <p className="mt-1 text-xs text-neutral-500">Переходите в рабочий раздел, а не в длинную страницу dashboard.</p>
            </div>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {[
              ["/searches", "Поиски", "Статусы, расписания и фильтры конкурентов"],
              ["/our-listings", "Мои объявления", "Цены и позиции выбранного продавца"],
              ["/recommendations", "Рекомендации", "Предложения к проверке по товарам"],
              ["/agents", "Агенты", "Плейбуки, входные данные и решения"],
            ].map(([href, title, description]) => (
              <Link key={href} href={href} className="rounded-lg border border-neutral-800 bg-neutral-950/50 p-3 transition hover:border-sky-500/40 hover:bg-sky-500/5 focus-visible:outline-sky-400">
                <p className="text-sm font-medium text-neutral-200">{title}</p>
                <p className="mt-1 text-xs text-neutral-500">{description}</p>
              </Link>
            ))}
          </div>
        </section>
        <AiSpendPanel initial={dashboard?.ai_spend} />
      </div>

      <section className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4 sm:p-5" aria-labelledby="latest-alerts-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="latest-alerts-heading" className="text-base font-medium text-amber-200 sm:text-lg">Последние алерты</h2>
            <p className="mt-1 text-xs text-amber-300/60">Только краткая сводка. Полный список — в разделе Алерты.</p>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/alerts" className="text-xs text-amber-200 underline-offset-4 hover:underline">Открыть все</Link>
            {stats.latest_alerts.length > 0 ? <ClearAlertsButton label="Очистить все" className="rounded-lg border border-amber-500/40 px-3 py-1 text-xs text-amber-200 transition hover:bg-amber-500/10" /> : null}
          </div>
        </div>
        {stats.latest_alerts.length > 0 ? (
          <ul className="mt-3 flex flex-col gap-2">
            {stats.latest_alerts.slice(0, 5).map((alert) => {
              const payload = alert.payload ?? {};
              const searchId = typeof payload.search_id === "string" ? payload.search_id : null;
              const ourPrice = typeof payload.our_price === "number" ? payload.our_price : null;
              const median = typeof payload.market_median === "number" ? payload.market_median : null;
              const delta = typeof payload.delta_pct === "number" ? payload.delta_pct / 100 : null;
              return <li key={alert.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/15 bg-neutral-900/50 px-3 py-2.5 text-sm">
                <div className="min-w-0"><p className="font-medium text-amber-100">{ALERT_TYPE_LABELS[alert.type] ?? alert.type}<span className="ml-2 text-[11px] font-normal text-neutral-500">{formatRelativeTime(alert.created_at)}</span></p><p className="truncate text-xs text-neutral-400">{String(payload.title ?? payload.sku ?? "")}{ourPrice !== null ? ` · наша ${formatPrice(ourPrice)}` : ""}{median !== null ? ` · медиана ${formatPrice(median)}` : ""}{delta !== null ? ` · +${formatPercent(delta)}` : ""}</p></div>
                {searchId ? <Link href={`/searches/${searchId}`} className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500">К поиску</Link> : null}
              </li>;
            })}
          </ul>
        ) : <p className="mt-4 rounded-lg border border-neutral-800 bg-neutral-950/40 p-3 text-sm text-neutral-500">Новых алертов нет — всё спокойно.</p>}
      </section>
    </main>
  );
}
