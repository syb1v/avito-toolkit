import Link from "next/link";

import { fetchOurListingsOverview } from "@/lib/api";
import { formatPercent, formatPrice } from "@/lib/format";

export default async function OurListingsPage() {
  const rows = await fetchOurListingsOverview();

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-3">
        <Link href="/" className="text-sm text-neutral-500 hover:text-neutral-300">
          ← Все поиски
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">Наши объявления</h1>
        <p className="max-w-2xl text-sm text-neutral-400">
          SKU из базы: цена, количество матчей с рынком и отклонение от медианы.
          Источники данных — импорт JSON/CSV и парсинг своего публичного профиля,
          без API Авито.
        </p>
      </header>

      {rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-neutral-800 p-8 text-sm text-neutral-400">
          <p>Пока пусто. Добавьте SKU через API или импортом:</p>
          <pre className="mt-4 overflow-x-auto rounded-lg bg-neutral-900 p-4 text-xs text-neutral-400">
{`curl -X POST http://localhost:8000/api/v1/our-listings/import \\
  -H 'Content-Type: application/json' \\
  -d '{"items":[
    {"sku":"SKU-1","title":"iPhone 15 128GB","price":"90 000 ₽","cost_price":60000}
  ]}'`}
          </pre>
          <p className="mt-3 text-xs text-neutral-500">
            Ещё вариант — обойти свой публичный профиль как обычный поиск
            (имя продавца в URL) и перенести объявления эндпоинтом{" "}
            <code>POST /api/v1/our-listings/import-from-search/&#123;id&#125;</code>.
          </p>
        </div>
      ) : (
        <section className="rounded-xl border border-neutral-800">
          <div className="flex items-baseline justify-between px-5 py-4">
            <h2 className="text-lg font-medium">SKU</h2>
            <span className="text-xs text-neutral-500">{rows.length} шт.</span>
          </div>
          <div className="overflow-x-auto">
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
                {rows.map((row) => {
                  const positive =
                    row.delta_to_median_pct !== null && row.delta_to_median_pct > 0;
                  return (
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
                      <td
                        className={`px-5 py-3 text-right tabular-nums ${
                          row.delta_to_median_pct === null
                            ? "text-neutral-500"
                            : positive
                              ? "text-amber-300"
                              : "text-emerald-300"
                        }`}
                      >
                        {row.delta_to_median_pct === null
                          ? "—"
                          : `${row.delta_to_median_pct > 0 ? "+" : ""}${formatPercent(
                              row.delta_to_median_pct / 100,
                            )}`}
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
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
