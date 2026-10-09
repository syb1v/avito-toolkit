import Link from "next/link";

import { AutoRepricePanel } from "@/app/components/auto-reprice-panel";
import { InfoHint } from "@/app/components/info-hint";
import { SkuEdits } from "@/app/components/sku-edits";
import { fetchOurListingsOverview, fetchRecommendations } from "@/lib/api";
import { formatPercent, formatPrice } from "@/lib/format";

const STRATEGY_LABELS: Record<string, string> = {
  undercut_p25: "Демпинг P25−1%",
  match_median: "По медиане",
  premium_p75: "Премиум P75",
  keep_current: "Держать цену",
};

function DeltaText({ deltaPct }: { deltaPct: number | null }) {
  if (deltaPct === null) {
    return <span className="text-neutral-500">—</span>;
  }
  const positive = deltaPct > 0;
  return (
    <span className={positive ? "text-amber-300" : "text-emerald-300"}>
      {positive ? "+" : ""}
      {formatPercent(deltaPct / 100)}
    </span>
  );
}

export default async function OurListingsPage() {
  const [rows, recommendations] = await Promise.all([
    fetchOurListingsOverview(),
    fetchRecommendations(),
  ]);

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6 sm:py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Наши объявления
        </h1>        <p className="max-w-2xl text-sm text-neutral-400">
          SKU из базы: цены, матчи с рынком, отклонение от медианы и рекомендации
          по стратегии. Источники — импорт JSON/CSV и парсинг своего профиля, без
          API Авито.
        </p>
      </header>

      <AutoRepricePanel />

      {rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-neutral-800 p-6 text-sm text-neutral-400 sm:p-8">
          <p className="text-neutral-200">Пока пусто. Добавьте SKU импортом:</p>
          <pre className="mt-4 overflow-x-auto rounded-lg bg-neutral-900 p-4 text-xs text-neutral-400">
{`curl -X POST http://localhost:8000/api/v1/our-listings/import \\
  -H 'Content-Type: application/json' \\
  -d '{"items":[
    {"sku":"SKU-1","title":"iPhone 15 128GB","price":"90 000 ₽","cost_price":60000}
  ]}'`}
          </pre>
          <p className="mt-3 text-xs text-neutral-500">
            Ещё вариант — обойти свой публичный профиль как обычный поиск и перенести
            объявления эндпоинтом{" "}
            <code>POST /api/v1/our-listings/import-from-search/&#123;id&#125;</code>,
            затем <code>POST /api/v1/our-listings/match-all</code>.
          </p>
        </div>
      ) : (
        <>
          <section className="flex flex-col gap-4">
            <div className="flex items-baseline justify-between gap-3">
              <div className="flex items-center">
                <h2 className="text-lg font-medium">Рекомендации по ценам</h2>
                <InfoHint
                  title="Как выбирается стратегия"
                  text="По вымыванию спроса: горячий рынок (>35%) — премиум P75; вялый (<17.5%) — демпинг P25−1%; иначе медиана. Цена не опускается ниже себестоимости, шаг за раз ≤5%, при изменении больше 10% нужно подтверждение."
                />
              </div>
              <span className="text-xs text-neutral-500">
                {recommendations.length} шт. с матчами
              </span>
            </div>
            {recommendations.length === 0 ? (
              <p className="rounded-xl border border-dashed border-neutral-800 p-5 text-sm text-neutral-500">
                Матчей с рынком пока нет. Запустите{" "}
                <code>POST /api/v1/our-listings/match-all</code> после обхода поисков.
              </p>
            ) : (
              <ul className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
                {recommendations.map((item) => (
                  <li
                    key={item.sku}
                    className="flex flex-col gap-3 rounded-xl border border-neutral-800 bg-neutral-900/60 p-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-medium" title={item.title}>
                          {item.title}
                        </p>
                        <p className="font-mono text-xs text-neutral-500">{item.sku}</p>
                      </div>
                      <span className="whitespace-nowrap rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-xs text-sky-200">
                        {STRATEGY_LABELS[item.strategy] ?? item.strategy}
                      </span>
                    </div>
                    <div className="flex items-end justify-between gap-3">
                      <div>
                        <p className="text-xs text-neutral-500">Наша → цель</p>
                        <p className="text-sm tabular-nums">
                          {formatPrice(item.our_price)} →{" "}
                          <span className="font-medium">
                            {formatPrice(item.clamped_price)}
                          </span>
                        </p>
                      </div>
                      <DeltaText deltaPct={item.delta_pct} />
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-500">
                      <span>медиана: {formatPrice(item.market_median)}</span>
                      <span>матчей: {item.matched_count}</span>
                      {item.requires_approval ? (
                        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200">
                          нужно подтверждение
                        </span>
                      ) : null}
                    </div>
                    <SkuEdits sku={item.sku} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-xl border border-neutral-800">
            <div className="flex items-baseline justify-between gap-3 px-4 py-4 sm:px-5">
              <div className="flex items-center">
                <h2 className="text-lg font-medium">SKU</h2>
                <InfoHint
                  title="Колонки таблицы"
                  text="Наша цена — из импорта/профиля. Медиана рынка — по сматченным конкурентам после IQR-фильтрации. Дельта = (наша − медиана) ÷ медиана: плюс означает, что мы дороже рынка. Матчей — сколько объявлений сопоставлено по названию (rapidfuzz)."
                />
              </div>
              <span className="text-xs text-neutral-500">{rows.length} шт.</span>
            </div>

            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y border-neutral-800 text-left text-xs uppercase tracking-wider text-neutral-500">
                    <th className="px-5 py-3 font-medium">SKU</th>
                    <th className="px-5 py-3 font-medium">Объявление</th>
                    <th className="px-5 py-3 text-right font-medium">Наша цена</th>
                    <th className="px-5 py-3 text-right font-medium">Медиана рынка</th>
                    <th className="px-5 py-3 text-right font-medium">Дельта</th>
                    <th className="px-5 py-3 text-right font-medium">Матчей</th>
                    <th className="px-5 py-3 font-medium">Авито</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800">
                  {rows.map((row) => (
                    <tr key={row.sku} className="hover:bg-neutral-900/60">
                      <td className="px-5 py-3 font-mono text-xs text-neutral-400">
                        {row.sku}
                      </td>
                      <td className="max-w-md px-5 py-3">
                        {row.avito_url ? (
                          <a
                            href={row.avito_url}
                            target="_blank"
                            rel="noreferrer"
                            className="line-clamp-1 hover:underline"
                            title={row.title}
                          >
                            {row.title}
                          </a>
                        ) : (
                          <span className="line-clamp-1" title={row.title}>
                            {row.title}
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums">
                        {formatPrice(row.our_price)}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums text-neutral-400">
                        {formatPrice(row.market_median)}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums">
                        <DeltaText deltaPct={row.delta_to_median_pct} />
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums text-neutral-400">
                        {row.matched_count}
                      </td>
                      <td className="px-5 py-3">
                        {row.avito_status ? (
                          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300">
                            {row.avito_status}
                          </span>
                        ) : (
                          <span className="text-xs text-neutral-600">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="flex flex-col divide-y divide-neutral-800 md:hidden">
              {rows.map((row) => (
                <li key={row.sku} className="flex flex-col gap-2 px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm" title={row.title}>
                        {row.title}
                      </p>
                      <p className="font-mono text-xs text-neutral-500">{row.sku}</p>
                    </div>
                    {row.avito_status ? (
                      <span className="whitespace-nowrap rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300">
                        {row.avito_status}
                      </span>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-400">
                    <span>
                      наша: <span className="tabular-nums">{formatPrice(row.our_price)}</span>
                    </span>
                    <span>
                      медиана:{" "}
                      <span className="tabular-nums">{formatPrice(row.market_median)}</span>
                    </span>
                    <span>
                      дельта: <DeltaText deltaPct={row.delta_to_median_pct} />
                    </span>
                    <span>матчей: {row.matched_count}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      <p className="text-xs text-neutral-600">
        Массовое применение рекомендаций появится в фазе 6 (dry-run, подтверждение,
        аудит, откат). Сейчас панель только показывает расчёты и статусы.
      </p>
    </main>
  );
}
